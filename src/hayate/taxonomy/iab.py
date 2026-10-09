"""Fetch, verify and parse the IAB Content Taxonomy TSV, and derive the frozen label set.

The file is downloaded at a pinned commit and checked against a pinned sha256; it is never vendored.
"""

import csv
import hashlib
import io
import urllib.parse
import urllib.request
from dataclasses import dataclass

RAW_URL = "https://raw.githubusercontent.com/{repo}/{commit}/{path}"
HEADER_ROWS = 2  # a title row, then the column names


@dataclass(frozen=True)
class Node:
    id: str
    parent: str | None
    name: str
    path: tuple[str, ...]  # tier names from Tier 1 down to this node
    scd: bool  # Extension=SCD: a sensitive category

    @property
    def tier(self) -> int:
        return len(self.path)


class ChecksumError(Exception):
    pass


def raw_url(repo: str, commit: str, path: str) -> str:
    return RAW_URL.format(repo=repo, commit=commit, path=urllib.parse.quote(path))


def download(url: str, timeout: float = 30.0) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read()


def verify(data: bytes, sha256: str) -> None:
    got = hashlib.sha256(data).hexdigest()
    if got != sha256:
        raise ChecksumError(f"sha256 mismatch: expected {sha256}, got {got}")


def parse(data: bytes) -> list[Node]:
    """Parse the TSV: Unique ID, Parent, Name, Tier 1..4, Extension."""
    rows = list(csv.reader(io.StringIO(data.decode("utf-8")), delimiter="\t"))[HEADER_ROWS:]
    nodes = []
    for row in rows:
        if not any(cell.strip() for cell in row):
            continue
        row = [cell.strip() for cell in row] + [""] * (8 - len(row))
        node_id, parent, name, *tiers = row[:7]
        path = tuple(t for t in tiers if t)
        if not node_id or not path:
            raise ValueError(f"malformed taxonomy row: {row}")
        nodes.append(Node(node_id, parent or None, name, path, scd=row[7] == "SCD"))
    ids = [n.id for n in nodes]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate IDs in taxonomy")
    return nodes


def label_set(nodes: list[Node], max_tier: int, exclude_tier1: list[str]) -> list[Node]:
    """Nodes up to `max_tier`, minus whole Tier-1 subtrees named in `exclude_tier1`."""
    excluded = set(exclude_tier1)
    unknown = excluded - {n.name for n in nodes if n.tier == 1}
    if unknown:
        raise ValueError(f"unknown Tier-1 names to exclude: {sorted(unknown)}")
    return [n for n in nodes if n.tier <= max_tier and n.path[0] not in excluded]
