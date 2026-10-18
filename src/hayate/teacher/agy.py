"""Label page batches with a model served by the Antigravity CLI (`agy -p`), e.g. Gemini 4 Argon.

Runs on Henrique's personal subscription, never an API key. `agy` has no system-prompt or
tools-off flag, so the teacher prompt, a no-tools instruction and the pages go in one prompt
argument (Linux caps one argument at 128 KiB; keep batches small). The answer is constrained by
the same JSON schema (`--json-schema`) and returned as `structured_output`, like `claude.call`.
"""

import json
import subprocess

from hayate.teacher.claude import CallError

NO_TOOLS = (
    "Do not use any tools, do not read or write files and do not make a plan. "
    "Answer directly with the JSON for every page."
)
MAX_PROMPT_CHARS = 120_000


def prompt(system_prompt: str, batch: str) -> str:
    return f"{system_prompt}\n\n{NO_TOOLS}\n\n{batch}"


def call(
    full_prompt: str, schema_json: str, model: str, cwd: str, binary: str = "agy",
    timeout: float = 600,
) -> dict:  # fmt: skip
    if len(full_prompt) > MAX_PROMPT_CHARS:
        raise CallError("bad", f"prompt of {len(full_prompt)} chars is too long for one argument")
    cmd = [
        binary, "--model", model, "--disable-slash-commands", "--json-schema", schema_json,
        "--output-format", "json", f"-p={full_prompt}",
    ]  # fmt: skip
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout, stdin=subprocess.DEVNULL
        )
    except subprocess.TimeoutExpired as e:
        raise CallError("transient", "timeout") from e
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        result = None
    if not isinstance(result, dict) or result.get("status") != "SUCCESS":
        text = (proc.stdout + proc.stderr)[:500]
        low = text.lower()
        if "quota" in low or "limit" in low or "resource_exhausted" in low:
            raise CallError("limit", text)
        raise CallError("transient", text)
    if not isinstance(result.get("structured_output"), dict):
        raise CallError("bad", "no structured_output")
    usage = result.get("usage", {})
    return {
        "structured_output": result["structured_output"],
        "duration_ms": round(result.get("duration_seconds", 0) * 1000),
        "usage": {
            "input_tokens": usage.get("input_tokens", 0) - usage.get("cache_read_tokens", 0),
            "cache_read_input_tokens": usage.get("cache_read_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0) + usage.get("thinking_tokens", 0),
        },
        "num_turns": result.get("num_turns"),
    }


def version(binary: str = "agy") -> str:
    try:
        out = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=30)
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
