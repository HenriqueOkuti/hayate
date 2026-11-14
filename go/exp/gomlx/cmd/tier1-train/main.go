// Command tier1-train is the GoMLX fit test for tier 1 (#86): the whole training pipeline in Go.
//
//	GOMLX_BACKEND="xla:cuda,preallocate=false" go run ./cmd/tier1-train
//
// It reads the page sample, the component split and the teacher's main-pass labels; builds every
// page's input string and hashed n-gram counts with the parity-checked go/tier1 featurizer; fits
// the IDF on the train pages (and compares it with the IDF Python fitted); and trains the tier-1
// linear head with GoMLX: an embedding bag (gather the weight rows of a batch's non-zero
// features, scale them by the TF-IDF value, scatter-sum them into per-page logits), binary
// cross-entropy, AdamW, early stopping on val loss. It then scores the GoMLX head and the
// PyTorch head from the bundle the same way on val (BCE, and micro F1 at the best single global
// threshold), and prints a JSON summary. Test pages are not touched.
package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"math"
	"math/rand/v2"
	"os"
	"slices"
	"sort"
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

// batchTensors packs pages into fixed-shape embedding-bag inputs: flat feature ids, TF-IDF
// values and the page each entry belongs to, padded to a multiple of `bucket` entries (padding
// adds zero), plus the 0/1 label matrix padded to `size` pages.
func batchTensors(ps []page, size, bucket int, col map[string]int, nl int) []*tensors.Tensor {
	n := 0
	for _, p := range ps {
		n += len(p.x.Idx)
	}
	n = (n + bucket - 1) / bucket * bucket
	idx := make([]int32, n)
	val := make([]float32, n)
	seg := make([]int32, n)
	y := make([]float32, size*nl)
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
		tensors.FromFlatDataAndDimensions(y, size, nl),
	}
}

