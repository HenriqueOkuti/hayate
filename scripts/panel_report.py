"""Build the panel reference for the holdout pages and score every teacher against it.

Usage: uv run python scripts/panel_report.py --config configs/panel.toml --out results/panel-v0.json

The panel is the [panel] members: label runs on the same pages by different teacher
models. Writes the reference (hayate.evaluation.panel: labels at least min_votes members gave)
to the [output] reference file, for later steps to score students against, and a report with
counts only, no page text:
- pairwise: every pair of members, on all pages ("a vs b" takes a as the prediction, which only
  matters for precision and recall), and the paired differences in first-label match between
  pairs;
- repeat: each member's main pass against its own repeat pass;
- reference: how many pages are agreed, tier1_only, none or split, per language;
- member_vs_others: each member against the labels the *other* members agree on, so no member is
  scored against its own vote. Each member then has its own reference and its own set of pages,
  so these rows do not rank the members; member_vs_others_common_pages scores them on the pages
  where every member has such a reference, which is the fairer comparison;
- other_runs: the [report] compare_runs against the reference, leaving out the member named in
  `leave_out` (the run's own model);
- reference_stability: on the pages every member labeled twice, the reference built from the
  repeat passes against the one built from the main passes.
The teacher is the prediction and the reference the truth for precision and recall. Pages with no
reference at a tier are left out of that tier's score, which flatters every score a little: they
are the pages the members disagree on. Intervals are 95% bootstrap over pages.
"""

import argparse
import hashlib
import json
import random
import statistics
import tomllib
from collections import Counter
from itertools import combinations
from pathlib import Path

import duckdb

from hayate import provenance
from hayate.evaluation import agreement, panel
from hayate.teacher import claude

NOTES = [
    "Agreement between models, not accuracy: no human checked these labels, and a mistake the "
    "panel members share is invisible.",
    "Leave-one-out scores (member_vs_others, and other_runs with leave_out) drop the pages where "
    "the remaining members share no label (see coverage). Those are the hard pages, so the "
    "scores are flattered, and each member's row is on different pages.",
    "Precision, recall and F1 depend on how many labels a run gives per page; the first-label "
    "match does not.",
    "Intervals resample pages with the reference fixed; they do not include the reference's own "
    "run-to-run noise (see reference_stability).",
    "Members differ in batch size and backend as well as model (see runs).",
]

Runs = dict[str, dict[str, list[dict]]]


def read_run(run_dir: Path) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    """A run's labels per page id: (main pass, repeat pass)."""
    main: dict[str, list[dict]] = {}
    repeat: dict[str, list[dict]] = {}
    for row in map(json.loads, (run_dir / "labels.jsonl").read_text().splitlines()):
        (main if row["pass"] == "main" else repeat)[row["page_id"]] = row["labels"]
    return main, repeat


def ids(labels: list[dict]) -> list[str]:
    return [x["id"] for x in labels]


