"""Summarize the #4 teacher pilot runs into results/teacher-pilot.json (counts only, no page text).

Usage: uv run python scripts/teacher_report.py --config configs/teacher.toml \
    --runs pilot-v1 pilot-v0 pilot-opus-v1 --out results/teacher-pilot.json

Per run: cost and timing per call, label counts, and the two behaviours prompt v1 targets (Tier-1
parents where a child fits, weak secondary labels). Between runs, and between a run's main and
repeat passes: Jaccard and same-top-label at Tier 2 and rolled up to Tier 1, with 95% bootstrap
intervals over pages, plus Tier-2 Jaccard with secondaries under 0.5 dropped. Two empty answers
count as Jaccard 1. Also: label shape of every run on the pages of the first run (--runs order),
and paired differences in repeat consistency between runs that repeated the same pages. Cost and
timing use main-pass calls only, since a repeat can hit the prompt cache.
"""

import argparse
import json
import random
import statistics
import tomllib
from itertools import combinations
from pathlib import Path

from hayate import provenance
from hayate.teacher import claude

BOOT = 2000
MIN_COMMON = 50  # compare two runs only if they share at least this many pages


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []


def ids(labels: list[dict], floor: float = 0.0) -> list[str]:
    """Label ids, keeping the top label and the secondaries with confidence >= floor."""
    return [x["id"] for i, x in enumerate(labels) if i == 0 or x["confidence"] >= floor]


def jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    return 1.0 if not sa | sb else len(sa & sb) / len(sa | sb)


def top_same(a: list[str], b: list[str]) -> float:
    return float((a[:1] or [None]) == (b[:1] or [None]))


def ci(values: list[float], seed: int = 0) -> dict:
    rng = random.Random(seed)
    n = len(values)
    means = sorted(statistics.fmean(rng.choices(values, k=n)) for _ in range(BOOT))
    return {
        "mean": round(statistics.fmean(values), 3),
        "ci95": [round(means[int(0.025 * BOOT)], 3), round(means[int(0.975 * BOOT) - 1], 3)],
        "n": n,
    }


def rollup(ids: list[str], tier1: dict[str, str]) -> list[str]:
    out = []
    for i in ids:
        if tier1[i] not in out:
            out.append(tier1[i])
    return out


def agreement(ra: dict[str, list[dict]], rb: dict[str, list[dict]], tier1: dict[str, str]) -> dict:
    common = sorted(ra.keys() & rb.keys())
    a = {p: ids(ra[p]) for p in common}
    b = {p: ids(rb[p]) for p in common}
    t1a = {p: rollup(a[p], tier1) for p in common}
    t1b = {p: rollup(b[p], tier1) for p in common}
    return {
        "pages": len(common),
        "both_empty": sum(not a[p] and not b[p] for p in common),
        "tier2_jaccard": ci([jaccard(a[p], b[p]) for p in common]),
        "tier2_jaccard_secondaries_0_5": ci(
            [jaccard(ids(ra[p], 0.5), ids(rb[p], 0.5)) for p in common]
        ),
        "tier2_same_top": ci([top_same(a[p], b[p]) for p in common]),
        "tier1_jaccard": ci([jaccard(t1a[p], t1b[p]) for p in common]),
        "tier1_same_top": ci([top_same(t1a[p], t1b[p]) for p in common]),
    }


def label_stats(rows: list[list[dict]], labels: dict[str, claude.Label]) -> dict:
    """Shape of one pass: `rows` holds each page's label list."""
    n_labels = [len(r) for r in rows]
    all_labels = [lab for r in rows for lab in r]
    secondary = [lab for r in rows for lab in r[1:]]
    parent_with_child = sum(
        any(labels[x["id"]].parent in {y["id"] for y in r} for x in r) for r in rows
    )
    return {
        "pages": len(rows),
        "labels_per_page": round(statistics.fmean(n_labels), 2),
        "empty_pages": sum(n == 0 for n in n_labels),
        "tier1_label_share": round(
            sum(labels[x["id"]].tier == 1 for x in all_labels) / max(len(all_labels), 1), 3
        ),
        "pages_with_parent_and_child": parent_with_child,
        "secondary_labels": len(secondary),
        "secondary_below_0_5": sum(x["confidence"] < 0.5 for x in secondary),
        "top_confidence_mean": round(statistics.fmean(r[0]["confidence"] for r in rows if r), 3),
    }


