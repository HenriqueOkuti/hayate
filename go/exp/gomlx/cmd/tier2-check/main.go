// Command tier2-check is the tier-2 part of the GoMLX fit test (#86): load a Model2Vec static
// model from Hugging Face in Go and check it against Python's model2vec.
//
//	go run ./cmd/tier2-check
//
// It downloads the model with go-huggingface, tokenizes with its pure-Go tokenizer, reads the
// embedding matrix straight from model.safetensors, and pools like model2vec (no special tokens,
// unknown tokens dropped, mean of the token vectors, l2 normalized). It compares the token ids
// and embeddings with artifacts/model2vec-reference.jsonl (scripts/model2vec_reference.py) and
// times the Go encode per text.
package main

import (
	"bufio"
	"encoding/binary"
	"encoding/json"
	"flag"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"regexp"
	"slices"
	"strings"
	"time"
	"unicode"
	"unicode/utf8"

	"github.com/gomlx/go-huggingface/hub"
	"golang.org/x/text/unicode/norm"
)

type tensorInfo struct {
	DType   string `json:"dtype"`
	Shape   []int  `json:"shape"`
	Offsets [2]int `json:"data_offsets"`
}

// readSafetensors returns the header and the raw data section of a .safetensors file.
func readSafetensors(path string) (map[string]tensorInfo, []byte, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, nil, err
	}
	n := binary.LittleEndian.Uint64(b[:8])
	var raw map[string]json.RawMessage
	if err := json.Unmarshal(b[8:8+n], &raw); err != nil {
		return nil, nil, err
	}
	out := map[string]tensorInfo{}
	for k, v := range raw {
		if k == "__metadata__" {
			continue
		}
		var t tensorInfo
		if err := json.Unmarshal(v, &t); err != nil {
			return nil, nil, err
		}
		out[k] = t
	}
	return out, b[8+n:], nil
}

func float32s(info tensorInfo, data []byte) []float32 {
	d := data[info.Offsets[0]:info.Offsets[1]]
	out := make([]float32, len(d)/4)
	for i := range out {
		out[i] = math.Float32frombits(binary.LittleEndian.Uint32(d[4*i:]))
	}
	return out
}

// unigram is a Unigram tokenizer model with a proper Viterbi search (go-huggingface's own
// Unigram is greedy longest-match, which picks lower-scoring segmentations).
type unigram struct {
	ids       map[string]int
	scores    []float64
	maxRunes  int
	maxByHead map[rune]int // longest piece starting with each rune
	unkID     int
	unkScore  float64
}

func newUnigram(vocab [][2]any, unkID int) *unigram {
	u := &unigram{ids: make(map[string]int, len(vocab)), scores: make([]float64, len(vocab)), unkID: unkID,
		maxByHead: map[rune]int{}}
	minScore := math.Inf(1)
	for i, v := range vocab {
		piece, score := v[0].(string), v[1].(float64)
		u.ids[piece] = i
		u.scores[i] = score
		rs := []rune(piece)
		u.maxRunes = max(u.maxRunes, len(rs))
		if len(rs) > 0 {
			u.maxByHead[rs[0]] = max(u.maxByHead[rs[0]], len(rs))
		}
		minScore = math.Min(minScore, score)
	}
	u.unkScore = minScore - 10 // the tokenizers library's unknown-piece penalty
	return u
}

