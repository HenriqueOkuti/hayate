import json
import subprocess
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from hayate.teacher import claude

ROOT = Path(__file__).resolve().parents[1]
LABELS = [
    claude.Label("1", None, ("Autos",)),
    claude.Label("2", "1", ("Autos", "Cars")),
    claude.Label("9", None, ("Health",)),
]
VALID = {lab.id for lab in LABELS}

# Stands in for `claude -p`: labels every page in its stdin with label 2.
FAKE = """#!/usr/bin/env python3
import json, re, sys
ids = re.findall(r'<page id="(p\\d+)">', sys.stdin.read())
out = {"pages": [{"page": i, "labels": [{"id": "2", "confidence": 0.9}]} for i in ids]}
print(json.dumps({"is_error": False, "structured_output": out, "duration_ms": 5,
                  "usage": {"input_tokens": 10, "output_tokens": 3}, "total_cost_usd": 0.0}))
"""


def test_system_prompt_lists_labels():
    sp = claude.system_prompt("Labels:\n{labels}", LABELS)
    assert "2 | Autos > Cars" in sp and "{labels}" not in sp


def test_schema_restricts_ids_and_pages():
    s = claude.schema(LABELS, 3)
    page = s["properties"]["pages"]["items"]
    assert page["properties"]["page"]["enum"] == ["p01", "p02", "p03"]
    assert page["properties"]["labels"]["maxItems"] == 5
    assert page["properties"]["labels"]["items"]["properties"]["id"]["enum"] == ["1", "2", "9"]


def test_batch_input_truncates_text():
    pages = [claude.Page("a", "https://x.test/", "T", "D", "x" * 50)]
    text = claude.batch_input(pages, max_chars=10)
    assert '<page id="p01">' in text and "x" * 10 + "\n</page>" in text


def lab(i, c=0.8):
    return {"id": i, "confidence": c}


def test_validate_sorts_by_confidence():
    ans = {"pages": [{"page": "p01", "labels": [lab("9", 0.4), lab("2", 0.9)]}]}
    assert [x["id"] for x in claude.validate(ans, 1, VALID)["p01"]] == ["2", "9"]


@pytest.mark.parametrize(
    "answer",
    [
        {"pages": []},  # missing page
        {"pages": [{"page": "p01", "labels": []}, {"page": "p01", "labels": []}]},  # repeated
        {"pages": [{"page": "p01", "labels": [lab("7")]}]},  # unknown label
        {"pages": [{"page": "p01", "labels": [lab("2"), lab("2")]}]},  # repeated label
        {"pages": [{"page": "p01", "labels": [lab("2", 1.5)]}]},  # confidence out of range
    ],
)
def test_validate_rejects(answer):
    with pytest.raises(claude.CallError):
        claude.validate(answer, 1, VALID)


def test_check_env_refuses_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    with pytest.raises(SystemExit):
        claude.check_env()


def test_driver_end_to_end_and_resume(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    fake = tmp_path / "fake-claude"
    fake.write_text(FAKE)
    fake.chmod(0o755)
    n = 6
    pq.write_table(
        pa.table(
            {
                "page_id": [f"id{i}" for i in range(n)],
                "url": [f"https://x{i}.test/" for i in range(n)],
                "domain": [f"x{i}.test" for i in range(n)],
                "title": ["t"] * n,
                "meta_description": ["d"] * n,
                "text_trafilatura": ["short"] * n,
                "text_resiliparse": ["long enough text " * 20] * n,
                "lang": ["por", "eng"] * (n // 2),
            }
        ),
        tmp_path / "pages.parquet",
    )
    labels_json = {
        "source": {"sha256": "abc"},
        "labels": [{"id": x.id, "parent": x.parent, "path": list(x.path)} for x in LABELS],
    }
    (tmp_path / "labels.json").write_text(json.dumps(labels_json))
    (tmp_path / "prompt.txt").write_text("Label pages.\n{labels}\n")
    (tmp_path / "teacher.toml").write_text(
        f"""
[input]
pages = "{tmp_path / "pages.parquet"}"
labels = "{tmp_path / "labels.json"}"
text_field = "text_trafilatura"
fallback_field = "text_resiliparse"
min_chars = 200
max_chars = 100
[teacher]
model = "sonnet"
batch_size = 2
workers = 2
retries = 1
backoff_s = 0
timeout_s = 30
[output]
dir = "{tmp_path / "labels"}"
"""
    )
    cmd = [
        sys.executable, str(ROOT / "scripts" / "label_pages.py"),
        "--config", str(tmp_path / "teacher.toml"), "--run", "t",
        "--prompt", str(tmp_path / "prompt.txt"), "--pages", str(n),
        "--repeat-frac", "0.5", "--claude-bin", str(fake),
    ]  # fmt: skip
    subprocess.run(cmd, check=True, capture_output=True, cwd=tmp_path)
    rows = [json.loads(x) for x in (tmp_path / "labels/t/labels.jsonl").read_text().splitlines()]
    main = [r for r in rows if r["pass"] == "main"]
    assert sorted(r["page_id"] for r in main) == [f"id{i}" for i in range(n)]
    assert len([r for r in rows if r["pass"] == "repeat"]) == 4  # 2 of 3 batches, rounded
    assert all(r["labels"] == [{"id": "2", "confidence": 0.9}] for r in rows)

    rerun = subprocess.run(cmd, check=True, capture_output=True, text=True, cwd=tmp_path)
    assert "5 already done" in rerun.stdout
    assert len((tmp_path / "labels/t/labels.jsonl").read_text().splitlines()) == len(rows)

    # a holdout that leaves out run t's domains has no pages left
    holdout = cmd[: cmd.index("--run")] + ["--run", "h"] + cmd[cmd.index("--run") + 2 :]
    out = subprocess.run(holdout + ["--exclude-runs", "t"], check=True, capture_output=True,
                         text=True, cwd=tmp_path)  # fmt: skip
    assert out.stdout.startswith("0 pages")


def test_ollama_call_parses_and_guards_context(monkeypatch):
    from hayate.teacher import ollama

    class Resp:
        status_code = 200

        def json(self):
            content = json.dumps({"pages": [{"page": "p01", "labels": []}]})
            return {"message": {"content": content}, "prompt_eval_count": 9, "eval_count": 3}

    monkeypatch.setattr(ollama.httpx, "post", lambda *a, **k: Resp())
    res = ollama.call("pages", "system", {}, "m", "http://x", num_ctx=100)
    assert res["structured_output"]["pages"][0]["page"] == "p01"
    assert res["usage"] == {"input_tokens": 9, "output_tokens": 3}
    with pytest.raises(claude.CallError):
        ollama.call("x" * 400, "system", {}, "m", "http://x", num_ctx=100)
