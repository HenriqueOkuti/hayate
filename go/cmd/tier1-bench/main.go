// Command tier1-bench measures Go tier-1 inference latency with the same method as
// scripts/bench_tier1.py: per input length and batch size, a warm-up, then trials of raw
// per-call timings for featurize, forward and decide; percentiles are nearest-rank on the raw
// calls. It measures inference only (extracted text to labels).
//
//	GOMAXPROCS=1 taskset -c 2 go run ./cmd/tier1-bench -name bench-tier1-go-local -profile local
//
// Inputs are the test pages in the bundle's reference-test.jsonl (their parts, rebuilt into an
// input string at each length). Writes the raw timings to <raw-dir>/<name>.csv and a summary to
// <out-dir>/<name>.json.
//
// Before and after the grid it times one fixed reference configuration and compares it with the
// last quiet reading in <out-dir>/bench-reference.json; a run more than 10% slower is marked busy
// (see reference.go). -accept-reference stores the reading anyway, for when the code or machine
// changed on purpose.
package main

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"math"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"runtime/debug"
	"slices"
	"strconv"
	"strings"
	"time"

	"github.com/HenriqueOkuti/hayate/go/tier1"
	"golang.org/x/sys/unix"
)

type parts struct {
	PageID      string `json:"page_id"`
	URL         string `json:"url"`
	Title       string `json:"title"`
	Description string `json:"description"`
	Text        string `json:"text"`
}

type call struct {
	maxChars, batch, trial, n         int
	featurize, forward, decide, total int64
}

func ints(s string) []int {
	var out []int
	for p := range strings.SplitSeq(s, ",") {
		v, err := strconv.Atoi(strings.TrimSpace(p))
		if err != nil {
			panic(err)
		}
		out = append(out, v)
	}
	return out
}

func percentile(v []float64, q float64) float64 {
	s := slices.Clone(v)
	slices.Sort(s)
	k := int(float64(len(s))*q/100+0.999999999) - 1
	return s[max(0, min(len(s)-1, k))]
}

func stats(v []float64, batch int) map[string]any {
	var sum, mx float64
	for _, x := range v {
		sum += x
		mx = max(mx, x)
	}
	per := func(x float64) float64 { return float64(int(x/float64(batch)*100+0.5)) / 100 }
	call := map[string]float64{"p50": percentile(v, 50), "p90": percentile(v, 90),
		"p99": percentile(v, 99), "max": mx, "mean": sum / float64(len(v))}
	page := map[string]float64{}
	for k, x := range call {
		page[k] = per(x)
	}
	return map[string]any{"call": call, "page": page}
}

