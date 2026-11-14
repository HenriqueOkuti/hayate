# Tier-1 tail and forward pass in Go (#85)

Run 2026-11-14 on commit `473f03c` (the grid and the GC runs) and `2cddf9a` (the allocating-path run), with `go/cmd/tier1-bench`, the method of [bench-tier1-go.md](bench-tier1-go.md) and [decision 0008](../docs/decisions/0008-reference-hardware.md). Every run times the busy-machine reference on the tier1-v2 float bundle (`-reference-bundle`), so all runs share one baseline; every result here passed it, and the runs it flagged busy were rerun. Inference latency only: extracted text to labels.

Four bundles, all with the [tier1-v2](tier1-v2.md) training procedure:

| Bundle | Features | Weights | Val Tier-2 F1 vs float v2, paired | Test Tier-2 F1 |
| --- | --- | --- | --- | --- |
| tier1-v2, float32 | 2^18 + 2^18 | 665 MB | | 0.481 |
| tier1-v2, int8 | 2^18 + 2^18 | 166 MB | -0.001 (-0.002 to 0.000) | 0.481 |
| tier1-v2-17, float32 | 2^17 + 2^17 | 332 MB | 0.000 (-0.005 to 0.006) | 0.478 |
| tier1-v2-17, int8 | 2^17 + 2^17 | 83 MB | 0.000 against its float bundle | 0.478 |

- **tier1-v2-17** is retrained with the Go trainer at the smaller size and tuned like v2 ([tier1-v2-17.json](tier1-v2-17.json), [compare-tier1-v2-17-v2.json](compare-tier1-v2-17-v2.json)). Val cross-fitted Tier-2 F1 0.493 (v2: 0.486); on test the paired difference is -0.003 (-0.009 to 0.003). Halving the hashed features costs nothing measurable.
- **int8** is a conversion, not a retrain (`scripts/quantize_tier1.py`): symmetric per-row int8 with one scale per feature row, scored with the float bundle's temperature and thresholds. On val 1,929 of 1,933 pages keep exactly their labels for v2 and 1,931 for v2-17; the largest probability difference is 0.0015 ([tier1-v2-int8.json](tier1-v2-int8.json), [tier1-v2-17-int8.json](tier1-v2-17-int8.json)).
- **Parity:** `go/cmd/tier1-parity` gives the same input, feature indices and labels as Python on all 1,875 test pages for all four bundles (probabilities within 3.6e-7).

## The tail is the pages, not the garbage collector

- **No GC runs while timing.** Each configuration now records allocations and GC cycles: 0 cycles in every configuration of every bundle with buffer reuse, and on the allocating path 0 at batch 1 to 32 and 1 to 2 cycles at batch 128. The weight matrix sets the heap goal far above what a benchmark allocates.
- **GOGC=off and a memory limit** (1,500 MiB) on tier1-v2-17 at 3,000 characters and batch 1: p99 1.88 and 1.39 ms, against 1.37 ms with the default ([gcoff](bench-tier1-go-v2-17-gcoff-local.json), [memlimit](bench-tier1-go-v2-17-memlimit-local.json), [default](bench-tier1-go-v2-17-local.json)). With no GC in any of them, the spread is run-to-run noise in p99, which the p50-based reference check does not watch.
- **The slow calls are the same pages every time.** In a scratch run of tier1-v2 (raw timings, not committed), the slowest 1% of calls at 3,000 characters took about 2.6 times longer to featurize and 3.2 times longer in the forward pass than the rest. A page's median time and its worst time correlate at 0.96 across repeats, and the 99th percentile of per-page medians alone is 1.44 ms, close to the 1.48 ms p99 of all calls. The tail is a few pages with many distinct n-grams, so more features to hash and more weight rows to read.

## Allocations

`FeaturizeInto` and `DecideInto` reuse the caller's slices and the model's scratch (lowercased input, token spans, values, label indices), and a test checks that a warm model allocates nothing per page. Against the allocating path on tier1-v2 ([bench-tier1-go-v2-alloc-local.json](bench-tier1-go-v2-alloc-local.json), `-reuse=false`): 5.5 allocations per page fall to 0.2 (the harness's own buffers growing), and latency moves by 1 to 3%, within run-to-run noise. Worth keeping for a server that runs many pages, but not a latency lever here.

## Results

Per page, p50 / p99 in milliseconds, small-VPS profile (local in the JSON files):

| Bundle | 500 chars, batch 1 | 1,000 chars, batch 1 | 3,000 chars, batch 1 | 3,000 chars, batch 32 |
| --- | --- | --- | --- | --- |
| tier1-v2, float32 | 0.30 / 0.79 | 0.45 / 1.02 | 0.59 / 1.62 | 0.62 / 0.93 |
| tier1-v2, int8 | 0.31 / 0.71 | 0.48 / 0.95 | 0.66 / 1.84 | 0.69 / 0.94 |
| tier1-v2-17, float32 | 0.24 / 0.77 | 0.40 / 0.98 | 0.51 / 1.34 | 0.54 / 0.76 |
| tier1-v2-17, int8 | 0.28 / 0.64 | 0.43 / 0.81 | 0.59 / 1.58 | 0.64 / 0.89 |

Files: `bench-tier1-go-<bundle>-<profile>.json` with bundle `v2`, `v2-int8`, `v2-17`, `v2-17-int8` and profile `local` or `vps`.

**Where the time goes** (3,000 characters, batch 1, p50, small VPS): featurizing 241 us for v2 and 204 us for v2-17, forward pass 350 us and 300 us. Both stages gain from the smaller model: the forward pass reads rows of a matrix half the size, and the featurizer's dense count array is half the size too.

**int8 is slower, not faster.** Its forward pass takes 441 us against 350 us for float32 (v2), although it reads a quarter of the bytes. The int8 rows are converted to float one value at a time in plain Go, while the float32 path uses gonum's assembly `Axpy`; the conversion costs more than the memory traffic it saves. An int8 kernel in assembly, or Go's SIMD package once it is stable, could change that; it would need its own parity check.

## Verdict

**tier1-v2-17 (float32) is the tier-1 build on the curve:** the same quality as tier1-v2 on val, 0.51 ms p50 and 1.34 ms p99 per page at 3,000 characters and batch 1 on the small-VPS profile (13% and 17% better than v2), and half the memory. int8 stays out until it has a vectorized kernel. The p99 tail is set by a few heavy pages; cutting it further means capping the work per page (fewer characters, or a cap on distinct n-grams), which changes the model and would need its own F1 check.
