"""Score the teacher against the human-checked gold sample (counts only, no page text).

Usage: uv run python scripts/gold_report.py --config configs/gold.toml --out results/gold-v0.json

Reads the tasks and decisions written by scripts/review_gold.py. The teacher's labels are the
prediction and the reviewer's the reference, at Tier 2 and rolled up to Tier 1, with 95% bootstrap
intervals over pages (hayate.evaluation.agreement). Skipped pages are left out, and so are blind
answers the reviewer marked as slips. Sections (what was fixed before any result existed is in
docs/decisions/0010-gold-sample.md):
- teacher_vs_human: against the final answers (all, assisted, blind, per language) and against the
  blind answers given before the teacher's labels were shown. The final answers were made looking
  at the teacher's labels, so all_final is the optimistic bound and blind_before_reveal the
  pessimistic one;
- teacher_secondaries_0_5: the one variant, the top label plus secondaries of confidence >= 0.5;
- anchoring: on the blind pages, F1 against the final minus F1 against the blind answers (paired),
  and assisted F1 minus blind-before-reveal F1 (separate pages, equal weight per language);
- blind_before_reveal_by_order: thirds of the blind pages in review order, since later blind
  answers come after many pages of seeing the teacher's labels;
- noise_floor_on_blind_pages: the teacher's repeat pass against its main pass and against the
  blind answers (the reviewer's own repeat noise is not measured);
- other_runs_vs_human_blind: the [report] compare_runs against the blind answers only, each with
  its paired F1 difference to the reviewed run.
Refuses to run on an unfinished review unless --partial is given.
"""

import argparse
import hashlib
import json
import statistics
import tomllib
from pathlib import Path

from hayate import provenance
from hayate.evaluation import agreement
from hayate.review import tasks as review_tasks
from hayate.review.store import Store
from hayate.teacher import claude

NOTES = [
    "One reviewer. Intervals cover the sampling of pages, not the reviewer's own variance.",
    "Final answers were made looking at the reviewed run's labels (preselected on assisted pages).",
    "Both anchoring differences are upper bounds: they include corrections where the teacher "
    "caught something the reviewer missed.",
    "Blind answers are mixed into the review order, so later ones follow many assisted pages.",
    "Other runs: the reviewer read the reviewed run's text field, and the tool forbids a Tier-1 "
    "label with its own child, which costs runs that give both some Tier-2 precision.",
]


def ids(labels: list[dict], floor: float = 0.0) -> list[str]:
    """Label ids, keeping the top label and the secondaries with confidence >= floor."""
    return [x["id"] for n, x in enumerate(labels) if n == 0 or x["confidence"] >= floor]


