package tier1

import (
	"math"
	"reflect"
	"slices"
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

func TestNpyRoundTrip(t *testing.T) {
	dir := t.TempDir()
	w := []float32{1, -2.5, 3e-8, 4, 5, 6}
	if err := WriteFloat32(dir+"/w.npy", w, 2, 3); err != nil {
		t.Fatal(err)
	}
	got, shape, err := ReadFloat32(dir + "/w.npy")
	if err != nil || !reflect.DeepEqual(got, w) || !reflect.DeepEqual(shape, []int{2, 3}) {
		t.Fatalf("float32 round trip: %v %v %v", got, shape, err)
	}
	v := []float64{1.5, 2, 1e-300}
	if err := WriteFloat64(dir+"/v.npy", v, 3); err != nil {
		t.Fatal(err)
	}
	got64, shape, err := ReadFloat64(dir + "/v.npy")
	if err != nil || !reflect.DeepEqual(got64, v) || !reflect.DeepEqual(shape, []int{3}) {
		t.Fatalf("float64 round trip: %v %v %v", got64, shape, err)
	}
}

func synthetic() *Model {
	m := NewHashing(1<<10, 1<<10, 3000)
	nf, nl := m.WordN+m.CharN, 7
	m.IDF = make([]float64, nf)
	m.W = make([]float32, nf*nl)
	for i := range m.IDF {
		m.IDF[i] = 1 + float64(i%5)/3
	}
	for i := range m.W {
		m.W[i] = float32((i*7919)%13-6) / 10
	}
	m.Bias = make([]float32, nl)
	m.Thresholds = []float32{0.5, 0.5, 0.6, 0.7, 0.5, 0.9, 0.5}
	m.Labels = []string{"a", "b", "c", "d", "e", "f", "g"}
	m.Temperature, m.MaxLabels = 1, 3
	fl := float32(0.01)
	m.Floor = &fl
	return m
}

var docs = []string{
	"Hello World, hello again\nhttps example com",
	"São Paulo É CAPITAL\tdo ΟΔΟΣ estado İstanbul",
	"日本語のテキスト 混在 mixed ASCII",
	"bad \xff\xfe utf8 \x1c sep",
	"",
}

func TestLowerAppendMatchesLower(t *testing.T) {
	m := synthetic()
	for _, d := range docs {
		if got := string(m.lowerAppend(nil, d)); got != Lower(d) {
			t.Errorf("lowerAppend(%q) = %q, want %q", d, got, Lower(d))
		}
	}
}

func TestIntoMatchesAllocating(t *testing.T) {
	m := synthetic()
	var x Sparse
	var labels []string
	for _, d := range docs {
		want := m.Featurize(d)
		m.FeaturizeInto(d, &x)
		if !slices.Equal(x.Idx, want.Idx) || !slices.Equal(x.Val, want.Val) {
			t.Fatalf("FeaturizeInto(%q) differs from Featurize", d)
		}
		prob := m.Forward(x, nil)
		labels = m.DecideInto(prob, labels)
		if want := m.Decide(prob); !slices.Equal(labels, want) {
			t.Fatalf("DecideInto(%q) = %v, Decide = %v", d, labels, want)
		}
	}
}

func TestWarmPathDoesNotAllocate(t *testing.T) {
	m := synthetic()
	var x Sparse
	var prob []float32
	var labels []string
	run := func() {
		for _, d := range docs {
			m.FeaturizeInto(d, &x)
			prob = m.Forward(x, prob)
			labels = m.DecideInto(prob, labels)
		}
	}
	run() // grow the buffers
	if n := testing.AllocsPerRun(20, run); n != 0 {
		t.Errorf("warm featurize, forward and decide allocate %.1f times per run", n)
	}
}

func TestForwardInt8MatchesDequantized(t *testing.T) {
	m := synthetic()
	nl := len(m.Labels)
	nf := len(m.W) / nl
	q := make([]int8, len(m.W))
	scale := make([]float32, nf)
	deq := make([]float32, len(m.W))
	for r := range nf {
		scale[r] = float32(r%7+1) / 1000
		for j := range nl {
			q[r*nl+j] = int8((r*31+j*17)%255 - 127)
			deq[r*nl+j] = scale[r] * float32(q[r*nl+j])
		}
	}
	fl := synthetic()
	fl.W = deq
	qm := synthetic()
	qm.W, qm.Q, qm.Scale = nil, q, scale
	for _, d := range docs {
		x := fl.Featurize(d)
		a, b := fl.Forward(x, nil), qm.Forward(x, nil)
		for j := range a {
			if math.Abs(float64(a[j]-b[j])) > 1e-6 {
				t.Fatalf("%q label %d: float %v, int8 %v", d, j, a[j], b[j])
			}
		}
	}
}