def run_info(run_dir: Path, main: dict[str, list[dict]]) -> dict:
    cfg = json.loads((run_dir / "run.json").read_text())
    calls = [json.loads(x) for x in (run_dir / "calls.jsonl").read_text().splitlines()]
    c = cfg["config"]
    return {
        "model": c["model"],
        "backend": c.get("backend", "claude"),
        "prompt": Path(c["prompt"]).name,
        "prompt_sha256": c.get("prompt_sha256"),
        "text_field": c["input"]["text_field"],
        "batch_size": max(x["pages"] for x in calls),
        "cli_version": c.get("claude_version") or c.get("agy_version") or c.get("ollama_version"),
        "commit": cfg["commit"],
        "created": cfg["created"],
        "taxonomy_sha256": c["taxonomy_sha256"],
        "labels_sha256": hashlib.sha256((run_dir / "labels.jsonl").read_bytes()).hexdigest(),
        "calls_failed": sum(not x["ok"] for x in calls),
        "resolved_models": sorted({m for x in calls for m in (x.get("model_usage") or {})}) or None,
        "thinking_tokens": sum(
            (x.get("usage") or {}).get("output_tokens_details", {}).get("thinking_tokens", 0)
            for x in calls
        )
        if any("output_tokens_details" in (x.get("usage") or {}) for x in calls)
        else None,
        "pages": len(main),
        "labels_per_page": round(statistics.fmean(len(x) for x in main.values()), 2),
        "empty_pages": sum(not x for x in main.values()),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    cfg = tomllib.loads(args.config.read_text())
    labels_dir, members = Path(cfg["panel"]["labels_dir"]), cfg["panel"]["members"]
    min_votes = cfg["panel"]["min_votes"]
    compare = cfg["report"]["compare_runs"]

    mains: Runs = {}
    repeats: Runs = {}
    info = {}
    for run in members + [c["run"] for c in compare]:
        mains[run], repeats[run] = read_run(labels_dir / run)
        info[run] = run_info(labels_dir / run, mains[run])
    first = json.loads((labels_dir / members[0] / "run.json").read_text())["config"]["input"]
    pages_path = first["pages"]
    labels = claude.load_labels(json.loads(Path(first["labels"]).read_text()))
    tier1 = {lab.id: lab.parent or lab.id for lab in labels}
    pages = sorted(mains[members[0]])
    for run in mains:
        if set(mains[run]) != set(pages):
            raise SystemExit(f"run {run} does not label the same pages as {members[0]}")
        if info[run]["taxonomy_sha256"] != info[members[0]]["taxonomy_sha256"]:
            raise SystemExit(f"run {run} used a different taxonomy file")
    lang = dict(duckdb.sql(f"select page_id, lang from read_parquet('{pages_path}')").fetchall())

    def reference(runs: Runs, who: list[str], on: list[str]) -> dict[str, dict]:
        return {p: panel.consensus([runs[m][p] for m in who], tier1, min_votes) for p in on}

    def against(pred: dict[str, list[dict]], ref: dict[str, dict]) -> dict:
        """Score at each tier on the pages that have a reference there."""
        on2 = [p for p in ref if panel.has_reference(ref[p], 2)]
        on1 = [p for p in ref if panel.has_reference(ref[p], 1)]
        t2 = agreement.summary([(ids(pred[p]), ref[p]["labels"]) for p in on2], tier1)
        t1 = agreement.summary([(ids(pred[p]), ref[p]["tier1"]) for p in on1], tier1)
        return {
            "coverage": {"pages": len(ref), "tier2": len(on2), "tier1": len(on1)},
            "tier2_labels": {
                "predicted": sum(len(pred[p]) for p in on2),
                "reference": sum(len(ref[p]["labels"]) for p in on2),
            },
            "tier2": t2.get("tier2"),
            "tier1": t1.get("tier1"),
        }

    def between(a: dict[str, list[dict]], b: dict[str, list[dict]], on: list[str]) -> dict:
        return agreement.summary([(ids(a[p]), ids(b[p])) for p in on], tier1)

    ref = reference(mains, members, pages)
    ref_path = Path(cfg["output"]["reference"])
    ref_path.parent.mkdir(parents=True, exist_ok=True)
    ref_path.write_text(
        "".join(
            json.dumps({"page_id": p, **ref[p], "votes": {m: ids(mains[m][p]) for m in members}})
            + "\n"
            for p in pages
        )
    )

    def others(run: str) -> list[str]:
        return [m for m in members if m != run]

    loo = {m: reference(mains, others(m), pages) for m in members}
    common = [p for p in pages if all(panel.has_reference(loo[m][p], 2) for m in members)]

    def first_match_diff(pair_a: tuple[str, str], pair_b: tuple[str, str]) -> dict:
        """Share of pages where pair a gives the same first label, minus the same for pair b."""

        def same(x: str, y: str) -> list[float]:
            return [float(ids(mains[x][p])[:1] == ids(mains[y][p])[:1]) for p in pages]

        diffs = [a - b for a, b in zip(same(*pair_a), same(*pair_b), strict=True)]
        rng = random.Random(0)
        draws = sorted(
            statistics.fmean(rng.choices(diffs, k=len(diffs))) for _ in range(agreement.BOOT)
        )
        return {
            "value": round(statistics.fmean(diffs), 3),
            "ci95": [
                round(draws[int(0.025 * len(draws))], 3),
                round(draws[int(0.975 * len(draws)) - 1], 3),
            ],
        }

    sets = {p: [frozenset(ids(mains[m][p])) for m in members] for p in pages}
    both = sorted(set.intersection(*(set(repeats[m]) for m in members)))
    ref_main, ref_repeat = reference(mains, members, both), reference(repeats, members, both)
    stable2 = [p for p in both if all(panel.has_reference(r[p], 2) for r in (ref_main, ref_repeat))]

    stamp_cfg = {
        "config": str(args.config),
        "config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
        "out": str(args.out),
    }
    report = provenance.stamp(stamp_cfg, "panel_report")
    report |= {
        "notes": NOTES,
        "panel": {"members": members, "min_votes": min_votes, "pages": len(pages)},
        "runs": info,
        "pairwise": {
            f"{a} vs {b}": between(mains[a], mains[b], pages) for a, b in combinations(members, 2)
        },
        "pairwise_first_label_differences": {
            f"({a[0]} and {a[1]}) minus ({b[0]} and {b[1]})": first_match_diff(a, b)
            for a, b in combinations(list(combinations(members, 2)), 2)
        },
        "repeat": {
            m: between(repeats[m], mains[m], sorted(repeats[m])) for m in members if repeats[m]
        },
        "reference": {
            "status": dict(Counter(r["status"] for r in ref.values())),
            "status_by_language": {
                code: dict(Counter(ref[p]["status"] for p in pages if lang[p] == code))
                for code in sorted(set(lang[p] for p in pages))
            },
            "unanimous_top_label": sum(
                len({tuple(ids(mains[m][p])[:1]) for m in members}) == 1 for p in pages
            ),
            "label_shared_by_all": sum(bool(frozenset.intersection(*sets[p])) for p in pages),
            "identical_label_sets": sum(len(set(sets[p])) == 1 for p in pages),
            "labels_per_agreed_page": round(
                statistics.fmean(len(r["labels"]) for r in ref.values() if r["status"] == "agreed"),
                2,
            ),
            "sha256": hashlib.sha256(ref_path.read_bytes()).hexdigest(),
        },
        "member_vs_others_common_pages": {
            m: against(mains[m], {p: loo[m][p] for p in common}) for m in members
        },
        "member_vs_others": {
            m: against(mains[m], loo[m])
            | {
                "by_language": {
                    code: against(
                        mains[m],
                        reference(mains, others(m), [p for p in pages if lang[p] == code]),
                    )
                    for code in sorted(set(lang[p] for p in pages))
                }
            }
            for m in members
        },
        "other_runs": {
            c["run"]: {"leave_out": c.get("leave_out")}
            | against(
                mains[c["run"]],
                reference(mains, [m for m in members if m != c.get("leave_out")], pages),
            )
            for c in compare
        },
        "reference_stability": {
            "pages": len(both),
            "same_status": sum(ref_main[p]["status"] == ref_repeat[p]["status"] for p in both),
            "identical_label_sets": sum(
                set(ref_main[p]["labels"]) == set(ref_repeat[p]["labels"]) for p in both
            ),
            "status_main": dict(Counter(ref_main[p]["status"] for p in both)),
            "status_repeat": dict(Counter(ref_repeat[p]["status"] for p in both)),
            "tier2_where_both_have_a_reference": agreement.summary(
                [(ref_repeat[p]["labels"], ref_main[p]["labels"]) for p in stable2], tier1
            ),
        },
    }
    args.out.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: report[k] for k in ("reference", "member_vs_others")}, indent=1))


if __name__ == "__main__":
    main()
