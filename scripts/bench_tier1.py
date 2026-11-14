"""Benchmark tier-1 inference latency: tokenization, forward pass and decision, timed apart.

Usage (local, one pinned thread):
  uv run python scripts/bench_tier1.py --name tier1-v1-local --bundle artifacts/tier1-v1/cpu \
      --profile local --cpus 2

Small-VPS profile (2 threads on one core, 4 GB; see docs/measurement.md and docker/bench):
  make bench-vps

Measures *inference* only (extracted text to labels), never processing or request latency. The
inputs are test pages of the component split, built exactly like the training input and cut to
each --max-chars; the page text never leaves the machine. For every (input length, batch size)
and trial: a warm-up, then raw per-call timings. Writes the raw timings to
artifacts/bench/<name>.parquet and results/<name>.json with percentiles per call and per page,
throughput, the spread over trials, and the environment (CPU model and ISA flags, affinity,
threads, versions, model hash, taxonomy SHA).

Before and after the grid it times one fixed reference configuration and compares it with the
last quiet reading in results/bench-reference.json (hayate.bench.reference, shared with the Go
harness); a run more than 10% slower is marked busy. --accept-reference stores the reading anyway.
"""

import os

THREAD_VARS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")
for _v in THREAD_VARS:  # before numpy is imported, so its thread pools start at this size
    os.environ.setdefault(_v, os.environ.get("BENCH_THREADS", "1"))

import argparse  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import platform  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

import duckdb  # noqa: E402
import numpy as np  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
import scipy  # noqa: E402
import sklearn  # noqa: E402
from threadpoolctl import threadpool_info, threadpool_limits  # noqa: E402

from hayate import provenance  # noqa: E402
from hayate.bench import reference  # noqa: E402
from hayate.bench.micro import cpu_info, percentile, summarize, time_stages  # noqa: E402
from hayate.students.features import page_input  # noqa: E402
from hayate.students.hashed_infer import Tier1  # noqa: E402
from hayate.teacher import claude  # noqa: E402

STAGES = ("featurize", "forward", "decide")


