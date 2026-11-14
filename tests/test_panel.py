import json
import subprocess
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from hayate.evaluation import panel

ROOT = Path(__file__).resolve().parents[1]
TIER1 = {"1": "1", "2": "1", "3": "1", "9": "9"}  # 2 and 3 are children of 1
LABELS = [("1", None, ["Autos"]), ("2", "1", ["Autos", "Cars"]), ("3", "1", ["Autos", "Vans"])]
LABELS.append(("9", None, ["Health"]))


def lab(i, c=0.8):
    return {"id": i, "confidence": c}


def test_consensus_keeps_labels_with_enough_votes_most_voted_first():
    out = panel.consensus([[lab("9"), lab("2")], [lab("2")], [lab("2"), lab("9")]], TIER1)
    assert out == {"status": "agreed", "labels": ["2", "9"], "tier1": ["1", "9"]}
    # same votes: the label ranked higher on average leads, whatever the confidences say
    tie = panel.consensus([[lab("9", 0.6), lab("2", 0.5)], [lab("9", 0.6), lab("2", 0.99)]], TIER1)
    assert tie["labels"] == ["9", "2"]


def test_consensus_states():
    siblings = panel.consensus([[lab("2")], [lab("3")], [lab("9")]], TIER1)
    assert siblings == {"status": "tier1_only", "labels": [], "tier1": ["1"]}
    assert panel.consensus([[lab("2")], [lab("9")], []], TIER1)["status"] == "split"
    none = panel.consensus([[], [lab("9")], []], TIER1)
    assert none == {"status": "none", "labels": [], "tier1": []}
    assert panel.consensus([[lab("2")], []], TIER1)["status"] == "split"  # two members, one vote


def test_has_reference_per_tier():
    by_status = {s: {"status": s} for s in ("agreed", "tier1_only", "none", "split")}
    assert [s for s, r in by_status.items() if panel.has_reference(r, 2)] == ["agreed", "none"]
    with_t1 = [s for s, r in by_status.items() if panel.has_reference(r, 1)]
    assert with_t1 == ["agreed", "tier1_only", "none"]


def write_run(base: Path, name: str, main: list[list[dict]], repeat: list[list[dict]], inp: dict):
    run = base / name
    run.mkdir(parents=True)
    rows = [{"page_id": f"id{i}", "pass": "main", "labels": x} for i, x in enumerate(main)]
    rows += [{"page_id": f"id{i}", "pass": "repeat", "labels": x} for i, x in enumerate(repeat)]
    (run / "labels.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (run / "calls.jsonl").write_text(json.dumps({"ok": True, "pages": len(main)}) + "\n")
    cfg = {"model": name, "prompt": "p/prompt-v2.txt", "input": inp, "taxonomy_sha256": "abc"}
    stamp = {"commit": "c0ffee", "created": "2026-11-13", "config": cfg}
    (run / "run.json").write_text(json.dumps(stamp))


def test_panel_report_script(tmp_path):
    n = 4
    table = {"page_id": [f"id{i}" for i in range(n)], "lang": ["por", "eng"] * 2}
    pq.write_table(pa.table(table | {"text": ["secret page text"] * n}), tmp_path / "pages.parquet")
    nodes = [{"id": i, "parent": p, "path": path} for i, p, path in LABELS]
    (tmp_path / "labels.json").write_text(json.dumps({"source": {}, "labels": nodes}))
    inp = {"pages": str(tmp_path / "pages.parquet"), "labels": str(tmp_path / "labels.json")}
    inp["text_field"] = "text"
    base = tmp_path / "labels"
    # pages: id0 all agree on 2; id1 a and b say 2, c says 3; id2 three ways; id3 two say nothing
    write_run(base, "a", [[lab("2")], [lab("2")], [lab("2")], []], [[lab("2")]], inp)
    write_run(base, "b", [[lab("2")], [lab("2")], [lab("9")], []], [[lab("9")]], inp)
    write_run(base, "c", [[lab("2")], [lab("3")], [], [lab("9")]], [[lab("2")]], inp)
    write_run(base, "a-old", [[lab("9")], [lab("2")], [lab("2")], []], [], inp)
    (tmp_path / "panel.toml").write_text(
        f"""
[panel]
labels_dir = "{base}"
members = ["a", "b", "c"]
min_votes = 2
[output]
reference = "{tmp_path / "ref" / "reference.jsonl"}"
[report]
compare_runs = [{{ run = "a-old", leave_out = "a" }}]
"""
    )
    cmd = [sys.executable, str(ROOT / "scripts" / "panel_report.py"), "--config",
           str(tmp_path / "panel.toml"), "--out", str(tmp_path / "panel.json")]  # fmt: skip
    subprocess.run(cmd, check=True, capture_output=True)

    ref = [json.loads(x) for x in (tmp_path / "ref" / "reference.jsonl").read_text().splitlines()]
    assert [r["status"] for r in ref] == ["agreed", "agreed", "split", "none"]
    assert ref[1]["labels"] == ["2"] and ref[1]["votes"] == {"a": ["2"], "b": ["2"], "c": ["3"]}

    res = json.loads((tmp_path / "panel.json").read_text())
    assert res["reference"]["status"] == {"agreed": 2, "split": 1, "none": 1}
    assert res["reference"]["unanimous_top_label"] == 1
    assert res["pairwise"]["a vs b"]["tier2"]["f1"]["value"] == 0.667
    # c against what a and b agree on: 2 on id0 and id1, nothing on id3; id2 has no reference
    c = res["member_vs_others"]["c"]
    assert c["coverage"] == {"pages": 4, "tier2": 3, "tier1": 3}
    assert c["tier2"]["f1"]["value"] == 0.4 and c["tier1"]["f1"]["value"] == 0.8
    assert c["by_language"]["por"]["coverage"]["pages"] == 2
    assert c["tier2_labels"] == {"predicted": 3, "reference": 2}
    # only id0 has a leave-one-out reference for all three members
    common = res["member_vs_others_common_pages"]
    assert {m: common[m]["coverage"]["tier2"] for m in "abc"} == {"a": 1, "b": 1, "c": 1}
    assert common["a"]["tier2"]["f1"]["value"] == 1.0 and common["c"]["tier2"]["f1"]["value"] == 1.0
    assert (
        res["reference"]["label_shared_by_all"] == 1
        and res["reference"]["identical_label_sets"] == 1
    )
    assert len(res["pairwise_first_label_differences"]) == 3
    # a-old is scored without a's vote: b and c agree only on id0 (2), and it said 9 there
    old = res["other_runs"]["a-old"]
    assert old["leave_out"] == "a" and old["coverage"]["tier2"] == 1
    assert old["tier2"]["f1"]["value"] == 0.0
    assert res["repeat"]["b"]["tier2"]["f1"]["value"] == 0.0
    stability = res["reference_stability"]
    assert stability["pages"] == 1 and stability["same_status"] == 1
    assert res["runs"]["a"]["labels_per_page"] == 0.75 and res["runs"]["a"]["empty_pages"] == 1
    assert "secret page text" not in json.dumps(res)

    write_run(base, "d", [[lab("2")]], [], inp)  # a run on other pages is refused
    (tmp_path / "panel.toml").write_text(
        (tmp_path / "panel.toml").read_text().replace('"a-old", leave_out = "a"', '"d"')
    )
    bad = subprocess.run(cmd, capture_output=True, text=True)
    assert bad.returncode != 0 and "does not label the same pages" in bad.stderr
