# Tier-1 latency in Go (#82)

Run 2026-11-14 on commit `6162ac9`, model bundle `e12a016e` (tier1-v1). The numbers are in [bench-tier1-go-local.json](bench-tier1-go-local.json) and [bench-tier1-go-vps.json](bench-tier1-go-vps.json), written by `go/cmd/tier1-bench`. The Python numbers they are compared with are the quiet runs in [bench-tier1-v1.md](bench-tier1-v1.md). [Decision 0012](../docs/decisions/0012-go-first.md) makes the Go numbers the ones on the trade-off curve.

**Inference latency only:** extracted text to labels, as for Python.

## Parity first

Before timing, `go/cmd/tier1-parity` ran the Go implementation on all 1,875 test pages against the Python reference (`scripts/tier1_reference.py`). Every page got the same input string, the same feature indices, bit-identical feature values, probabilities within 1.2e-7 (float32 rounding) and the same labels. So the Go and Python numbers below time the same function.

## Setup

- **Same method as Python:** per configuration, 20 warm-up calls, then 3 trials of at least 2,000 pages (and at least 50 calls) each; every call timed per stage; nearest-rank percentiles on the raw calls.
- **One thread:** `GOMAXPROCS=1`, and the timing goroutine locked to an OS thread pinned to one CPU (2 locally, 0 in the container). Only that thread is pinned; Go's runtime threads can still run on the container's second CPU.
- **Local:** Go 1.27.1. **Small VPS:** Docker, 2 CPUs (`--cpuset-cpus=0,1`), 4 GB, a static binary built with Go 1.27.4 (the `golang:1.27` image).
- **Code:** featurizing hashes each n-gram in place from byte ranges (no string per n-gram) into a reused count array; the forward pass adds one weight row per feature with gonum's assembly `Axpy`.
- **Machine:** heavy apps closed, as for the Python quiet run. No reference check was built yet (decision 0008), so the two runs are comparable only as far as the desktop stayed equally quiet.

## Results

Per page, p50 / p99 in milliseconds, small-VPS profile:

| Input | Batch 1 | Batch 8 | Batch 32 | Batch 128 |
| --- | --- | --- | --- | --- |
| 500 chars | 0.27 / 0.61 | 0.27 / 0.45 | 0.28 / 0.43 | 0.25 / 0.33 |
| 1,000 chars | 0.43 / 0.79 | 0.39 / 0.64 | 0.41 / 0.64 | 0.38 / 0.60 |
| 3,000 chars | 0.62 / 1.75 | 0.65 / 1.06 | 0.62 / 0.83 | 0.57 / 0.72 |

Local p50 numbers are within 15% of these, and p99 up to about 50% apart (3,000 characters, batch 8: 1.59 ms locally, 1.06 ms on the small VPS). Against the quiet Python runs at the same settings, Go is 1.9 to 3.6 times faster at p50 on the small-VPS profile and 1.5 to 3.3 times locally, most at batch 1 and short inputs. The Python and Go runs were about 20 minutes apart with no reference check, and closing apps alone moved Python's p50 by 12 to 27%, so the ratios carry about that much uncertainty.

Per-page numbers at batch 8 and above are per-call times divided by the batch size: a page in a batch of 128 waits for the whole call.

**Where the time goes** (3,000 characters, batch 1, p50): featurizing 0.26 ms (Python 1.24 ms), forward pass 0.35 ms (Python 0.40 ms), decision under 0.01 ms. The forward pass is now the larger part: it reads about 2,700 rows of 317 floats from a 665 MB matrix per page, so memory access bounds it.

**Tier 1 is sub-millisecond at p50** in every configuration (at most 0.72 ms), and measured throughput at full input length and batch 1 is about 1,450 pages per second per thread (mean, not 1/p50). The p99 at batch 1 and 3,000 characters (1.75 ms) is a long tail, likely garbage collection and the longest pages.

## What next

- **Forward pass:** fewer hashed features or int8 weights would shrink the matrix and its cache misses.
- **Tail:** measure with `GOGC=off` or a memory limit to see how much of p99 is the garbage collector.
- **Reference check:** each run should first time one fixed configuration and compare it with the last quiet run (decision 0008). Done in [#84](https://github.com/HenriqueOkuti/hayate/issues/84); the runs here seeded `results/bench-reference.json`.
