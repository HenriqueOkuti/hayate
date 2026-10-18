"""Label a seeded page sample with headless Claude Code, in parallel batches, resumably.

Usage:
  PYTHONUNBUFFERED=1 uv run python scripts/label_pages.py --config configs/teacher.toml \
      --run pilot-v1 --prompt configs/teacher/prompt-v1.txt --pages 500 --repeat-frac 0.1

Pages are drawn per language (half pt, half en) in seeded page-id hash order, so two runs with
the same --pages and --seed see the same pages. Writes to data/labels/<run>/:
- labels.jsonl: one row per page and pass (main, or repeat for the re-labeled batches, sent
  with their pages shuffled);
- calls.jsonl: one row per call attempt, with usage, timing and errors;
- run.json: the provenance stamp.
--exclude-runs leaves out every domain an earlier run labeled, for a holdout. --backend ollama
labels with a local model instead (the [ollama] section of the config), --backend agy with a
model served by the Antigravity CLI (the [agy] section). A rerun skips
finished batches. On a usage-limit error the run stops after in-flight batches.
"""

import argparse
import hashlib
import json
import random
import subprocess
import tempfile
import threading
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import duckdb

from hayate import provenance
from hayate.teacher import agy, claude, ollama

LANGS = ("por", "eng")


def pick_pages(
    path: str, n: int, seed: int, inp: dict, exclude_domains: set[str]
) -> list[claude.Page]:
    per_lang = n // len(LANGS)
    field, fallback = inp["text_field"], inp["fallback_field"]
    rows = duckdb.sql(
        f"""
        select page_id, url, coalesce(title, '') title,
               coalesce(meta_description, '') description,
               case when length(coalesce({field}, '')) >= {int(inp["min_chars"])}
                    then {field} else coalesce({fallback}, '') end as text,
               row_number() over (partition by lang order by md5(page_id || '{seed}')) rk
        from read_parquet('{path}')
        where not list_contains($exclude, domain)
        qualify rk <= {per_lang}
        order by md5(page_id || '{seed}')
        """,
        params={"exclude": sorted(exclude_domains)},
    ).fetchall()
    return [claude.Page(*r[:5]) for r in rows]


def run_domains(pages_path: str, run_dir: Path) -> set[str]:
    """Domains of the pages an earlier run labeled, to keep a holdout apart from it."""
    page_ids = {r["page_id"] for r in map(json.loads, (run_dir / "labels.jsonl").open())}
    rows = duckdb.sql(f"select page_id, domain from read_parquet('{pages_path}')").fetchall()
    return {d for p, d in rows if p in page_ids}


def claude_version(binary: str) -> str:
    try:
        return subprocess.run([binary, "--version"], capture_output=True, text=True).stdout.strip()
    except OSError:
        return "unknown"


def batch_key(pages: list[claude.Page]) -> str:
    return hashlib.sha1("".join(p.page_id for p in pages).encode()).hexdigest()[:12]