func main() {
	pagesPath := flag.String("pages", "../../../data/pages/pages.parquet", "page sample")
	splitsPath := flag.String("splits", "../../../data/splits/splits-v1.parquet", "split")
	labelsPath := flag.String("labels", "../../../data/labels/bulk-v2/labels.jsonl", "teacher labels")
	bundle := flag.String("bundle", "../../../artifacts/tier1-v1/cpu", "tier-1 bundle (hashing settings, PyTorch head)")
	batchSize := flag.Int("batch", 256, "pages per batch")
	bucket := flag.Int("bucket", 1<<16, "pad feature entries to a multiple of this")
	lr := flag.Float64("lr", 0.01, "AdamW learning rate")
	maxEpochs := flag.Int("max-epochs", 20, "epochs")
	patience := flag.Int("patience", 3, "epochs without val improvement before stopping")
	flag.Parse()

	t0 := time.Now()
	ref, err := tier1.Load(*bundle) // hashing settings, label ids and the PyTorch head
	check(err)
	rows, err := parquet.ReadFile[pageRow](*pagesPath)
	check(err)
	splitRows, err := parquet.ReadFile[splitRow](*splitsPath)
	check(err)
	split := map[string]string{}
	for _, s := range splitRows {
		split[s.PageID] = s.Split
	}
	teacher := readLabels(*labelsPath)
	readS := time.Since(t0)

	// features: counts for every page, IDF from train pages only
	t1 := time.Now()
	type counted struct {
		id     string
		idx    []int32
		counts []float64
	}
	all := make([]counted, len(rows))
	for i, r := range rows {
		in := tier1.PageInput(r.URL, str(r.Title), str(r.Description), text(r, 200), ref.MaxChars)
		idx, c := ref.Counts(in)
		all[i] = counted{r.PageID, idx, c}
	}
	var trainIdx [][]int32
	for _, c := range all {
		if split[c.id] == "train" {
			trainIdx = append(trainIdx, c.idx)
		}
	}
	nf := ref.WordN + ref.CharN
	idf := tier1.FitIDF(trainIdx, nf)
	var idfDiff float64
	for i := range idf {
		idfDiff = max(idfDiff, math.Abs(idf[i]-ref.IDF[i]))
	}
	ref.IDF = idf
	labelSet := map[string]bool{}
	parts := map[string][]page{}
	for _, c := range all {
		s := split[c.id]
		p := page{ref.Weigh(c.idx, c.counts), teacher[c.id]}
		parts[s] = append(parts[s], p)
		if s == "train" {
			for _, l := range p.labels {
				labelSet[l] = true
			}
		}
	}
	labelIDs := make([]string, 0, len(labelSet))
	for l := range labelSet {
		labelIDs = append(labelIDs, l)
	}
	sort.Strings(labelIDs)
	featS := time.Since(t1)
	nl := len(labelIDs)
	col := map[string]int{}
	for i, l := range labelIDs {
		col[l] = i
	}

	// base-rate bias start, as in the PyTorch head
	rate := make([]float32, nl)
	for _, p := range parts["train"] {
		for _, l := range p.labels {
			rate[col[l]]++
		}
	}
	for j := range rate {
		r := math.Min(math.Max(float64(rate[j])/float64(len(parts["train"])), 1e-4), 1-1e-4)
		rate[j] = float32(math.Log(r / (1 - r)))
	}

	backend := compute.MustNew()
	store := model.NewStore()
	logitsFn := func(scope *model.Scope, idx, val, seg *Node, pages int) *Node {
		g := idx.Graph()
		head := scope.In("head")
		bias := head.VariableWithValue("bias", rate).NodeValue(g)
		w := head.WithInitializer(func(g *Graph, shape shapes.Shape) *Node {
			return Zeros(g, shape)
		}).VariableWithShape("weights", shapes.Make(dtypes.Float32, nf, nl)).NodeValue(g)
		rowsW := Gather(w, idx)     // [n, nl]
		weighted := Mul(rowsW, val) // [n, nl], val broadcast from [n, 1]
		zero := Zeros(g, shapes.Make(dtypes.Float32, pages, nl))
		return Add(ScatterSum(zero, seg, weighted, true, false), InsertAxes(bias, 0)) // [pages, nl]
	}
	modelFn := func(scope *model.Scope, spec any, inputs []*Node) []*Node {
		return []*Node{logitsFn(scope, inputs[0], inputs[1], inputs[2], *batchSize)}
	}
	lossFn := func(labels, predictions []*Node) *Node {
		return ReduceAllMean(loss.BinaryCrossentropyLogits(labels, predictions))
	}
	opt := optimizer.Adam().LearningRate(*lr).WeightDecay(0).Done()
	trainer := train.NewTrainer(backend, store, modelFn, lossFn, opt, nil, nil)
	evalExec := model.MustNewExec(backend, store, func(scope *model.Scope, idx, val, seg *Node) *Node {
		return logitsFn(scope, idx, val, seg, *batchSize)
	})

	logitsOf := func(ps []page) [][]float32 {
		var out [][]float32
		for i := 0; i < len(ps); i += *batchSize {
			chunk := ps[i:min(i+*batchSize, len(ps))]
			ts := batchTensors(chunk, *batchSize, *bucket, col, nl)
			res := evalExec.MustCall1(ts[0], ts[1], ts[2])
			flat := tensors.MustCopyFlatData[float32](res)
			for b := range chunk {
				out = append(out, flat[b*nl:(b+1)*nl])
			}
		}
		return out
	}
	bce := func(ps []page, z [][]float32) float64 {
		var s float64
		for i, p := range ps {
			y := make([]bool, nl)
			for _, l := range p.labels {
				if c, ok := col[l]; ok {
					y[c] = true
				}
			}
			for j, v := range z[i] {
				x := float64(v)
				t := 0.0
				if y[j] {
					t = 1
				}
				s += math.Max(x, 0) - x*t + math.Log1p(math.Exp(-math.Abs(x)))
			}
		}
		return s / float64(len(ps)*nl)
	}

	rng := rand.New(rand.NewPCG(0, 0))
	trainPages := parts["train"]
	valPages := parts["val"]
	var history []float64
	best, bestEpoch, wait := math.Inf(1), 0, 0
	var bestW, bestB *tensors.Tensor
	t2 := time.Now()
	var epochTimes []float64
	for epoch := 1; epoch <= *maxEpochs; epoch++ {
		te := time.Now()
		order := rng.Perm(len(trainPages))
		for i := 0; i+*batchSize <= len(order); i += *batchSize {
			chunk := make([]page, *batchSize)
			for k := range chunk {
				chunk[k] = trainPages[order[i+k]]
			}
			ts := batchTensors(chunk, *batchSize, *bucket, col, nl)
			_, err := trainer.TrainStep(train.Batch{Inputs: ts[:3], Labels: ts[3:]})
			check(err)
		}
		epochTimes = append(epochTimes, time.Since(te).Seconds())
		vl := bce(valPages, logitsOf(valPages))
		history = append(history, vl)
		fmt.Fprintf(os.Stderr, "epoch %d: val BCE %.6f (%.1fs)\n", epoch, vl, epochTimes[len(epochTimes)-1])
		if vl < best-1e-6 {
			best, bestEpoch, wait = vl, epoch, 0
			bestW = snapshot(store, "/head/weights")
			bestB = snapshot(store, "/head/bias")
		} else if wait++; wait >= *patience {
			break
		}
	}
	trainS := time.Since(t2)
	restore(store, "/head/weights", bestW)
	restore(store, "/head/bias", bestB)

	// score both heads on val the same way
	zGo := logitsOf(valPages)
	zPt := make([][]float32, len(valPages))
	refCol := map[string]int{}
	for i, l := range ref.Labels {
		refCol[l] = i
	}
	for i, p := range valPages {
		row := make([]float32, nl)
		raw := make([]float32, len(ref.Labels))
		for k, fi := range p.x.Idx {
			v := p.x.Val[k]
			r := ref.W[int(fi)*len(ref.Labels) : (int(fi)+1)*len(ref.Labels)]
			for j := range raw {
				raw[j] += v * r[j]
			}
		}
		for j, l := range labelIDs {
			if c, ok := refCol[l]; ok {
				row[j] = raw[c] + ref.Bias[c]
			} else {
				row[j] = -50
			}
		}
		zPt[i] = row
	}
	sameLabels := slices.Equal(labelIDs, ref.Labels)
	out := map[string]any{
		"backend":                     backend.Description(),
		"pages":                       map[string]int{"train": len(trainPages), "val": len(valPages), "test": len(parts["test"])},
		"labels":                      nl,
		"label_ids_match_pytorch_run": sameLabels,
		"idf_max_abs_diff_vs_python":  idfDiff,
		"read_s":                      readS.Seconds(),
		"featurize_s":                 featS.Seconds(),
		"train_s":                     trainS.Seconds(),
		"epoch_s":                     epochTimes,
		"best_epoch":                  bestEpoch,
		"val_bce_by_epoch":            history,
		"val": map[string]any{
			"gomlx":   map[string]any{"bce": bce(valPages, zGo), "micro_f1_best_global": bestF1(valPages, zGo, labelIDs)},
			"pytorch": map[string]any{"bce": bce(valPages, zPt), "micro_f1_best_global": bestF1(valPages, zPt, labelIDs)},
		},
	}
	b, _ := json.MarshalIndent(out, "", " ")
	fmt.Println(string(b))
}

// bestF1 is the val micro F1 at the best single global threshold on sigmoid(logits), a simple
// score that treats both heads alike (no temperature, no per-label thresholds, no top-1 rule).
func bestF1(ps []page, z [][]float32, labelIDs []string) map[string]float64 {
	best := map[string]float64{"f1": 0}
	for t := 0.05; t < 0.951; t += 0.025 {
		var tp, np, nr float64
		for i, p := range ps {
			ref := map[string]bool{}
			for _, l := range p.labels {
				ref[l] = true
			}
			nr += float64(len(ref))
			for j, v := range z[i] {
				if 1/(1+math.Exp(-float64(v))) >= t {
					np++
					if ref[labelIDs[j]] {
						tp++
					}
				}
			}
		}
		if f := 2 * tp / (np + nr); f > best["f1"] {
			best = map[string]float64{"f1": f, "threshold": t, "precision": tp / np, "recall": tp / nr}
		}
	}
	return best
}

func snapshot(store *model.Store, path string) *tensors.Tensor {
	t, err := store.GetVariable(path).MustValue().LocalClone()
	check(err)
	return t
}

func restore(store *model.Store, path string, t *tensors.Tensor) {
	store.GetVariable(path).MustSetValue(t)
}

func check(err error) {
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
