// Command tier3-check is the tier-3 part of the GoMLX fit test (#86): run a small multilingual
// encoder's ONNX export through onnx-gomlx and compare it with ONNX Runtime in Python.
//
//	GOMLX_BACKEND="xla:cuda,preallocate=false" go run ./cmd/tier3-check
//
// It reads artifacts/e5-reference.json (scripts/e5_reference.py): the input ids, attention mask
// and ONNX Runtime's mean-pooled, normalized embeddings. It converts the same model.onnx with
// onnx-gomlx, runs it on the same ids, pools the same way, and reports the largest difference,
// the lowest cosine and the forward-pass time.
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"math"
	"os"
	"time"

	"github.com/gomlx/compute"
	"github.com/gomlx/compute/shapes"
	_ "github.com/gomlx/gomlx/backends/default"
	. "github.com/gomlx/gomlx/core/graph"
	"github.com/gomlx/gomlx/core/tensors"
	"github.com/gomlx/gomlx/ml/model"
	"github.com/gomlx/gomlx/ml/train"
	"github.com/gomlx/gomlx/ml/train/loss"
	"github.com/gomlx/gomlx/ml/train/optimizer"
	"github.com/gomlx/onnx-gomlx/onnx"
	"github.com/gomlx/onnx-gomlx/onnx/parser"
)

type reference struct {
	Model      string      `json:"model"`
	InputNames []string    `json:"input_names"`
	IDs        [][]int64   `json:"ids"`
	Mask       [][]int64   `json:"mask"`
	Embeddings [][]float64 `json:"embeddings"`
	OnnxPath   string      `json:"onnx_path"`
}

func main() {
	refPath := flag.String("ref", "../../../artifacts/e5-reference.json", "ONNX Runtime reference")
	runs := flag.Int("runs", 5, "timed forward passes")
	steps := flag.Int("finetune-steps", 0, "if > 0, also fine-tune the whole encoder plus a head for this many steps")
	flag.Parse()

	b, err := os.ReadFile(*refPath)
	check(err)
	var ref reference
	check(json.Unmarshal(b, &ref))
	t0 := time.Now()
	m, err := parser.ParseFile(ref.OnnxPath)
	check(err)
	store := model.NewStore()
	check(m.VariablesToScope(store.RootScope()))
	loadS := time.Since(t0).Seconds()

	backend := compute.MustNew()
	types := make([][]int64, len(ref.IDs))
	for i := range types {
		types[i] = make([]int64, len(ref.IDs[i]))
	}
	exec := model.MustNewExec(backend, store, func(scope *model.Scope, ids, mask, tt *Node) *Node {
		out := m.CallGraph(scope, ids.Graph(), map[string]*Node{
			"input_ids": ids, "attention_mask": mask, "token_type_ids": tt,
		})
		return out[0]
	})
	var times []float64
	var hidden *tensors.Tensor
	for r := 0; r <= *runs; r++ {
		t := time.Now()
		hidden = exec.MustCall1(ref.IDs, ref.Mask, types)
		_ = tensors.MustCopyFlatData[float32](hidden)
		if r > 0 { // the first call compiles
			times = append(times, time.Since(t).Seconds()*1000)
		}
	}
	dims := hidden.Shape().Dimensions // [batch, seq, dim]
	flat := tensors.MustCopyFlatData[float32](hidden)
	nb, seq, dim := dims[0], dims[1], dims[2]
	var maxDiff, minCos float64 = 0, 1
	for i := range nb {
		pooled := make([]float64, dim)
		var cnt float64
		for t := range seq {
			if ref.Mask[i][t] == 0 {
				continue
			}
			cnt++
			for d := range dim {
				pooled[d] += float64(flat[(i*seq+t)*dim+d])
			}
		}
		var sq float64
		for d := range pooled {
			pooled[d] /= cnt
			sq += pooled[d] * pooled[d]
		}
		var dot float64
		for d := range pooled {
			pooled[d] /= math.Sqrt(sq)
			maxDiff = math.Max(maxDiff, math.Abs(pooled[d]-ref.Embeddings[i][d]))
			dot += pooled[d] * ref.Embeddings[i][d]
		}
		minCos = math.Min(minCos, dot)
	}
	var mean float64
	for _, t := range times {
		mean += t / float64(len(times))
	}
	out := map[string]any{
		"model": ref.Model, "backend": backend.Description(), "batch": nb, "tokens": seq, "dim": dim,
		"load_s": loadS, "max_abs_embedding_diff": maxDiff, "min_cosine": minCos,
		"forward_ms_mean": mean, "forward_ms_runs": times,
	}
	if *steps > 0 {
		out["finetune"] = finetune(backend, store, m, ref, types, *steps)
	}
	j, _ := json.MarshalIndent(out, "", " ")
	fmt.Println(string(j))
}

// finetune checks that gradients flow through the converted graph: mean-pooled encoder output,
// a linear head to 317 labels, binary cross-entropy against fixed pseudo-labels, AdamW on every
// encoder weight and the head. It reports the loss per step and the time per step.
func finetune(backend compute.Backend, store *model.Store, m onnx.Model, ref reference, types [][]int64, steps int) map[string]any {
	const nl = 317
	nb := len(ref.IDs)
	y := make([]float32, nb*nl)
	for i := range nb {
		y[i*nl+(i*37)%nl] = 1 // one fixed label per page: enough to see the loss fall
	}
	labels := tensors.FromFlatDataAndDimensions(y, nb, nl)
	modelFn := func(scope *model.Scope, spec any, inputs []*Node) []*Node {
		g := inputs[0].Graph()
		hidden := m.CallGraph(scope.In("encoder"), g, map[string]*Node{
			"input_ids": inputs[0], "attention_mask": inputs[1], "token_type_ids": inputs[2],
		})[0] // [b, seq, 384]
		mask := ConvertDType(InsertAxes(inputs[1], -1), hidden.DType())
		pooled := Div(ReduceSum(Mul(hidden, mask), 1), ReduceSum(mask, 1)) // [b, 384]
		head := scope.In("head")
		w := head.VariableWithShape("w", shapes.Make(hidden.DType(), 384, nl)).NodeValue(g)
		bias := head.VariableWithShape("b", shapes.Make(hidden.DType(), nl)).NodeValue(g)
		return []*Node{Add(MatMul(pooled, w), InsertAxes(bias, 0))}
	}
	lossFn := func(labels, predictions []*Node) *Node {
		return ReduceAllMean(loss.BinaryCrossentropyLogits(labels, predictions))
	}
	fs := model.NewStore()
	check(m.VariablesToScope(fs.RootScope().In("encoder")))
	trainer := train.NewTrainer(backend, fs, modelFn, lossFn,
		optimizer.Adam().LearningRate(3e-5).WeightDecay(0.01).Done(), nil, nil)
	var losses, times []float64
	for range steps {
		t := time.Now()
		metrics, err := trainer.TrainStep(train.Batch{
			Inputs: []*tensors.Tensor{tensors.FromValue(ref.IDs), tensors.FromValue(ref.Mask), tensors.FromValue(types)},
			Labels: []*tensors.Tensor{labels},
		})
		check(err)
		losses = append(losses, float64(tensors.ToScalar[float32](metrics[0])))
		times = append(times, time.Since(t).Seconds()*1000)
	}
	return map[string]any{"steps": steps, "loss_by_step": losses, "step_ms": times,
		"trainable_parameters": fs.NumParameters()}
}

func check(err error) {
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
