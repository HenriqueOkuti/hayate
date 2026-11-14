# Tier-1 latency v1 (W07, #8)

Run 2026-11-14 on commit `a787b0e`, model bundle `e12a016e` (tier1-v1 exported to CPU, see `scripts/export_tier1.py`). The numbers are in four files, written by `scripts/bench_tier1.py`: [local quiet](bench-tier1-v1-local-quiet.json), [small VPS quiet](bench-tier1-v1-vps-quiet.json), [local busy](bench-tier1-v1-local-busy.json) and [small VPS busy](bench-tier1-v1-vps-busy.json). Raw per-call timings are in `artifacts/bench/` (not committed). The method is [decision 0008](../docs/decisions/0008-reference-hardware.md).

**This is inference latency only:** extracted text to labels. Extraction (processing latency) and the fetch (request latency) are not included and are never added to these numbers.

## Setup

- **Hardware:** i7-13700F (AVX2, AVX-VNNI, no AVX-512) under WSL2. **Local:** one pinned logical CPU, no container. **Small VPS:** Docker with 2 CPUs (`--cpuset-cpus=0,1`, one core's two threads), 4 GB of memory, the inference pinned to one of them.
- **Threads:** 1 everywhere (`OMP_NUM_THREADS` and the BLAS pools, checked with threadpoolctl).
- **Model:** tier1-v1: 2^18 + 2^18 hashed features, 317 labels, float32, no quantization.
- **Inputs:** the 1,875 test pages, built like the training input and cut at 500, 1,000 or 3,000 characters of page text.
- **Method:** per configuration, 20 warm-up calls, then 3 trials of at least 2,000 pages (and at least 50 calls) each. Every call is timed per stage with `perf_counter_ns`. Percentiles are nearest-rank on the raw calls, divided by the batch size for per-page numbers.
- **Two conditions:** "busy" with Henrique's usual desktop apps open, then "quiet" with heavy apps closed (Steam idle in the background).

## Results (quiet)

Per page, p50 and p99 in milliseconds, small-VPS profile:

| Input | Batch 1 | Batch 8 | Batch 32 | Batch 128 |
| --- | --- | --- | --- | --- |
| 500 chars | 0.99 / 1.75 | 0.60 / 0.88 | 0.54 / 0.87 | 0.51 / 0.62 |
| 1,000 chars | 1.30 / 2.08 | 0.86 / 1.20 | 0.78 / 1.10 | 0.74 / 0.87 |
| 3,000 chars | 1.67 / 3.43 | 1.41 / 2.14 | 1.28 / 1.71 | 1.26 / 1.70 |

The local profile is within about 5% of these at every setting (for example 1.63 / 3.23 ms at 3,000 characters and batch 1). At 3,000 characters and batch 1 that is about 600 pages per second per thread.

**Where the time goes** (3,000 characters, batch 1, p50, small VPS): tokenization (hashing and TF-IDF) 1.24 ms, forward pass 0.40 ms, decision 0.02 ms. Tokenization is three quarters of the cost: scikit-learn's `char_wb` analyzer builds every character n-gram as a Python string. The forward pass gathers about 2,700 rows of a 665 MB weight matrix per page.

**Tier 1 is not sub-millisecond** at full input length, against the "well under 1 ms" expected in [models.md](../docs/models.md). It reaches about 0.5 ms per page only with short inputs (500 characters) in large batches.

## Busy against quiet

Closing heavy apps made every configuration faster by about 20% at both p50 and p99, in both profiles (range 12% to 34%). At 3,000 characters and batch 1 on the small VPS: 2.22 / 5.16 ms busy, 1.67 / 3.43 ms quiet.

- **The trial spread did not show it.** Within each run the three trials agreed closely (the p50 spread was usually under 50 microseconds per page busy and quiet alike), so a busy desktop slows every trial by the same amount. A run cannot tell on its own that it ran busy; it has to be compared with a known reference.
- **The forward pass suffers most:** 0.70 ms busy against 0.40 ms quiet locally (-42%), against -15% for tokenization. Gathering rows of a 665 MB matrix depends on cache and memory bandwidth, which other apps share.
- Whether the Windows power mode also changed between the runs was not recorded, so the difference is "heavy apps closed, possibly with the power mode".

## What next

- **Tokenization:** a compiled hashing tokenizer (Rust or Go, or a vectorized NumPy one) is the obvious win, since the model itself is cheap. The Go request path in Phase 2 needs one anyway.
- **Forward pass:** fewer hashed features, or int8 weights, would shrink the matrix and the cache misses.
- **Method:** each benchmark run should first time one reference configuration and compare it with the last quiet run, so a busy machine is caught (decision 0008).
