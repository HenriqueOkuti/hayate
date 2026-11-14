"""Assign every sampled page to train, val or test, by related-domain group and by page.

Usage:
  uv run python scripts/make_splits.py --name splits-v1 \
      --train-runs 'pilot-*' --test-runs 'holdout-*'

Rules in hayate.data.splits (decision 0011): domains are joined into components by brand, same
text and near-duplicate text (the text the teacher sees, from configs/teacher.toml [input]);
components of the --test-runs pages' domains go to test (the holdout), of the --train-runs pages'
domains to train (prompt `v2` was tuned on the pilot pages), and every other component to test
below --test-frac and val below --test-frac + --val-frac of a seeded hash. Run names are glob
patterns over the top level of --labels-dir (so old/ is never matched); every page any matching
run labeled counts. Writes data/splits/<name>.parquet (page_id, domain, component, lang, split,
split_by_page, with the provenance stamp) and results/<name>.json with counts, leakage checks
and input hashes only, no page text. `assignment_sha256` hashes the sorted (page_id, split,
split_by_page) rows, so it names the assignment itself, independent of file metadata.
"""

import argparse
import hashlib
import json
import tomllib
from collections import Counter, defaultdict
from pathlib import Path

import duckdb
import pyarrow as pa

from hayate import provenance
from hayate.data.splits import SPLITS, Page, assign, components
from hayate.teacher import claude