// encode runs Viterbi over the whole (normalized, pre-tokenized) string: the segmentation with
// the highest total piece score; characters no piece covers become the unknown token, and
// consecutive unknowns are fused into one, as the tokenizers library does by default.
func (u *unigram) encode(text string) []int {
	offs := make([]int, 0, len(text)+1) // byte offset of each rune, so pieces are substrings
	for i := range text {
		offs = append(offs, i)
	}
	offs = append(offs, len(text))
	n := len(offs) - 1
	best := make([]float64, n+1)
	from := make([]int, n+1)
	piece := make([]int, n+1)
	for i := 1; i <= n; i++ {
		best[i] = math.Inf(-1)
	}
	for i := 0; i < n; i++ {
		if math.IsInf(best[i], -1) {
			continue
		}
		covered := false
		head, _ := utf8.DecodeRuneInString(text[offs[i]:])
		for l := 1; l <= u.maxByHead[head] && i+l <= n; l++ {
			if id, ok := u.ids[text[offs[i]:offs[i+l]]]; ok {
				if l == 1 {
					covered = true
				}
				if s := best[i] + u.scores[id]; s > best[i+l] {
					best[i+l], from[i+l], piece[i+l] = s, i, id
				}
			}
		}
		if !covered {
			if s := best[i] + u.unkScore; s > best[i+1] {
				best[i+1], from[i+1], piece[i+1] = s, i, u.unkID
			}
		}
	}
	var out []int
	for i := n; i > 0; i = from[i] {
		out = append(out, piece[i])
	}
	slices.Reverse(out)
	fused := out[:0]
	for _, id := range out {
		if id == u.unkID && len(fused) > 0 && fused[len(fused)-1] == u.unkID {
			continue
		}
		fused = append(fused, id)
	}
	return fused
}

// normalizerSpec is the subset of tokenizer.json normalizers this model uses.
type normalizerSpec struct {
	Type        string           `json:"type"`
	Normalizers []normalizerSpec `json:"normalizers"`
	Pattern     struct {
		String *string `json:"String"`
		Regex  *string `json:"Regex"`
	} `json:"pattern"`
	Content    string `json:"content"`
	StripLeft  bool   `json:"strip_left"`
	StripRight bool   `json:"strip_right"`
}

// buildNormalizer compiles the normalizer chain. Precompiled (SentencePiece's character map) is
// approximated with NFKC; regexes are Rust syntax, where \s is Unicode White_Space, so \s is
// widened before Go compiles them.
func buildNormalizer(n normalizerSpec) (func(string) string, error) {
	switch n.Type {
	case "Sequence":
		var steps []func(string) string
		for _, c := range n.Normalizers {
			f, err := buildNormalizer(c)
			if err != nil {
				return nil, err
			}
			steps = append(steps, f)
		}
		return func(s string) string {
			for _, f := range steps {
				s = f(s)
			}
			return s
		}, nil
	case "Precompiled":
		return norm.NFKC.String, nil
	case "Replace":
		if n.Pattern.String != nil {
			old, repl := *n.Pattern.String, n.Content
			return func(s string) string { return strings.ReplaceAll(s, old, repl) }, nil
		}
		re, err := regexp.Compile(strings.ReplaceAll(*n.Pattern.Regex, `\s`, `[\t\n\v\f\r \x{85}\p{Z}]`))
		if err != nil {
			return nil, err
		}
		repl := n.Content
		return func(s string) string { return re.ReplaceAllLiteralString(s, repl) }, nil
	case "Strip":
		left, right := n.StripLeft, n.StripRight
		return func(s string) string {
			if left {
				s = strings.TrimLeftFunc(s, unicode.IsSpace)
			}
			if right {
				s = strings.TrimRightFunc(s, unicode.IsSpace)
			}
			return s
		}, nil
	}
	return nil, fmt.Errorf("normalizer %q not supported", n.Type)
}

type ref struct {
	Text      string    `json:"text"`
	IDs       []int     `json:"ids"`
	Embedding []float32 `json:"embedding"`
}