func main() {
	name := flag.String("name", "", "result name")
	profile := flag.String("profile", "", "label: local, vps-docker, ...")
	bundle := flag.String("bundle", "../artifacts/tier1-v1/cpu", "tier-1 CPU bundle")
	batches := flag.String("batches", "1,8,32,128", "batch sizes")
	lengths := flag.String("max-chars", "500,1000,3000", "input lengths in characters")
	trials := flag.Int("trials", 3, "trials per configuration")
	perConfig := flag.Int("pages-per-config", 2000, "timed pages per trial")
	minCalls := flag.Int("min-calls", 50, "minimum timed calls per trial")
	warmup := flag.Int("warmup", 20, "warm-up calls")
	outDir := flag.String("out-dir", "../results", "summary directory")
	rawDir := flag.String("raw-dir", "../artifacts/bench", "raw timings directory")
	cpu := flag.Int("cpu", -1, "pin the benchmark thread to this logical CPU")
	refPath := flag.String("reference", "", "reference readings (default <out-dir>/"+refFile+")")
	accept := flag.Bool("accept-reference", false, "store this run's reference reading even if busy")
	flag.Parse()
	if *cpu >= 0 {
		// the timing loop runs on this goroutine, so lock it to one OS thread and pin that thread
		runtime.LockOSThread()
		var set unix.CPUSet
		set.Set(*cpu)
		check(unix.SchedSetaffinity(0, &set))
		pinnedCPU = *cpu
	}
	if *name == "" || *profile == "" {
		fmt.Fprintln(os.Stderr, "-name and -profile are required")
		os.Exit(2)
	}

	m, err := tier1.Load(*bundle)
	check(err)
	pages := readParts(filepath.Join(*bundle, "reference-test.jsonl"))
	var raw []call
	var configs []map[string]any
	before := timeReference(m, pages, *warmup)
	fmt.Printf("reference (chars %d batch %d) before: per page p50 %.1f us p99 %.1f us\n",
		refMaxChars, refBatch, before.P50, before.P99)
	for _, maxChars := range ints(*lengths) {
		docs := make([]string, len(pages))
		for i, p := range pages {
			docs[i] = tier1.PageInput(p.URL, p.Title, p.Description, p.Text, maxChars)
		}
		for _, batch := range ints(*batches) {
			calls := max(*minCalls, *perConfig/batch)
			pooled, trialP50, trialP99 := timeConfig(m, docs, maxChars, batch, *trials, calls, *warmup)
			raw = append(raw, pooled...)
			series := map[string][]float64{}
			for _, t := range pooled {
				series["featurize"] = append(series["featurize"], float64(t.featurize)/1000)
				series["forward"] = append(series["forward"], float64(t.forward)/1000)
				series["decide"] = append(series["decide"], float64(t.decide)/1000)
				series["total"] = append(series["total"], float64(t.total)/1000)
			}
			cfg := map[string]any{"max_chars": maxChars, "batch": batch, "calls": len(pooled)}
			for stage, v := range series {
				s := stats(v, batch)
				cfg["us_per_call_"+stage] = s["call"]
				cfg["us_per_page_"+stage] = s["page"]
			}
			mean := cfg["us_per_call_total"].(map[string]float64)["mean"]
			cfg["pages_per_s"] = float64(int(float64(batch)/(mean/1e6)*10+0.5)) / 10
			cfg["trial_spread_us_per_page"] = map[string][]float64{
				"p50": {slices.Min(trialP50), slices.Max(trialP50)},
				"p99": {slices.Min(trialP99), slices.Max(trialP99)},
			}
			configs = append(configs, cfg)
			pp := cfg["us_per_page_total"].(map[string]float64)
			fmt.Printf("chars %5d batch %3d: per page p50 %8.1f us p99 %8.1f us, %9.1f pages/s\n",
				maxChars, batch, pp["p50"], pp["p99"], cfg["pages_per_s"])
		}
	}

	after := timeReference(m, pages, *warmup)
	fmt.Printf("reference (chars %d batch %d) after:  per page p50 %.1f us p99 %.1f us\n",
		refMaxChars, refBatch, after.P50, after.P99)
	if *refPath == "" {
		*refPath = filepath.Join(*outDir, refFile)
	}
	created, rev, sha := time.Now().UTC().Format(time.RFC3339), commit(), bundleSHA(*bundle)
	check(os.MkdirAll(*outDir, 0o755))
	ref, err := referenceCheck(*refPath, baselineKey("go", *profile, sha), before, after, *accept,
		created, rev, *name+".json")
	check(err)
	switch ref.Status {
	case "busy":
		fmt.Fprintf(os.Stderr, "WARNING: reference %.0f%% slower than the last quiet run (%s, %s): "+
			"the machine looks busy; this result is marked busy. Close heavy apps and rerun.\n",
			*ref.Slowdown*100, ref.Baseline.Source, ref.Baseline.Created)
	case "no-baseline":
		fmt.Fprintln(os.Stderr, "note: no quiet reference stored for this profile and bundle yet; "+
			"this run's reading is now the baseline")
	default:
		fmt.Printf("reference check: quiet (%+.1f%% against %s)\n", *ref.Slowdown*100, ref.Baseline.Source)
	}

	check(os.MkdirAll(*rawDir, 0o755))
	rf, err := os.Create(filepath.Join(*rawDir, *name+".csv"))
	check(err)
	w := bufio.NewWriter(rf)
	fmt.Fprintln(w, "max_chars,batch,trial,call,ns_featurize,ns_forward,ns_decide,ns_total")
	for _, c := range raw {
		fmt.Fprintf(w, "%d,%d,%d,%d,%d,%d,%d,%d\n", c.maxChars, c.batch, c.trial, c.n,
			c.featurize, c.forward, c.decide, c.total)
	}
	check(w.Flush())
	check(rf.Close())

	report := map[string]any{
		"step":     "tier1-bench (go)",
		"commit":   rev,
		"created":  created,
		"measures": "inference: extracted text to labels (no extraction, no fetch)",
		"profile":  *profile,
		"config": map[string]any{"batches": ints(*batches), "max_chars": ints(*lengths),
			"trials": *trials, "pages_per_config": *perConfig, "min_calls": *minCalls,
			"warmup": *warmup, "bundle": *bundle},
		"environment": environment(),
		"reference":   ref,
		"model": map[string]any{"bundle_sha256": sha, "labels": len(m.Labels),
			"features": m.WordN + m.CharN, "dtype": "float32", "quantization": nil,
			"taxonomy_sha256": taxonomySHA(*outDir)},
		"inputs":  map[string]any{"pages": len(pages), "split": "test (component split)"},
		"configs": configs,
	}
	b, err := json.MarshalIndent(report, "", " ")
	check(err)
	check(os.WriteFile(filepath.Join(*outDir, *name+".json"), append(b, '\n'), 0o644))
}

