"""Write a Model2Vec reference for the Go tier-2 check (#86): token ids and embeddings.

Usage (model2vec is not a project dependency; uv fetches it for this run only):
  uv run --with model2vec python scripts/model2vec_reference.py --n 200

Takes the first --n test pages of artifacts/tier1-v1/cpu/reference-test.jsonl, cuts each input to
--chars characters, and writes artifacts/model2vec-reference.jsonl with, per page: the text, the
token ids Model2Vec uses (no special tokens) and the embedding it returns. Page text stays in
artifacts/ and is never committed.
"""

import argparse
import json
from pathlib import Path

from model2vec import StaticModel


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default="minishlab/potion-multilingual-128M")
    ap.add_argument("--ref", type=Path, default=Path("artifacts/tier1-v1/cpu/reference-test.jsonl"))
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--chars", type=int, default=1000)
    ap.add_argument("--out", type=Path, default=Path("artifacts/model2vec-reference.jsonl"))
    args = ap.parse_args()

    model = StaticModel.from_pretrained(args.model)
    texts = []
    with args.ref.open() as f:
        for line in f:
            texts.append(json.loads(line)["input"][: args.chars])
            if len(texts) == args.n:
                break
    vecs = model.encode(texts)
    enc = model.tokenizer.encode_batch_fast(texts, add_special_tokens=False)
    with args.out.open("w") as f:
        for t, e, v in zip(texts, enc, vecs, strict=True):
            row = {"text": t, "ids": e.ids, "embedding": [float(x) for x in v]}
            f.write(json.dumps(row) + "\n")
    print(
        f"{len(texts)} texts, dim {vecs.shape[1]}, normalize={model.normalize}, "
        f"max_length={getattr(model, 'max_length', None)} -> {args.out}"
    )


if __name__ == "__main__":
    main()