def done_batches(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    return {(r["batch"], r["pass"]) for r in map(json.loads, path.read_text().splitlines())}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--prompt", type=Path, required=True)
    ap.add_argument("--pages", type=int, required=True)
    ap.add_argument("--seed", type=int, default=20261018)
    ap.add_argument("--model")
    ap.add_argument("--workers", type=int)
    ap.add_argument("--repeat-frac", type=float, default=0.0, help="batches labeled twice")
    ap.add_argument("--backend", choices=["claude", "ollama", "agy"], default="claude")
    ap.add_argument("--batch-size", type=int)
    ap.add_argument("--text-field", help="override [input] text_field, e.g. text_resiliparse")
    ap.add_argument("--fallback-field", help="override [input] fallback_field")
    ap.add_argument("--claude-bin", default="claude")
    ap.add_argument("--agy-bin", default="agy")
    ap.add_argument("--exclude-runs", nargs="*", default=[], help="skip these runs' domains")
    args = ap.parse_args()

    claude.check_env()
    cfg = tomllib.loads(args.config.read_text())
    inp, tch = cfg["input"], cfg["teacher"]
    inp["text_field"] = args.text_field or inp["text_field"]
    inp["fallback_field"] = args.fallback_field or inp["fallback_field"]
    olm = cfg.get("ollama", {})
    model = args.model or {"ollama": olm.get("model"), "agy": cfg.get("agy", {}).get("model")}.get(
        args.backend, tch["model"]
    )
    workers = args.workers or tch["workers"]
    labels_json = json.loads(Path(inp["labels"]).read_text())
    labels = claude.load_labels(labels_json)
    valid_ids = {lab.id for lab in labels}

    out = Path(cfg["output"]["dir"]) / args.run
    out.mkdir(parents=True, exist_ok=True)
    sp_file = out / "system-prompt.txt"
    prompt_text = args.prompt.read_text()
    sp_text = claude.system_prompt(prompt_text, labels)
    sp_file.write_text(sp_text)
    run_cfg = {
        **vars(args),
        "config": str(args.config),
        "prompt": str(args.prompt),
        "model": model,
        "workers": workers,
        "prompt_sha256": hashlib.sha256(prompt_text.encode()).hexdigest(),
        "claude_version": claude_version(args.claude_bin) if args.backend == "claude" else None,
        "ollama_version": ollama.version(olm["host"]) if args.backend == "ollama" else None,
        "ollama": olm if args.backend == "ollama" else None,
        "agy_version": agy.version(args.agy_bin) if args.backend == "agy" else None,
        "teacher": tch,
        "input": inp,
        "taxonomy_sha256": labels_json["source"]["sha256"],
    }
    (out / "run.json").write_text(json.dumps(provenance.stamp(run_cfg, "label_pages"), indent=1))

    excluded = set().union(
        *(run_domains(inp["pages"], Path(cfg["output"]["dir"]) / r) for r in args.exclude_runs)
    )
    pages = pick_pages(inp["pages"], args.pages, args.seed, inp, excluded)
    size = args.batch_size or cfg.get(args.backend, {}).get("batch_size") or tch["batch_size"]
    batches = [pages[i : i + size] for i in range(0, len(pages), size)]
    n_repeat = round(len(batches) * args.repeat_frac)
    jobs = [("main", b) for b in batches] + [("repeat", b) for b in batches[:n_repeat]]
    labels_path, calls_path = out / "labels.jsonl", out / "calls.jsonl"
    done = done_batches(labels_path)
    todo = [(ps, b) for ps, b in jobs if (batch_key(b), ps) not in done]
    print(f"{len(pages)} pages, {len(jobs)} batch jobs, {len(jobs) - len(todo)} already done")

    lock = threading.Lock()
    stop = threading.Event()
    workdir = tempfile.mkdtemp(prefix="hayate-teacher-")  # empty: no CLAUDE.md or settings

    def log_call(row: dict) -> None:
        with lock, calls_path.open("a") as f:
            f.write(json.dumps(row) + "\n")

    def run_job(pass_: str, batch: list[claude.Page]) -> int:
        key = batch_key(batch)
        if pass_ == "repeat":  # same pages in a different order, so the repeat is not a replay
            batch = random.Random(key).sample(batch, len(batch))
        sch = json.dumps(claude.schema(labels, len(batch)))
        stdin = claude.batch_input(batch, inp["max_chars"])
        for attempt in range(1, tch["retries"] + 2):
            if stop.is_set():
                return 0
            t0 = time.time()
            row = {"batch": key, "pass": pass_, "attempt": attempt, "pages": len(batch), "t0": t0}
            try:
                if args.backend == "agy":
                    res = agy.call(
                        agy.prompt(sp_text, stdin), sch, model, workdir, args.agy_bin,
                        tch["timeout_s"],
                    )  # fmt: skip
                elif args.backend == "ollama":
                    res = ollama.call(
                        stdin, sp_text, json.loads(sch), model, olm["host"], olm["num_ctx"],
                        tch["timeout_s"],
                    )  # fmt: skip
                else:
                    res = claude.call(
                        stdin, str(sp_file.resolve()), sch, model, workdir, args.claude_bin,
                        tch["timeout_s"],
                    )  # fmt: skip
                answer = claude.validate(res["structured_output"], len(batch), valid_ids)
            except claude.CallError as e:
                log_call(row | {"ok": False, "kind": e.kind, "error": str(e)[:300],
                                "wall_s": round(time.time() - t0, 2)})  # fmt: skip
                if e.kind == "limit":
                    stop.set()
                    print(f"usage limit hit, stopping: {e}")
                    return 0
                time.sleep(tch["backoff_s"] * 2 ** (attempt - 1) if e.kind == "transient" else 1)
                continue
            log_call(row | {"ok": True, "wall_s": round(time.time() - t0, 2),
                            "duration_ms": res.get("duration_ms"), "usage": res.get("usage"),
                            "model_usage": res.get("modelUsage"),
                            "cost_usd_list": res.get("total_cost_usd")})  # fmt: skip
            meta = {"batch": key, "pass": pass_, "model": model, "prompt": args.prompt.name}
            rows = [
                {"page_id": p.page_id, **meta, "labels": answer[local]}
                for local, p in zip(claude.local_ids(len(batch)), batch, strict=True)
            ]
            with lock, labels_path.open("a") as f:
                f.write("".join(json.dumps(r) + "\n" for r in rows))
            return len(batch)
        print(f"batch {key} ({pass_}) failed after {tch['retries'] + 1} attempts, skipped")
        return 0

    t_start, pages_done = time.time(), 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_job, ps, b) for ps, b in todo]
        for i, fut in enumerate(as_completed(futures), 1):
            pages_done += fut.result()
            elapsed = time.time() - t_start
            eta = elapsed / i * (len(todo) - i)
            print(f"{i}/{len(todo)} batches, {pages_done} pages, {elapsed:.0f}s, eta {eta:.0f}s")
    print("stopped on usage limit; rerun to resume" if stop.is_set() else "done")


if __name__ == "__main__":
    main()