def bundle_sha256(path: Path) -> str:
    h = hashlib.sha256()
    for name in ("weights.npy", "bias.npy", "meta.json"):
        h.update((path / name).read_bytes())
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--name", required=True)
    ap.add_argument("--bundle", type=Path, default=Path("artifacts/tier1-v1/cpu"))
    ap.add_argument("--profile", required=True, help="label: local, vps-docker, ...")
    ap.add_argument("--cpus", type=int, nargs="*", help="pin to these logical CPUs")
    ap.add_argument("--threads", type=int, default=int(os.environ.get("BENCH_THREADS", "1")))
    ap.add_argument("--batches", type=int, nargs="+", default=[1, 8, 32, 128])
    ap.add_argument("--max-chars", type=int, nargs="+", default=[500, 1000, 3000])
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--pages-per-config", type=int, default=2000, help="timed pages per trial")
    ap.add_argument("--min-calls", type=int, default=50)
    ap.add_argument("--warmup", type=int, default=20)
    ap.add_argument("--pages", type=Path, default=Path("data/pages/pages.parquet"))
    ap.add_argument("--splits", type=Path, default=Path("data/splits/splits-v1.parquet"))
    ap.add_argument("--out-dir", type=Path, default=Path("results"))
    ap.add_argument("--raw-dir", type=Path, default=Path("artifacts/bench"))
    ap.add_argument("--reference", type=Path, help=f"default <out-dir>/{reference.FILE}")
    ap.add_argument("--accept-reference", action="store_true", help="store the reading if busy")
    args = ap.parse_args()

    if args.cpus:
        os.sched_setaffinity(0, set(args.cpus))
    meta = json.loads((args.bundle / "meta.json").read_text())
    model = Tier1.load(args.bundle)
    rows = duckdb.sql(
        f"""select p.page_id, p.url, coalesce(p.title, ''), coalesce(p.meta_description, ''),
                   {claude.text_sql(meta["input"])}
            from '{args.pages}' p join '{args.splits}' s using (page_id)
            where s.split = 'test' order by p.page_id"""
    ).fetchall()
    stages = [
        ("featurize", model.featurize),
        ("forward", model.forward),
        ("decide", model.decide),
    ]

    ref_docs = [page_input(r[1], r[2], r[3], r[4], reference.MAX_CHARS) for r in rows]

    def time_reference(when: str) -> dict:
        timed = time_stages(stages, ref_docs, reference.BATCH, reference.CALLS, args.warmup)
        tot = summarize(timed, reference.BATCH, STAGES)["us_per_page_total"]
        reading = {"p50_us_per_page": tot["p50"], "p99_us_per_page": tot["p99"]}
        print(
            f"reference (chars {reference.MAX_CHARS} batch {reference.BATCH}) {when}: per page "
            f"p50 {tot['p50']:8.1f} us p99 {tot['p99']:8.1f} us"
        )
        return reading

    raw, configs = [], []
    with threadpool_limits(args.threads):
        before = time_reference("before")
        pools = [
            {k: p.get(k) for k in ("user_api", "internal_api", "num_threads")}
            for p in threadpool_info()
        ]
        for max_chars in args.max_chars:
            docs = [page_input(r[1], r[2], r[3], r[4], max_chars) for r in rows]
            for batch in args.batches:
                calls = max(args.min_calls, args.pages_per_config // batch)
                trials = []
                for trial in range(args.trials):
                    timed = time_stages(stages, docs, batch, calls, args.warmup, start=trial * 997)
                    for r in timed:
                        raw.append({"max_chars": max_chars, "batch": batch, "trial": trial, **r})
                    trials.append(summarize(timed, batch, STAGES))
                pooled = summarize(
                    [r for r in raw if r["max_chars"] == max_chars and r["batch"] == batch],
                    batch,
                    STAGES,
                )
                per_trial = [t["us_per_page_total"] for t in trials]
                configs.append(
                    {
                        "max_chars": max_chars,
                        **pooled,
                        "trial_spread_us_per_page": {
                            q: [min(t[q] for t in per_trial), max(t[q] for t in per_trial)]
                            for q in ("p50", "p99")
                        },
                    }
                )
                tot = pooled["us_per_page_total"]
                print(
                    f"chars {max_chars:5d} batch {batch:3d}: per page p50 {tot['p50']:8.1f} us "
                    f"p99 {tot['p99']:8.1f} us, {pooled['pages_per_s']:9.1f} pages/s"
                )
        after = time_reference("after")

    stamp = provenance.stamp(
        {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}, "bench_tier1"
    )
    sha = bundle_sha256(args.bundle)
    args.out_dir.mkdir(exist_ok=True)
    ref = reference.check(
        args.reference or args.out_dir / reference.FILE,
        reference.key("python", args.profile, sha),
        before,
        after,
        args.accept_reference,
        stamp["created"],
        stamp["commit"],
        f"{args.name}.json",
    )
    if ref["status"] == "busy":
        print(
            f"WARNING: reference {ref['slowdown']:.0%} slower than the last quiet run "
            f"({ref['baseline']['source']}, {ref['baseline']['created']}): the machine looks "
            "busy; this result is marked busy. Close heavy apps and rerun.",
            file=sys.stderr,
        )
    elif ref["status"] == "no-baseline":
        print(
            "note: no quiet reference stored for this profile and bundle yet; this run's "
            "reading is now the baseline",
            file=sys.stderr,
        )
    else:
        print(
            f"reference check: quiet ({ref['slowdown']:+.1%} against {ref['baseline']['source']})"
        )

    args.raw_dir.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(raw), args.raw_dir / f"{args.name}.parquet")
    doc_chars = [len(page_input(r[1], r[2], r[3], r[4], 3000)) for r in rows]
    report = {
        **stamp,
        "measures": "inference: extracted text to labels (no extraction, no fetch)",
        "profile": args.profile,
        "environment": {
            "cpu": cpu_info(),
            "threads": args.threads,
            "thread_env": {v: os.environ.get(v) for v in THREAD_VARS},
            "threadpools": pools,
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "sklearn": sklearn.__version__,
            "cgroup_cpu_max": (
                Path("/sys/fs/cgroup/cpu.max").read_text().strip()
                if Path("/sys/fs/cgroup/cpu.max").exists()
                else None
            ),
        },
        "reference": ref,
        "model": {
            "bundle_sha256": sha,
            "source_run": meta["source_run"],
            "source_commit": meta["source_commit"],
            "features": meta["features"],
            "labels": len(meta["label_ids"]),
            "dtype": "float32",
            "quantization": None,
            "taxonomy_sha256": json.loads(Path(f"results/{meta['source_run']}.json").read_text())[
                "inputs"
            ]["taxonomy_sha256"]
            if Path(f"results/{meta['source_run']}.json").exists()
            else None,
        },
        "inputs": {
            "pages": len(rows),
            "split": "test (component split)",
            "input_chars_at_3000": {
                "p50": percentile(doc_chars, 50),
                "p90": percentile(doc_chars, 90),
                "max": max(doc_chars),
            },
        },
        "configs": configs,
    }
    (args.out_dir / f"{args.name}.json").write_text(json.dumps(report, indent=1) + "\n")


if __name__ == "__main__":
    main()
