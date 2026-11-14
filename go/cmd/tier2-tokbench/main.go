// Command tier2-tokbench checks and times the tier-2 tokenizer options of #91 in Go.
//
//	GOMAXPROCS=1 go run ./cmd/tier2-tokbench -cpu 2
//
// For each page of artifacts/tier2-probe/reference.jsonl (scripts/tier2_tok_reference.py) it
// checks that Go gives the same token ids as Python for: potion-multilingual-128M's tokenizer
// (Viterbi with map lookups, and with the trie), and the word-first tokenizer with and without
// the Unigram fallback. Then, one page at a time (batch 1) on one pinned thread, it times the
// three stages of a tier-2 student: tokenize, pool (mean of the token rows, l2 norm) and a
// linear head to 317 labels (random weights; the cost does not depend on them). Writes
// results/tier2-tokbench.json.
package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"math"
	"math/rand/v2"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"slices"
	"strings"
	"time"

	"github.com/HenriqueOkuti/hayate/go/exp/tier2tok"
	"github.com/HenriqueOkuti/hayate/go/tier1"
	"golang.org/x/sys/unix"
	"gonum.org/v1/gonum/blas"
	"gonum.org/v1/gonum/blas/blas32"
)

type refPage struct {
	Text      string  `json:"text"`
	Potion    []int32 `json:"potion"`
	WordFirst []int32 `json:"wordfirst"`
	WordOnly  []int32 `json:"wordonly"`
}

type variant struct {
	name   string
	encode func(text string, dst []int32) []int32
	table  []float32
	dim    int
	skip   int32
	want   func(r refPage) []int32
}

func percentile(v []float64, q float64) float64 {
	s := slices.Clone(v)
	slices.Sort(s)
	k := int(float64(len(s))*q/100+0.999999999) - 1
	return math.Round(s[max(0, min(len(s)-1, k))]*10) / 10
}

