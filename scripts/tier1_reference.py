"""Write the Python reference that the Go tier-1 implementation must reproduce.

Usage: uv run python scripts/tier1_reference.py --bundle artifacts/tier1-v1/cpu

Adds to the bundle what a non-Python loader needs (idf.npy, and the hashing settings in
featurizer.json), then writes reference-<split>.jsonl with, per page: the input parts (URL,
title, description and the selected page text, before the input string is built), the input
string, the TF-IDF features (indices and float32 values), the probabilities and the labels.
These files hold page text, so they live in artifacts/ and are never committed.
"""

import argparse
import json
from pathlib import Path

import duckdb
import numpy as np

from hayate.students.features import page_input
from hayate.students.hashed_infer import Tier1
from hayate.teacher import claude


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bundle", type=Path, default=Path("artifacts/tier1-v1/cpu"))
    ap.add_argument("--split", default="test")
    ap.add_argument("--pages", type=Path, default=Path("data/pages/pages.parquet"))
    ap.add_argument("--splits", type=Path, default=Path("data/splits/splits-v1.parquet"))
    args = ap.parse_args()

    model = Tier1.load(args.bundle)
    meta = json.loads((args.bundle / "meta.json").read_text())
    f = model.featurizer
    np.save(args.bundle / "idf.npy", f.tfidf.idf_.astype(np.float64))
    settings = {
        "word": {"n_features": f.word.n_features, "ngram_range": list(f.word.ngram_range),
                 "token_pattern": f.word.token_pattern},
        "char": {"n_features": f.char.n_features, "ngram_range": list(f.char.ngram_range),
                 "analyzer": f.char.analyzer},
        "lowercase": True,
        "alternate_sign": False,
        "tfidf": {"sublinear_tf": f.tfidf.sublinear_tf, "norm": f.tfidf.norm,
                  "smooth_idf": f.tfidf.smooth_idf},
        "dtype": "float64 until the end, then float32",
        "max_chars": meta["max_chars"],
    }  # fmt: skip
    (args.bundle / "featurizer.json").write_text(json.dumps(settings, indent=1) + "\n")

    rows = duckdb.sql(
        f"""select p.page_id, p.url, coalesce(p.title, ''), coalesce(p.meta_description, ''),
                   {claude.text_sql(meta["input"])}
            from '{args.pages}' p join '{args.splits}' s using (page_id)
            where s.split = '{args.split}' order by p.page_id"""
    ).fetchall()
    docs = [page_input(r[1], r[2], r[3], r[4], meta["max_chars"]) for r in rows]
    x = model.featurize(docs)
    prob = model.forward(x)
    labels = model.decide(prob)
    out = args.bundle / f"reference-{args.split}.jsonl"
    with out.open("w") as fh:
        for k, r in enumerate(rows):
            row = x[k]
            fh.write(json.dumps({
                "page_id": r[0], "url": r[1], "title": r[2], "description": r[3], "text": r[4],
                "input": docs[k],
                "indices": row.indices.tolist(), "values": row.data.tolist(),
                "prob": [round(float(p), 7) for p in prob[k]],
                "labels": labels[k],
            }) + "\n")  # fmt: skip
    print(f"{len(rows)} pages -> {out}")


if __name__ == "__main__":
    main()
