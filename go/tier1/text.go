// Package tier1 serves the tier-1 student (hashed n-grams and one linear layer) without Python.
//
// It reproduces the Python reference exactly: hayate.students.features.page_input builds the
// input string, scikit-learn's HashingVectorizer (word 1-2 grams and char_wb 3-5 grams,
// MurmurHash3) and TfidfTransformer (sublinear tf, l2) turn it into features, and the exported
// weights give one probability per label. Python string semantics that Go does not share are
// handled explicitly: full lowercasing (U+0130 and the final sigma), str.isspace and the \w class.
package tier1

import (
	"strings"
	"unicode"
)

// isSpace matches Python's str.isspace: Unicode White_Space plus the four information
// separators U+001C..U+001F, which Python treats as whitespace and Go does not.
func isSpace(r rune) bool {
	return unicode.IsSpace(r) || (r >= 0x1c && r <= 0x1f)
}

// isWord matches Python's re \w on str: alphanumeric (str.isalnum) or underscore.
func isWord(r rune) bool {
	return r == '_' || unicode.IsLetter(r) || unicode.IsNumber(r)
}

func isCased(r rune) bool {
	return unicode.IsUpper(r) || unicode.IsLower(r) || unicode.IsTitle(r) ||
		unicode.Is(unicode.Other_Lowercase, r) || unicode.Is(unicode.Other_Uppercase, r)
}

func isCaseIgnorable(r rune) bool {
	switch r {
	case '\'', '.', ':', '^', '`', 0xb7, 0x2018, 0x2019, 0x2024, 0xfe52, 0xfe55, 0xff07, 0xff0e, 0xff1a:
		return true
	}
	return unicode.In(r, unicode.Mn, unicode.Me, unicode.Cf, unicode.Lm, unicode.Sk)
}

// finalSigma reports whether the capital sigma at rs[i] is in the Final_Sigma context:
// a cased letter before it (skipping case-ignorables) and none after it.
func finalSigma(rs []rune, i int) bool {
	j := i - 1
	for j >= 0 && isCaseIgnorable(rs[j]) {
		j--
	}
	if j < 0 || !isCased(rs[j]) {
		return false
	}
	k := i + 1
	for k < len(rs) && isCaseIgnorable(rs[k]) {
		k++
	}
	return k >= len(rs) || !isCased(rs[k])
}

// Lower is Python's str.lower: the simple lowercase mapping plus the full mapping of U+0130
// (to "i" and a combining dot above) and the final-sigma rule.
func Lower(s string) string {
	ascii := true
	for i := 0; i < len(s); i++ {
		if s[i] >= 0x80 {
			ascii = false
			break
		}
	}
	if ascii {
		return strings.ToLower(s)
	}
	rs := []rune(s)
	var b strings.Builder
	b.Grow(len(s) + 8)
	for i, r := range rs {
		switch {
		case r == 0x130:
			b.WriteString("i̇")
		case r == 0x3a3:
			if finalSigma(rs, i) {
				b.WriteRune(0x3c2)
			} else {
				b.WriteRune(0x3c3)
			}
		default:
			b.WriteRune(unicode.ToLower(r))
		}
	}
	return b.String()
}

// urlKeep is the character class [0-9a-zA-ZÀ-ɏ] that page_input keeps from a URL.
func urlKeep(r rune) bool {
	return (r >= '0' && r <= '9') || (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') ||
		(r >= 0xc0 && r <= 0x24f)
}

var urlNoise = map[string]bool{"https": true, "http": true, "www": true}

// PageInput is hayate.students.features.page_input: URL words, title, description and the first
// maxChars code points of the text, one per line.
func PageInput(url, title, description, text string, maxChars int) string {
	var words []string
	for _, w := range strings.FieldsFunc(Lower(url), func(r rune) bool { return !urlKeep(r) }) {
		if !urlNoise[w] {
			words = append(words, w)
		}
	}
	if n := 0; maxChars >= 0 {
		for i := range text {
			if n == maxChars {
				text = text[:i]
				break
			}
			n++
		}
	}
	return strings.Join([]string{strings.Join(words, " "), title, description, text}, "\n")
}

// WordNgrams is the word analyzer: lowercase, tokens matching \b\w\w+\b, then n-grams from
// minN to maxN joined by single spaces.
func WordNgrams(doc string, minN, maxN int, emit func(string)) {
	var tokens []string
	start := -1
	runes := 0
	lower := Lower(doc)
	for i, r := range lower {
		if isWord(r) {
			if start < 0 {
				start, runes = i, 0
			}
			runes++
			continue
		}
		if start >= 0 && runes >= 2 {
			tokens = append(tokens, lower[start:i])
		}
		start = -1
	}
	if start >= 0 && runes >= 2 {
		tokens = append(tokens, lower[start:])
	}
	for n := minN; n <= maxN; n++ {
		for i := 0; i+n <= len(tokens); i++ {
			if n == 1 {
				emit(tokens[i])
			} else {
				emit(strings.Join(tokens[i:i+n], " "))
			}
		}
	}
}

// CharWbNgrams is scikit-learn's char_wb analyzer: lowercase, split on whitespace, pad each
// word with one space on both sides, and emit its character n-grams from minN to maxN. A word
// shorter than n is emitted once, whole, and ends the loop over n for that word.
func CharWbNgrams(doc string, minN, maxN int, emit func(string)) {
	lower := Lower(doc)
	for _, w := range strings.FieldsFunc(lower, isSpace) {
		padded := []rune(" " + w + " ")
		wl := len(padded)
		for n := minN; n <= maxN; n++ {
			offset := 0
			end := min(n, wl)
			emit(string(padded[0:end]))
			for offset+n < wl {
				offset++
				emit(string(padded[offset : offset+n]))
			}
			if offset == 0 {
				break
			}
		}
	}
}