func main() {
	modelID := flag.String("model", "minishlab/potion-multilingual-128M", "Hugging Face model")
	refPath := flag.String("ref", "../../../artifacts/model2vec-reference.jsonl", "Python reference")
	dump := flag.Bool("dump", false, "print Go and Python token ids around the first mismatch, then exit")
	flag.Parse()

	repo := hub.New(*modelID)
	paths, err := repo.DownloadFiles("model.safetensors", "config.json", "tokenizer.json")
	check(err)
	header, data, err := readSafetensors(paths[0])
	check(err)
	var names []string
	for k, v := range header {
		names = append(names, fmt.Sprintf("%s %s %v", k, v.DType, v.Shape))
	}
	slices.Sort(names)
	emb, ok := header["embeddings"]
	if !ok || emb.DType != "F32" || len(emb.Shape) != 2 {
		check(fmt.Errorf("want a float32 'embeddings' tensor, have %v", names))
	}
	if len(header) != 1 {
		check(fmt.Errorf("token mapping or weights present (%v); not handled by this check", names))
	}
	vocab, dim := emb.Shape[0], emb.Shape[1]
	table := float32s(emb, data)

	var tj struct {
		Model struct {
			UnkID *int     `json:"unk_id"`
			Vocab [][2]any `json:"vocab"`
		} `json:"model"`
		Normalizer normalizerSpec `json:"normalizer"`
	}
	b, err := os.ReadFile(filepath.Join(filepath.Dir(paths[2]), "tokenizer.json"))
	check(err)
	check(json.Unmarshal(b, &tj))

	normalize, err := buildNormalizer(tj.Normalizer)
	check(err)
	uni := newUnigram(tj.Model.Vocab, *tj.Model.UnkID)
	encode := func(text string) ([]int, []float32) {
		// the model's normalizer chain, Metaspace (replacement "▁", prepend always, no split),
		// then Viterbi
		seq := strings.ReplaceAll(normalize(text), " ", "▁")
		if !strings.HasPrefix(seq, "▁") {
			seq = "▁" + seq
		}
		ids := uni.encode(seq)
		var kept []int
		for _, id := range ids {
			if tj.Model.UnkID == nil || id != *tj.Model.UnkID {
				kept = append(kept, id)
			}
		}
		out := make([]float32, dim)
		if len(kept) == 0 {
			return ids, out
		}
		for _, id := range kept {
			row := table[id*dim : (id+1)*dim]
			for j, v := range row {
				out[j] += v
			}
		}
		var sq float64
		for j := range out {
			out[j] /= float32(len(kept))
			sq += float64(out[j]) * float64(out[j])
		}
		norm := float32(math.Sqrt(sq) + 1e-32)
		for j := range out {
			out[j] /= norm
		}
		return ids, out
	}

	f, err := os.Open(*refPath)
	check(err)
	defer f.Close()
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 16<<20), 16<<20)
	var n, sameIDs int
	var maxDiff, minCos float64 = 0, 1
	var firstBad string
	var times []float64
	for sc.Scan() {
		var r ref
		check(json.Unmarshal(sc.Bytes(), &r))
		n++
		t0 := time.Now()
		ids, vec := encode(r.Text)
		times = append(times, float64(time.Since(t0).Microseconds()))
		if slices.Equal(ids, r.IDs) {
			sameIDs++
		} else if firstBad == "" {
			k := 0
			for k < min(len(ids), len(r.IDs)) && ids[k] == r.IDs[k] {
				k++
			}
			firstBad = fmt.Sprintf("text %d: %d ids in Go, %d in Python, first difference at %d", n, len(ids), len(r.IDs), k)
			if *dump {
				lo := max(0, k-3)
				fmt.Printf("go     %v\npython %v\n", ids[lo:min(len(ids), k+6)], r.IDs[lo:min(len(r.IDs), k+6)])
				os.Exit(0)
			}
		}
		var dot, na, nb float64
		for j := range vec {
			maxDiff = math.Max(maxDiff, math.Abs(float64(vec[j]-r.Embedding[j])))
			dot += float64(vec[j]) * float64(r.Embedding[j])
			na += float64(vec[j]) * float64(vec[j])
			nb += float64(r.Embedding[j]) * float64(r.Embedding[j])
		}
		minCos = math.Min(minCos, dot/math.Sqrt(na*nb))
	}
	check(sc.Err())
	slices.Sort(times)
	out := map[string]any{
		"model": *modelID, "tensors": names, "vocab": vocab, "dim": dim,
		"texts": n, "same_token_ids": sameIDs, "first_mismatch": firstBad,
		"max_abs_embedding_diff": maxDiff, "min_cosine": minCos,
		"go_encode_us_p50": times[len(times)/2], "go_encode_us_max": times[len(times)-1],
	}
	j, _ := json.MarshalIndent(out, "", " ")
	fmt.Println(string(j))
}

func check(err error) {
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