def run_pages(labels_dir: Path, patterns: list[str]) -> tuple[list[str], set[str]]:
    runs = sorted({d.name for pat in patterns for d in labels_dir.glob(pat) if d.is_dir()})
    ids: set[str] = set()
    for r in runs:
        with (labels_dir / r / "labels.jsonl").open() as f:
            ids |= {json.loads(line)["page_id"] for line in f}
    return runs, ids


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def counts(pages: list[Page], split_of: dict[str, str], component_of: dict[str, str]) -> dict:
    out = {}
    for s in SPLITS:
        ps = [p for p in pages if split_of[p.page_id] == s]
        out[s] = {
            "pages": len(ps),
            "domains": len({p.domain for p in ps}),
            "pages_by_lang": dict(sorted(Counter(p.lang for p in ps).items())),
        }
    doms, comps = defaultdict(set), defaultdict(set)
    for p in pages:
        doms[p.domain].add(split_of[p.page_id])
        comps[component_of[p.domain]].add(split_of[p.page_id])
    out["domains_in_two_or_more_splits"] = sum(len(s) > 1 for s in doms.values())
    out["components_in_two_or_more_splits"] = sum(len(s) > 1 for s in comps.values())
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--name", required=True)
    ap.add_argument("--pages", type=Path, default=Path("data/pages/pages.parquet"))
    ap.add_argument("--labels-dir", type=Path, default=Path("data/labels"))
    ap.add_argument("--teacher-config", type=Path, default=Path("configs/teacher.toml"))
    ap.add_argument("--threshold", type=float, default=0.8, help="near-duplicate Jaccard")
    ap.add_argument("--train-runs", nargs="+", required=True)
    ap.add_argument("--test-runs", nargs="+", required=True)
    ap.add_argument("--seed", type=int, default=20261114)
    ap.add_argument("--val-frac", type=float, default=0.10, help="of the free components")
    ap.add_argument("--test-frac", type=float, default=0.08, help="of the free components")
    ap.add_argument("--out-dir", type=Path, default=Path("data/splits"))
    ap.add_argument("--report-dir", type=Path, default=Path("results"))
    args = ap.parse_args()

    inp = tomllib.loads(args.teacher_config.read_text())["input"]
    rows = duckdb.sql(
        f"select page_id, domain, lang, {claude.text_sql(inp)} from '{args.pages}' order by 1"
    ).fetchall()
    pages = [Page(*r[:3]) for r in rows]
    texts = {r[0]: r[3] or "" for r in rows}
    domain_of = {p.page_id: p.domain for p in pages}
    train_runs, train_ids = run_pages(args.labels_dir, args.train_runs)
    test_runs, test_ids = run_pages(args.labels_dir, args.test_runs)
    if not train_runs or not test_runs:
        raise SystemExit("no label runs match --train-runs or --test-runs")
    missing = (train_ids | test_ids) - domain_of.keys()
    if missing:
        raise SystemExit(f"{len(missing)} labeled pages are not in {args.pages}")
    train_domains = {domain_of[i] for i in train_ids}
    test_domains = {domain_of[i] for i in test_ids}
    fracs = {"val": args.val_frac, "test": args.test_frac}
    component_of, links = components(pages, texts, args.threshold)
    out = assign(pages, component_of, train_domains, test_domains, args.seed, fracs)
    comp_pages = Counter(component_of[p.domain] for p in pages)

    langs_of = defaultdict(set)
    for p in pages:
        langs_of[p.domain].add(p.lang)
    split = {i: s for i, (s, _) in out.items()}
    split_by_page = {i: s for i, (_, s) in out.items()}
    lines = "".join(f"{i}\t{a}\t{b}\n" for i, (a, b) in sorted(out.items()))
    config = {
        **{k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        "train_runs_matched": train_runs,
        "test_runs_matched": test_runs,
        "text_field": inp["text_field"],
        "fallback_field": inp["fallback_field"],
        "min_chars": inp["min_chars"],
    }
    inputs = {str(args.pages): sha256_file(args.pages)} | {
        str(args.labels_dir / r / "labels.jsonl"): sha256_file(args.labels_dir / r / "labels.jsonl")
        for r in train_runs + test_runs
    }
    report = {
        **provenance.stamp(config, "make_splits"),
        "assignment_sha256": hashlib.sha256(lines.encode()).hexdigest(),
        "inputs_sha256": inputs,
        "pages": len(pages),
        "domains": len({p.domain for p in pages}),
        "bilingual_domains": sum(len(s) > 1 for s in langs_of.values()),
        "components": {
            "count": len(comp_pages),
            "links": links,
            "multi_domain": sum(
                len({p.domain for p in pages if component_of[p.domain] == c}) > 1
                for c in comp_pages
                if comp_pages[c] > 1
            ),
            "largest_pages": [n for _, n in comp_pages.most_common(5)],
        },
        "forced": {
            name: {
                "runs": runs,
                "labeled_pages": len(ids),
                "domains": len(doms),
                "pages_in_their_components": sum(
                    component_of[p.domain] in {component_of[d] for d in doms} for p in pages
                ),
            }
            for name, runs, ids, doms in (
                ("train", train_runs, train_ids, train_domains),
                ("test", test_runs, test_ids, test_domains),
            )
        },
        "checks": {
            "test_run_pages_in_test": sum(split[i] == "test" for i in test_ids),
            "train_run_pages_in_train": sum(split[i] == "train" for i in train_ids),
            "pages_where_splits_differ": sum(a != b for a, b in out.values()),
        },
        "by_component": counts(pages, split, component_of),
        "by_page": counts(pages, split_by_page, component_of),
    }
    if report["by_component"]["components_in_two_or_more_splits"]:
        raise SystemExit("component split leaks a component across splits")  # assign() prevents it

    args.out_dir.mkdir(parents=True, exist_ok=True)
    table = pa.table(
        {
            "page_id": [p.page_id for p in pages],
            "domain": [p.domain for p in pages],
            "component": [component_of[p.domain] for p in pages],
            "lang": [p.lang for p in pages],
            "split": [split[p.page_id] for p in pages],
            "split_by_page": [split_by_page[p.page_id] for p in pages],
        }
    )
    provenance.write_parquet(table, args.out_dir / f"{args.name}.parquet", config, "make_splits")
    (args.report_dir / f"{args.name}.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: report[k] for k in ("components", "forced", "checks", "by_component")}))


if __name__ == "__main__":
    main()
