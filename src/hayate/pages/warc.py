"""Fetch single WARC records from Common Crawl with HTTP range reads, and parse them."""

import io
import random
import threading
import time
from dataclasses import dataclass

import httpx
from fastwarc.warc import ArchiveIterator, WarcRecordType

RETRY_STATUS = {429, 500, 502, 503, 504}


class FetchError(Exception):
    pass


class BlockedError(Exception):
    """CloudFront refused the request (403): the client is sending too much. Stop, don't retry."""


class RateLimiter:
    """At most `per_second` calls to `wait()` per second, shared across threads."""

    def __init__(self, per_second: float):
        self.interval = 1.0 / per_second
        self.next_at = time.monotonic()
        self.lock = threading.Lock()

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            at = max(now, self.next_at)
            self.next_at = at + self.interval
        time.sleep(max(0.0, at - now))


def fetch_record(
    client: httpx.Client,
    base_url: str,
    warc_filename: str,
    offset: int,
    length: int,
    retries: int = 8,
    limiter: RateLimiter | None = None,
) -> bytes:
    """One gzip member: the WARC response record at `offset`. Retries busy responses with
    exponential backoff and jitter, since data.commoncrawl.org throttles with 503s."""
    headers = {"Range": f"bytes={offset}-{offset + length - 1}"}
    for attempt in range(retries + 1):
        if limiter:
            limiter.wait()
        try:
            resp = client.get(base_url + warc_filename, headers=headers)
            if resp.status_code == 206 and len(resp.content) == length:
                return resp.content
            if resp.status_code == 403:
                raise BlockedError(f"HTTP 403 from {resp.headers.get('server', '?')}")
            if resp.status_code not in RETRY_STATUS:
                raise FetchError(f"HTTP {resp.status_code}, {len(resp.content)} bytes")
        except httpx.TransportError:
            if attempt == retries:
                raise
        if attempt < retries:
            time.sleep(min(60.0, 2.0**attempt) * (0.5 + random.random()))
    raise FetchError(f"gave up after {retries} retries")


@dataclass
class HttpResponse:
    target_uri: str
    status: int
    content_type: str
    body: bytes


def parse_record(record_gz: bytes) -> HttpResponse:
    """The HTTP response inside one gzipped WARC record."""
    for rec in ArchiveIterator(io.BytesIO(record_gz), record_types=WarcRecordType.response):
        return HttpResponse(
            target_uri=rec.headers.get("WARC-Target-URI", ""),
            status=rec.http_headers.status_code if rec.http_headers else 0,
            content_type=rec.http_content_type or "",
            body=rec.reader.read(),
        )
    raise ValueError("no response record")
