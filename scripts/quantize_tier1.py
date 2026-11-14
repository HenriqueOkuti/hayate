"""Quantize a tier-1 CPU bundle's weights to int8, one scale per feature row, and check it.

Usage: uv run python scripts/quantize_tier1.py --name tier1-v2

Reads artifacts/<name>/cpu and writes artifacts/<name>/cpu-int8: weights_int8.npy (features x
labels, int8) and scales.npy (one float32 per feature row, symmetric: the row's largest
absolute weight over 127), with the other bundle files copied and no weights.npy. A row's
weights are scale * int8 value. Then scores both bundles on the run's val and test pages with
the same temperature, thresholds and floor (no retuning: this checks the conversion, it is not
a new model), and writes results/<name>-int8.json: the largest probability difference, how
many pages keep exactly their labels, and the F1 of each bundle against the teacher, with the
int8 minus float difference paired over the same pages. Counts and scores only, no page text.
"""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import duckdb
import numpy as np

from hayate import provenance
from hayate.evaluation import agreement, metrics
from hayate.students.features import page_input
from hayate.students.hashed_infer import Tier1
from hayate.teacher import claude

COPY = ("bias.npy", "meta.json", "idf.npy", "featurizer.json", "featurizer.joblib")


def quantize(w: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Symmetric per-row int8: q = round(w / s), s = max |w| / 127 (0 for an all-zero row)."""
    scale = (np.abs(w).max(axis=1) / 127).astype(np.float32)
    safe = np.where(scale > 0, scale, 1)[:, None]
    q = np.clip(np.rint(w / safe), -127, 127).astype(np.int8)
    return q, scale


def bundle_sha256(path: Path) -> str:
    h = hashlib.sha256()
    for name in ("weights_int8.npy", "scales.npy", "bias.npy", "meta.json"):
        h.update((path / name).read_bytes())
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--name", required=True)
    ap.add_argument("--labels-json", type=Path, default=Path("data/taxonomy/labels.json"))
    args = ap.parse_args()

    src = Path("artifacts") / args.name / "cpu"
    dst = src.with_name("cpu-int8")
    dst.mkdir(exist_ok=True)
    w = np.load(src / "weights.npy")
    q, scale = quantize(w)
    np.save(dst / "weights_int8.npy", q)
    np.save(dst / "scales.npy", scale)
    for f in COPY:
        shutil.copyfile(src / f, dst / f)
    err = np.abs(q.astype(np.float32) * scale[:, None] - w)

    report = json.loads(Path(f"results/{args.name}.json").read_text())
    cfg = report["config"]
    teacher = {}
    labels_dir = Path(cfg["labels_dir"]) / cfg["labels_run"] / "labels.jsonl"
    with labels_dir.open() as f:
        for r in map(json.loads, f):
            if r["pass"] == "main":
                teacher[r["page_id"]] = [x["id"] for x in r["labels"]]
    tier1 = {
        lab.id: lab.parent or lab.id
        for lab in claude.load_labels(json.loads(args.labels_json.read_text()))
    }
    float_model, int8_model = Tier1.load(src), Tier1.load(dst)
    inp = {k: cfg[k] for k in ("text_field", "fallback_field", "min_chars")}
    splits_path = Path(cfg["splits_dir"]) / f"{cfg['splits']}.parquet"
    out = {}
    for split in ("val", "test"):
        rows = duckdb.sql(
            f"""select p.page_id, p.url, coalesce(p.title, ''), coalesce(p.meta_description, ''),
                       {claude.text_sql(inp)}
                from '{cfg["pages"]}' p join '{splits_path}' s using (page_id)
                where s.{cfg["split_column"]} = '{split}' order by p.page_id"""
        ).fetchall()
        x = float_model.featurize([page_input(*r[1:5], cfg["max_chars"]) for r in rows])
        pf, pq = float_model.forward(x), int8_model.forward(x)
        lf, lq = float_model.decide(pf), int8_model.decide(pq)
        ref = [teacher[r[0]] for r in rows]
        out[split] = {
            "pages": len(rows),
            "max_abs_prob_diff": float(np.abs(pf - pq).max()),
            "same_labels": sum(a == b for a, b in zip(lf, lq, strict=True)),
            "float_tier2_f1": metrics.micro(ref, lf)["f1"],
            "int8_tier2_f1": metrics.micro(ref, lq)["f1"],
            "int8_minus_float": agreement.f1_diff_paired(
                list(zip(lq, ref, strict=True)), list(zip(lf, ref, strict=True)), tier1
            ),
        }
        print(split, json.dumps(out[split]))

    result = {
        **provenance.stamp({"name": args.name}, "quantize_tier1"),
        "bundle": {
            "source": str(src),
            "int8": str(dst),
            "int8_sha256": bundle_sha256(dst),
            "weights_mb": {"float32": round(w.nbytes / 1e6, 1), "int8": round(q.nbytes / 1e6, 1)},
            "max_abs_weight_error": float(err.max()),
            "zero_rows": int((scale == 0).sum()),
        },
        "same_thresholds": "temperature, thresholds and floor of the float bundle, not retuned",
        **out,
    }
    Path(f"results/{args.name}-int8.json").write_text(json.dumps(result, indent=1) + "\n")


if __name__ == "__main__":
    main()
