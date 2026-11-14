// Command tier1-train trains the tier-1 linear head in Go with GoMLX (#90), one candidate per
// learning rate, for scripts/train_tier1.py --heads to tune and score with the v1 procedure.
//
//	cd go/train && GOMLX_BACKEND="xla:cuda,preallocate=false" go run ./cmd/tier1-train \
//	    -out ../../artifacts/tier1-v2/heads
//
// It reads the page sample, the component split and the teacher's main-pass labels; builds the
// train and val pages' input strings and hashed n-gram counts with the parity-checked go/tier1
// featurizer (test pages are never read past their split); fits the IDF on the train pages; and
// for each learning rate trains an embedding bag (gather the weight rows of a batch's non-zero
// features, scale them by the TF-IDF value, scatter-sum them into per-page logits) with mean
// binary cross-entropy, Adam and early stopping on val loss, keeping the best epoch.
//
// Writes to -out: featurizer.json and idf.npy (as in a CPU bundle), and per learning rate
// lr-<lr>/weights.npy (features x labels, float32), bias.npy and train.json (label ids,
// settings, val loss by epoch, times, backend, commit).
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
	"sort"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/HenriqueOkuti/hayate/go/tier1"
	"github.com/gomlx/compute"
	"github.com/gomlx/compute/dtypes"
	"github.com/gomlx/compute/shapes"
	_ "github.com/gomlx/gomlx/backends/default"
	. "github.com/gomlx/gomlx/core/graph"
	"github.com/gomlx/gomlx/core/tensors"
	"github.com/gomlx/gomlx/ml/model"
	"github.com/gomlx/gomlx/ml/train"
	"github.com/gomlx/gomlx/ml/train/loss"
	"github.com/gomlx/gomlx/ml/train/optimizer"
	"github.com/parquet-go/parquet-go"
)

type pageRow struct {
	PageID      string  `parquet:"page_id"`
	URL         string  `parquet:"url"`
	Title       *string `parquet:"title,optional"`
	Description *string `parquet:"meta_description,optional"`
	Trafilatura *string `parquet:"text_trafilatura,optional"`
	Resiliparse *string `parquet:"text_resiliparse,optional"`
}

type splitRow struct {
	PageID string `parquet:"page_id"`
	Split  string `parquet:"split"`
}

func str(p *string) string {
	if p == nil {
		return ""
	}
	return *p
}

// text is the teacher's text selection (claude.text_sql): trafilatura unless it has fewer than
// minChars code points, then resiliparse.
func text(r pageRow, minChars int) string {
	if t := str(r.Trafilatura); utf8.RuneCountInString(t) >= minChars {
		return t
	}
	return str(r.Resiliparse)
}

func readLabels(path string) map[string][]string {
	f, err := os.Open(path)
	check(err)
	defer f.Close()
	out := map[string][]string{}
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 1<<20)
	for sc.Scan() {
		var r struct {
			PageID string `json:"page_id"`
			Pass   string `json:"pass"`
			Labels []struct {
				ID string `json:"id"`
			} `json:"labels"`
		}
		check(json.Unmarshal(sc.Bytes(), &r))
		if r.Pass != "main" {
			continue
		}
		ids := make([]string, len(r.Labels))
		for i, l := range r.Labels {
			ids[i] = l.ID
		}
		out[r.PageID] = ids
	}
	check(sc.Err())
	return out
}

type page struct {
	x      tier1.Sparse
	labels []string
}

// batchTensors packs pages into embedding-bag inputs: flat feature ids, TF-IDF values and the
// page each entry belongs to, padded to a multiple of bucket entries (padding adds zero to page
// 0), a [pages] placeholder that carries the batch size into the graph, and the 0/1 labels.
func batchTensors(ps []page, bucket int, col map[string]int, nl int) []*tensors.Tensor {
	n := 0
	for _, p := range ps {
		n += len(p.x.Idx)
	}
	n = (n + bucket - 1) / bucket * bucket
	idx := make([]int32, n)
	val := make([]float32, n)
	seg := make([]int32, n)
	y := make([]float32, len(ps)*nl)
	k := 0
	for b, p := range ps {
		for j, i := range p.x.Idx {
			idx[k], val[k], seg[k] = i, p.x.Val[j], int32(b)
			k++
		}
		for _, l := range p.labels {
			if c, ok := col[l]; ok {
				y[b*nl+c] = 1
			}
		}
	}
	return []*tensors.Tensor{
		tensors.FromFlatDataAndDimensions(idx, n, 1),
		tensors.FromFlatDataAndDimensions(val, n, 1),
		tensors.FromFlatDataAndDimensions(seg, n, 1),
		tensors.FromFlatDataAndDimensions(make([]float32, len(ps)), len(ps)),
		tensors.FromFlatDataAndDimensions(y, len(ps), nl),
	}
}

