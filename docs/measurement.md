# Measurement: quality, speed, cost

## Quality

**References:**

| Comparison | What it tells us |
| --- | --- |
| Student vs teacher (held-out split) | Distillation loss |
| Student vs human-checked sample | Real quality |
| Teacher vs human | Teacher label noise |
| Teacher vs teacher (repeated runs) | Teacher self-consistency |

**Splits:**

- Split **by domain**, so near-duplicate pages can't leak between train and
  test. A by-page split is reported alongside for comparison.
- Thresholds and calibration are tuned on validation, never on test.

**Metrics:**

- Micro, macro and **per-category F1** (with support counts).
- Flat F1 at Tier 1 and at Tier 2, plus hierarchical P/R/F (labels expanded
  with their ancestors).
- Per-category ECE and Brier score, with the binning reported. Try
  temperature scaling first.
- Per-category thresholds tuned on validation. Watch rare labels, where
  "always positive" can game F1.

**Human-checked sample:**

- Start with ~300 pages, stratified by language and Tier 1.
- The reviewer accepts or corrects the teacher's labels.
- A small subset is labeled **blind** to measure anchoring on the teacher's
  answer.
- Keep the reviewer's decisions alongside the teacher output.

## Speed

Three numbers are **never merged**:

1. **Inference:** extracted text → scores, split into tokenization and the
   forward pass.
2. **Processing:** HTML → scores (adds extraction).
3. **Request:** request → response (adds the fetch).

**Micro-benchmarks:**

- Warm up first, keep raw per-call timings (`perf_counter_ns`), and report
  p50/p90/p99/max. pytest-benchmark has no p99, so dump its raw data.
- Fix threads explicitly (`OMP_NUM_THREADS`, ORT `intra_op_num_threads`) and
  pin CPUs.
- Sweep the batch size (1, 8, 32, 128) and the input length.
- Run several trials and report the spread.

**Request benchmarks:**

- Use open-model, constant-rate load (`wrk2 -R`, k6 arrival-rate) to avoid
  coordinated omission.
- Report latency vs offered load as a curve.

**Every result records:**

- CPU model and ISA flags, cores vs threads, OS;
- runtime versions, quantization and thread settings;
- model hash, taxonomy SHA, truncation and batch size.

### Local setup (no cloud needed)

Host: i7-13700F (24 threads, AVX2 + AVX-VNNI, **no AVX-512/AMX**), 23 GB RAM,
RTX 4070 SUPER, under WSL2. Docker and `/dev/kvm` are available.

- **"Small VPS" profile:**

  ```bash
  docker run --cpuset-cpus=0,1 --cpus=2 --memory=4g --memory-swap=4g …
  ```

  This approximates a c7i.large. `0,1` gives two threads sharing one core
  (like AWS SMT vCPUs); `0,2` gives two separate cores.
- **Network:** local replay server plus `tc netem` delay and loss inside the
  container network. Run the load generator pinned to different CPUs.
- **WSL2 caveats:**
  - Windows schedules the vCPUs onto P-cores *or* E-cores, and the CPU
    frequency can't be locked.
  - Close heavy apps and use the "Best performance" power mode.
  - For clean headline numbers, boot native Linux.
- Local results are labeled "per core on i7-13700F/WSL2". **Relative**
  comparisons between students carry over to the cloud. Absolute cost needs
  one calibration run.

## Cost

```text
cost_per_M_pages = price_per_hour / (measured_pages_per_s × 3600 / 1e6)
```

On-demand and spot prices are reported separately, and teacher and fetch
costs are listed apart from inference.

Reference prices (us-east-1, 2026-10-07, on-demand $/h):

| Instance | Hardware | On-demand $/h |
| --- | --- | --- |
| c7i.large | 2 vCPU, Sapphire Rapids | 0.0893 |
| c8g.large | 2 vCPU, Graviton4 | 0.0798 |
| g6.xlarge | 1× L4 | 0.805 |

This is a snapshot of AWS list prices. **Re-check them against the public
pricing pages before use.**

As an illustration: 1 ms/page on 2 threads works out to about $0.012 per
million pages on-demand.

The optional calibration run uses a few hours of spot time on a **personal**
account and costs under $1.
