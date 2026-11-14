// Command tier1-parity checks the Go tier-1 implementation against the Python reference.
//
//	go run ./cmd/tier1-parity -bundle ../artifacts/tier1-v1/cpu
//
// It reads reference-test.jsonl (written by scripts/tier1_reference.py) and, for every page,
// rebuilds the input string from its parts, featurizes it, runs the forward pass and decides the
// labels, then compares each step with Python's. It prints a JSON summary and exits non-zero if
// any page differs in its input string, feature indices or labels, or if a feature value or
// probability differs by more than the tolerance.
package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"slices"

	"github.com/HenriqueOkuti/hayate/go/tier1"
)

type refPage struct {
	PageID      string    `json:"page_id"`
	URL         string    `json:"url"`
	Title       string    `json:"title"`
	Description string    `json:"description"`
	Text        string    `json:"text"`
	Input       string    `json:"input"`
	Indices     []int32   `json:"indices"`
	Values      []float32 `json:"values"`
	Prob        []float32 `json:"prob"`
	Labels      []string  `json:"labels"`
}

type mismatch struct {
	PageID string `json:"page_id"`
	Step   string `json:"step"`
	Detail string `json:"detail"`
}

func main() {
	bundle := flag.String("bundle", "../artifacts/tier1-v1/cpu", "tier-1 CPU bundle")
	ref := flag.String("ref", "", "reference jsonl (default: <bundle>/reference-test.jsonl)")
	tol := flag.Float64("tol", 1e-5, "max abs difference for feature values and probabilities")
	show := flag.Int("show", 5, "mismatches to print")
	flag.Parse()
	if *ref == "" {
		*ref = filepath.Join(*bundle, "reference-test.jsonl")
	}
	m, err := tier1.Load(*bundle)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	f, err := os.Open(*ref)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 64<<20), 64<<20)

	var pages, sameInput, sameIdx, sameLabels int
	var maxVal, maxProb float64
	var bad []mismatch
	prob := make([]float32, 0, len(m.Labels))
	for sc.Scan() {
		var r refPage
		if err := json.Unmarshal(sc.Bytes(), &r); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(2)
		}
		pages++
		in := tier1.PageInput(r.URL, r.Title, r.Description, r.Text, m.MaxChars)
		if in == r.Input {
			sameInput++
		} else {
			bad = append(bad, mismatch{r.PageID, "input", firstDiff(in, r.Input)})
		}
		x := m.Featurize(r.Input) // featurize Python's input, so later steps are compared alone
		refIdx := slices.Clone(r.Indices)
		order := argsort(refIdx)
		if slices.Equal(x.Idx, sortedBy(refIdx, order)) {
			sameIdx++
			refVal := sortedVals(r.Values, order)
			for k := range x.Val {
				maxVal = math.Max(maxVal, math.Abs(float64(x.Val[k]-refVal[k])))
			}
		} else {
			bad = append(bad, mismatch{r.PageID, "features",
				fmt.Sprintf("%d indices in Go, %d in Python", len(x.Idx), len(r.Indices))})
		}
		prob = m.Forward(x, prob)
		for j := range prob {
			maxProb = math.Max(maxProb, math.Abs(float64(prob[j]-r.Prob[j])))
		}
		labels := m.Decide(prob)
		if slices.Equal(labels, r.Labels) || (len(labels) == 0 && len(r.Labels) == 0) {
			sameLabels++
		} else {
			bad = append(bad, mismatch{r.PageID, "labels", fmt.Sprintf("go %v python %v", labels, r.Labels)})
		}
	}
	if err := sc.Err(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	ok := sameInput == pages && sameIdx == pages && sameLabels == pages && maxVal <= *tol && maxProb <= *tol
	out := map[string]any{
		"pages": pages, "same_input": sameInput, "same_feature_indices": sameIdx,
		"same_labels": sameLabels, "max_abs_feature_diff": maxVal, "max_abs_prob_diff": maxProb,
		"tolerance": *tol, "ok": ok, "mismatches": bad[:min(*show, len(bad))],
		"mismatch_count": len(bad),
	}
	b, _ := json.MarshalIndent(out, "", " ")
	fmt.Println(string(b))
	if !ok {
		os.Exit(1)
	}
}

func argsort(v []int32) []int {
	idx := make([]int, len(v))
	for i := range idx {
		idx[i] = i
	}
	slices.SortFunc(idx, func(a, b int) int { return int(v[a]) - int(v[b]) })
	return idx
}

func sortedBy(v []int32, order []int) []int32 {
	out := make([]int32, len(order))
	for k, i := range order {
		out[k] = v[i]
	}
	return out
}

func sortedVals(v []float32, order []int) []float32 {
	out := make([]float32, len(order))
	for k, i := range order {
		out[k] = v[i]
	}
	return out
}

func firstDiff(a, b string) string {
	ra, rb := []rune(a), []rune(b)
	for i := 0; i < min(len(ra), len(rb)); i++ {
		if ra[i] != rb[i] {
			lo := max(0, i-10)
			return fmt.Sprintf("at rune %d: go %q python %q", i, string(ra[lo:min(len(ra), i+10)]),
				string(rb[lo:min(len(rb), i+10)]))
		}
	}
	return fmt.Sprintf("lengths %d and %d", len(ra), len(rb))
}
