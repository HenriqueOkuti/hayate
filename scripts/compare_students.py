"""Paired comparison of two student runs on the pages both scored, against the teacher.

Usage:
  uv run python scripts/compare_students.py --a tier1-v0 --b tier1-v0-resiliparse \
      --labels-run bulk-v2 --out results/compare-tier1-extractor.json

Reads artifacts/<run>/predictions.jsonl of both runs (label ids per val and test page) and the
teacher's main-pass labels. For each split, the F1 of run a minus run b on the same pages, with a
95% bootstrap interval that resamples pages once for both (hayate.evaluation.agreement). Choices
between runs are made on val; test is reported alongside, never used to choose.
"""

import argparse
import json
from pathlib import Path

from hayate import provenance
from hayate.evaluation import agreement
from hayate.teacher import claude


def read_preds(run: str) -> dict[tuple[str, str], list[str]]:
    with (Path("artifacts") / run / "predictions.jsonl").open() as f:
        return {(r["split"], r["page_id"]): r["labels"] for r in map(json.loads, f)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--labels-run", required=True)
    ap.add_argument("--labels-json", type=Path, default=Path("data/taxonomy/labels.json"))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    labels = claude.load_labels(json.loads(args.labels_json.read_text()))
    tier1 = {lab.id: lab.parent or lab.id for lab in labels}
    teacher = {}
    with (Path("data/labels") / args.labels_run / "labels.jsonl").open() as f:
        for r in map(json.loads, f):
            if r["pass"] == "main":
                teacher[r["page_id"]] = [x["id"] for x in r["labels"]]
    a, b = read_preds(args.a), read_preds(args.b)
    out = {**provenance.stamp({k: str(v) for k, v in vars(args).items()}, "compare_students")}
    for split in ("val", "test"):
        keys = sorted(k for k in a.keys() & b.keys() if k[0] == split)
        pa = [(a[k], teacher[k[1]]) for k in keys]
        pb = [(b[k], teacher[k[1]]) for k in keys]
        out[split] = {
            "a": agreement.summary(pa, tier1, boot=200)["tier2"]["f1"]
            | {"tier1": agreement.summary(pa, tier1, boot=200)["tier1"]["f1"]},
            "b": agreement.summary(pb, tier1, boot=200)["tier2"]["f1"]
            | {"tier1": agreement.summary(pb, tier1, boot=200)["tier1"]["f1"]},
            "a_minus_b": agreement.f1_diff_paired(pa, pb, tier1),
        }
    args.out.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({s: out[s]["a_minus_b"] for s in ("val", "test")}))


if __name__ == "__main__":
    main()
