# Tier-1 tail and forward pass in Go (#85)

Run 2026-11-14 on commit `787c275`, with `go/cmd/tier1-bench` built fresh for the set, the method of [bench-tier1-go.md](bench-tier1-go.md) and [decision 0008](../docs/decisions/0008-reference-hardware.md). Every run times the busy-machine reference on the tier1-v2 float bundle (`-reference-bundle`), so all runs in a profile are judged under one baseline key. Locally its stored value moved twice as quieter readings came in (559, 553, then 545 us); on the small-VPS profile it stayed the seed reading (555 us). In each profile a first v2 run seeded the baseline and was discarded; the v2 run recorded here is a second one, judged against it like every other run. All recorded runs passed the check (slowdowns from -1.4% to +8.6%, in each file's `reference` block). Five attempts were flagged busy (13 to 20% slower) and rerun a minute later; those attempts are not committed. Inference latency only: extracted text to labels.

Four bundles, all with the [tier1-v2](tier1-v2.md) training procedure:

| Bundle | Features | Weights | Val Tier-2 F1 against float v2, paired |
| --- | --- | --- | --- |
| tier1-v2, float32 | 2^18 + 2^18 | 665 MB | |
| tier1-v2, int8 | 2^18 + 2^18 | 166 MB | -0.001 (-0.002 to 0.000) |
| tier1-v2-17, float32 | 2^17 + 2^17 | 332 MB | 0.000 (-0.005 to 0.006) |
| tier1-v2-17, int8 | 2^17 + 2^17 | 83 MB | 0.000 against its own float bundle |

- **tier1-v2-17** is retrained with the Go trainer at the smaller size and tuned like v2 ([tier1-v2-17.json](tier1-v2-17.json), [compare-tier1-v2-17-v2.json](compare-tier1-v2-17-v2.json)). On val, its cross-fitted Tier-2 F1 is 0.493 (v2: 0.486), and the paired difference above is 0.000; both runs' val predictions use thresholds fitted on val, so the pairing is in-sample on both sides alike. Halving the hashed features costs nothing measurable on val. Test, reported after the choice: 0.478 against 0.481, paired -0.003 (-0.009 to 0.003).
- **int8** is a conversion, not a retrain (`scripts/quantize_tier1.py`): symmetric per-row int8 with one scale per feature row, scored with the float bundle's temperature and thresholds. On val 1,929 of 1,933 pages keep exactly their labels for v2 and 1,931 for v2-17; the largest probability difference is 0.0015 ([tier1-v2-int8.json](tier1-v2-int8.json), [tier1-v2-17-int8.json](tier1-v2-17-int8.json)). That check uses the Python loader, which dequantizes; the Go int8 kernel is checked by parity below.
- **Parity** ([tier1-bundles-parity.json](tier1-bundles-parity.json)): `go/cmd/tier1-parity` gives the same input, feature indices and labels as Python on all 1,875 test pages for all four bundles, probabilities within 3.6e-7 (int8 included, so the Go int8 kernel matches the dequantized Python model).

## The tail is the pages, not the garbage collector

- **No GC runs while timing.** Each configuration now records allocations and GC cycles. With buffer reuse there are 0 cycles in every configuration of every bundle; on the allocating path, 0 at batches 1 to 32 and 1 or 2 at batch 128. The weight matrix sets the heap goal far above what a benchmark allocates.
- **GOGC=off and a memory limit** (1,500 MiB) on tier1-v2-17, local profile, 3,000 characters, batch 1: p99 1.61 and 1.38 ms, against 1.33 ms with the default ([gcoff](bench-tier1-go-v2-17-gcoff-local.json), [memlimit](bench-tier1-go-v2-17-memlimit-local.json), [default](bench-tier1-go-v2-17-local.json)). With 0 GC cycles in all three, the settings cannot be the cause: the GC-off run's three trials ranged from 1.41 to 1.86 ms at p99, so one trial was disturbed mid-grid, which the before-and-after reference cannot see.
- **The slow calls are the same pages every time.** In a scratch run of tier1-v2 (local profile, raw timings not committed), the slowest 1% of calls at 3,000 characters took about 2.6 times longer to featurize and 3.2 times longer in the forward pass than the rest. A page's median time and its worst time correlated at 0.96 across repeats, and the 99th percentile of per-page medians alone was 1.44 ms, close to that run's call p99. The tail is a few pages with many distinct n-grams, so more features to hash and more weight rows to read.

## Allocations

`FeaturizeInto` and `DecideInto` reuse the caller's slices and the model's scratch (lowercased input, token spans, values, label indices), and a test checks that a warm model allocates nothing per page. Against the allocating path on tier1-v2 ([bench-tier1-go-v2-alloc-local.json](bench-tier1-go-v2-alloc-local.json), `-reuse=false`, against [bench-tier1-go-v2-local.json](bench-tier1-go-v2-local.json)), 5.4 to 5.6 allocations per page fall to 0.1 to 0.4 (the harness's own buffers growing). Latency shows no resolvable gain: relative to the allocating path, the reuse path's p50 ranges from -3% to +10% and its p99 from -11% to +30% across the configurations, with no pattern, and the two runs' reference readings differ by about 3%. Worth keeping for a server, but not a latency lever.

## Results

Per page, p50 / p99 in milliseconds, small-VPS profile:

| Bundle | 500 chars, batch 1 | 1,000 chars, batch 1 | 3,000 chars, batch 1 | 3,000 chars, batch 32 |
| --- | --- | --- | --- | --- |
| tier1-v2, float32 | 0.26 / 0.60 | 0.42 / 0.76 | 0.56 / 1.41 | 0.59 / 0.81 |
| tier1-v2, int8 | 0.31 / 0.64 | 0.48 / 0.89 | 0.66 / 1.73 | 0.72 / 1.18 |
| tier1-v2-17, float32 | 0.25 / 0.58 | 0.38 / 0.77 | 0.52 / 1.40 | 0.54 / 0.78 |
| tier1-v2-17, int8 | 0.29 / 0.67 | 0.46 / 0.89 | 0.60 / 1.48 | 0.65 / 0.82 |

Local profile, same columns: v2 0.27 / 0.59, 0.45 / 1.05, 0.57 / 1.51, 0.60 / 0.86; v2-17 0.23 / 0.53, 0.38 / 0.70, 0.50 / 1.33, 0.55 / 0.70. Files: `bench-tier1-go-<bundle>-<profile>.json` with bundle `v2`, `v2-int8`, `v2-17`, `v2-17-int8` and profile `local` or `vps`.

**tier1-v2-17 against v2** at 3,000 characters and batch 1: 12% faster at both p50 and p99 locally, where the two runs' reference readings agree. On the small-VPS profile the grid says 7% at p50, but that run of v2 read its reference about 4% slower than the v2-17 run did; scaled by each run's own reference the gain is about 3%, within machine-state noise. Read it as "somewhat faster and half the memory", not as a precise gain. Both stages contribute (small VPS, p50): featurizing 213 against 230 us, since the dense count array is half the size, and the forward pass 308 against 326 us.

**int8 is slower, not faster.** Its forward pass is slower in every configuration: 431 against 326 us for v2 and 406 against 308 us for v2-17 (small VPS, 3,000 characters, batch 1), although it reads a quarter of the bytes. The likely reason, not measured with a separate kernel benchmark: the int8 rows are converted to float in a scalar loop (unrolled four ways), while the float32 path uses gonum's assembly `Axpy`. A vectorized int8 kernel, in assembly or with Go's SIMD package once it is stable, could change that, and would need its own parity check.

## Verdict

**tier1-v2-17 (float32) is the tier-1 build on the curve:** the same quality as tier1-v2 on val, somewhat faster (12% locally; 0.52 ms p50 and 1.40 ms p99 per page at 3,000 characters and batch 1 on the small-VPS profile, a few percent there) and half the memory. int8 stays out until it has a vectorized kernel. The p99 tail is set by a few heavy pages; cutting it further means capping the work per page (fewer characters, or a cap on distinct n-grams), which changes the model and needs its own F1 check.

Not recorded here: the Go and GoMLX versions used for training (the trainer's `train.json` records the backend, not the versions), and the Go harness's dirty check covers `go/` only.
