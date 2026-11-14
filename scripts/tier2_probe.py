"""Tier-2 tokenizer probe (#91): val F1 of one linear head on four static-embedding variants.

Usage (model2vec is not a project dependency; uv fetches it for this run only):
  uv run --with 'model2vec[distill,quantization]' python scripts/tier2_probe.py

Every variant embeds a page as the l2-normalized mean of its tokens' rows (as Model2Vec does) and
gets the same head and tuning; only the tokenizer and the embedding table change:
- potion: minishlab/potion-multilingual-128M with its own tokenizer (Unigram over bge-m3's
  vocabulary, about 500k rows); the options "stock tokenizer" and "faster tokenizer with parity"
  produce the same tokens, so they share this row;
- distill: a plain Model2Vec distillation of BAAI/bge-m3 (potion's teacher) with its own
  250k-piece Unigram vocabulary, the control for the next two;
- wordfirst: the same distillation with a vocabulary of the --vocab-size most frequent words of
  the train pages added, and a simple tokenizer: NFKC, lowercase, `\\w+` words; a word in the
  vocabulary is one token, any other word is split by the Unigram model alone;
- wordonly: the same, but words outside the vocabulary are dropped, so the table holds only the
  vocabulary's rows.
No variant truncates: every page's whole input (3,000 characters of text) is tokenized.
The head is one linear layer to the label set, trained with binary cross-entropy and Adam
(epsilon 1e-7) on the train pages, the learning rate and epoch chosen by val loss; then one
temperature and per-label thresholds as in scripts/train_tier1.py, scored cross-fitted on val
halves split by component, with no top-label floor. The vocabulary comes from train pages only,
and test pages are never read. Each variant's cross-fitted val F1 is also compared with the first
variant's, paired over the same pages. Writes results/tier2-probe-v0.json (counts and scores
only), and to artifacts/tier2-probe/ (not committed) the distilled models and the vocabulary.
"""

import argparse
import hashlib
import json
import re
import time
import unicodedata
from collections import Counter
from pathlib import Path

import duckdb
import numpy as np
import torch

from hayate import provenance
from hayate.evaluation import agreement, metrics
from hayate.students.features import page_input
from hayate.teacher import claude

WORD = re.compile(r"\w+")


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).lower()


def half(key: str) -> bool:
    return hashlib.sha256(f"0:half:{key}".encode()).digest()[0] % 2 == 0


def word_vocab(texts: list[str], size: int, min_df: int) -> list[str]:
    df = Counter()
    for t in texts:
        df.update(set(WORD.findall(normalize(t))))
    return [w for w, n in df.most_common(size) if n >= min_df]


class WordFirst:
    """NFKC, lowercase, \\w+ words; vocabulary words are one token, others go to the Unigram
    model alone (fallback) or are dropped."""

    def __init__(self, tokenizer, words: list[str], fallback: bool) -> None:
        self.model = tokenizer.model
        self.ids = {}
        for w in words:
            i = tokenizer.token_to_id("▁" + w)
            if i is not None:
                self.ids[w] = i
        self.fallback = fallback
        self.cache: dict[str, list[int]] = {}

    def encode(self, text: str) -> tuple[list[int], int, int]:
        out, words, known = [], 0, 0
        for w in WORD.findall(normalize(text)):
            words += 1
            if w in self.ids:
                out.append(self.ids[w])
                known += 1
            elif self.fallback:
                if w not in self.cache:
                    self.cache[w] = [t.id for t in self.model.tokenize("▁" + w)]
                out.extend(self.cache[w])
        return out, words, known


def pool(emb: np.ndarray, ids: list[int]) -> np.ndarray:
    if not ids:
        return np.zeros(emb.shape[1], np.float32)
    v = emb[ids].mean(0)
    n = np.linalg.norm(v)
    return (v / n if n > 0 else v).astype(np.float32)


