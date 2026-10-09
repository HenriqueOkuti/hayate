"""Sample pages from the Common Crawl columnar index (Parquet) with DuckDB over HTTPS.

Two passes, so only a small part of the ~150 GB index is downloaded:

1. Census: per row group, count eligible pages per language. Reads only a few cheap columns
   (about 1 GB for a whole crawl).
2. Sample: per language, draw row groups with probability proportional to their page count
   (with replacement), then draw pages uniformly inside each drawn row group. Every eligible
   page has the same inclusion probability, and only the drawn row groups' URL and WARC
   columns are read.

The index is sorted by SURT key (reversed host), so a row group holds a contiguous slice of
hosts and languages cluster by TLD. That is why row groups are drawn by page count, not
uniformly.
"""

import gzip
import math
import random
import time
import urllib.request
from collections import Counter
from dataclasses import dataclass

import duckdb

BASE_URL = "https://data.commoncrawl.org/"

# Eligible: a successful HTML fetch whose record was not truncated.
ELIGIBLE = (
    "fetch_status = 200 AND content_mime_detected = 'text/html' AND content_truncated IS NULL"
)


@dataclass(frozen=True)
class RowGroup:
    file: str  # full URL of the index Parquet file
    row_group: int
    row_start: int  # first file row number, inclusive
    row_end: int  # last file row number, exclusive
    surt_lo: str
    surt_hi: str


def connect(threads: int = 8) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs")
    # data.commoncrawl.org answers 503 when busy; back off and retry instead of failing.
    con.execute("SET http_retries = 10; SET http_retry_wait_ms = 2000; SET http_retry_backoff = 2")
    con.execute(f"SET threads = {threads}")
    return con


def is_transient(e: duckdb.Error) -> bool:
    """Network trouble worth retrying, as opposed to a bad query."""
    return isinstance(e, duckdb.HTTPException | duckdb.IOException) or any(
        s in str(e) for s in ("partial file", "HTTP", "Connection", "timed out")
    )


def retrying(fn, *args, attempts: int = 8, wait_s: float = 15.0):
    """Call `fn(*args)`, retrying transient network errors with a growing wait. Common Crawl
    503s can outlast DuckDB's own retries."""
    for attempt in range(attempts):
        try:
            return fn(*args)
        except duckdb.Error as e:
            if not is_transient(e) or attempt == attempts - 1:
                raise
            time.sleep(wait_s * (attempt + 1) * (0.5 + random.random()))


def index_files(crawl: str, base_url: str = BASE_URL) -> list[str]:
    """URLs of the crawl's `subset=warc` index files."""
    url = f"{base_url}crawl-data/{crawl}/cc-index-table.paths.gz"
    with urllib.request.urlopen(url, timeout=60) as resp:
        paths = gzip.decompress(resp.read()).decode().split()
    return [base_url + p for p in paths if "/subset=warc/" in p]


def row_groups(con: duckdb.DuckDBPyConnection, file: str) -> list[RowGroup]:
    """Row group boundaries and SURT key ranges, from the file footer only."""
    rows = con.execute(
        """
        SELECT row_group_id, row_group_num_rows, stats_min_value, stats_max_value
        FROM parquet_metadata(?) WHERE path_in_schema = 'url_surtkey' ORDER BY row_group_id
        """,
        [file],
    ).fetchall()
    out, start = [], 0
    for rg, n, lo, hi in rows:
        out.append(RowGroup(file, rg, start, start + n, lo, hi))
        start += n
    return out


def census(con: duckdb.DuckDBPyConnection, file: str, languages: list[str]) -> list[dict]:
    """Eligible page counts per row group for each language (primary CLD2 language)."""
    rgs = row_groups(con, file)
    bucket = " ".join(f"WHEN file_row_number < {rg.row_end} THEN {i}" for i, rg in enumerate(rgs))
    counts = ", ".join(
        f"count(*) FILTER (WHERE content_languages LIKE '{lang}%') AS n_{lang}"
        for lang in languages
    )
    rows = con.execute(
        f"""
        SELECT CASE {bucket} END AS rg, {counts}
        FROM read_parquet(?, file_row_number = true)
        WHERE {ELIGIBLE}
        GROUP BY rg
        """,
        [file],
    ).fetchall()
    by_rg = {r[0]: r[1:] for r in rows}
    out = []
    for i, rg in enumerate(rgs):
        n = by_rg.get(i, (0,) * len(languages))
        out.append(
            {
                "file": rg.file,
                "row_group": rg.row_group,
                "row_start": rg.row_start,
                "row_end": rg.row_end,
                "surt_lo": rg.surt_lo,
                "surt_hi": rg.surt_hi,
                **{f"n_{lang}": n[j] for j, lang in enumerate(languages)},
            }
        )
    return out


def draw_clusters(weights: list[int], draws: int, seed: int) -> Counter:
    """Indices drawn with replacement, probability proportional to weight -> times drawn."""
    rng = random.Random(seed)
    return Counter(rng.choices(range(len(weights)), weights=weights, k=draws))


SAMPLE_COLUMNS = """
    url, url_host_registered_domain AS domain, url_host_tld AS tld, content_languages,
    fetch_time, warc_filename, warc_record_offset AS warc_offset,
    warc_record_length AS warc_length
"""


def sample_row_group(
    con: duckdb.DuckDBPyConnection,
    rg: dict,
    language: str,
    n: int,
    domain_cap: int,
    seed: int,
) -> list[dict]:
    """Up to `n` eligible pages of `language` from one row group, at most `domain_cap` per
    registered domain. Order is a seeded hash of the URL, so reruns pick the same pages."""
    cur = con.execute(
        f"""
        WITH pages AS (
            SELECT {SAMPLE_COLUMNS}, md5(url || ?) AS rank_key
            FROM read_parquet(?, file_row_number = true)
            WHERE url_surtkey BETWEEN ? AND ?
              AND file_row_number >= ? AND file_row_number < ?
              AND {ELIGIBLE} AND content_languages LIKE ?
        ),
        capped AS (
            SELECT *, row_number() OVER (PARTITION BY domain ORDER BY rank_key) AS nth_in_domain
            FROM pages
        )
        SELECT * EXCLUDE (nth_in_domain) FROM capped
        WHERE nth_in_domain <= ? ORDER BY rank_key LIMIT ?
        """,
        [
            str(seed),
            rg["file"],
            rg["surt_lo"],
            rg["surt_hi"],
            rg["row_start"],
            rg["row_end"],
            language + "%",
            domain_cap,
            n,
        ],
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def cap_domains(pages: list[dict], cap: int) -> list[dict]:
    """Keep at most `cap` pages per domain, in rank order (a domain can span row groups)."""
    seen: Counter = Counter()
    out = []
    for p in sorted(pages, key=lambda p: p["rank_key"]):
        if seen[p["domain"]] < cap:
            seen[p["domain"]] += 1
            out.append(p)
    return out


def per_cluster(total: int, draws: int) -> int:
    return math.ceil(total / draws)
