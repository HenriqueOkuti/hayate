"""Summarize a bulk label run and write its manifest, the label set's version record.

Usage:
  uv run python scripts/label_summary.py --run bulk-v2 --splits splits-v1

Reads data/labels/<run>/ (labels.jsonl, calls.jsonl, run.json, usage.jsonl), the page sample
and data/splits/<splits>.parquet. Writes:
- results/labels-<run>.json: counts only, no page text. Coverage (pages with a main label row,
  missing and duplicated pages), labels per page, empty pages, Tier-1 label counts per language,
  per split and for the most common TLDs, repeat consistency (main against repeat pass, at Tier 2
  and Tier 1, 95% bootstrap intervals), calls, failures, tokens, the served model ids and the plan
  meter readings;
- the same file's `manifest`: run, model alias and served ids, CLI versions, prompt and
  taxonomy hashes, the split assignment hash, file hashes, and `label_set_sha256`, a hash of the
  sorted main-pass labels that names the label set independently of row order.
"""

import argparse
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import duckdb

from hayate import provenance
from hayate.evaluation import agreement
from hayate.teacher import claude


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open() as f:
        return [json.loads(line) for line in f]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tld(domain: str) -> str:
    return domain.rsplit(".", 1)[-1]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--splits", required=True, help="name of data/splits/<name>.parquet")
    ap.add_argument("--pages", type=Path, default=Path("data/pages/pages.parquet"))
    ap.add_argument("--labels-json", type=Path, default=Path("data/taxonomy/labels.json"))
    ap.add_argument("--labels-dir", type=Path, default=Path("data/labels"))
    ap.add_argument("--splits-dir", type=Path, default=Path("data/splits"))
    ap.add_argument("--top-tlds", type=int, default=12)
    ap.add_argument("--out-dir", type=Path, default=Path("results"))
    args = ap.parse_args()

    run_dir = args.labels_dir / args.run
    rows = read_jsonl(run_dir / "labels.jsonl")
    calls = read_jsonl(run_dir / "calls.jsonl")
    usage = read_jsonl(run_dir / "usage.jsonl")
    run_json = json.loads((run_dir / "run.json").read_text())
    labels_json = json.loads(args.labels_json.read_text())
    tier1 = {lab.id: lab.parent or lab.id for lab in claude.load_labels(labels_json)}
    name = {lab["id"]: lab["path"][-1] for lab in labels_json["labels"]}
    splits_path = args.splits_dir / f"{args.splits}.parquet"
    meta = {
        r[0]: r[1:]
        for r in duckdb.sql(
            f"""select p.page_id, p.lang, p.domain, s.split from '{args.pages}' p
                join '{splits_path}' s using (page_id)"""
        ).fetchall()
    }

    def ids(labels: list[dict]) -> list[str]:
        return [x["id"] for x in labels]

    main_rows: dict[str, list[dict]] = {}
    repeat_rows: dict[str, list[dict]] = {}
    dup = Counter()
    for r in rows:
        target = main_rows if r["pass"] == "main" else repeat_rows
        if r["page_id"] in target:
            dup[r["pass"]] += 1
        target[r["page_id"]] = r["labels"]
    missing = sorted(meta.keys() - main_rows.keys())
    unknown = sorted(main_rows.keys() - meta.keys())

    def tier1_counts(page_ids) -> dict:
        c = Counter(t for p in page_ids for t in agreement.rollup(ids(main_rows[p]), tier1))
        return {f"{k} {name[k]}": v for k, v in c.most_common()}

    labeled = sorted(main_rows.keys() & meta.keys())
    by = defaultdict(lambda: defaultdict(list))
    for p in labeled:
        lang, domain, split = meta[p]
        by["lang"][lang].append(p)
        by["split"][split].append(p)
        by["tld"][tld(domain)].append(p)
    top_tlds = sorted(by["tld"], key=lambda t: -len(by["tld"][t]))[: args.top_tlds]

    def shape(page_ids: list[str]) -> dict:
        n = [len(main_rows[p]) for p in page_ids]
        return {
            "pages": len(n),
            "labels_per_page": round(statistics.fmean(n), 3) if n else None,
            "labels_per_page_hist": dict(sorted(Counter(n).items())),
            "empty_pages": sum(x == 0 for x in n),
        }

    ok = [c for c in calls if c["ok"]]
    served = Counter(m for c in ok for m in (c.get("model_usage") or {}))
    tok = Counter()
    for c in ok:
        tok.update({k: v for k, v in (c.get("usage") or {}).items() if isinstance(v, int)})
    rep = sorted(repeat_rows.keys() & main_rows.keys())
    label_lines = "".join(
        f"{p}\t" + json.dumps(main_rows[p], sort_keys=True) + "\n" for p in sorted(main_rows)
    )
    cfg = run_json["config"]
    manifest = {
        "run": args.run,
        "model_alias": cfg["model"],
        "served_models": dict(served),
        "claude_version_last_invocation": cfg.get("claude_version"),
        "prompt": cfg["prompt"],
        "prompt_sha256": cfg["prompt_sha256"],
        "taxonomy_sha256": cfg["taxonomy_sha256"],
        "run_commit_last_invocation": run_json["commit"],
        "splits": args.splits,
        "splits_stamp": provenance.read_stamp(splits_path)["commit"],
        "label_set_sha256": hashlib.sha256(label_lines.encode()).hexdigest(),
        "files_sha256": {
            f.name: sha256_file(f)
            for f in sorted(run_dir.iterdir())
            if f.suffix in {".jsonl", ".json", ".txt"}
        },
    }
    report = {
        **provenance.stamp({k: str(v) for k, v in vars(args).items()}, "label_summary"),
        "manifest": manifest,
        "coverage": {
            "sample_pages": len(meta),
            "labeled_pages": len(labeled),
            "missing_pages": len(missing),
            "unknown_pages": len(unknown),
            "duplicate_rows": dict(dup),
            "repeat_pages": len(rep),
        },
        "shape": {"all": shape(labeled)} | {k: shape(v) for k, v in sorted(by["lang"].items())},
        "tier1_by_lang": {k: tier1_counts(v) for k, v in sorted(by["lang"].items())},
        "tier1_by_split": {k: tier1_counts(v) for k, v in sorted(by["split"].items())},
        "tier1_by_tld": {t: tier1_counts(by["tld"][t]) for t in top_tlds},
        "pages_by_tld": {t: len(by["tld"][t]) for t in top_tlds},
        "repeat_consistency": agreement.summary(
            [(ids(main_rows[p]), ids(repeat_rows[p])) for p in rep], tier1
        ),
        "calls": {
            "ok": len(ok),
            "failed": len(calls) - len(ok),
            "failures_by_kind": dict(Counter(c.get("kind") for c in calls if not c["ok"])),
            "tokens": dict(tok),
            "tokens_per_labeled_page": round(
                sum(tok[k] for k in tok if k.endswith("tokens")) / max(len(labeled), 1), 1
            ),
            "wall_s_sum": round(sum(c["wall_s"] for c in calls), 1),
        },
        "usage_snapshots": usage,
    }
    out = args.out_dir / f"labels-{args.run}.json"
    out.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report["coverage"] | {"manifest": manifest["label_set_sha256"]}, indent=1))


if __name__ == "__main__":
    main()
