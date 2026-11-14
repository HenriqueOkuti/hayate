// Package tier2tok holds the tokenizers compared for tier 2 in #91: a Unigram tokenizer for
// Model2Vec models (the fit test's Viterbi with substring lookups, and the same search over a
// byte trie), a word-first tokenizer, and mean pooling over a static embedding table. It is
// research code; W08 builds the tier-2 student from what the comparison picks.
package tier2tok

import (
	"math"
	"slices"
	"unicode/utf8"
)

// Unigram is a SentencePiece Unigram model: pieces with log-probability scores, searched with a
// Viterbi for the highest-scoring segmentation, as in the Hugging Face tokenizers library.
type Unigram struct {
	ids       map[string]int32
	scores    []float64
	maxByHead map[rune]int // longest piece, in runes, starting with each rune
	UnkID     int32
	unkScore  float64

	// byte trie over the pieces: child of node n on byte b is next[n<<8|b]; end[n] is the id of
	// the piece ending at n, or -1
	next map[uint64]int32
	end  []int32
}

// NewUnigram builds the model from tokenizer.json's [piece, score] list and its unk_id.
func NewUnigram(vocab [][2]any, unkID int) *Unigram {
	u := &Unigram{ids: make(map[string]int32, len(vocab)), scores: make([]float64, len(vocab)),
		maxByHead: map[rune]int{}, UnkID: int32(unkID), next: map[uint64]int32{}, end: []int32{-1}}
	minScore := math.Inf(1)
	for i, v := range vocab {
		piece, score := v[0].(string), v[1].(float64)
		u.ids[piece] = int32(i)
		u.scores[i] = score
		if r, _ := utf8.DecodeRuneInString(piece); piece != "" {
			u.maxByHead[r] = max(u.maxByHead[r], utf8.RuneCountInString(piece))
		}
		minScore = math.Min(minScore, score)
		node := int32(0)
		for k := 0; k < len(piece); k++ {
			key := uint64(node)<<8 | uint64(piece[k])
			child, ok := u.next[key]
			if !ok {
				child = int32(len(u.end))
				u.end = append(u.end, -1)
				u.next[key] = child
			}
			node = child
		}
		if piece != "" {
			u.end[node] = int32(i)
		}
	}
	u.unkScore = minScore - 10 // the tokenizers library's unknown-piece penalty
	return u
}

// ID returns a piece's id and whether it is in the vocabulary.
func (u *Unigram) ID(piece string) (int32, bool) {
	id, ok := u.ids[piece]
	return id, ok
}

// Scratch holds reusable buffers for one goroutine's encodes.
type Scratch struct {
	offs  []int
	best  []float64
	from  []int
	piece []int32
	out   []int32
}

// EncodeMap appends the Viterbi segmentation of text to dst, looking up every substring up to
// the longest piece for its first rune in a map (the fit test's method, #86).
func (u *Unigram) EncodeMap(text string, dst []int32, s *Scratch) []int32 {
	return u.encode(text, dst, s, false)
}

// EncodeTrie is EncodeMap with the candidate pieces found by one walk of a byte trie; it visits
// the same pieces in the same order (shortest first), so the segmentation is identical.
func (u *Unigram) EncodeTrie(text string, dst []int32, s *Scratch) []int32 {
	return u.encode(text, dst, s, true)
}

func (u *Unigram) encode(text string, dst []int32, s *Scratch, trie bool) []int32 {
	offs := s.offs[:0] // byte offset of each rune, so pieces are substrings
	for i := range text {
		offs = append(offs, i)
	}
	offs = append(offs, len(text))
	n := len(offs) - 1
	best, from, piece := grow(s.best, n+1), growInt(s.from, n+1), grow32(s.piece, n+1)
	best[0] = 0
	for i := 1; i <= n; i++ {
		best[i] = math.Inf(-1)
	}
	relax := func(i, j int, id int32) {
		if sc := best[i] + u.scores[id]; sc > best[j] {
			best[j], from[j], piece[j] = sc, i, id
		}
	}
	for i := 0; i < n; i++ {
		if math.IsInf(best[i], -1) {
			continue
		}
		covered := false
		if trie {
			// walk bytes from offs[i]; a piece can only end on a rune boundary, at offs[j]
			node, j := int32(0), i+1
			for b := offs[i]; b < len(text); b++ {
				child, ok := u.next[uint64(node)<<8|uint64(text[b])]
				if !ok {
					break
				}
				node = child
				if b+1 == offs[j] {
					if id := u.end[node]; id >= 0 {
						covered = covered || j == i+1
						relax(i, j, id)
					}
					j++
				}
			}
		} else {
			head, _ := utf8.DecodeRuneInString(text[offs[i]:])
			for l := 1; l <= u.maxByHead[head] && i+l <= n; l++ {
				if id, ok := u.ids[text[offs[i]:offs[i+l]]]; ok {
					covered = covered || l == 1
					relax(i, i+l, id)
				}
			}
		}
		if !covered {
			if sc := best[i] + u.unkScore; sc > best[i+1] {
				best[i+1], from[i+1], piece[i+1] = sc, i, u.UnkID
			}
		}
	}
	out := s.out[:0]
	for i := n; i > 0; i = from[i] {
		out = append(out, piece[i])
	}
	slices.Reverse(out)
	start := len(dst)
	for _, id := range out { // consecutive unknowns are fused, as the tokenizers library does
		if id == u.UnkID && len(dst) > start && dst[len(dst)-1] == u.UnkID {
			continue
		}
		dst = append(dst, id)
	}
	s.offs, s.best, s.from, s.piece, s.out = offs, best, from, piece, out
	return dst
}

func grow(b []float64, n int) []float64 {
	if cap(b) < n {
		return make([]float64, n)
	}
	return b[:n]
}

func growInt(b []int, n int) []int {
	if cap(b) < n {
		return make([]int, n)
	}
	return b[:n]
}

func grow32(b []int32, n int) []int32 {
	if cap(b) < n {
		return make([]int32, n)
	}
	return b[:n]
}
