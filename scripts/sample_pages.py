"""Sample candidate pages from the Common Crawl columnar index (pointers only, no HTML).

Usage: uv run python scripts/sample_pages.py --config configs/pages.toml

1. census.parquet: eligible pages per index row group and language (reused if present).
2. candidates.parquet: per language, row groups drawn proportional to page count, pages drawn
   uniformly inside them with a per-domain cap. URL, domain and WARC pointer per page.
"""

import argparse
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from hayate import provenance
from hayate.pages import ccindex


def run_census(con, files: list[str], languages: list[str], path: Path, cfg: dict) -> pa.Table:
    if path.exists():
        print(f"census: reusing {path}")
        return pq.read_table(path)

    def one(file: str) -> list[dict]:
        return ccindex.retrying(ccindex.census, con.cursor(), file, languages)

    rows = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for i, part in enumerate(pool.map(one, files), 1):
            rows.extend(part)
            if i % 25 == 0:
                print(f"census: {i}/{len(files)} files")
    table = pa.Table.from_pylist(rows)
    provenance.write_parquet(table, path, cfg, "census")
    return table


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    args = ap.parse_args()
    cfg = tomllib.loads(args.config.read_text())
    crawl, sample = cfg["crawl"], cfg["sample"]
    out = Path(cfg["output"]["dir"])
    out.mkdir(parents=True, exist_ok=True)

    con = ccindex.connect()
    files = ccindex.index_files(crawl["id"], crawl["base_url"])
    census = run_census(con, files, sample["languages"], out / "census.parquet", cfg).to_pylist()

    candidates = []
    for li, lang in enumerate(sample["languages"]):
        total = sum(rg[f"n_{lang}"] for rg in census)
        want = round(sample["pages_per_language"] * sample["oversample"])
        draws = ccindex.draw_clusters(
            [rg[f"n_{lang}"] for rg in census],
            sample["clusters_per_language"],
            seed=sample["seed"] + li,
        )
        k = ccindex.per_cluster(want, sample["clusters_per_language"])
        print(f"{lang}: {total:,} eligible pages, {len(draws)} row groups, {k} pages per draw")

        def one(item, lang=lang, k=k):
            i, times = item
            return ccindex.retrying(
                ccindex.sample_row_group,
                con.cursor(),
                census[i],
                lang,
                k * times,
                sample["domain_cap"],
                sample["seed"],
            )

        pages = []
        with ThreadPoolExecutor(max_workers=2) as pool:
            for part in pool.map(one, sorted(draws.items())):
                pages.extend(part)
        pages = ccindex.cap_domains(pages, sample["domain_cap"])
        for p in pages:
            p["lang"] = lang
            p["crawl"] = crawl["id"]
        domains = len({p["domain"] for p in pages})
        print(f"{lang}: {len(pages):,} candidates from {domains:,} domains")
        candidates.extend(pages)

    seen, unique = set(), []
    for p in candidates:
        if p["url"] not in seen:
            seen.add(p["url"])
            unique.append(p)
    provenance.write_parquet(
        pa.Table.from_pylist(unique), out / "candidates.parquet", cfg, "sample_pages"
    )
    print(f"wrote {len(unique):,} candidates -> {out / 'candidates.parquet'}")


if __name__ == "__main__":
    main()