// timeConfig times trials of calls batches (after warmup untimed calls) and returns the pooled
// calls and each trial's p50 and p99 per page in microseconds.
func timeConfig(m *tier1.Model, docs []string, maxChars, batch, trials, calls, warmup int) ([]call, []float64, []float64) {
	var trialP50, trialP99 []float64
	var pooled []call
	prob := make([]float32, 0, len(m.Labels))
	for trial := 0; trial < trials; trial++ {
		start := trial * 997
		var timed []call
		for c := -warmup; c < calls; c++ {
			k := start + (c+warmup)*batch
			xs := make([]tier1.Sparse, batch)
			probs := make([][]float32, batch)
			t0 := time.Now()
			for i := range batch {
				xs[i] = m.Featurize(docs[(k+i)%len(docs)])
			}
			t1 := time.Now()
			for i := range batch {
				prob = m.Forward(xs[i], prob)
				probs[i] = slices.Clone(prob)
			}
			t2 := time.Now()
			for i := range batch {
				_ = m.Decide(probs[i])
			}
			t3 := time.Now()
			if c >= 0 {
				timed = append(timed, call{maxChars, batch, trial, c,
					t1.Sub(t0).Nanoseconds(), t2.Sub(t1).Nanoseconds(),
					t3.Sub(t2).Nanoseconds(), t3.Sub(t0).Nanoseconds()})
			}
		}
		tot := make([]float64, len(timed))
		for i, t := range timed {
			tot[i] = float64(t.total) / 1000
		}
		trialP50 = append(trialP50, percentile(tot, 50)/float64(batch))
		trialP99 = append(trialP99, percentile(tot, 99)/float64(batch))
		pooled = append(pooled, timed...)
	}
	return pooled, trialP50, trialP99
}

// timeReference times the fixed reference configuration once (see reference.go).
func timeReference(m *tier1.Model, pages []parts, warmup int) reading {
	docs := make([]string, len(pages))
	for i, p := range pages {
		docs[i] = tier1.PageInput(p.URL, p.Title, p.Description, p.Text, refMaxChars)
	}
	_, p50, p99 := timeConfig(m, docs, refMaxChars, refBatch, 1, refCalls, warmup)
	return reading{math.Round(p50[0]*100) / 100, math.Round(p99[0]*100) / 100}
}

func readParts(path string) []parts {
	f, err := os.Open(path)
	check(err)
	defer f.Close()
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 64<<20), 64<<20)
	var out []parts
	for sc.Scan() {
		var p parts
		check(json.Unmarshal(sc.Bytes(), &p))
		out = append(out, p)
	}
	check(sc.Err())
	return out
}

var pinnedCPU = -1

func environment() map[string]any {
	model, flags := "", map[string]bool{}
	if b, err := os.ReadFile("/proc/cpuinfo"); err == nil {
		for _, line := range strings.Split(string(b), "\n") {
			k, v, ok := strings.Cut(line, ":")
			if !ok {
				continue
			}
			switch strings.TrimSpace(k) {
			case "model name":
				model = strings.TrimSpace(v)
			case "flags":
				for _, f := range strings.Fields(v) {
					flags[f] = true
				}
			}
		}
	}
	var isa []string
	for _, f := range []string{"sse4_2", "avx", "avx2", "fma", "avx_vnni", "avx512f", "avx512_vnni", "amx_tile"} {
		if flags[f] {
			isa = append(isa, f)
		}
	}
	affinity := ""
	if b, err := os.ReadFile("/proc/self/status"); err == nil {
		for _, line := range strings.Split(string(b), "\n") {
			if v, ok := strings.CutPrefix(line, "Cpus_allowed_list:"); ok {
				affinity = strings.TrimSpace(v)
			}
		}
	}
	cg := ""
	if b, err := os.ReadFile("/sys/fs/cgroup/cpu.max"); err == nil {
		cg = strings.TrimSpace(string(b))
	}
	gogc := os.Getenv("GOGC")
	return map[string]any{
		"cpu": map[string]any{"model": model, "isa": isa, "logical_cpus": runtime.NumCPU(),
			"affinity": affinity, "os": runtime.GOOS + "/" + runtime.GOARCH},
		"go": runtime.Version(), "gomaxprocs": runtime.GOMAXPROCS(0), "gogc": gogc,
		"pinned_thread_cpu": pinnedCPU,
		"memory_limit":      debug.SetMemoryLimit(-1), "cgroup_cpu_max": cg,
	}
}

func bundleSHA(dir string) string {
	h := sha256.New()
	for _, f := range []string{"weights.npy", "bias.npy", "meta.json"} {
		b, err := os.ReadFile(filepath.Join(dir, f))
		check(err)
		h.Write(b)
	}
	return hex.EncodeToString(h.Sum(nil))
}

func taxonomySHA(resultsDir string) any {
	b, err := os.ReadFile(filepath.Join(resultsDir, "tier1-v1.json"))
	if err != nil {
		return nil
	}
	var r struct {
		Inputs struct {
			Taxonomy string `json:"taxonomy_sha256"`
		} `json:"inputs"`
	}
	if json.Unmarshal(b, &r) != nil {
		return nil
	}
	return r.Inputs.Taxonomy
}

func commit() string {
	if c := os.Getenv("HAYATE_COMMIT"); c != "" {
		return c
	}
	out, err := exec.Command("git", "rev-parse", "HEAD").Output()
	if err != nil {
		return "unknown"
	}
	c := strings.TrimSpace(string(out))
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