def train_head(x, y, xv, yv, lrs, max_epochs=200, patience=5, batch=256, seed=0):
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    xt, yt = torch.from_numpy(x).to(dev), torch.from_numpy(y.astype(np.float32)).to(dev)
    xvt, yvt = torch.from_numpy(xv).to(dev), torch.from_numpy(yv.astype(np.float32)).to(dev)
    rate = np.clip(y.mean(0), 1e-4, 1 - 1e-4)
    loss_fn = torch.nn.BCEWithLogitsLoss()
    best = None
    for lr in lrs:
        torch.manual_seed(seed)
        head = torch.nn.Linear(x.shape[1], y.shape[1]).to(dev)
        torch.nn.init.zeros_(head.weight)
        head.bias.data = torch.tensor(np.log(rate / (1 - rate)), dtype=torch.float32, device=dev)
        opt = torch.optim.Adam(head.parameters(), lr=lr, eps=1e-7)
        rng = np.random.default_rng(seed)
        top, state, wait, hist = np.inf, None, 0, []
        for _ in range(max_epochs):
            order = rng.permutation(len(x))
            for i in range(0, len(order), batch):
                rows = torch.from_numpy(order[i : i + batch]).to(dev)
                loss = loss_fn(head(xt[rows]), yt[rows])
                opt.zero_grad(set_to_none=True)
                loss.backward()
                opt.step()
            with torch.no_grad():
                vl = float(loss_fn(head(xvt), yvt))
            hist.append(vl)
            if vl < top - 1e-6:
                top, wait = vl, 0
                state = {k: v.clone() for k, v in head.state_dict().items()}
            elif (wait := wait + 1) >= patience:
                break
        if best is None or top < best[0]:
            best = (top, lr, int(np.argmin(hist)) + 1, state)
    head.load_state_dict(best[3])
    with torch.no_grad():
        z = head(xvt).cpu().numpy()
    return z, {"val_bce": round(best[0], 6), "lr": best[1], "best_epoch": best[2]}


