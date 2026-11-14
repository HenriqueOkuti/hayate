"""Micro-benchmarks: raw per-call stage timings, then percentiles (docs/measurement.md).

`time_stages` runs a pipeline of stages on batches of inputs and keeps every call's time per
stage in nanoseconds (`perf_counter_ns`), after a warm-up. `summarize` turns raw rows into
p50/p90/p99/max per call and per page, throughput, and the spread over trials. Percentiles use
the nearest-rank method on the raw values, never on means.
"""

import os
import platform
import time
from collections.abc import Callable, Sequence
from pathlib import Path

Stage = tuple[str, Callable]


def time_stages(
    stages: Sequence[Stage], inputs: Sequence, batch: int, calls: int, warmup: int, start: int = 0
) -> list[dict]:
    """Time `calls` batches of `batch` inputs (cycling through `inputs` from `start`).

    Each stage gets the previous stage's output; the first gets the list of inputs. Returns one
    row per timed call: {"call", "ns_<stage>", "ns_total"}.
    """
    n = len(inputs)
    rows = []
    for call in range(-warmup, calls):
        k = (start + (call + warmup) * batch) % n
        x = [inputs[(k + i) % n] for i in range(batch)]
        row = {"call": call}
        t_all = time.perf_counter_ns()
        for name, fn in stages:
            t0 = time.perf_counter_ns()
            x = fn(x)
            row[f"ns_{name}"] = time.perf_counter_ns() - t0
        row["ns_total"] = time.perf_counter_ns() - t_all
        if call >= 0:
            rows.append(row)
    return rows


def percentile(values: Sequence[float], q: float) -> float:
    """Nearest-rank percentile (q in 0..100) of the raw values."""
    s = sorted(values)
    if not s:
        return float("nan")
    k = max(0, min(len(s) - 1, int(-(-q * len(s) // 100)) - 1))
    return float(s[k])


def summarize(rows: list[dict], batch: int, stage_names: Sequence[str]) -> dict:
    """Percentiles in microseconds per call and per page, for the total and each stage."""
    out = {"calls": len(rows), "batch": batch}
    for name in [*stage_names, "total"]:
        v = [r[f"ns_{name}"] / 1000 for r in rows]
        stats = {f"p{q}": round(percentile(v, q), 2) for q in (50, 90, 99)}
        stats["max"] = round(max(v), 2)
        stats["mean"] = round(sum(v) / len(v), 2)
        out[f"us_per_call_{name}"] = stats
        out[f"us_per_page_{name}"] = {k: round(x / batch, 2) for k, x in stats.items()}
    out["pages_per_s"] = round(batch / (out["us_per_call_total"]["mean"] / 1e6), 1)
    return out


def cpu_info() -> dict:
    model, flags = platform.processor(), set()
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text().splitlines():
            if line.startswith("model name"):
                model = line.split(":", 1)[1].strip()
            elif line.startswith("flags"):
                flags = set(line.split(":", 1)[1].split())
    isa = ("sse4_2", "avx", "avx2", "fma", "avx_vnni", "avx512f", "avx512_vnni", "amx_tile")
    return {
        "model": model,
        "isa": sorted(f for f in isa if f in flags),
        "logical_cpus": os.cpu_count(),
        "affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
        "os": platform.platform(),
        "wsl": "microsoft" in platform.release().lower(),
    }
