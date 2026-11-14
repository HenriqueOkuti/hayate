package tier2tok

import (
	"math/rand/v2"
	"slices"
	"strings"
	"testing"
)

func toyUnigram() *Unigram {
	pieces := []string{"<unk>", "▁", "a", "b", "c", "ab", "bc", "abc", "▁a", "▁ab", "ç", "çã", "ão", "o", "▁ç", "日", "日本", "本語", "語"}
	vocab := make([][2]any, len(pieces))
	for i, p := range pieces {
		vocab[i] = [2]any{p, -float64(len(p)%5) - float64(i)/10}
	}
	return NewUnigram(vocab, 0)
}

func TestTrieMatchesMap(t *testing.T) {
	u := toyUnigram()
	alphabet := []string{"a", "b", "c", "ç", "ã", "o", "日", "本", "語", "x", "▁"}
	rng := rand.New(rand.NewPCG(1, 2))
	var s Scratch
	for range 2000 {
		var b strings.Builder
		for range rng.IntN(12) {
			b.WriteString(alphabet[rng.IntN(len(alphabet))])
		}
		text := b.String()
		m := u.EncodeMap(text, nil, &s)
		tr := u.EncodeTrie(text, nil, &s)
		if !slices.Equal(m, tr) {
			t.Fatalf("%q: map %v, trie %v", text, m, tr)
		}
	}
}

func TestUnknownsFused(t *testing.T) {
	u := toyUnigram()
	var s Scratch
	if got := u.EncodeTrie("axxb", nil, &s); !slices.Equal(got, []int32{2, 0, 3}) {
		t.Fatalf("got %v", got)
	}
}
