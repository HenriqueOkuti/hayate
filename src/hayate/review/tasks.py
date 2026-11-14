"""Build the review tasks of a gold sample from one teacher run.

A task is one page with exactly the input the teacher was sent (URL, title, description and the
same slice of text), the teacher's labels, and a review mode: "blind" for the pages the run
labeled twice (so the teacher's own repeat noise is known on the same pages), "assisted" for the
rest. Tasks hold page text, so they live under data/ and are never committed.
"""

import hashlib
import json
from pathlib import Path

import duckdb

from hayate.teacher import claude


def read_run(run_dir: Path) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    """A run's labels per page id: (main pass, repeat pass)."""
    main: dict[str, list[dict]] = {}
    repeat: dict[str, list[dict]] = {}
    for row in map(json.loads, (run_dir / "labels.jsonl").read_text().splitlines()):
        (main if row["pass"] == "main" else repeat)[row["page_id"]] = row["labels"]
    return main, repeat


def build(run_dir: Path, order_seed: int, more_chars: int) -> list[dict]:
    """One task per page of the run's main pass, in seeded hash order."""
    inp = json.loads((run_dir / "run.json").read_text())["config"]["input"]
    main, repeat = read_run(run_dir)
    rows = duckdb.sql(
        f"""
        select page_id, lang, url, coalesce(title, '') title,
               coalesce(meta_description, '') description, {claude.text_sql(inp)} as text
        from read_parquet('{inp["pages"]}')
        where list_contains($ids, page_id)
        """,
        params={"ids": sorted(main)},
    ).fetchall()
    missing = main.keys() - {r[0] for r in rows}
    if missing:
        raise SystemExit(f"{len(missing)} pages of the run are not in {inp['pages']}")
    cut = inp["max_chars"]
    tasks = [
        {
            "page_id": page_id,
            "lang": lang,
            "mode": "blind" if page_id in repeat else "assisted",
            "url": url,
            "title": title,
            "description": description,
            "text": text[:cut],
            "more_text": text[cut : cut + more_chars],
            "teacher": main[page_id],
        }
        for page_id, lang, url, title, description, text in rows
    ]
    return sorted(
        tasks, key=lambda t: hashlib.sha1(f"{order_seed}:{t['page_id']}".encode()).hexdigest()
    )


def guidelines(prompt_text: str) -> str:
    """The teacher prompt without its label list: the rules the reviewer follows too."""
    return prompt_text.split("Labels (id | path):")[0].strip()
