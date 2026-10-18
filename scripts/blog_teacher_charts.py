# ruff: noqa: E501
"""Blog charts for the W03 post, from the committed teacher pilot summary.

Usage: uv run python scripts/blog_teacher_charts.py results/teacher-pilot.json site/src/assets

Writes teacher-agreement.svg (Tier-2 Jaccard of each other teacher with Sonnet 5.5, against
Sonnet's own repeat) and prompt-shape.svg (label shape of prompts v0 and v2 on the holdout).
"""

import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text())
out = Path(sys.argv[2])
runs, pairs = report["runs"], report["agreement"]

STYLE = """<style>
  .ink { fill: #0b0b0b; } .muted, .tick { fill: #52514e; } .tick { font-size: 12px; }
  .grid { stroke: #e4e3df; stroke-width: 1; } .band { fill: #e4e3df; } .bandline { stroke: #8a8984; stroke-width: 1.5; stroke-dasharray: 4 4; }
  .s1 { fill: #2a78d6; } .s1l { stroke: #2a78d6; } .s2 { fill: #eb6834; }
  .ring { stroke: #fcfcfb; }
  text { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
  @media (prefers-color-scheme: dark) {
    .ink { fill: #f0efec; } .muted, .tick { fill: #c3c2b7; } .grid { stroke: #2e2e2c; } .band { fill: #2e2e2c; } .bandline { stroke: #8a8984; }
    .s1 { fill: #3987e5; } .s1l { stroke: #3987e5; } .s2 { fill: #d95926; } .ring { stroke: #1a1a19; }
  }
</style>"""


