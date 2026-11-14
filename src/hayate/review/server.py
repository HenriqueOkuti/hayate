"""A local page for reviewing teacher labels, on the standard library's HTTP server.

Serves one HTML file and a small JSON API. It listens on localhost only and rejects requests
whose Host header is not local. A blind task is sent without the teacher's labels until its blind
answer is locked (`Store.teacher_visible`), so the page can't show them early.
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from hayate.review.store import ReviewError, Store
from hayate.teacher import claude

PAGE = Path(__file__).with_name("review.html")
LOCAL_HOSTS = ("127.0.0.1", "localhost", "[::1]")


class App:
    def __init__(self, tasks: list[dict], labels: list[claude.Label], store: Store, guide: str):
        self.tasks, self.labels, self.store, self.guide = tasks, labels, store, guide

    def meta(self) -> dict:
        return {
            "labels": [{"id": x.id, "parent": x.parent, "path": list(x.path)} for x in self.labels],
            "max_labels": claude.MAX_LABELS,
            "guidelines": self.guide,
            "tasks": [
                {"mode": t["mode"], "status": self.store.status(t["page_id"])} for t in self.tasks
            ],
        }

    def task(self, i: int) -> dict:
        if not 0 <= i < len(self.tasks):
            raise ReviewError("no such task")
        t = self.tasks[i]
        page_id = t["page_id"]
        blind, final = self.store.blind.get(page_id), self.store.final.get(page_id)
        return {k: v for k, v in t.items() if k != "teacher"} | {
            "i": i,
            "status": self.store.status(page_id),
            "teacher": t["teacher"] if self.store.teacher_visible(page_id) else None,
            "blind_labels": blind["labels"] if blind else None,
            "final": {k: final[k] for k in ("status", "labels", "note", "blind_void")}
            if final
            else None,
        }

    def review(self, body: dict) -> dict:
        i = body.get("i")
        if not isinstance(i, int) or not 0 <= i < len(self.tasks):
            raise ReviewError("no such task")
        labels = body.get("labels", [])
        if not isinstance(labels, list):
            raise ReviewError("labels must be a list")
        try:
            seconds = float(body.get("seconds", 0))
        except (TypeError, ValueError) as e:
            raise ReviewError("bad seconds") from e
        self.store.save(
            self.tasks[i]["page_id"], body.get("stage"), body.get("status"), labels,
            body.get("note", ""), seconds,
            {k: body.get(k) for k in ("more_opened", "link_clicked", "blind_void")},
        )  # fmt: skip
        return self.task(i)


def handler(app: App) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # quiet: the page reports progress itself
            pass

        def send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def reply(self, fn) -> None:
            if (self.headers.get("Host") or "").rsplit(":", 1)[0] not in LOCAL_HOSTS:
                return self.send(403, b'{"error": "local requests only"}')
            try:
                self.send(200, json.dumps(fn()).encode())
            except ReviewError as e:
                self.send(400, json.dumps({"error": str(e)}).encode())

        def do_GET(self) -> None:  # noqa: N802
            url = urlparse(self.path)
            if url.path == "/":
                self.send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/api/meta":
                self.reply(app.meta)
            elif url.path == "/api/task":
                raw = parse_qs(url.query).get("i", [""])[0]
                self.reply(lambda: app.task(int(raw) if raw.isdigit() else -1))
            else:
                self.send(404, b'{"error": "not found"}')

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/api/review" or self.headers.get("Content-Type") != "application/json":
                return self.send(404, b'{"error": "not found"}')

            def run() -> dict:
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                except ValueError as e:
                    raise ReviewError("bad JSON") from e
                if not isinstance(body, dict):
                    raise ReviewError("bad JSON")
                return app.review(body)

            self.reply(run)

    return Handler


def serve(app: App, host: str, port: int) -> ThreadingHTTPServer:
    if host not in ("127.0.0.1", "localhost"):
        raise SystemExit("the review page holds page text: serve it on localhost only")
    return ThreadingHTTPServer((host, port), handler(app))
