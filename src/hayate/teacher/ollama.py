"""Label page batches with a local open-weight model served by Ollama.

Same contract as `claude.call`: the answer is constrained by the same JSON schema (Ollama's
structured outputs) and returned as `structured_output`, so the driver validates both alike.
"""

import json

import httpx

from hayate.teacher.claude import CallError


def call(
    stdin: str,
    system_prompt: str,
    schema: dict,
    model: str,
    host: str,
    num_ctx: int,
    timeout: float = 600,
) -> dict:
    # Ollama silently truncates a prompt longer than num_ctx; refuse instead (about 3 chars/token
    # is a safe lower bound for pt and en text)
    if (len(system_prompt) + len(stdin)) / 3 > num_ctx:
        raise CallError("bad", f"prompt may not fit the {num_ctx}-token context")
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": stdin},
        ],
        "format": schema,
        "stream": False,
        "think": False,
        "options": {"num_ctx": num_ctx},
    }
    try:
        resp = httpx.post(f"{host}/api/chat", json=body, timeout=timeout)
    except httpx.HTTPError as e:
        raise CallError("transient", repr(e)) from e
    if resp.status_code != 200:
        raise CallError("transient", resp.text[:500])
    data = resp.json()
    try:
        answer = json.loads(data["message"]["content"])
    except (KeyError, json.JSONDecodeError) as e:
        raise CallError("bad", f"unparseable answer: {e}") from e
    if not isinstance(answer, dict):
        raise CallError("bad", "answer is not an object")
    return {
        "structured_output": answer,
        "duration_ms": round(data.get("total_duration", 0) / 1e6),
        "usage": {
            "input_tokens": data.get("prompt_eval_count", 0),
            "output_tokens": data.get("eval_count", 0),
        },
    }


def version(host: str) -> str:
    try:
        return httpx.get(f"{host}/api/version", timeout=10).json()["version"]
    except (httpx.HTTPError, KeyError, ValueError):
        return "unknown"