def pairs(pred: dict[str, list[str]], ref: dict[str, list[str]], pages) -> list[agreement.Pair]:
    return [(pred[p], ref[p]) for p in pages]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def median_seconds(rows: list[dict]) -> float | None:
    return round(statistics.median(r["seconds"] for r in rows), 1) if rows else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--partial", action="store_true", help="score an unfinished review")
    args = ap.parse_args()
    cfg = tomllib.loads(args.config.read_text())
    smp, out_dir = cfg["sample"], Path(cfg["output"]["dir"])
    labels_dir = Path(smp["labels_dir"])
    review_stamp = json.loads((out_dir / "run.json").read_text())
    run_cfg = review_stamp["config"]["teacher_run_config"]
    labels = claude.load_labels(json.loads(Path(run_cfg["input"]["labels"]).read_text()))
    tier1 = {lab.id: lab.parent or lab.id for lab in labels}
    names = {lab.id: lab.path[-1] for lab in labels}

    tasks = [json.loads(x) for x in (out_dir / "tasks.jsonl").read_text().splitlines()]
    store = Store(out_dir / "reviews.jsonl", tasks, labels)
    progress = store.progress()
    if (progress["todo"] or progress["blind_done"]) and not args.partial:
        raise SystemExit(f"review not finished: {progress} (use --partial to score it anyway)")

    # The reviewed labels are the ones frozen in the tasks; the run's files must still match them.
    main_pass, repeat_pass = review_tasks.read_run(labels_dir / smp["teacher_run"])
    if any(main_pass.get(t["page_id"]) != t["teacher"] for t in tasks):
        raise SystemExit(f"run {smp['teacher_run']} no longer matches the frozen tasks")
    if {t["page_id"] for t in tasks if t["mode"] == "blind"} != repeat_pass.keys():
        raise SystemExit("the blind tasks are not the run's repeat pages")
    files = {f"gold/{n}": sha256(out_dir / n) for n in ("tasks.jsonl", "reviews.jsonl")}
    files[smp["teacher_run"]] = sha256(labels_dir / smp["teacher_run"] / "labels.jsonl")

    kept = [t for t in tasks if store.status(t["page_id"]) == "done"]
    lang = {t["page_id"]: t["lang"] for t in kept}
    all_pages = [t["page_id"] for t in kept]
    assisted_pages = [t["page_id"] for t in kept if t["mode"] == "assisted"]
    done_blind = [t["page_id"] for t in kept if t["mode"] == "blind"]
    blind_pages = [p for p in done_blind if not store.final[p].get("blind_void")]
    final = {p: store.final[p]["labels"] for p in all_pages}
    blind = {p: store.blind[p]["labels"] for p in blind_pages}
    teacher = {t["page_id"]: ids(t["teacher"]) for t in tasks}
    teacher_05 = {t["page_id"]: ids(t["teacher"], 0.5) for t in tasks}
    repeat = {p: ids(x) for p, x in repeat_pass.items()}

    def score(pred: dict, ref: dict, pages: list[str]) -> dict:
        return agreement.summary(pairs(pred, ref, pages), tier1)

    def of(pages: list[str], code: str) -> list[str]:
        return [p for p in pages if lang[p] == code]

    teacher_set = {p: set(x) for p, x in teacher.items()}
    added = {p: set(final[p]) - set(blind[p]) for p in blind_pages}
    after_reveal = {
        "pages": len(blind_pages),
        "pages_changed": sum(set(final[p]) != set(blind[p]) for p in blind_pages),
        "main_label_changed": sum(final[p][:1] != blind[p][:1] for p in blind_pages),
        "labels_added_from_teacher": sum(len(added[p] & teacher_set[p]) for p in blind_pages),
        "labels_added_other": sum(len(added[p] - teacher_set[p]) for p in blind_pages),
        "labels_removed": sum(len(set(blind[p]) - set(final[p])) for p in blind_pages),
    }

    third = -(-len(blind_pages) // 3) or 1  # blind_pages is already in review order
    by_order = [blind_pages[n : n + third] for n in range(0, len(blind_pages), third)]

    other_runs = {}
    for run in cfg["report"]["compare_runs"]:
        other = {p: ids(x) for p, x in review_tasks.read_run(labels_dir / run)[0].items()}
        if not other.keys() >= {t["page_id"] for t in tasks}:
            raise SystemExit(f"run {run} does not cover every gold page")
        files[run] = sha256(labels_dir / run / "labels.jsonl")
        other_runs[run] = score(other, blind, blind_pages) | {
            "f1_minus_reviewed_run": agreement.f1_diff_paired(
                pairs(other, blind, blind_pages), pairs(teacher, blind, blind_pages), tier1
            ),
            "by_order": [score(other, blind, pages) for pages in by_order],
        }

    skipped = [t for t in tasks if store.status(t["page_id"]) == "skipped"]
    used = [store.blind.get(p, {}) for p in all_pages] + [store.final[p] for p in all_pages]
    report = provenance.stamp(
        {"config": str(args.config), "out": str(args.out), "partial": args.partial}, "gold_report"
    )
    report |= {
        "notes": NOTES,
        "review": {"commit": review_stamp["commit"], "created": review_stamp["created"]},
        "files_sha256": files,
        "teacher_run": {
            k: run_cfg.get(k) for k in ("run", "model", "prompt", "prompt_sha256", "seed")
        }
        | {"taxonomy_sha256": run_cfg["taxonomy_sha256"], "input": run_cfg["input"]},
        "sample": {
            "tasks": len(tasks),
            "progress": progress,
            "scored_pages": {
                "all": len(all_pages),
                "blind": len(blind_pages),
                "blind_voided": len(done_blind) - len(blind_pages),
                "assisted": len(assisted_pages),
                "por": len(of(all_pages, "por")),
                "eng": len(of(all_pages, "eng")),
            },
            "skipped": {
                "blind": sum(t["mode"] == "blind" for t in skipped),
                "assisted": sum(t["mode"] == "assisted" for t in skipped),
                "with_a_blind_answer": sum(t["page_id"] in store.blind for t in skipped),
                "teacher_empty": sum(not t["teacher"] for t in skipped),
            },
            "pages_where_reviewer_went_beyond_the_teacher_input": {
                "opened_more_text": len({r["page_id"] for r in used if r.get("more_opened")}),
                "clicked_live_link": len({r["page_id"] for r in used if r.get("link_clicked")}),
            },
            "human_labels_per_page": round(statistics.fmean(len(x) for x in final.values()), 2)
            if final
            else None,
            "human_empty_pages": sum(not x for x in final.values()),
            "teacher_empty_pages": sum(not teacher[p] for p in all_pages),
            "median_seconds_first_save": {
                "blind_answer": median_seconds([store.blind[p] for p in done_blind]),
                "blind_final": median_seconds([store.first_final[p] for p in done_blind]),
                "assisted": median_seconds([store.first_final[p] for p in assisted_pages]),
            },
        },
        "teacher_vs_human": {
            "all_final": score(teacher, final, all_pages),
            "assisted_final": score(teacher, final, assisted_pages),
            "blind_final": score(teacher, final, blind_pages),
            "blind_before_reveal": score(teacher, blind, blind_pages),
            "por_final": score(teacher, final, of(all_pages, "por")),
            "eng_final": score(teacher, final, of(all_pages, "eng")),
        },
        "teacher_secondaries_0_5": {
            "all_final": score(teacher_05, final, all_pages),
            "blind_before_reveal": score(teacher_05, blind, blind_pages),
        },
        "anchoring": {
            "f1_blind_final_minus_blind_before_reveal": agreement.f1_diff_paired(
                pairs(teacher, final, blind_pages), pairs(teacher, blind, blind_pages), tier1
            ),
            "f1_assisted_minus_blind_before_reveal": {
                name: agreement.f1_diff(
                    [
                        (
                            pairs(teacher, final, of(assisted_pages, code)),
                            pairs(teacher, blind, of(blind_pages, code)),
                        )
                        for code in codes
                    ],
                    tier1,
                )
                for name, codes in {
                    "equal_weight_per_language": ("por", "eng"),
                    "por": ("por",),
                    "eng": ("eng",),
                }.items()
            },
            "blind_answers_after_reveal": after_reveal,
        },
        "blind_before_reveal_by_order": [score(teacher, blind, pages) for pages in by_order],
        "noise_floor_on_blind_pages": {
            "teacher_repeat_vs_teacher": score(repeat, teacher, blind_pages),
            "teacher_repeat_vs_human_blind": score(repeat, blind, blind_pages),
        },
        "other_runs_vs_human_blind": other_runs,
        "per_tier1_all_final": {
            names[c]: v
            for c, v in agreement.per_tier1(pairs(teacher, final, all_pages), tier1).items()
        },
    }
    args.out.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: report[k] for k in ("sample", "teacher_vs_human", "anchoring")}, indent=1))


if __name__ == "__main__":
    main()