def paired_repeat_diff(a: tuple, b: tuple) -> dict:
    """Repeat Tier-2 Jaccard of run b minus run a, paired over the pages both repeated."""
    (main_a, rep_a), (main_b, rep_b) = a, b
    common = sorted(rep_a.keys() & rep_b.keys())
    diffs = [
        jaccard(ids(main_b[p]), ids(rep_b[p])) - jaccard(ids(main_a[p]), ids(rep_a[p]))
        for p in common
    ]
    return ci(diffs)


def call_stats(calls: list[dict]) -> dict:
    ok = [c for c in calls if c["ok"]]
    main = [c for c in ok if c["pass"] == "main"]
    pages = sum(c["pages"] for c in main)

    def per_page(key: str) -> float:
        return round(sum(c["usage"].get(key, 0) for c in main) / pages, 1)

    walls = sorted(c["wall_s"] for c in main)
    return {
        "calls_ok": len(ok),
        "calls_failed": len(calls) - len(ok),
        "failures_by_kind": {
            k: sum(c.get("kind") == k for c in calls) for k in ("limit", "transient", "bad")
        },
        "pages_labeled": sum(c["pages"] for c in ok),
        "tokens_per_page": {
            "input": per_page("input_tokens"),
            "cache_write": per_page("cache_creation_input_tokens"),
            "cache_read": per_page("cache_read_input_tokens"),
            "output": per_page("output_tokens"),
        },
        "list_price_usd_per_1k_pages": round(
            sum(c.get("cost_usd_list") or 0 for c in main) / pages * 1000, 2
        ),
        "wall_s_per_call": {
            "median": round(statistics.median(walls), 1),
            "p90": round(walls[int(0.9 * (len(walls) - 1))], 1),
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    cfg = tomllib.loads(args.config.read_text())
    labels = {
        lab.id: lab
        for lab in claude.load_labels(json.loads(Path(cfg["input"]["labels"]).read_text()))
    }
    tier1 = {i: lab.parent or i for i, lab in labels.items()}
    base = Path(cfg["output"]["dir"])

    runs, mains, repeats = {}, {}, {}
    for run in args.runs:
        rows = read_jsonl(base / run / "labels.jsonl")
        mains[run] = {r["page_id"]: r["labels"] for r in rows if r["pass"] == "main"}
        repeats[run] = {r["page_id"]: r["labels"] for r in rows if r["pass"] == "repeat"}
        stamp = json.loads((base / run / "run.json").read_text())
        runs[run] = {
            "model": stamp["config"]["model"],
            "prompt": Path(stamp["config"]["prompt"]).name,
            "workers": stamp["config"]["workers"],
            "commit": stamp["commit"],
            "prompt_sha256": stamp["config"].get("prompt_sha256"),
            "claude_version": stamp["config"].get("claude_version"),
            "taxonomy_sha256": stamp["config"]["taxonomy_sha256"],
            "calls": call_stats(read_jsonl(base / run / "calls.jsonl")),
            "labels": label_stats(list(mains[run].values()), labels),
            "repeat_consistency": (
                agreement(mains[run], repeats[run], tier1) if repeats[run] else None
            ),
        }
    first = args.runs[0]
    for run in args.runs:
        shared = mains[first].keys() & mains[run].keys()
        if len(shared) >= MIN_COMMON:
            rows = [mains[run][p] for p in sorted(shared)]
            runs[run][f"labels_on_{first}_pages"] = label_stats(rows, labels)
    pairs = {
        f"{a} vs {b}": agreement(mains[a], mains[b], tier1)
        for a, b in combinations(args.runs, 2)
        if len(mains[a].keys() & mains[b].keys()) >= MIN_COMMON
    }
    repeat_diffs = {
        f"{b} minus {a}": paired_repeat_diff((mains[a], repeats[a]), (mains[b], repeats[b]))
        for a, b in combinations(args.runs, 2)
        if len(repeats[a].keys() & repeats[b].keys()) >= MIN_COMMON
    }
    report = provenance.stamp(vars(args) | {"config": str(args.config), "out": str(args.out)},
                              "teacher_report")  # fmt: skip
    report |= {"runs": runs, "agreement": pairs, "repeat_diff_tier2_jaccard": repeat_diffs}
    args.out.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: report[k] for k in ("runs", "agreement", "repeat_diff_tier2_jaccard")}))


if __name__ == "__main__":
    main()
