package tier1

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"slices"
	"sort"
	"strings"

	"gonum.org/v1/gonum/blas/blas32"
)

// Sparse is one page's TF-IDF features: sorted indices and float32 values.
type Sparse struct {
	Idx []int32
	Val []float32
}

type featurizerJSON struct {
	Word struct {
		NFeatures  int   `json:"n_features"`
		NgramRange []int `json:"ngram_range"`
	} `json:"word"`
	Char struct {
		NFeatures  int   `json:"n_features"`
		NgramRange []int `json:"ngram_range"`
	} `json:"char"`
	MaxChars int `json:"max_chars"`
}

type metaJSON struct {
	LabelIDs    []string  `json:"label_ids"`
	Temperature float64   `json:"temperature"`
	Thresholds  []float32 `json:"thresholds"`
	Top1Floor   *float64  `json:"top1_floor"`
	MaxLabels   int       `json:"max_labels"`
	MaxChars    int       `json:"max_chars"`
	Features    int       `json:"features"`
}

// Model is a loaded tier-1 bundle (artifacts/<run>/cpu, written by the Python export).
type Model struct {
	WordN, CharN     int
	WordMin, WordMax int
	CharMin, CharMax int
	MaxChars         int
	IDF              []float64
	W                []float32 // features x labels, row-major
	Bias             []float32
	Labels           []string
	Temperature      float32
	Thresholds       []float32
	Floor            *float32
	MaxLabels        int
	counts           []float64 // dense scratch for one page; only touched entries are non-zero
	touched          []int32   // indices set in counts, reset after each page
	buf              []byte    // scratch for n-gram bytes
	offs             []int     // scratch for rune byte offsets
}

func readJSON(path string, v any) error {
	b, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(b, v)
}

// Load reads a bundle directory.
func Load(dir string) (*Model, error) {
	var f featurizerJSON
	var m metaJSON
	if err := readJSON(filepath.Join(dir, "featurizer.json"), &f); err != nil {
		return nil, err
	}
	if err := readJSON(filepath.Join(dir, "meta.json"), &m); err != nil {
		return nil, err
	}
	idf, _, err := ReadFloat64(filepath.Join(dir, "idf.npy"))
	if err != nil {
		return nil, err
	}
	w, shape, err := ReadFloat32(filepath.Join(dir, "weights.npy"))
	if err != nil {
		return nil, err
	}
	bias, _, err := ReadFloat32(filepath.Join(dir, "bias.npy"))
	if err != nil {
		return nil, err
	}
	nf := f.Word.NFeatures + f.Char.NFeatures
	if len(shape) != 2 || shape[0] != nf || shape[1] != len(m.LabelIDs) || len(idf) != nf ||
		len(bias) != len(m.LabelIDs) || len(m.Thresholds) != len(m.LabelIDs) {
		return nil, fmt.Errorf("bundle shapes do not agree: weights %v, %d features, %d labels",
			shape, nf, len(m.LabelIDs))
	}
	model := &Model{
		WordN: f.Word.NFeatures, CharN: f.Char.NFeatures,
		WordMin: f.Word.NgramRange[0], WordMax: f.Word.NgramRange[1],
		CharMin: f.Char.NgramRange[0], CharMax: f.Char.NgramRange[1],
		MaxChars: m.MaxChars, IDF: idf, W: w, Bias: bias, Labels: m.LabelIDs,
		Temperature: float32(m.Temperature), Thresholds: m.Thresholds, MaxLabels: m.MaxLabels,
		counts: make([]float64, nf), touched: make([]int32, 0, 8192),
		buf: make([]byte, 0, 256), offs: make([]int, 0, 256),
	}
	if m.Top1Floor != nil {
		fl := float32(*m.Top1Floor)
		model.Floor = &fl
	}
	return model, nil
}

