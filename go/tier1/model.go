package tier1

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"slices"
	"unicode/utf8"
	"unsafe"

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
	W                []float32 // features x labels, row-major (nil for an int8 bundle)
	Q                []int8    // int8 bundle: features x labels, row-major; weight = Scale[row] * Q
	Scale            []float32 // int8 bundle: one scale per feature row
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
	spans            [][2]int  // scratch for word token byte ranges
	lowerBuf         []byte    // scratch for the lowercased input
	runes            []rune    // scratch for non-ASCII lowercasing
	vals             []float64 // scratch for TF-IDF values before the norm
	keep             []int     // scratch for Decide
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
	var w, scale []float32
	var q []int8
	var shape []int
	if _, err := os.Stat(filepath.Join(dir, "weights_int8.npy")); err == nil {
		if q, shape, err = ReadInt8(filepath.Join(dir, "weights_int8.npy")); err != nil {
			return nil, err
		}
		if scale, _, err = ReadFloat32(filepath.Join(dir, "scales.npy")); err != nil {
			return nil, err
		}
		if len(shape) == 2 && len(scale) != shape[0] {
			return nil, fmt.Errorf("%d scales for %d weight rows", len(scale), shape[0])
		}
	} else if w, shape, err = ReadFloat32(filepath.Join(dir, "weights.npy")); err != nil {
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
		MaxChars: m.MaxChars, IDF: idf, W: w, Q: q, Scale: scale, Bias: bias, Labels: m.LabelIDs,
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
	idx, counts := m.Counts(doc)
	return m.Weigh(idx, counts)
}

// Counts returns the hashed n-gram counts of one input string: sorted feature indices (word
// features first, char features offset by WordN) and how often each occurs.
func (m *Model) Counts(doc string) ([]int32, []float64) {
	m.hash(doc)
	idx := slices.Clone(m.touched)
	counts := make([]float64, len(idx))
	for k, i := range idx {
		counts[k] = m.counts[i]
		m.counts[i] = 0
	}
	return idx, counts
}

// FeaturizeInto is Featurize writing into dst and reusing its slices and the model's scratch,
// so a warm model allocates nothing per page. Not safe for concurrent use of one Model.
func (m *Model) FeaturizeInto(doc string, dst *Sparse) {
	m.hash(doc)
	dst.Idx = append(dst.Idx[:0], m.touched...)
	m.vals = m.vals[:0]
	var sq float64
	for _, i := range dst.Idx {
		v := (math.Log(m.counts[i]) + 1) * m.IDF[i]
		m.counts[i] = 0
		m.vals = append(m.vals, v)
		sq += v * v
	}
	norm := math.Sqrt(sq)
	dst.Val = dst.Val[:0]
	for _, v := range m.vals {
		if norm > 0 {
			v /= norm
		}
		dst.Val = append(dst.Val, float32(v))
	}
}

// hash fills the dense counts with one input's hashed n-grams and leaves the touched indices
// sorted in m.touched; the caller reads and zeroes m.counts at those indices.
func (m *Model) hash(doc string) {
	m.touched = m.touched[:0]
	m.lowerBuf = m.lowerAppend(m.lowerBuf[:0], doc)
	lower := unsafe.String(unsafe.SliceData(m.lowerBuf), len(m.lowerBuf)) // valid until the next call
	m.wordHashes(lower)
	m.charHashes(lower)
	slices.Sort(m.touched)
}

func (m *Model) add(i int) {
	if m.counts[i] == 0 {
		m.touched = append(m.touched, int32(i))
	}
	m.counts[i]++
}

// Weigh turns counts into TF-IDF features like scikit-learn's TfidfTransformer with
// sublinear_tf and l2 norm: 1 + log(tf), times the IDF, l2 normalized, all in float64, then
// cast to float32.
func (m *Model) Weigh(idx []int32, counts []float64) Sparse {
	vals := make([]float64, len(idx))
	var sq float64
	for k, i := range idx {
		v := (math.Log(counts[k]) + 1) * m.IDF[i]
		vals[k] = v
		sq += v * v
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

// FitIDF is scikit-learn's smoothed IDF over the given pages' feature indices:
// ln((1 + n) / (1 + df)) + 1 for each of nFeatures features.
func FitIDF(pages [][]int32, nFeatures int) []float64 {
	df := make([]float64, nFeatures)
	for _, idx := range pages {
		for _, i := range idx {
			df[i]++
		}
	}
	n := float64(len(pages))
	idf := make([]float64, nFeatures)
	for i, d := range df {
		idf[i] = math.Log((1+n)/(1+d)) + 1
	}
	return idf
}

// wordHashes hashes the word n-grams of an already lowercased document without building a
// string per n-gram: tokens are byte ranges of `lower`, bigrams are joined in a reused buffer.
func (m *Model) wordHashes(lower string) {
	spans := m.spans[:0]
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
	m.spans = spans
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
			m.add(bucket(Murmur3(buf, 0), m.WordN))
		}
	}
}

