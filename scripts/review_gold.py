"""Review a teacher run's labels by hand in a local page, to make the gold sample.

Usage:
  uv run python scripts/review_gold.py --config configs/gold.toml

The first run freezes the tasks (pages, review order, blind or assisted) in <dir>/tasks.jsonl;
later runs reuse them and resume from <dir>/reviews.jsonl, which only ever grows. Each start adds
a row to <dir>/sessions.jsonl with the code commit and the tasks file's hash. Open the printed
address in a browser; stop with Ctrl+C at any time. Score the result with scripts/gold_report.py.
"""

import argparse
import hashlib
import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path

from hayate import provenance
from hayate.review import server, tasks
from hayate.review.store import Store
from hayate.teacher import claude


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--port", type=int)
    ap.add_argument("--build-only", action="store_true", help="write the tasks and exit")
    args = ap.parse_args()
    cfg = tomllib.loads(args.config.read_text())
    smp = cfg["sample"]
    run_dir = Path(smp["labels_dir"]) / smp["teacher_run"]
    run_cfg = json.loads((run_dir / "run.json").read_text())["config"]
    out = Path(cfg["output"]["dir"])
    out.mkdir(parents=True, exist_ok=True)

    tasks_path = out / "tasks.jsonl"
    if tasks_path.exists():
        todo = [json.loads(x) for x in tasks_path.read_text().splitlines()]
    else:
        todo = tasks.build(run_dir, smp["order_seed"], smp["more_chars"])
        tasks_path.write_text("".join(json.dumps(t) + "\n" for t in todo))
        stamp = provenance.stamp(
            {"config": str(args.config), "sample": smp, "teacher_run_config": run_cfg},
            "review_gold",
        )
        (out / "run.json").write_text(json.dumps(stamp, indent=1))
    blind = sum(t["mode"] == "blind" for t in todo)
    print(f"{len(todo)} tasks ({blind} blind, {len(todo) - blind} assisted) in {tasks_path}")
    if args.build_only:
        return

    labels = claude.load_labels(json.loads(Path(run_cfg["input"]["labels"]).read_text()))
    store = Store(out / "reviews.jsonl", todo, labels)
    guide = tasks.guidelines(Path(run_cfg["prompt"]).read_text())
    session = {
        "started": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": provenance.git_commit(),
        "tasks_sha256": hashlib.sha256(tasks_path.read_bytes()).hexdigest(),
        "progress": store.progress(),
    }
    with (out / "sessions.jsonl").open("a") as f:
        f.write(json.dumps(session) + "\n")
    host, port = cfg["server"]["host"], args.port or cfg["server"]["port"]
    httpd = server.serve(server.App(todo, labels, store, guide), host, port)
    print(f"progress: {store.progress()}")
    print(f"review page: http://{host}:{port}/  (Ctrl+C to stop; decisions are saved as you go)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print(f"\nstopped. progress: {store.progress()}")


if __name__ == "__main__":
    main()
