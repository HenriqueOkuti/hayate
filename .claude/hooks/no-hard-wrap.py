#!/usr/bin/env python3
"""Fail if Markdown prose is hard-wrapped; with --fix, unwrap it in place.

Project rule: one line per paragraph or list item, never wrapped at a fixed
width. See CLAUDE.md. With no file args, checks every tracked Markdown file
outside docs/research/ (dated notes are kept as written).
"""

import re
import subprocess
import sys

FENCE = re.compile(r"^\s*(```|~~~)")
# Lines that start a new block, so they are never a continuation of the line above.
BLOCK_START = re.compile(
    r"^\s*([-*+]\s|\d+[.)]\s|#|\||>|<|```|~~~|\[[^\]]+\]:|(\*\s*){3,}$|(-\s*){3,}$|(_\s*){3,}$)"
)
# Lines that can't be continued onto: tables, headings, HTML, link definitions.
NO_JOIN = re.compile(r"^\s*(\||#|<|>|\[[^\]]+\]:)")
HARD_BREAK = re.compile(r"(  |\\|<br\s*/?>)$")


def scan(lines):
    """Yield (index, joinable) for each line; joinable means it continues the line above."""
    in_fence = False
    in_front = bool(lines) and lines[0].rstrip() == "---"
    prev_text = False
    for i, line in enumerate(lines):
        s = line.rstrip("\n")
        if in_front:
            if i > 0 and s.rstrip() == "---":
                in_front = False
            yield i, False
            continue
        if FENCE.match(s):
            in_fence = not in_fence
            prev_text = False
            yield i, False
            continue
        if in_fence or not s.strip():
            prev_text = False
            yield i, False
            continue
        joinable = prev_text and not BLOCK_START.match(s)
        yield i, joinable
        prev = s
        prev_text = not NO_JOIN.match(prev) and not HARD_BREAK.search(prev)


def check(path, fix):
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()
    joins = [i for i, ok in scan(lines) if ok]
    if not joins:
        return []
    if fix:
        out = []
        for i, line in enumerate(lines):
            if i in joins:
                out[-1] = out[-1].rstrip("\n").rstrip() + " " + line.strip() + "\n"
            else:
                out.append(line)
        with open(path, "w", encoding="utf-8") as fh:
            fh.writelines(out)
        return []
    return [f"{path}:{i + 1}: continues the line above (hard-wrapped)" for i in joins]


def main(argv):
    fix = "--fix" in argv
    files = [a for a in argv if a != "--fix"]
    if not files:
        tracked = subprocess.run(
            ["git", "ls-files", "*.md"], capture_output=True, text=True, check=True
        ).stdout.split()
        files = [f for f in tracked if not f.startswith("docs/research/")]
    hits = [h for f in files for h in check(f, fix)]
    if hits:
        rule = "one line per paragraph or list item"
        print(f"Hard-wrapped Markdown (project rule: {rule}):", file=sys.stderr)
        print("\n".join(hits), file=sys.stderr)
        print("Run `make fix` to unwrap.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