def svg(w, h, title, desc, body):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-labelledby="t d">
<title id="t">{title}</title>
<desc id="d">{desc}</desc>
{STYLE}
{body}
</svg>
"""


# Chart 1: agreement with Sonnet, with 95% intervals, against Sonnet's own repeat
rows = [
    ("Opus 5.5", "100 pages", pairs["pilot-v2 vs pilot-opus-v2"]["tier2_jaccard"]),
    ("Gemini 4 Argon", "100 pages", pairs["pilot-v2 vs pilot-argon-v2"]["tier2_jaccard"]),
    ("Gemma 4 12B", "300 holdout pages", pairs["holdout-v2 vs holdout-gemma-v2"]["tier2_jaccard"]),
]
self_rep = runs["holdout-v2"]["repeat_consistency"]["tier2_jaccard"]
W, H, L, R, T = 720, 300, 170, 40, 92
pw, row_h = W - L - R, 52


def x(v):
    return L + pw * v


body = [
    '<text class="ink" x="16" y="26" font-size="16" font-weight="600">Opus and Argon land near Sonnet&#8217;s own rerun; Gemma is far off</text>',
    '<text class="muted" x="16" y="45" font-size="12">Tier-2 Jaccard with Sonnet 5.5 labels, prompt v2, dots with 95% intervals. Gray band: Sonnet against its own rerun.</text>',
]
ph = row_h * len(rows)
for v in (0, 0.25, 0.5, 0.75, 1):
    body.append(f'<line class="grid" x1="{x(v):.1f}" x2="{x(v):.1f}" y1="{T - 12}" y2="{T + ph}"/>')
    body.append(
        f'<text class="tick" x="{x(v):.1f}" y="{T + ph + 18}" text-anchor="middle">{v:g}</text>'
    )
lo, hi = self_rep["ci95"]
body.append(
    f'<rect class="band" x="{x(lo):.1f}" y="{T - 12}" width="{x(hi) - x(lo):.1f}" height="{ph + 12}" opacity="0.8"/>'
)
body.append(
    f'<line class="bandline" x1="{x(self_rep["mean"]):.1f}" x2="{x(self_rep["mean"]):.1f}" y1="{T - 12}" y2="{T + ph}"/>'
)
body.append(
    f'<text class="muted" x="{x(self_rep["mean"]):.1f}" y="{T - 18}" font-size="12" text-anchor="middle">Sonnet vs itself {self_rep["mean"]:.2f}</text>'
)
for i, (name, pages, a) in enumerate(rows):
    cy = T + row_h * i + row_h / 2
    body.append(
        f'<text class="ink" x="{L - 12}" y="{cy - 2:.1f}" font-size="13" text-anchor="end">{name}</text>'
    )
    body.append(
        f'<text class="muted" x="{L - 12}" y="{cy + 13:.1f}" font-size="11" text-anchor="end">{pages}</text>'
    )
    lo, hi = a["ci95"]
    body.append(
        f'<line class="s1l" x1="{x(lo):.1f}" x2="{x(hi):.1f}" y1="{cy:.1f}" y2="{cy:.1f}" stroke-width="2" stroke-linecap="round"/>'
    )
    body.append(
        f'<circle class="s1 ring" cx="{x(a["mean"]):.1f}" cy="{cy:.1f}" r="6" stroke-width="2"/>'
    )
    label_x = x(hi) + 8 if a["mean"] < 0.6 else x(lo) - 8
    anchor = "start" if a["mean"] < 0.6 else "end"
    body.append(
        f'<text class="ink" x="{label_x:.1f}" y="{cy + 4:.1f}" font-size="12" text-anchor="{anchor}">{a["mean"]:.2f}</text>'
    )
body.append(
    f'<text class="muted" x="{L + pw / 2:.1f}" y="{T + ph + 38}" font-size="12" text-anchor="middle">Jaccard: shared labels / all labels used, averaged over pages (1 = identical)</text>'
)
desc = "; ".join(
    f"{n} {a['mean']:.2f} (95% interval {a['ci95'][0]:.2f} to {a['ci95'][1]:.2f}, {p})"
    for n, p, a in rows
)
(out / "teacher-agreement.svg").write_text(
    svg(
        W,
        H,
        "Agreement of each teacher with Sonnet 5.5",
        f"Tier-2 Jaccard with Sonnet 5.5: {desc}. Sonnet against its own rerun: {self_rep['mean']:.2f} ({self_rep['ci95'][0]:.2f} to {self_rep['ci95'][1]:.2f}).",
        "\n".join(body),
    )
)

# Chart 2: label shape of v0 and v2 on the holdout, one small panel per measure
v0, v2 = runs["holdout-v0"]["labels"], runs["holdout-v2"]["labels"]
panels = [
    ("Labels per page", v0["labels_per_page"], v2["labels_per_page"], "{:.2f}", 2.5),
    (
        "Pages with a parent and its child",
        100 * v0["pages_with_parent_and_child"] / v0["pages"],
        100 * v2["pages_with_parent_and_child"] / v2["pages"],
        "{:.1f}%",
        20,
    ),
    (
        "Empty pages",
        100 * v0["empty_pages"] / v0["pages"],
        100 * v2["empty_pages"] / v2["pages"],
        "{:.1f}%",
        10,
    ),
]
W, H, T, B = 720, 300, 96, 40
pw_each, gap = 200, 34
ph = H - T - B
body = [
    '<text class="ink" x="16" y="26" font-size="16" font-weight="600">Prompt v2 cleans up the labels</text>',
    f'<text class="muted" x="16" y="45" font-size="12">Sonnet 5.5 on the {v2["pages"]} holdout pages, prompts v0 and v2. Each panel has its own scale.</text>',
    '<rect class="s2" x="16" y="60" width="12" height="12" rx="2"/><text class="ink" x="34" y="70" font-size="12">v0 (plain prompt)</text>',
    '<rect class="s1" x="160" y="60" width="12" height="12" rx="2"/><text class="ink" x="178" y="70" font-size="12">v2 (final prompt)</text>',
]
for i, (name, a, b, fmt, top) in enumerate(panels):
    px = 16 + i * (pw_each + gap)
    base = T + ph
    body.append(f'<line class="grid" x1="{px}" x2="{px + pw_each}" y1="{base}" y2="{base}"/>')
    body.append(
        f'<text class="muted" x="{px + pw_each / 2}" y="{base + 20}" font-size="12" text-anchor="middle">{name}</text>'
    )
    bw = 56
    for j, (val, cls) in enumerate(((a, "s2"), (b, "s1"))):
        bx = px + pw_each / 2 - bw - 1 + j * (bw + 2)
        bh = max(ph * val / top, 2)
        r = min(4, bh / 2)
        body.append(
            f'<path class="{cls}" d="M{bx},{base} V{base - bh + r} Q{bx},{base - bh} {bx + r},{base - bh} H{bx + bw - r} Q{bx + bw},{base - bh} {bx + bw},{base - bh + r} V{base} Z"/>'
        )
        body.append(
            f'<text class="ink" x="{bx + bw / 2}" y="{base - bh - 6:.1f}" font-size="12" text-anchor="middle">{fmt.format(val)}</text>'
        )
desc = "; ".join(f"{n}: v0 {f.format(a)}, v2 {f.format(b)}" for n, a, b, f, _ in panels)
(out / "prompt-shape.svg").write_text(
    svg(
        W,
        H,
        "Label shape of prompts v0 and v2 on the holdout",
        f"Sonnet 5.5 on {v2['pages']} holdout pages. {desc}.",
        "\n".join(body),
    )
)
print(out / "teacher-agreement.svg", out / "prompt-shape.svg")
