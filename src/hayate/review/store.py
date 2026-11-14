"""Append-only log of review decisions, one JSON row per save.

A blind task is answered in two stages: a "blind" row before the teacher's labels are shown
(only the first one counts, so it can't be redone after the reveal), then a "final" row. An
assisted task has only "final" rows. The last final row of a page wins. A skipped page (can't be
judged) is a final row with status "skipped" and stays out of the gold sample.

Every row also records the task's position in the review order and what the reviewer used that
the teacher never saw (the text behind the fold, the live page). A final row of a blind task can
set `blind_void`: the blind answer was a slip, and scoring leaves it out; it is never re-answered.
"""

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

from hayate.teacher import claude


class ReviewError(Exception):
    pass


class Store:
    def __init__(self, path: Path, tasks: list[dict], labels: list[claude.Label]):
        self.path = path
        self.tasks = {t["page_id"]: t for t in tasks}
        self.parent = {lab.id: lab.parent for lab in labels}
        self.lock = threading.Lock()
        self.position = {t["page_id"]: i for i, t in enumerate(tasks)}
        self.blind: dict[str, dict] = {}
        self.final: dict[str, dict] = {}
        self.first_final: dict[str, dict] = {}  # for timing: a later re-save is quick
        lines = path.read_text().splitlines() if path.exists() else []
        for n, line in enumerate(lines):
            try:
                self._apply(json.loads(line))
            except ValueError:
                if n < len(lines) - 1:
                    raise
                print(f"warning: ignoring a torn last line in {path}")

    def _apply(self, row: dict) -> None:
        if row["stage"] == "blind":
            self.blind.setdefault(row["page_id"], row)
        else:
            self.final[row["page_id"]] = row
            if row["status"] == "labeled":
                self.first_final.setdefault(row["page_id"], row)

    def status(self, page_id: str) -> str:
        """todo, blind_done (blind answer locked, final pending), done or skipped."""
        if page_id in self.final:
            return "skipped" if self.final[page_id]["status"] == "skipped" else "done"
        return "blind_done" if page_id in self.blind else "todo"

    def teacher_visible(self, page_id: str) -> bool:
        """A blind task shows the teacher's labels only once its blind answer is locked."""
        return self.tasks[page_id]["mode"] == "assisted" or page_id in self.blind

    def check_labels(self, ids: list) -> None:
        if not all(isinstance(i, str) and i in self.parent for i in ids):
            raise ReviewError("unknown label id")
        if len(set(ids)) != len(ids):
            raise ReviewError("repeated label")
        if len(ids) > claude.MAX_LABELS:
            raise ReviewError(f"more than {claude.MAX_LABELS} labels")
        both = [i for i in ids if self.parent[i] in ids]
        if both:
            raise ReviewError("a Tier-1 label together with one of its own children")

    def save(
        self,
        page_id: str,
        stage: str,
        status: str,
        labels: list,
        note: str,
        seconds: float,
        flags: dict | None = None,
    ) -> dict:
        if page_id not in self.tasks:
            raise ReviewError("unknown page")
        if stage not in ("blind", "final") or status not in ("labeled", "skipped"):
            raise ReviewError("bad stage or status")
        mode = self.tasks[page_id]["mode"]
        labels = [] if status == "skipped" else labels
        self.check_labels(labels)
        with self.lock:
            if stage == "blind":
                if mode != "blind" or status != "labeled":
                    raise ReviewError("a blind answer needs a blind task and labels (or no topic)")
                if page_id in self.blind:
                    raise ReviewError("the blind answer is already locked")
            elif mode == "blind" and status == "labeled" and page_id not in self.blind:
                raise ReviewError("lock the blind answer first")
            row = {
                "page_id": page_id,
                "i": self.position[page_id],
                "mode": mode,
                "stage": stage,
                "status": status,
                "labels": labels,
                "note": str(note)[:2000],
                "seconds": round(float(seconds), 1),  # time with the page visible
                "more_opened": bool((flags or {}).get("more_opened")),
                "link_clicked": bool((flags or {}).get("link_clicked")),
                "blind_void": bool(
                    mode == "blind" and stage == "final" and (flags or {}).get("blind_void")
                ),
                "saved_at": datetime.now(UTC).isoformat(timespec="seconds"),
            }
            with self.path.open("a") as f:
                f.write(json.dumps(row) + "\n")
                f.flush()
                os.fsync(f.fileno())
            self._apply(row)
        return row

    def progress(self) -> dict:
        states = [self.status(p) for p in self.tasks]
        return {s: states.count(s) for s in ("todo", "blind_done", "done", "skipped")}
