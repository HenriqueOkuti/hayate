"""Train/val/test splits by groups of related domains, with a by-page split alongside.

Rules (decision 0011):
- the unit is a component: registered domains joined when they share a brand label across
  suffixes (cointelegraph.com, cointelegraph.com.br), when two of their pages have the same text,
  or when two pages are near-duplicates (MinHash over 5-word shingles, then exact shingle Jaccard
  of at least `threshold`). Templates, mirrors and bot-check pages on many domains then fall into
  one split;
- a component holding a `test_domains` domain (the holdout) goes to test, one holding a
  `train_domains` domain (the prompt-tuning pilot) to train, in both splits; both at once is an
  error;
- every other component gets its split from a seeded SHA-256 hash of its key alone: test below
  `fracs["test"]`, val below test + val, else train. The split of a component does not depend on
  the rest of the sample, so it stays put when pages are added (unless a new page joins it to
  another component).
The by-page split keeps the forced components and hashes every other page on its own, so the gap
between the two shows how much related pages across splits flatter a score.
"""

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass

SPLITS = ("train", "val", "test")
SHINGLE = 5
N_HASH = 64
BANDS = 16
MAX_BUCKET = 500  # a bigger LSH bucket is boilerplate; exact-text matches still catch it
WORD = re.compile(r"\w+")


@dataclass(frozen=True)
class Page:
    page_id: str
    domain: str
    lang: str


def unit_hash(seed: int, key: str) -> float:
    """A number in [0, 1) from the seed and key alone."""
    return int(hashlib.sha256(f"{seed}:{key}".encode()).hexdigest(), 16) / 2**256


def brand(domain: str) -> str:
    return domain.split(".", 1)[0]


def words(text: str) -> list[str]:
    return WORD.findall(text.lower())


def shingles(ws: list[str]) -> set[int]:
    grams = (" ".join(ws[i : i + SHINGLE]) for i in range(max(len(ws) - SHINGLE + 1, 1)))
    return {int.from_bytes(hashlib.blake2b(g.encode(), digest_size=8).digest()) for g in grams}


def minhash(sh: set[int]) -> tuple[int, ...]:
    """One-permutation MinHash: the smallest shingle hash in each of N_HASH bins."""
    bins = [2**64] * N_HASH
    for x in sh:
        b = x % N_HASH
        if x < bins[b]:
            bins[b] = x
    return tuple(bins)


def near_duplicates(texts: dict[str, str], threshold: float) -> list[tuple[str, str]]:
    """Pairs of page ids whose shingle sets have Jaccard >= threshold (LSH candidates, checked)."""
    sh = {p: shingles(words(t)) for p, t in texts.items()}
    sig = {p: minhash(s) for p, s in sh.items() if len(s) >= SHINGLE}
    rows = N_HASH // BANDS
    cand: set[tuple[str, str]] = set()
    for band in range(BANDS):
        buckets = defaultdict(list)
        for p, s in sig.items():
            buckets[s[band * rows : (band + 1) * rows]].append(p)
        for ps in buckets.values():
            if 1 < len(ps) <= MAX_BUCKET:
                ps.sort()
                cand.update((a, b) for i, a in enumerate(ps) for b in ps[i + 1 :])
    return sorted((a, b) for a, b in cand if len(sh[a] & sh[b]) >= threshold * len(sh[a] | sh[b]))


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def components(
    pages: list[Page], texts: dict[str, str], threshold: float
) -> tuple[dict[str, str], dict[str, int]]:
    """domain -> component key (its smallest domain), and the count of joining links by kind."""
    uf = UnionFind()
    domain_of = {p.page_id: p.domain for p in pages}
    links = {"brand": 0, "same_text": 0, "near_duplicate": 0}

    def link(kind: str, a: str, b: str) -> None:
        if uf.find(a) != uf.find(b):
            links[kind] += 1
        uf.union(a, b)

    first: dict[tuple[str, str], str] = {}
    for d in sorted({p.domain for p in pages}):
        uf.find(d)
        link("brand", first.setdefault(("brand", brand(d)), d), d)
    for p in sorted(texts):
        if ws := words(texts[p]):
            key = ("text", hashlib.sha256(" ".join(ws).encode()).hexdigest())
            link("same_text", domain_of[first.setdefault(key, p)], domain_of[p])
    for a, b in near_duplicates(texts, threshold):
        link("near_duplicate", domain_of[a], domain_of[b])
    return {d: uf.find(d) for d in {p.domain for p in pages}}, links


def _by_hash(u: float, fracs: dict[str, float]) -> str:
    if u < fracs["test"]:
        return "test"
    return "val" if u < fracs["test"] + fracs["val"] else "train"


def assign(
    pages: list[Page],
    component_of: dict[str, str],
    train_domains: set[str],
    test_domains: set[str],
    seed: int,
    fracs: dict[str, float],
) -> dict[str, tuple[str, str]]:
    """page_id -> (component split, by-page split)."""
    forced_test = {component_of[d] for d in test_domains}
    forced_train = {component_of[d] for d in train_domains}
    clash = forced_test & forced_train
    if clash:
        raise ValueError(f"{len(clash)} components hold both a forced-train and forced-test domain")

    def forced(c: str) -> str | None:
        return "test" if c in forced_test else "train" if c in forced_train else None

    out = {}
    for p in pages:
        c = component_of[p.domain]
        f = forced(c)
        out[p.page_id] = (
            f or _by_hash(unit_hash(seed, c), fracs),
            f or _by_hash(unit_hash(seed, "page:" + p.page_id), fracs),
        )
    return out