// charHashes hashes the char_wb n-grams of an already lowercased document: each padded word is
// encoded once, and an n-gram is the byte range between two rune offsets.
func (m *Model) charHashes(lower string) {
	for start := 0; start < len(lower); {
		r, size := utf8.DecodeRuneInString(lower[start:])
		if isSpace(r) {
			start += size
			continue
		}
		end := start
		for end < len(lower) {
			r, size := utf8.DecodeRuneInString(lower[end:])
			if isSpace(r) {
				break
			}
			end += size
		}
		w := lower[start:end]
		start = end
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
			m.add(m.WordN + bucket(Murmur3(buf[offs[0]:offs[min(n, wl)]], 0), m.CharN))
			for offset+n < wl {
				offset++
				m.add(m.WordN + bucket(Murmur3(buf[offs[offset]:offs[offset+n]], 0), m.CharN))
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
	if m.Q != nil {
		m.forwardInt8(x, out)
	} else {
		y := blas32.Vector{N: nl, Data: out, Inc: 1}
		for k, i := range x.Idx {
			blas32.Axpy(x.Val[k], blas32.Vector{N: nl, Data: m.W[int(i)*nl : int(i)*nl+nl], Inc: 1}, y)
		}
	}
	for j := range out {
		z := (out[j] + m.Bias[j]) / m.Temperature
		z = max(-50, min(50, z))
		out[j] = float32(1 / (1 + math.Exp(-float64(z))))
	}
	return out
}

// forwardInt8 adds each feature's int8 row, scaled by value times row scale, to out: a quarter
// of the bytes of a float32 row, converted in plain Go (no SIMD), four lanes at a time.
func (m *Model) forwardInt8(x Sparse, out []float32) {
	nl := len(out)
	for k, i := range x.Idx {
		a := x.Val[k] * m.Scale[i]
		if a == 0 {
			continue
		}
		row := m.Q[int(i)*nl : int(i)*nl+nl]
		o := out[:len(row)]
		j := 0
		for ; j+4 <= len(row); j += 4 {
			o[j] += a * float32(row[j])
			o[j+1] += a * float32(row[j+1])
			o[j+2] += a * float32(row[j+2])
			o[j+3] += a * float32(row[j+3])
		}
		for ; j < len(row); j++ {
			o[j] += a * float32(row[j])
		}
	}
}

// Decide returns the labels at or above their threshold, most probable first, at most
// MaxLabels; with a floor, a page where none passes keeps its top label if it reaches the floor.
func (m *Model) Decide(prob []float32) []string {
	return m.DecideInto(prob, nil)
}

// DecideInto is Decide appending to dst[:0] and reusing the model's scratch.
func (m *Model) DecideInto(prob []float32, dst []string) []string {
	keep := m.keep[:0]
	for j, p := range prob {
		if p >= m.Thresholds[j] {
			keep = append(keep, j)
		}
	}
	// stable insertion sort, most probable first (few labels pass)
	for a := 1; a < len(keep); a++ {
		for b := a; b > 0 && prob[keep[b]] > prob[keep[b-1]]; b-- {
			keep[b], keep[b-1] = keep[b-1], keep[b]
		}
	}
	m.keep = keep
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
			keep = append(keep[:0], best)
		}
	}
	dst = dst[:0]
	for _, j := range keep {
		dst = append(dst, m.Labels[j])
	}
	if dst == nil {
		dst = []string{}
	}
	return dst
}

// NewHashing is a featurizer with no trained weights, for training: word 1-2 grams into wordN
// buckets and char_wb 3-5 grams into charN buckets, like the Python Featurizer. Counts works at
// once; set IDF (FitIDF on the train pages) before Weigh or Featurize.
func NewHashing(wordN, charN, maxChars int) *Model {
	return &Model{
		WordN: wordN, CharN: charN, WordMin: 1, WordMax: 2, CharMin: 3, CharMax: 5,
		MaxChars: maxChars, counts: make([]float64, wordN+charN),
		touched: make([]int32, 0, 8192), buf: make([]byte, 0, 256), offs: make([]int, 0, 256),
	}
}
