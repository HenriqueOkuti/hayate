"""Export a trained tier-1 model to a torch-free CPU bundle and check it against the original.

Usage: uv run python scripts/export_tier1.py --name tier1-v1

Reads artifacts/<name>/ (featurizer.joblib, head.pt) and results/<name>.json (the chosen top-1
floor and max labels), writes artifacts/<name>/cpu/ (see hayate.students.hashed_infer) and checks
on the run's val pages that the bundle gives the same labels as the training-time predictions
(artifacts/<name>/predictions.jsonl) and logits within float tolerance of the torch head.
Prints the check and the bundle's SHA-256 (over weights, bias and meta), which the benchmark
records as the model hash.
"""

import argparse
import hashlib
import json
from pathlib import Path

import duckdb
import joblib
import numpy as np
import torch

from hayate.students.hashed import LinearHead, logits, page_input
from hayate.students.hashed_infer import Tier1
from hayate.teacher import claude


def bundle_sha256(path: Path) -> str:
    h = hashlib.sha256()
    for name in ("weights.npy", "bias.npy", "meta.json"):
        h.update((path / name).read_bytes())
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--name", required=True)
    ap.add_argument("--check-pages", type=int, default=500)
    args = ap.parse_args()

    art = Path("artifacts") / args.name
    report = json.loads(Path(f"results/{args.name}.json").read_text())
    cfg = report["config"]
    saved = joblib.load(art / "featurizer.joblib")
    state = torch.load(art / "head.pt", map_location="cpu")
    weights = state["weight.weight"].numpy().astype(np.float32)
    bias = state["bias"].numpy().astype(np.float32)
    out = art / "cpu"
    out.mkdir(exist_ok=True)
    np.save(out / "weights.npy", weights)
    np.save(out / "bias.npy", bias)
    joblib.dump(saved["featurizer"], out / "featurizer.joblib")
    meta = {
        "source_run": args.name,
        "source_commit": report["commit"],
        "label_ids": saved["label_ids"],
        "temperature": float(saved["temperature"]),
        "thresholds": [float(t) for t in saved["thresholds"]],
        "top1_floor": report["model"].get("top1_floor"),
        "max_labels": cfg["max_labels"],
        "max_chars": cfg["max_chars"],
        "input": {k: cfg[k] for k in ("text_field", "fallback_field", "min_chars")},
        "features": int(weights.shape[0]),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=1) + "\n")

    # check: same labels as training time, and logits close to the torch head, on val pages
    preds = {}
    with (art / "predictions.jsonl").open() as f:
        for r in map(json.loads, f):
            if r["split"] == "val":
                preds[r["page_id"]] = r["labels"]
    pages = sorted(preds)[: args.check_pages]
    inp = meta["input"]
    rows = duckdb.sql(
        f"""select page_id, url, coalesce(title, ''), coalesce(meta_description, ''),
                   {claude.text_sql(inp)} from '{cfg["pages"]}'
            where list_contains($ids, page_id) order by page_id""",
        params={"ids": pages},
    ).fetchall()
    docs = [page_input(r[1], r[2], r[3], r[4], meta["max_chars"]) for r in rows]
    model = Tier1.load(out)
    x = model.featurize(docs)
    head = LinearHead(weights.shape[0], weights.shape[1])
    head.load_state_dict(state)
    z_torch = logits(head, x)
    z_cpu = x @ model.weights + model.bias
    labels = model.decide(model.forward(x))
    same = sum(a == preds[r[0]] for a, r in zip(labels, rows, strict=True))
    check = {
        "pages": len(rows),
        "max_abs_logit_diff": float(np.abs(z_torch - z_cpu).max()),
        "same_labels_as_training": same,
        "bundle_sha256": bundle_sha256(out),
    }
    (out / "check.json").write_text(json.dumps(check, indent=1) + "\n")
    print(json.dumps(check))
    if same != len(rows) or check["max_abs_logit_diff"] > 1e-3:
        raise SystemExit("the CPU bundle does not reproduce the trained model")


if __name__ == "__main__":
    main()
