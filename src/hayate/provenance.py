"""Record which config and code version produced an output file."""

import json
import subprocess
from datetime import UTC, datetime

import pyarrow as pa
import pyarrow.parquet as pq


def git_commit() -> str:
    """Current commit, with a -dirty suffix if the work tree has uncommitted changes."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return sha + ("-dirty" if dirty else "")


def stamp(config: dict, step: str) -> dict:
    return {
        "step": step,
        "commit": git_commit(),
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "config": config,
    }


def write_parquet(table: pa.Table, path, config: dict, step: str) -> None:
    """Write `table` with the provenance stamp in the Parquet key-value metadata (key `hayate`)."""
    meta = dict(table.schema.metadata or {})
    meta[b"hayate"] = json.dumps(stamp(config, step)).encode()
    pq.write_table(table.replace_schema_metadata(meta), path, compression="zstd")


def read_stamp(path) -> dict:
    return json.loads(pq.read_schema(path).metadata[b"hayate"])
