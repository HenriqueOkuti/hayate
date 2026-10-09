"""Fetch the candidates' WARC records from Common Crawl with HTTP range reads.

Usage: uv run python scripts/fetch_records.py --config configs/pages.toml

Reads candidates.parquet and writes records/part-NNNNN.parquet (url, record_gz: the raw gzipped
WARC record, byte for byte). Finished shards are skipped, so an interrupted run resumes.
Failed fetches are listed in records/failed.jsonl. Requests are rate-limited (`max_rps`), and a
403 block from CloudFront stops the run without writing the current shard; rerun it later.
"""

import argparse
import json
import sys
import threading
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from hayate import provenance
from hayate.pages import warc

USER_AGENT = "hayate-research/0.1 (+https://github.com/HenriqueOkuti/hayate)"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    args = ap.parse_args()
    cfg = tomllib.loads(args.config.read_text())
    base_url, fetch = cfg["crawl"]["base_url"], cfg["fetch"]
    out = Path(cfg["output"]["dir"])
    shards_dir = out / "records"
    shards_dir.mkdir(parents=True, exist_ok=True)

    cands = pq.read_table(
        out / "candidates.parquet", columns=["url", "warc_filename", "warc_offset", "warc_length"]
    ).to_pylist()
    size = fetch["shard_size"]
    shards = [cands[i : i + size] for i in range(0, len(cands), size)]

    limiter = warc.RateLimiter(fetch["max_rps"])
    blocked = threading.Event()
    limits = httpx.Limits(max_connections=fetch["workers"])
    with (
        httpx.Client(timeout=60, limits=limits, headers={"User-Agent": USER_AGENT}) as client,
        ThreadPoolExecutor(max_workers=fetch["workers"]) as pool,
        open(shards_dir / "failed.jsonl", "a") as failed,
    ):

        def one(c: dict) -> tuple[dict, bytes | None, str]:
            if blocked.is_set():
                return c, None, "skipped: blocked"
            try:
                rec = warc.fetch_record(
                    client,
                    base_url,
                    c["warc_filename"],
                    c["warc_offset"],
                    c["warc_length"],
                    fetch["retries"],
                    limiter,
                )
                return c, rec, ""
            except warc.BlockedError as e:
                blocked.set()
                return c, None, repr(e)
            except (warc.FetchError, httpx.HTTPError) as e:
                return c, None, repr(e)

        for n, shard in enumerate(shards):
            path = shards_dir / f"part-{n:05d}.parquet"
            if path.exists():
                continue
            rows, errors = [], []
            for c, rec, err in pool.map(one, shard):
                if rec is None:
                    errors.append({"url": c["url"], "error": err})
                else:
                    rows.append({"url": c["url"], "record_gz": rec})
            if blocked.is_set():
                sys.exit(f"blocked by CloudFront (403) in shard {n + 1}; not written, rerun later")
            failed.writelines(json.dumps(e) + "\n" for e in errors)
            table = pa.Table.from_pylist(
                rows, schema=pa.schema([("url", pa.string()), ("record_gz", pa.binary())])
            )
            provenance.write_parquet(table, path, cfg, "fetch_records")
            print(f"shard {n + 1}/{len(shards)}: {len(rows)}/{len(shard)} records")


if __name__ == "__main__":
    main()