def cross_f1(y_val, z_val, ref_val, label_ids, halves, min_supports=(5, 20, 50, 10**9)):
    """Temperature, then per-label thresholds fitted on one val half and scored on the other;
    returns the score at the best min support and that setting's cross-fitted predictions."""
    temp = metrics.fit_temperature(y_val, z_val)
    prob = metrics.sigmoid(z_val / temp)
    out, preds = {}, {}
    for ms in min_supports:
        pred = [None] * len(ref_val)
        for fit_on in (halves, ~halves):
            thr, _ = metrics.fit_thresholds(y_val[fit_on], prob[fit_on], max(ms // 2, 1))
            for k in np.flatnonzero(~fit_on):
                row = prob[k]
                keep = np.flatnonzero(row >= thr)
                keep = keep[np.argsort(-row[keep])][:5]
                pred[k] = [label_ids[j] for j in keep]
        out[ms] = metrics.micro(ref_val, pred)["f1"]
        preds[ms] = pred
    ms = max(out, key=lambda m: (out[m], m))
    return {"val_f1_cross": out[ms], "min_support": ms, "temperature": round(temp, 3)}, preds[ms]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--variants", nargs="+", default=["potion", "distill", "wordfirst", "wordonly"])
    ap.add_argument("--vocab-size", type=int, default=100_000)
    ap.add_argument("--min-df", type=int, default=3)
    ap.add_argument("--max-chars", type=int, default=3000)
    ap.add_argument("--lrs", type=float, nargs="+", default=[1e-3, 3e-3, 1e-2, 3e-2])
    ap.add_argument("--potion", default="minishlab/potion-multilingual-128M")
    ap.add_argument("--teacher", default="BAAI/bge-m3")
    ap.add_argument("--labels-run", default="bulk-v2")
    ap.add_argument("--splits", type=Path, default=Path("data/splits/splits-v1.parquet"))
    ap.add_argument("--pages", type=Path, default=Path("data/pages/pages.parquet"))
    ap.add_argument("--art", type=Path, default=Path("artifacts/tier2-probe"))
    ap.add_argument("--out", type=Path, default=Path("results/tier2-probe-v0.json"))
    args = ap.parse_args()

    from model2vec import StaticModel
    from model2vec.distill import distill

    inp = {"text_field": "text_trafilatura", "fallback_field": "text_resiliparse", "min_chars": 200}
    rows = duckdb.sql(
        f"""select p.page_id, s.split, s.component, p.url, coalesce(p.title, ''),
                   coalesce(p.meta_description, ''), {claude.text_sql(inp)}
            from '{args.pages}' p join '{args.splits}' s using (page_id)
            where s.split in ('train', 'val') order by p.page_id"""
    ).fetchall()
    teacher = {}
    with Path(f"data/labels/{args.labels_run}/labels.jsonl").open() as f:
        for r in map(json.loads, f):
            if r["pass"] == "main":
                teacher[r["page_id"]] = [x["id"] for x in r["labels"]]
    part = {s: [r for r in rows if r[1] == s] for s in ("train", "val")}
    texts = {s: [page_input(*r[3:7], args.max_chars) for r in part[s]] for s in part}
    label_ids = sorted({i for r in part["train"] for i in teacher[r[0]]})
    y = {s: metrics.to_matrix([[i for i in teacher[r[0]] if i in label_ids] for r in part[s]],
                              label_ids) for s in part}  # fmt: skip
    ref_val = [teacher[r[0]] for r in part["val"]]
    halves = np.array([half(r[2]) for r in part["val"]])
    vocab = word_vocab(texts["train"], args.vocab_size, args.min_df)
    n_train, n_val = len(part["train"]), len(part["val"])
    print(f"{n_train} train, {n_val} val pages; vocabulary {len(vocab)} words")

    args.art.mkdir(parents=True, exist_ok=True)
    (args.art / "vocab.json").write_text(json.dumps(vocab, ensure_ascii=False) + "\n")
    built: dict[str, object] = {}

    def model(kind: str):
        if kind not in built:
            path = args.art / kind
            if (path / "model.safetensors").exists():
                built[kind] = StaticModel.from_pretrained(str(path))
            elif kind == "potion":
                built[kind] = StaticModel.from_pretrained(args.potion)
            else:
                m = distill(args.teacher, vocabulary=vocab if kind == "words" else None,
                            pca_dims=256, quantize_to="float32")  # fmt: skip
                m.save_pretrained(str(path))
                (path / "README.md").unlink(missing_ok=True)  # generated card; artifacts are linted
                built[kind] = m
        return built[kind]

    results, preds = {}, {}
    for variant in args.variants:
        t0 = time.time()
        m = model({"potion": "potion", "distill": "plain"}.get(variant, "words"))
        emb = np.asarray(m.embedding, dtype=np.float32)
        m.tokenizer.no_truncation()  # potion's tokenizer.json truncates at 512 tokens; use it all
        stats = {}
        if variant in ("potion", "distill"):

            def encode(t, tok=m.tokenizer):
                return tok.encode(t, add_special_tokens=False).ids, 0, 0

            rows_used = emb.shape[0]
        else:
            wf = WordFirst(m.tokenizer, vocab, fallback=variant == "wordfirst")
            encode = wf.encode
            rows_used = emb.shape[0] if variant == "wordfirst" else len(set(wf.ids.values()))
            stats["vocab_words_in_table"] = len(wf.ids)
        x, tokens = {}, {}
        for s in part:
            enc = [encode(t) for t in texts[s]]
            x[s] = np.stack([pool(emb, e[0]) for e in enc])
            tokens[s] = [len(e[0]) for e in enc]
            if s == "val" and variant in ("wordfirst", "wordonly"):
                stats["val_word_coverage"] = round(
                    sum(e[2] for e in enc) / max(1, sum(e[1] for e in enc)), 4
                )
        z, head = train_head(x["train"], y["train"], x["val"], y["val"], args.lrs)
        score, preds[variant] = cross_f1(y["val"], z, ref_val, label_ids, halves)
        results[variant] = {
            **score,
            **head,
            **stats,
            "table_rows": rows_used,
            "dims": emb.shape[1],
            "table_mb_float32": round(rows_used * emb.shape[1] * 4 / 1e6, 1),
            "val_tokens_per_page_p50": float(np.median(tokens["val"])),
            "seconds": round(time.time() - t0, 1),
        }
        print(variant, json.dumps(results[variant]))

    taxonomy = json.loads(Path("data/taxonomy/labels.json").read_text())
    tier1 = {lab.id: lab.parent or lab.id for lab in claude.load_labels(taxonomy)}
    base = args.variants[0]
    paired = {
        v: agreement.f1_diff_paired(
            list(zip(preds[v], ref_val, strict=True)),
            list(zip(preds[base], ref_val, strict=True)),
            tier1,
        )
        for v in args.variants[1:]
    }
    report = {
        **provenance.stamp(
            {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}, "tier2_probe"
        ),
        "pages": {s: len(v) for s, v in part.items()},
        "labels": len(label_ids),
        "vocabulary_words": len(vocab),
        "note": "val only; cross-fitted thresholds, no top-label floor; test never read",
        "variants": results,
        f"val_minus_{base}_paired": paired,
    }
    args.out.write_text(json.dumps(report, indent=1) + "\n")


if __name__ == "__main__":
    main()