// Featurize turns one input string into TF-IDF features, like the Python featurizer: hashed
// counts (word features first, char features offset by WordN), 1 + log(tf), times the IDF, l2
// normalized, all in float64, then cast to float32.
func (m *Model) Featurize(doc string) Sparse {
	m.touched = m.touched[:0]
	add := func(i int) {
		if m.counts[i] == 0 {
			m.touched = append(m.touched, int32(i))
		}
		m.counts[i]++
	}
	lower := Lower(doc)
	m.wordHashes(lower, func(h int32) { add(bucket(h, m.WordN)) })
	m.charHashes(lower, func(h int32) { add(m.WordN + bucket(h, m.CharN)) })
	idx := slices.Clone(m.touched)
	slices.Sort(idx)
	vals := make([]float64, len(idx))
	var sq float64
	for k, i := range idx {
		v := (math.Log(m.counts[i]) + 1) * m.IDF[i]
		vals[k] = v
		sq += v * v
		m.counts[i] = 0
	}
	norm := math.Sqrt(sq)
	out := Sparse{Idx: idx, Val: make([]float32, len(idx))}
	for k, v := range vals {
		if norm > 0 {
			v /= norm
		}
		out.Val[k] = float32(v)
	}
	return out
}

// wordHashes hashes the word n-grams of an already lowercased document without building a
// string per n-gram: tokens are byte ranges of `lower`, bigrams are joined in a reused buffer.
func (m *Model) wordHashes(lower string, emit func(int32)) {
	var spans [][2]int
	start, runes := -1, 0
	for i, r := range lower {
		if isWord(r) {
			if start < 0 {
				start, runes = i, 0
			}
			runes++
			continue
		}
		if start >= 0 && runes >= 2 {
			spans = append(spans, [2]int{start, i})
		}
		start = -1
	}
	if start >= 0 && runes >= 2 {
		spans = append(spans, [2]int{start, len(lower)})
	}
	for n := m.WordMin; n <= m.WordMax; n++ {
		for i := 0; i+n <= len(spans); i++ {
			buf := m.buf[:0]
			for j := i; j < i+n; j++ {
				if j > i {
					buf = append(buf, ' ')
				}
				buf = append(buf, lower[spans[j][0]:spans[j][1]]...)
			}
			m.buf = buf
			emit(Murmur3(buf, 0))
		}
	}
}

// charHashes hashes the char_wb n-grams of an already lowercased document: each padded word is
// encoded once, and an n-gram is the byte range between two rune offsets.
func (m *Model) charHashes(lower string, emit func(int32)) {
	for _, w := range strings.FieldsFunc(lower, isSpace) {
		buf := append(append(append(m.buf[:0], ' '), w...), ' ')
		offs := m.offs[:0]
		for i := range string(buf) {
			offs = append(offs, i)
		}
		offs = append(offs, len(buf))
		m.buf, m.offs = buf, offs
		wl := len(offs) - 1
		for n := m.CharMin; n <= m.CharMax; n++ {
			offset := 0
			emit(Murmur3(buf[offs[0]:offs[min(n, wl)]], 0))
			for offset+n < wl {
				offset++
				emit(Murmur3(buf[offs[offset]:offs[offset+n]], 0))
			}
			if offset == 0 {
				break
			}
		}
	}
}

// Forward returns one probability per label: sigmoid((x W + b) / T), accumulated in float32.
func (m *Model) Forward(x Sparse, out []float32) []float32 {
	nl := len(m.Labels)
	if cap(out) < nl {
		out = make([]float32, nl)
	}
	out = out[:nl]
	clear(out)
	y := blas32.Vector{N: nl, Data: out, Inc: 1}
	for k, i := range x.Idx {
		blas32.Axpy(x.Val[k], blas32.Vector{N: nl, Data: m.W[int(i)*nl : int(i)*nl+nl], Inc: 1}, y)
	}
	for j := range out {
		z := (out[j] + m.Bias[j]) / m.Temperature
		z = max(-50, min(50, z))
		out[j] = float32(1 / (1 + math.Exp(-float64(z))))
	}
	return out
}

// Decide returns the labels at or above their threshold, most probable first, at most
// MaxLabels; with a floor, a page where none passes keeps its top label if it reaches the floor.
func (m *Model) Decide(prob []float32) []string {
	var keep []int
	for j, p := range prob {
		if p >= m.Thresholds[j] {
			keep = append(keep, j)
		}
	}
	sort.SliceStable(keep, func(a, b int) bool { return prob[keep[a]] > prob[keep[b]] })
	if len(keep) > m.MaxLabels {
		keep = keep[:m.MaxLabels]
	}
	if len(keep) == 0 && m.Floor != nil {
		best := 0
		for j, p := range prob {
			if p > prob[best] {
				best = j
			}
		}
		if prob[best] >= *m.Floor {
			keep = []int{best}
		}
	}
	out := make([]string, len(keep))
	for k, j := range keep {
		out[k] = m.Labels[j]
	}
	return out
}
