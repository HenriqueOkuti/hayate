"""The benchmark reference check (decision 0008), shared with go/cmd/tier1-bench/reference.go.

A busy desktop slows every configuration by about the same amount while the trials still agree,
so the trial spread cannot catch it. Each run times one fixed configuration before and after the
grid and compares the slower reading with the last quiet one of the same harness, profile and
model bundle, kept in results/bench-reference.json. A run more than THRESHOLD slower is marked
busy and does not replace the stored reading.
"""

import json
from pathlib import Path

MAX_CHARS = 3000
BATCH = 1
CALLS = 2000
THRESHOLD = 0.10
FILE = "bench-reference.json"


def key(harness: str, profile: str, bundle_sha256: str) -> str:
    return f"{harness}/{profile}/{bundle_sha256[:16]}"


def worse(a: dict, b: dict) -> dict:
    """The slower of two readings, quantile by quantile."""
    return {q: max(a[q], b[q]) for q in ("p50_us_per_page", "p99_us_per_page")}


def judge(
    before: dict, after: dict, base: dict | None, threshold: float = THRESHOLD
) -> tuple[float | None, str]:
    """("busy" above the threshold, "quiet" otherwise, "no-baseline" with nothing stored)."""
    if not base or base["p50_us_per_page"] <= 0:
        return None, "no-baseline"
    slow = round(worse(before, after)["p50_us_per_page"] / base["p50_us_per_page"] - 1, 4)
    return slow, "busy" if slow > threshold else "quiet"


def check(
    path: Path,
    k: str,
    before: dict,
    after: dict,
    accept: bool,
    created: str,
    commit: str,
    source: str,
) -> dict:
    """Judge a run; store its reading under k when it is quiet, has no baseline yet or accept."""
    stored = json.loads(path.read_text()) if path.exists() else {}
    base = stored.get(k)
    slow, status = judge(before, after, base)
    out = {
        "config": {"max_chars": MAX_CHARS, "batch": BATCH, "calls": CALLS},
        "before": before,
        "after": after,
        "baseline": base,
        "slowdown": slow,
        "threshold": THRESHOLD,
        "status": status,
        "baseline_updated": False,
    }
    if status != "busy" or accept:
        stored[k] = {**worse(before, after), "created": created, "commit": commit, "source": source}
        path.write_text(
            json.dumps(dict(sorted(stored.items())), indent=1) + "\n"
        )  # as Go writes it
        out["baseline_updated"] = True
    return out
