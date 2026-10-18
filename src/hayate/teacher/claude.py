"""Label page batches with headless Claude Code (`claude -p`, tools off, JSON schema).

Runs on the Claude Code plan, never on an API key: `check_env` refuses to run if one is set.
Pages go in on stdin under short batch-local ids (p01, p02, ...); the schema restricts label ids
to the label set, and `validate` checks the answer again, since a schema is not a guarantee.
"""

import json
import os
import subprocess
from dataclasses import dataclass

API_KEY_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
MAX_LABELS = 5


@dataclass(frozen=True)
class Label:
    id: str
    parent: str | None
    path: tuple[str, ...]

    @property
    def tier(self) -> int:
        return len(self.path)


@dataclass(frozen=True)
class Page:
    page_id: str
    url: str
    title: str
    description: str
    text: str


class CallError(Exception):
    """A failed call. `kind` is "limit" (usage limit: stop), "transient" (retry) or "bad"."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def check_env() -> None:
    found = [v for v in API_KEY_VARS if os.environ.get(v)]
    if found:
        raise SystemExit(f"refusing to run: {', '.join(found)} is set (labeling runs on the plan)")


def load_labels(labels_json: dict) -> list[Label]:
    return [Label(n["id"], n["parent"], tuple(n["path"])) for n in labels_json["labels"]]


def system_prompt(template: str, labels: list[Label]) -> str:
    listing = "\n".join(f"{lab.id} | {' > '.join(lab.path)}" for lab in labels)
    return template.replace("{labels}", listing)


def local_ids(n: int) -> list[str]:
    return [f"p{i:02d}" for i in range(1, n + 1)]


def schema(labels: list[Label], n_pages: int) -> dict:
    label = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "enum": [lab.id for lab in labels]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["id", "confidence"],
        "additionalProperties": False,
    }
    page = {
        "type": "object",
        "properties": {
            "page": {"type": "string", "enum": local_ids(n_pages)},
            "labels": {"type": "array", "items": label, "maxItems": MAX_LABELS},
        },
        "required": ["page", "labels"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"pages": {"type": "array", "items": page}},
        "required": ["pages"],
        "additionalProperties": False,
    }


def batch_input(pages: list[Page], max_chars: int) -> str:
    parts = []
    for local, p in zip(local_ids(len(pages)), pages, strict=True):
        parts.append(
            f'<page id="{local}">\nURL: {p.url}\nTitle: {p.title}\n'
            f"Description: {p.description}\nText:\n{p.text[:max_chars]}\n</page>"
        )
    return f"Label these {len(pages)} pages.\n\n" + "\n\n".join(parts)


def validate(answer: dict, n_pages: int, valid_ids: set[str]) -> dict[str, list[dict]]:
    """Map local page id -> labels. Raises CallError("bad") on any missing, extra or bad entry."""
    expected = set(local_ids(n_pages))
    out: dict[str, list[dict]] = {}
    for entry in answer.get("pages", []):
        local = entry.get("page")
        if local not in expected or local in out:
            raise CallError("bad", f"unexpected or repeated page id {local!r}")
        labels = entry.get("labels", [])
        if len(labels) > MAX_LABELS:
            raise CallError("bad", f"{local}: {len(labels)} labels")
        seen = set()
        for lab in labels:
            if lab.get("id") not in valid_ids or lab["id"] in seen:
                raise CallError("bad", f"{local}: invalid or repeated label {lab.get('id')!r}")
            if not 0 <= lab.get("confidence", -1) <= 1:
                raise CallError("bad", f"{local}: confidence out of range")
            seen.add(lab["id"])
        out[local] = sorted(labels, key=lambda lab: -lab["confidence"])
    missing = expected - out.keys()
    if missing:
        raise CallError("bad", f"missing pages: {sorted(missing)}")
    return out


def call(
    stdin: str,
    system_prompt_file: str,
    schema_json: str,
    model: str,
    cwd: str,
    binary: str = "claude",
    timeout: float = 600,
) -> dict:
    """One headless call. Returns the parsed result JSON; raises CallError on failure."""
    cmd = [
        binary, "-p", "--model", model, "--tools", "", "--strict-mcp-config",
        "--no-session-persistence", "--setting-sources", "",
        "--system-prompt-file", system_prompt_file,
        "--json-schema", schema_json, "--output-format", "json",
    ]  # fmt: skip
    try:
        proc = subprocess.run(
            cmd, input=stdin, capture_output=True, text=True, cwd=cwd, timeout=timeout
        )
    except subprocess.TimeoutExpired as e:
        raise CallError("transient", "timeout") from e
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        result = None
    if not isinstance(result, dict) or result.get("is_error") or proc.returncode != 0:
        text = (proc.stdout + proc.stderr).lower()
        if "usage limit" in text or "limit reached" in text or "resets" in text:
            raise CallError("limit", (proc.stdout + proc.stderr)[:500])
        raise CallError("transient", (proc.stdout + proc.stderr)[:500])
    if not isinstance(result.get("structured_output"), dict):
        raise CallError("bad", "no structured_output")
    return result
