package tier1

import (
	"reflect"
	"testing"
)

// Expected values come from scikit-learn 1.9.1 (murmurhash3_32 and build_analyzer).
func TestMurmur3MatchesScikitLearn(t *testing.T) {
	cases := map[string]int32{
		"foo": -156908512, "hello world": 1586663183, " ab": -760043134, "olá": 871295443,
		"": 0, " são ": 622235137, "日本語": -1515949417,
	}
	for s, want := range cases {
		if got := Murmur3([]byte(s), 0); got != want {
			t.Errorf("Murmur3(%q) = %d, want %d", s, got, want)
		}
	}
}

func TestBucket(t *testing.T) {
	n := 1 << 18
	if got := bucket(-156908512, n); got != 156908512%n {
		t.Errorf("bucket = %d", got)
	}
	if got := bucket(-2147483648, n); got != (2147483647-(n-1))%n {
		t.Errorf("bucket(INT_MIN) = %d", got)
	}
}

func collect(f func(string, int, int, func(string)), doc string, lo, hi int) []string {
	var out []string
	f(doc, lo, hi, func(g string) { out = append(out, g) })
	return out
}

func TestCharWbMatchesScikitLearn(t *testing.T) {
	got := collect(CharWbNgrams, "Hi  são\npaulo\x1cx", 3, 5)
	want := []string{" hi", "hi ", " hi ", " sã", "são", "ão ", " são", "são ", " são ", " pa",
		"pau", "aul", "ulo", "lo ", " pau", "paul", "aulo", "ulo ", " paul", "paulo", "aulo ", " x "}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("char_wb:\n got %q\nwant %q", got, want)
	}
}

func TestWordMatchesScikitLearn(t *testing.T) {
	got := collect(WordNgrams, "Olá, mundo! a_b x 3d İstanbul ñandú 日本語", 1, 2)
	want := []string{"olá", "mundo", "a_b", "3d", "stanbul", "ñandú", "日本語", "olá mundo",
		"mundo a_b", "a_b 3d", "3d stanbul", "stanbul ñandú", "ñandú 日本語"}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("word:\n got %q\nwant %q", got, want)
	}
}

func TestLowerFinalSigma(t *testing.T) {
	if got := Lower("ΣΑΣ ΟΔΟΣ."); got != "σας οδος." {
		t.Errorf("Lower = %q", got)
	}
}

func TestPageInputCutsCodePoints(t *testing.T) {
	got := PageInput("https://www.Exemplo.com.br/são-paulo?x=1", "T", "D", "ãbcdé", 3)
	want := "exemplo com br são paulo x 1\nT\nD\nãbc"
	if got != want {
		t.Errorf("PageInput = %q, want %q", got, want)
	}
}
