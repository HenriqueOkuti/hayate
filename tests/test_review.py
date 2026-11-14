import json
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from hayate.review import server, tasks
from hayate.review.store import ReviewError, Store
from hayate.teacher import claude

ROOT = Path(__file__).resolve().parents[1]
LABELS = [
    claude.Label("1", None, ("Autos",)),
    claude.Label("2", "1", ("Autos", "Cars")),
    claude.Label("9", None, ("Health",)),
]
N = 6  # pages id0..id5; the teacher's repeat pass covers id0 and id1, so those are blind


def lab(i, c=0.8):
    return {"id": i, "confidence": c}


@pytest.fixture
def sample(tmp_path):
    """A pages file, a teacher run and a gold config in tmp_path. Returns the config path."""
    pq.write_table(
        pa.table(
            {
                "page_id": [f"id{i}" for i in range(N)],
                "url": [f"https://x{i}.test/" for i in range(N)],
                "title": ["t"] * N,
                "meta_description": [None] * N,
                "text_trafilatura": ["short"] + ["A" * 10 + "B" * 30] * (N - 1),
                "text_resiliparse": ["fallback text"] * N,
                "lang": ["por", "eng"] * (N // 2),
            }
        ),
        tmp_path / "pages.parquet",
    )
    labels_json = {
        "source": {"sha256": "abc"},
        "labels": [{"id": x.id, "parent": x.parent, "path": list(x.path)} for x in LABELS],
    }
    (tmp_path / "labels.json").write_text(json.dumps(labels_json))
    (tmp_path / "prompt.txt").write_text("Rules: be right.\n\nLabels (id | path):\n{labels}\n")
    run = tmp_path / "labels" / "t"
    run.mkdir(parents=True)
    rows = [{"page_id": f"id{i}", "pass": "main", "labels": [lab("2")]} for i in range(N)]
    rows += [{"page_id": f"id{i}", "pass": "repeat", "labels": [lab("9")]} for i in range(2)]
    (run / "labels.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    inp = {
        "pages": str(tmp_path / "pages.parquet"),
        "labels": str(tmp_path / "labels.json"),
        "text_field": "text_trafilatura",
        "fallback_field": "text_resiliparse",
        "min_chars": 10,
        "max_chars": 10,
    }
    run_cfg = {"run": "t", "model": "sonnet", "prompt": str(tmp_path / "prompt.txt"), "input": inp}
    run_cfg["taxonomy_sha256"] = "abc"
    (run / "run.json").write_text(json.dumps({"config": run_cfg}))
    (tmp_path / "gold.toml").write_text(
        f"""
[sample]
labels_dir = "{tmp_path / "labels"}"
teacher_run = "t"
order_seed = 1
more_chars = 20
[output]
dir = "{tmp_path / "gold"}"
[server]
host = "127.0.0.1"
port = 0
[report]
compare_runs = ["t"]
"""
    )
    return tmp_path / "gold.toml"


def build(sample) -> list[dict]:
    return tasks.build(sample.parent / "labels" / "t", order_seed=1, more_chars=20)


def test_build_gives_the_teacher_input_and_modes(sample):
    todo = build(sample)
    by_id = {t["page_id"]: t for t in todo}
    assert len(todo) == N and [t["page_id"] for t in todo] != sorted(by_id)  # seeded order
    assert {p for p, t in by_id.items() if t["mode"] == "blind"} == {"id0", "id1"}
    assert by_id["id0"]["text"] == "fallback t"  # main field under min_chars: the fallback, cut
    assert by_id["id1"]["text"] == "A" * 10 and by_id["id1"]["more_text"] == "B" * 20
    assert by_id["id1"]["description"] == "" and by_id["id1"]["teacher"] == [lab("2")]
    assert tasks.guidelines("Rules.\n\nLabels (id | path):\n{labels}") == "Rules."


def test_store_blind_flow_and_resume(sample, tmp_path):
    todo = build(sample)
    store = Store(tmp_path / "reviews.jsonl", todo, LABELS)
    assert not store.teacher_visible("id0") and store.teacher_visible("id2")
    with pytest.raises(ReviewError, match="lock the blind answer first"):
        store.save("id0", "final", "labeled", ["2"], "", 1)
    store.save("id0", "blind", "labeled", ["9"], "", 4)
    assert store.status("id0") == "blind_done" and store.teacher_visible("id0")
    with pytest.raises(ReviewError, match="already locked"):
        store.save("id0", "blind", "labeled", ["2"], "", 1)
    store.save("id0", "final", "labeled", ["9", "2"], "both fit", 2)
    store.save("id2", "final", "labeled", [], "", 3)  # no topic
    store.save("id2", "final", "labeled", ["2"], "", 3)  # changed their mind: the last one wins
    store.save("id1", "final", "skipped", ["2"], "broken page", 1)  # skipping needs no blind answer
    assert not store.teacher_visible("id1")  # and does not reveal the teacher's labels

    again = Store(tmp_path / "reviews.jsonl", todo, LABELS)
    assert again.blind["id0"]["labels"] == ["9"] and again.final["id0"]["labels"] == ["9", "2"]
    assert again.final["id2"]["labels"] == ["2"] and again.final["id1"]["labels"] == []
    assert again.progress() == {"todo": 3, "blind_done": 0, "done": 2, "skipped": 1}
    assert (
        again.first_final["id2"]["labels"] == []
        and again.final["id0"]["i"] == store.position["id0"]
    )

    # flags are kept; a slip can void the blind answer but never replace it
    row = again.save(
        "id0", "final", "labeled", ["9"], "", 1, {"blind_void": 1, "more_opened": True}
    )
    assert row["blind_void"] and row["more_opened"] and not row["link_clicked"]
    assert not again.save("id2", "final", "labeled", ["2"], "", 1, {"blind_void": True})[
        "blind_void"
    ]
    with (tmp_path / "reviews.jsonl").open("a") as f:
        f.write('{"page_id": "id3", "sta')  # a crash mid-write
    torn = Store(tmp_path / "reviews.jsonl", todo, LABELS)
    assert torn.blind["id0"]["labels"] == ["9"] and torn.status("id3") == "todo"


@pytest.mark.parametrize(
    ("stage", "status", "labels"),
    [
        ("final", "labeled", ["7"]),  # unknown label
        ("final", "labeled", ["2", "2"]),  # repeated
        ("final", "labeled", ["1", "2"]),  # parent with its child
        ("final", "labeled", [2]),  # not a string
        ("blind", "labeled", ["2"]),  # blind answer on an assisted task
        ("final", "maybe", ["2"]),  # bad status
    ],
)
def test_store_rejects(sample, tmp_path, stage, status, labels):
    store = Store(tmp_path / "reviews.jsonl", build(sample), LABELS)
    with pytest.raises(ReviewError):
        store.save("id2", stage, status, labels, "", 1)
    assert not (tmp_path / "reviews.jsonl").exists()


def test_server_hides_teacher_labels_until_the_blind_answer_is_locked(sample, tmp_path):
    todo = build(sample)
    store = Store(tmp_path / "reviews.jsonl", todo, LABELS)
    httpd = server.serve(server.App(todo, LABELS, store, "Rules"), "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def call(path, body=None, host=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base + path, data, {"Content-Type": "application/json"})
        if host:
            req.add_header("Host", host)
        try:
            with urllib.request.urlopen(req) as res:
                return res.status, json.loads(res.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    try:
        with urllib.request.urlopen(base + "/") as res:
            assert b"Hayate gold review" in res.read()
        meta = call("/api/meta")[1]
        assert len(meta["labels"]) == 3 and meta["guidelines"] == "Rules"
        i = next(n for n, t in enumerate(todo) if t["mode"] == "blind")
        task = call(f"/api/task?i={i}")[1]
        assert task["teacher"] is None and task["status"] == "todo" and task["text"]
        review = {"i": i, "stage": "blind", "status": "labeled", "labels": ["9"], "seconds": 3}
        review["link_clicked"] = True
        code, task = call("/api/review", review)
        assert code == 200 and task["teacher"] == [lab("2")] and task["blind_labels"] == ["9"]
        code, task = call("/api/review", review | {"stage": "final", "labels": ["9", "2"]})
        assert task["status"] == "done" and task["final"]["labels"] == ["9", "2"]
        assert store.blind[todo[i]["page_id"]]["link_clicked"] and not task["final"]["blind_void"]
        assert call("/api/meta")[1]["tasks"][i]["status"] == "done"
        code, err = call("/api/review", review | {"stage": "final", "labels": ["1", "2"]})
        assert code == 400 and "children" in err["error"]
        assert call("/api/task?i=99")[0] == 400
        assert call("/api/meta", host="evil.test")[0] == 403
    finally:
        httpd.shutdown()
    with pytest.raises(SystemExit):
        server.serve(None, "0.0.0.0", 0)


def test_review_and_report_scripts(sample):
    cmd = [sys.executable, str(ROOT / "scripts" / "review_gold.py"), "--config", str(sample)]
    out = subprocess.run(cmd + ["--build-only"], check=True, capture_output=True, text=True)
    assert out.stdout.startswith("6 tasks (2 blind, 4 assisted)")
    gold = sample.parent / "gold"
    frozen = (gold / "tasks.jsonl").read_text()
    subprocess.run(cmd + ["--build-only"], check=True, capture_output=True)
    assert (gold / "tasks.jsonl").read_text() == frozen  # a second run reuses the tasks

    todo = [json.loads(x) for x in frozen.splitlines()]
    store = Store(gold / "reviews.jsonl", todo, LABELS)
    report = [sys.executable, str(ROOT / "scripts" / "gold_report.py"), "--config", str(sample),
              "--out", str(sample.parent / "gold.json")]  # fmt: skip
    unfinished = subprocess.run(report, capture_output=True, text=True)
    assert unfinished.returncode != 0 and "review not finished" in unfinished.stderr

    store.save("id0", "blind", "labeled", ["9"], "", 5)  # disagrees with the teacher (2)...
    store.save("id0", "final", "labeled", ["9", "2"], "", 5)  # ...then accepts its label too
    store.save("id1", "blind", "labeled", ["2"], "", 5)
    store.save("id1", "final", "labeled", ["2"], "", 5)
    store.save("id2", "final", "labeled", ["2"], "", 5)
    store.save("id3", "final", "labeled", ["2"], "", 5)
    store.save("id4", "final", "labeled", ["9"], "", 5)
    store.save("id5", "final", "skipped", [], "", 5)
    subprocess.run(report, check=True, capture_output=True)
    res = json.loads((sample.parent / "gold.json").read_text())
    scored = {"all": 5, "blind": 2, "blind_voided": 0, "assisted": 3, "por": 3, "eng": 2}
    assert res["sample"]["scored_pages"] == scored
    tvh = res["teacher_vs_human"]
    assert tvh["blind_before_reveal"]["tier2"]["f1"]["value"] == 0.5
    assert tvh["blind_final"]["tier2"]["precision"]["value"] == 1.0
    assert tvh["assisted_final"]["tier2"]["f1"]["value"] == 0.667
    diff = res["anchoring"]["f1_assisted_minus_blind_before_reveal"]
    assert diff["eng"]["pages_b"] == 1 and diff["equal_weight_per_language"]["pages_a"] == 3
    paired = res["anchoring"]["f1_blind_final_minus_blind_before_reveal"]
    assert paired["pages"] == 2 and paired["tier2"]["value"] == 0.3
    assert len(res["blind_before_reveal_by_order"]) == 2
    assert res["sample"]["skipped"]["assisted"] == 1
    assert res["teacher_secondaries_0_5"]["all_final"] == tvh["all_final"]
    after = res["anchoring"]["blind_answers_after_reveal"]
    assert after["pages_changed"] == 1 and after["labels_added_from_teacher"] == 1
    floor = res["noise_floor_on_blind_pages"]
    assert floor["teacher_repeat_vs_teacher"]["tier2"]["f1"]["value"] == 0.0
    assert floor["teacher_repeat_vs_human_blind"]["tier2"]["f1"]["value"] == 0.5
    same_run = res["other_runs_vs_human_blind"]["t"]
    assert same_run["tier2"] == tvh["blind_before_reveal"]["tier2"]
    assert same_run["f1_minus_reviewed_run"]["tier2"]["value"] == 0.0

    # a voided blind answer leaves the blind scoring; the page stays in the final scoring
    store.save("id0", "final", "labeled", ["9", "2"], "", 1, {"blind_void": True})
    subprocess.run(report, check=True, capture_output=True)
    res = json.loads((sample.parent / "gold.json").read_text())
    assert res["sample"]["scored_pages"] == scored | {"blind": 1, "blind_voided": 1}
    assert res["per_tier1_all_final"]["Autos"]["support"] == 4
    assert "A" * 10 not in json.dumps(res)  # no page text in the report
