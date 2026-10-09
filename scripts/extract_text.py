"""Extract text from the fetched records with trafilatura and resiliparse, and pick the sample.

Usage: uv run python scripts/extract_text.py --config configs/pages.toml

Writes:
- extracted.parquet: every fetched candidate, with title, meta description, both texts and the
  time each extractor took;
- pages.parquet: the page sample. Per language, the first `pages_per_language` pages (in seeded
  URL-hash order) where either extractor gives at least `min_chars` characters;
- results/page-sample.json (committed): counts per language, no page text or URLs.
"""

import argparse
import hashlib
import json
import tomllib
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from hayate import provenance
from hayate.pages import extract, warc


def process(item: tuple[str, bytes]) -> dict:
    url, record_gz = item
    row = {"url": url, "error": ""}
    try:
        resp = warc.parse_record(record_gz)
        html = extract.decode(resp.body, resp.content_type)
        ex = extract.extract(html)
        row |= {
            "http_status": resp.status,
            "content_type": resp.content_type,
            "html_bytes": len(resp.body),
            **vars(ex),
        }
    except Exception as e:  # noqa: BLE001 - one bad page must not stop the run
        row["error"] = repr(e)[:500]
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    args = ap.parse_args()
    cfg = tomllib.loads(args.config.read_text())
    sample, ext = cfg["sample"], cfg["extract"]
    out = Path(cfg["output"]["dir"])

    cands = {c["url"]: c for c in pq.read_table(out / "candidates.parquet").to_pylist()}
    shards = sorted((out / "records").glob("part-*.parquet"))

    rows = []
    with ProcessPoolExecutor(max_workers=ext["workers"]) as pool:
        for path in shards:
            recs = pq.read_table(path).to_pylist()
            items = [(r["url"], r["record_gz"]) for r in recs]
            for row in pool.map(process, items, chunksize=16):
                c = cands[row["url"]]
                row |= {
                    "page_id": hashlib.md5(row["url"].encode()).hexdigest()[:16],
                    **{k: c[k] for k in c if k != "url"},
                }
                rows.append(row)
            print(f"{path.name}: {len(rows):,} pages extracted")

    table = pa.Table.from_pylist(rows)
    provenance.write_parquet(table, out / "extracted.parquet", cfg, "extract_text")

    picked, summary = [], {}
    for lang in sample["languages"]:
        ok = [
            r
            for r in rows
            if r["lang"] == lang
            and not r["error"]
            and max(len(r["text_trafilatura"]), len(r["text_resiliparse"])) >= ext["min_chars"]
        ]
        ok.sort(key=lambda r: r["rank_key"])
        chosen = ok[: sample["pages_per_language"]]
        print(
            f"{lang}: {len(ok):,} usable of {sum(r['lang'] == lang for r in rows):,}, "
            f"kept {len(chosen):,}"
        )
        picked.extend(chosen)
        summary[lang] = {
            "candidates": sum(c["lang"] == lang for c in cands.values()),
            "fetched": sum(r["lang"] == lang for r in rows),
            "extraction_errors": sum(r["lang"] == lang and bool(r["error"]) for r in rows),
            "usable": len(ok),
            "kept": len(chosen),
            "domains": len({r["domain"] for r in chosen}),
            "top_tlds": Counter(r["tld"] for r in chosen).most_common(10),
        }
    provenance.write_parquet(
        pa.Table.from_pylist(picked, schema=table.schema),
        out / "pages.parquet",
        cfg,
        "extract_text",
    )
    print(f"wrote {len(picked):,} pages -> {out / 'pages.parquet'}")

    results = Path(cfg["output"]["summary"])
    results.parent.mkdir(parents=True, exist_ok=True)
    stamp = provenance.stamp(cfg, "extract_text")
    results.write_text(json.dumps(stamp | {"languages": summary}, indent=2) + "\n")
    print(f"summary -> {results}")


if __name__ == "__main__":
    main()
