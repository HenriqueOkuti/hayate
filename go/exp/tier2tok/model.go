package tier2tok

import (
	"encoding/binary"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"unicode"
	"unicode/utf8"

	"golang.org/x/text/unicode/norm"
)

// Static is a Model2Vec model: an embedding table, its Unigram tokenizer and the tokenizer's
// normalizer chain and Metaspace pre-tokenizer.
type Static struct {
	Table     []float32 // rows x Dim
	Rows, Dim int
	Uni       *Unigram
	normalize func(string) string
	split     bool // Metaspace split: each whitespace-separated word is segmented on its own
}

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

type preTokenizerSpec struct {
	Type          string             `json:"type"`
	Split         bool               `json:"split"`
	PreTokenizers []preTokenizerSpec `json:"pretokenizers"`
}

// LoadStatic reads model.safetensors (one float32 "embeddings" tensor) and tokenizer.json from a
// Model2Vec model directory.
func LoadStatic(dir string) (*Static, error) {
	table, shape, err := readEmbeddings(filepath.Join(dir, "model.safetensors"))
	if err != nil {
		return nil, err
	}
	var tj struct {
		Model struct {
			UnkID *int     `json:"unk_id"`
			Vocab [][2]any `json:"vocab"`
		} `json:"model"`
		Normalizer   *normalizerSpec  `json:"normalizer"`
		PreTokenizer preTokenizerSpec `json:"pre_tokenizer"`
	}
	b, err := os.ReadFile(filepath.Join(dir, "tokenizer.json"))
	if err != nil {
		return nil, err
	}
	if err := json.Unmarshal(b, &tj); err != nil {
		return nil, err
	}
	normalize := func(s string) string { return s }
	if tj.Normalizer != nil {
		if normalize, err = buildNormalizer(*tj.Normalizer); err != nil {
			return nil, err
		}
	}
	split := false
	for _, p := range append([]preTokenizerSpec{tj.PreTokenizer}, tj.PreTokenizer.PreTokenizers...) {
		if p.Type == "Metaspace" {
			split = p.Split
		}
	}
	unk := -1
	if tj.Model.UnkID != nil {
		unk = *tj.Model.UnkID
	}
	return &Static{Table: table, Rows: shape[0], Dim: shape[1], Uni: NewUnigram(tj.Model.Vocab, unk),
		normalize: normalize, split: split}, nil
}

func readEmbeddings(path string) ([]float32, []int, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, nil, err
	}
	n := binary.LittleEndian.Uint64(b[:8])
	var header map[string]json.RawMessage
	if err := json.Unmarshal(b[8:8+n], &header); err != nil {
		return nil, nil, err
	}
	var info struct {
		DType   string `json:"dtype"`
		Shape   []int  `json:"shape"`
		Offsets [2]int `json:"data_offsets"`
	}
	raw, ok := header["embeddings"]
	if !ok {
		return nil, nil, fmt.Errorf("%s: no embeddings tensor", path)
	}
	if err := json.Unmarshal(raw, &info); err != nil {
		return nil, nil, err
	}
	if info.DType != "F32" || len(info.Shape) != 2 {
		return nil, nil, fmt.Errorf("%s: embeddings are %s %v, want F32 rows x dims", path, info.DType, info.Shape)
	}
	d := b[8+n:][info.Offsets[0]:info.Offsets[1]]
	out := make([]float32, len(d)/4)
	for i := range out {
		out[i] = math.Float32frombits(binary.LittleEndian.Uint32(d[4*i:]))
	}
	return out, info.Shape, nil
}

// buildNormalizer compiles the normalizer chain. Precompiled (SentencePiece's character map) is
// approximated with NFKC, as in the fit test; regexes are Rust syntax, where \s is Unicode
// White_Space, so \s is widened before Go compiles them.
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
	case "Precompiled", "NFKC":
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

// Encode appends the model's token ids for text to dst (no special tokens): its normalizer,
// Metaspace (spaces to "▁", "▁" prepended; with split, each word on its own), then the Unigram
// search, by trie or by map lookups.
func (m *Static) Encode(text string, dst []int32, s *Scratch, trie bool) []int32 {
	seq := m.normalize(text)
	enc := m.Uni.EncodeMap
	if trie {
		enc = m.Uni.EncodeTrie
	}
	if !m.split {
		seq = strings.ReplaceAll(seq, " ", "▁")
		if !strings.HasPrefix(seq, "▁") {
			seq = "▁" + seq
		}
		return enc(seq, dst, s)
	}
	for w := range strings.FieldsSeq(seq) {
		dst = enc("▁"+w, dst, s)
	}
	return dst
}

// Pool is Model2Vec's sentence vector: the mean of the rows of ids (skipping skip, for example
// the unknown token), l2 normalized, written to out (length Dim). No ids give a zero vector.
func Pool(table []float32, dim int, ids []int32, skip int32, out []float32) {
	clear(out)
	n := 0
	for _, id := range ids {
		if id == skip {
			continue
		}
		row := table[int(id)*dim : int(id)*dim+dim]
		for j, v := range row {
			out[j] += v
		}
		n++
	}
	if n == 0 {
		return
	}
	var sq float64
	for j := range out {
		out[j] /= float32(n)
		sq += float64(out[j]) * float64(out[j])
	}
	if norm := float32(math.Sqrt(sq)); norm > 0 {
		for j := range out {
			out[j] /= norm
		}
	}
}

// WordFirst is the custom tokenizer of #91: NFKC, lowercase, `\w+` words (Python's \w); a word
// in the vocabulary is one token; any other word is segmented by the Unigram model on its own
// ("▁" + word), or dropped when Fallback is false.
type WordFirst struct {
	IDs      map[string]int32
	Uni      *Unigram
	Fallback bool
	lower    func(string) string
}

// NewWordFirst takes the vocabulary words and the Unigram model whose pieces "▁" + word give
// their ids; lower is Python's str.lower (tier1.Lower).
func NewWordFirst(words []string, uni *Unigram, fallback bool, lower func(string) string) *WordFirst {
	ids := make(map[string]int32, len(words))
	for _, w := range words {
		if id, ok := uni.ID("▁" + w); ok {
			ids[w] = id
		}
	}
	return &WordFirst{IDs: ids, Uni: uni, Fallback: fallback, lower: lower}
}

func isWord(r rune) bool { return r == '_' || unicode.IsLetter(r) || unicode.IsNumber(r) }

// Encode appends the token ids of text to dst.
func (w *WordFirst) Encode(text string, dst []int32, s *Scratch, buf []byte) ([]int32, []byte) {
	t := w.lower(norm.NFKC.String(text))
	for i := 0; i < len(t); {
		r, size := utf8.DecodeRuneInString(t[i:])
		if !isWord(r) {
			i += size
			continue
		}
		j := i + size
		for j < len(t) {
			r, size := utf8.DecodeRuneInString(t[j:])
			if !isWord(r) {
				break
			}
			j += size
		}
		word := t[i:j]
		if id, ok := w.IDs[word]; ok {
			dst = append(dst, id)
		} else if w.Fallback {
			buf = append(append(buf[:0], "▁"...), word...)
			dst = w.Uni.EncodeTrie(string(buf), dst, s)
		}
		i = j
	}
	return dst, buf
}

// Normalize applies the model's normalizer chain.
func (m *Static) Normalize(text string) string { return m.normalize(text) }