// meanBCE is the mean binary cross-entropy over pages and labels, in float64.
func meanBCE(ps []page, z [][]float32, col map[string]int, nl int) float64 {
	var s float64
	y := make([]float64, nl)
	for i, p := range ps {
		clear(y)
		for _, l := range p.labels {
			if c, ok := col[l]; ok {
				y[c] = 1
			}
		}
		for j, v := range z[i] {
			x := float64(v)
			s += math.Max(x, 0) - x*y[j] + math.Log1p(math.Exp(-math.Abs(x)))
		}
	}
	return s / float64(len(ps)*nl)
}

func floats(s string) []float64 {
	var out []float64
	for p := range strings.SplitSeq(s, ",") {
		v, err := strconv.ParseFloat(strings.TrimSpace(p), 64)
		check(err)
		out = append(out, v)
	}
	return out
}

func main() {
	pagesPath := flag.String("pages", "../../data/pages/pages.parquet", "page sample")
	splitsPath := flag.String("splits", "../../data/splits/splits-v1.parquet", "split (component column)")
	labelsPath := flag.String("labels", "../../data/labels/bulk-v2/labels.jsonl", "teacher labels")
	out := flag.String("out", "../../artifacts/tier1-v2/heads", "output directory")
	lrs := flag.String("lrs", "0.003,0.01,0.03", "learning rates, one candidate each")
	wordBits := flag.Int("word-bits", 18, "log2 of the word-feature buckets")
	charBits := flag.Int("char-bits", 18, "log2 of the char-feature buckets")
	maxChars := flag.Int("max-chars", 3000, "page-text characters in the input")
	minChars := flag.Int("min-chars", 200, "use resiliparse text below this many characters")
	batchSize := flag.Int("batch", 256, "pages per batch")
	bucket := flag.Int("bucket", 1<<16, "pad feature entries to a multiple of this")
	eps := flag.Float64("adam-eps", 1e-7, "Adam epsilon (GoMLX default; PyTorch's is 1e-8)")
	maxEpochs := flag.Int("max-epochs", 20, "epochs")
	patience := flag.Int("patience", 3, "epochs without val improvement before stopping")
	seed := flag.Uint64("seed", 0, "shuffle seed")
	flag.Parse()

	t0 := time.Now()
	rows, err := parquet.ReadFile[pageRow](*pagesPath)
	check(err)
	splitRows, err := parquet.ReadFile[splitRow](*splitsPath)
	check(err)
	split := map[string]string{}
	for _, s := range splitRows {
		split[s.PageID] = s.Split
	}
	teacher := readLabels(*labelsPath)

	// features: counts for train and val pages only, IDF from train pages
	feat := tier1.NewHashing(1<<*wordBits, 1<<*charBits, *maxChars)
	type counted struct {
		split  string
		labels []string
		idx    []int32
		counts []float64
	}
	var all []counted
	var trainIdx [][]int32
	sort.Slice(rows, func(i, j int) bool { return rows[i].PageID < rows[j].PageID })
	for _, r := range rows {
		s := split[r.PageID]
		if s != "train" && s != "val" {
			continue
		}
		labels, ok := teacher[r.PageID]
		if !ok {
			check(fmt.Errorf("page %s has no teacher label", r.PageID))
		}
		in := tier1.PageInput(r.URL, str(r.Title), str(r.Description), text(r, *minChars), *maxChars)
		idx, c := feat.Counts(in)
		all = append(all, counted{s, labels, idx, c})
		if s == "train" {
			trainIdx = append(trainIdx, idx)
		}
	}
	nf := feat.WordN + feat.CharN
	feat.IDF = tier1.FitIDF(trainIdx, nf)
	labelSet := map[string]bool{}
	parts := map[string][]page{}
	for _, c := range all {
		parts[c.split] = append(parts[c.split], page{feat.Weigh(c.idx, c.counts), c.labels})
		if c.split == "train" {
			for _, l := range c.labels {
				labelSet[l] = true
			}
		}
	}
	labelIDs := make([]string, 0, len(labelSet))
	for l := range labelSet {
		labelIDs = append(labelIDs, l)
	}
	sort.Strings(labelIDs) // labels never seen in train can't be learned, as in train_tier1.py
	featS := time.Since(t0).Seconds()
	nl := len(labelIDs)
	col := map[string]int{}
	for i, l := range labelIDs {
		col[l] = i
	}
	trainPages, valPages := parts["train"], parts["val"]
	fmt.Fprintf(os.Stderr, "%d train, %d val pages, %d labels, %d features (%.1fs)\n",
		len(trainPages), len(valPages), nl, nf, featS)

	check(os.MkdirAll(*out, 0o755))
	check(tier1.WriteFloat64(filepath.Join(*out, "idf.npy"), feat.IDF, nf))
	writeJSON(filepath.Join(*out, "featurizer.json"), map[string]any{
		"word": map[string]any{"n_features": feat.WordN, "ngram_range": []int{1, 2},
			"token_pattern": `(?u)\b\w\w+\b`},
		"char":           map[string]any{"n_features": feat.CharN, "ngram_range": []int{3, 5}, "analyzer": "char_wb"},
		"lowercase":      true,
		"alternate_sign": false,
		"tfidf":          map[string]any{"sublinear_tf": true, "norm": "l2", "smooth_idf": true},
		"dtype":          "float64 until the end, then float32",
		"max_chars":      *maxChars,
	})

	// base-rate bias start, as in the PyTorch head
	rate := make([]float32, nl)
	for _, p := range trainPages {
		for _, l := range p.labels {
			rate[col[l]]++
		}
	}
	for j := range rate {
		r := math.Min(math.Max(float64(rate[j])/float64(len(trainPages)), 1e-4), 1-1e-4)
		rate[j] = float32(math.Log(r / (1 - r)))
	}

	backend := compute.MustNew()
	rev, created := commit(), time.Now().UTC().Format(time.RFC3339)
	for _, lr := range floats(*lrs) {
		store := model.NewStore()
		logitsFn := func(scope *model.Scope, idx, val, seg, rowsOf *Node) *Node {
			g := idx.Graph()
			pages := rowsOf.Shape().Dimensions[0]
			head := scope.In("head")
			bias := head.VariableWithValue("bias", rate).NodeValue(g)
			w := head.WithInitializer(func(g *Graph, shape shapes.Shape) *Node {
				return Zeros(g, shape)
			}).VariableWithShape("weights", shapes.Make(dtypes.Float32, nf, nl)).NodeValue(g)
			weighted := Mul(Gather(w, idx), val) // [n, nl], val broadcast from [n, 1]
			zero := Zeros(g, shapes.Make(dtypes.Float32, pages, nl))
			return Add(ScatterSum(zero, seg, weighted, true, false), InsertAxes(bias, 0))
		}
		modelFn := func(scope *model.Scope, spec any, in []*Node) []*Node {
			return []*Node{logitsFn(scope, in[0], in[1], in[2], in[3])}
		}
		lossFn := func(labels, predictions []*Node) *Node {
			return ReduceAllMean(loss.BinaryCrossentropyLogits(labels, predictions))
		}
		opt := optimizer.Adam().LearningRate(lr).WeightDecay(0).Epsilon(*eps).Done()
		trainer := train.NewTrainer(backend, store, modelFn, lossFn, opt, nil, nil)
		evalExec := model.MustNewExec(backend, store, logitsFn)
		logitsOf := func(ps []page) [][]float32 {
			var z [][]float32
			for i := 0; i < len(ps); i += *batchSize {
				chunk := ps[i:min(i+*batchSize, len(ps))]
				ts := batchTensors(chunk, *bucket, col, nl)
				flat := tensors.MustCopyFlatData[float32](evalExec.MustCall1(ts[0], ts[1], ts[2], ts[3]))
				for b := range chunk {
					z = append(z, flat[b*nl:(b+1)*nl])
				}
			}
			return z
		}

		rng := rand.New(rand.NewPCG(*seed, 0))
		var history, epochS []float64
		best, bestEpoch, wait := math.Inf(1), 0, 0
		var bestW, bestB []float32
		t1 := time.Now()
		for epoch := 1; epoch <= *maxEpochs; epoch++ {
			te := time.Now()
			order := rng.Perm(len(trainPages))
			for i := 0; i < len(order); i += *batchSize {
				chunk := make([]page, 0, *batchSize)
				for _, k := range order[i:min(i+*batchSize, len(order))] {
					chunk = append(chunk, trainPages[k])
				}
				ts := batchTensors(chunk, *bucket, col, nl)
				_, err := trainer.TrainStep(train.Batch{Inputs: ts[:4], Labels: ts[4:]})
				check(err)
			}
			epochS = append(epochS, math.Round(time.Since(te).Seconds()*10)/10)
			vl := meanBCE(valPages, logitsOf(valPages), col, nl)
			history = append(history, math.Round(vl*1e6)/1e6)
			fmt.Fprintf(os.Stderr, "lr %g epoch %d: val BCE %.6f (%.1fs)\n", lr, epoch, vl, epochS[len(epochS)-1])
			if vl < best-1e-6 {
				best, bestEpoch, wait = vl, epoch, 0
				bestW = value(store, "/head/weights")
				bestB = value(store, "/head/bias")
			} else if wait++; wait >= *patience {
				break
			}
		}
		dir := filepath.Join(*out, "lr-"+strconv.FormatFloat(lr, 'g', -1, 64))
		check(os.MkdirAll(dir, 0o755))
		check(tier1.WriteFloat32(filepath.Join(dir, "weights.npy"), bestW, nf, nl))
		check(tier1.WriteFloat32(filepath.Join(dir, "bias.npy"), bestB, nl))
		writeJSON(filepath.Join(dir, "train.json"), map[string]any{
			"trainer": "go/train/cmd/tier1-train", "commit": rev, "created": created,
			"backend": backend.Description(), "lr": lr,
			"optimizer": map[string]any{"name": "adam", "epsilon": *eps, "beta1": 0.9, "beta2": 0.999,
				"weight_decay": 0.0},
			"batch": *batchSize, "max_epochs": *maxEpochs, "patience": *patience, "seed": *seed,
			"inputs": map[string]any{"pages": *pagesPath, "splits": *splitsPath, "labels": *labelsPath,
				"max_chars": *maxChars, "min_chars": *minChars},
			"pages":            map[string]int{"train": len(trainPages), "val": len(valPages)},
			"features":         nf,
			"label_ids":        labelIDs,
			"val_bce_by_epoch": history,
			"best_epoch":       bestEpoch,
			"epoch_s":          epochS,
			"featurize_s":      math.Round(featS*10) / 10,
			"train_s":          math.Round(time.Since(t1).Seconds()*10) / 10,
		})
		fmt.Fprintf(os.Stderr, "lr %g: best epoch %d, val BCE %.6f -> %s\n", lr, bestEpoch, best, dir)
	}
}

func value(store *model.Store, path string) []float32 {
	t, err := store.GetVariable(path).MustValue().LocalClone()
	check(err)
	return tensors.MustCopyFlatData[float32](t)
}

func writeJSON(path string, v any) {
	b, err := json.MarshalIndent(v, "", " ")
	check(err)
	check(os.WriteFile(path, append(b, '\n'), 0o644))
}

func commit() string {
	out, err := exec.Command("git", "rev-parse", "HEAD").Output()
	if err != nil {
		return "unknown"
	}
	c := strings.TrimSpace(string(out))
	if exec.Command("git", "diff", "--quiet", "HEAD", "--", "..").Run() != nil {
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