func main() {
	potionDir := flag.String("potion", "", "potion-multilingual-128M snapshot directory (default: the Hugging Face cache)")
	wordsDir := flag.String("words", "../artifacts/tier2-probe/words", "the probe's word-vocabulary model")
	refPath := flag.String("ref", "../artifacts/tier2-probe/reference.jsonl", "Python token-id reference")
	out := flag.String("out", "../results/tier2-tokbench.json", "summary")
	trials := flag.Int("trials", 3, "timed passes over the pages")
	labels := flag.Int("labels", 317, "head outputs")
	cpu := flag.Int("cpu", -1, "pin the benchmark thread to this logical CPU")
	flag.Parse()
	if *cpu >= 0 {
		runtime.LockOSThread()
		var set unix.CPUSet
		set.Set(*cpu)
		check(unix.SchedSetaffinity(0, &set))
	}
	if *potionDir == "" {
		home, _ := os.UserHomeDir()
		m, _ := filepath.Glob(filepath.Join(home, ".cache/huggingface/hub/models--minishlab--potion-multilingual-128M/snapshots/*"))
		if len(m) == 0 {
			check(fmt.Errorf("potion not in the Hugging Face cache; pass -potion"))
		}
		*potionDir = m[0]
	}

	potion, err := tier2tok.LoadStatic(*potionDir)
	check(err)
	words, err := tier2tok.LoadStatic(*wordsDir)
	check(err)
	b, err := os.ReadFile(filepath.Join(*wordsDir, "vocab.txt"))
	check(err)
	vocab := strings.Fields(string(b))
	wf := tier2tok.NewWordFirst(vocab, words.Uni, true, tier1.Lower)
	wo := tier2tok.NewWordFirst(vocab, words.Uni, false, tier1.Lower)

	var pages []refPage
	f, err := os.Open(*refPath)
	check(err)
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 64<<20), 64<<20)
	for sc.Scan() {
		var r refPage
		check(json.Unmarshal(sc.Bytes(), &r))
		pages = append(pages, r)
	}
	check(sc.Err())
	f.Close()

	var s tier2tok.Scratch
	var buf []byte
	variants := []variant{
		{"potion-map", func(t string, d []int32) []int32 { return potion.Encode(t, d, &s, false) },
			potion.Table, potion.Dim, potion.Uni.UnkID, func(r refPage) []int32 { return r.Potion }},
		{"potion-trie", func(t string, d []int32) []int32 { return potion.Encode(t, d, &s, true) },
			potion.Table, potion.Dim, potion.Uni.UnkID, func(r refPage) []int32 { return r.Potion }},
		{"wordfirst", func(t string, d []int32) []int32 { d, buf = wf.Encode(t, d, &s, buf); return d },
			words.Table, words.Dim, -1, func(r refPage) []int32 { return r.WordFirst }},
		{"wordonly", func(t string, d []int32) []int32 { d, buf = wo.Encode(t, d, &s, buf); return d },
			words.Table, words.Dim, -1, func(r refPage) []int32 { return r.WordOnly }},
	}

	rng := rand.New(rand.NewPCG(0, 0))
	report := map[string]any{"pages": len(pages), "trials": *trials, "go": runtime.Version(),
		"gomaxprocs": runtime.GOMAXPROCS(0), "pinned_cpu": *cpu, "commit": commit(),
		"created": time.Now().UTC().Format(time.RFC3339), "measures": "tier-2 inference: input string to logits, batch 1, one thread"}
	results := map[string]any{}
	for _, v := range variants {
		same, firstBad := 0, -1
		var ids []int32
		for k, r := range pages {
			ids = v.encode(r.Text, ids[:0])
			if slices.Equal(ids, v.want(r)) {
				same++
			} else if firstBad < 0 {
				firstBad = k
			}
		}
		head := make([]float32, *labels*v.dim)
		for i := range head {
			head[i] = float32(rng.NormFloat64() / 16)
		}
		vec := make([]float32, v.dim)
		logits := make([]float32, *labels)
		var tok, pool, lin, tot, nTokens []float64
		for trial := -1; trial < *trials; trial++ { // trial -1 warms up
			for _, r := range pages {
				t0 := time.Now()
				ids = v.encode(r.Text, ids[:0])
				t1 := time.Now()
				tier2tok.Pool(v.table, v.dim, ids, v.skip, vec)
				t2 := time.Now()
				blas32.Gemv(blas.NoTrans, 1, blas32.General{Rows: *labels, Cols: v.dim, Stride: v.dim, Data: head},
					blas32.Vector{N: v.dim, Data: vec, Inc: 1}, 0, blas32.Vector{N: *labels, Data: logits, Inc: 1})
				t3 := time.Now()
				if trial >= 0 {
					tok = append(tok, float64(t1.Sub(t0).Nanoseconds())/1000)
					pool = append(pool, float64(t2.Sub(t1).Nanoseconds())/1000)
					lin = append(lin, float64(t3.Sub(t2).Nanoseconds())/1000)
					tot = append(tot, float64(t3.Sub(t0).Nanoseconds())/1000)
					nTokens = append(nTokens, float64(len(ids)))
				}
			}
		}
		stage := func(x []float64) map[string]float64 {
			return map[string]float64{"p50": percentile(x, 50), "p90": percentile(x, 90), "p99": percentile(x, 99)}
		}
		results[v.name] = map[string]any{
			"same_ids_as_python": same, "first_mismatch_page": firstBad,
			"us_per_page_tokenize": stage(tok), "us_per_page_pool": stage(pool),
			"us_per_page_head": stage(lin), "us_per_page_total": stage(tot),
			"tokens_per_page_p50": percentile(nTokens, 50),
		}
		fmt.Printf("%-12s same ids %d/%d  tokenize p50 %7.1f us  total p50 %7.1f us p99 %7.1f us\n",
			v.name, same, len(pages), percentile(tok, 50), percentile(tot, 50), percentile(tot, 99))
	}
	report["variants"] = results
	j, err := json.MarshalIndent(report, "", " ")
	check(err)
	check(os.WriteFile(*out, append(j, '\n'), 0o644))
}

func commit() string {
	o, err := exec.Command("git", "rev-parse", "HEAD").Output()
	if err != nil {
		return "unknown"
	}
	c := strings.TrimSpace(string(o))
	if exec.Command("git", "diff", "--quiet", "HEAD", "--", ".").Run() != nil {
		c += "-dirty"
	}
	return c
}

func check(err error) {
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
