# ruff: noqa: E501
"""Blog chart: cumulative share of eligible pages vs CC index row groups, pt vs en.

Usage: uv run python scripts/blog_index_concentration.py data/pages/census.parquet \
    site/src/assets/cc-index-concentration.svg
"""

import sys

import duckdb

census, out = sys.argv[1], sys.argv[2]
rows = duckdb.sql(f"select n_por, n_eng from '{census}'").fetchall()
n = len(rows)

W, H = 720, 420
L, R, T, B = 64, 150, 56, 56
pw, ph = W - L - R, H - T - B


def curve(counts):
    counts = sorted(counts, reverse=True)
    total = sum(counts)
    pts, acc = [(0, 0.0)], 0
    for i, c in enumerate(counts, 1):
        acc += c
        pts.append((i, acc / total))
    return pts, total


def first_at(pts, share):
    return next(i for i, s in pts if s >= share)


def x(i):
    return L + pw * i / n


def y(s):
    return T + ph * (1 - s)


def path(pts):
    step = max(1, len(pts) // 600)
    keep = pts[::step] + [pts[-1]]
    return "M" + " L".join(f"{x(i):.1f},{y(s):.1f}" for i, s in keep)


por, tot_p = curve([r[0] for r in rows])
eng, tot_e = curve([r[1] for r in rows])
half_p, half_e = first_at(por, 0.5), first_at(eng, 0.5)

grid = "".join(
    f'<line class="grid" x1="{L}" x2="{L + pw}" y1="{y(s):.1f}" y2="{y(s):.1f}"/><text class="tick" x="{L - 8}" y="{y(s) + 4:.1f}" text-anchor="end">{int(s * 100)}%</text>'
    for s in (0, 0.25, 0.5, 0.75, 1)
)
xticks = "".join(
    f'<text class="tick" x="{x(i):.1f}" y="{T + ph + 20}" text-anchor="middle">{i:,}</text>'
    for i in (0, 250, 500, 750, 1000, 1250, n)
)

svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="t d">
<title id="t">Half of Portuguese pages sit in {half_p} of {n:,} index row groups</title>
<desc id="d">Cumulative share of eligible pages against the number of Common Crawl CC-MAIN-2026-39 index row groups, sorted from fullest to emptiest. Portuguese reaches 50% after {half_p} row groups; English after {half_e}.</desc>
<style>
  .ink {{ fill: #1e293b; }} .muted {{ fill: #64748b; }} .tick {{ fill: #64748b; font-size: 12px; }}
  .grid {{ stroke: #e2e8f0; stroke-width: 1; }} .ref {{ stroke: #94a3b8; stroke-width: 1; stroke-dasharray: 3 4; }}
  .por {{ stroke: #eb6834; }} .eng {{ stroke: #2a78d6; }} .pordot {{ fill: #eb6834; }} .engdot {{ fill: #2a78d6; }}
  .ring {{ stroke: #ffffff; }}
  text {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }}
  @media (prefers-color-scheme: dark) {{
    .ink {{ fill: #e2e8f0; }} .muted, .tick {{ fill: #94a3b8; }} .grid {{ stroke: #1e2d38; }} .ref {{ stroke: #64748b; }}
    .por {{ stroke: #d95926; }} .eng {{ stroke: #3987e5; }} .pordot {{ fill: #d95926; }} .engdot {{ fill: #3987e5; }}
    .ring {{ stroke: #0b1218; }}
  }}
</style>
<text class="ink" x="{L}" y="24" font-size="16" font-weight="600">Half of all Portuguese pages sit in {half_p} of {n:,} index chunks</text>
<text class="muted" x="{L}" y="42" font-size="12">Cumulative share of eligible pages, row groups sorted fullest first. CC-MAIN-2026-39 census.</text>
{grid}{xticks}
<line class="ref" x1="{L}" x2="{L + pw}" y1="{y(0.5):.1f}" y2="{y(0.5):.1f}"/>
<path class="por" d="{path(por)}" fill="none" stroke-width="2" stroke-linejoin="round"/>
<path class="eng" d="{path(eng)}" fill="none" stroke-width="2" stroke-linejoin="round"/>
<circle class="pordot ring" cx="{x(half_p):.1f}" cy="{y(0.5):.1f}" r="5" stroke-width="2"/>
<circle class="engdot ring" cx="{x(half_e):.1f}" cy="{y(0.5):.1f}" r="5" stroke-width="2"/>
<text class="ink" x="{x(half_p) + 10:.1f}" y="{y(0.5) - 10:.1f}" font-size="12">{half_p} chunks</text>
<text class="ink" x="{x(half_e) + 10:.1f}" y="{y(0.5) + 18:.1f}" font-size="12">{half_e} chunks</text>
<text class="ink" x="{L + pw + 12}" y="{y(1) + 4:.1f}" font-size="13" font-weight="600">Portuguese</text>
<text class="muted" x="{L + pw + 12}" y="{y(1) + 20:.1f}" font-size="12">{tot_p / 1e6:.0f}M pages</text>
<text class="ink" x="{L + pw + 12}" y="{y(0.86) + 4:.1f}" font-size="13" font-weight="600">English</text>
<text class="muted" x="{L + pw + 12}" y="{y(0.86) + 20:.1f}" font-size="12">{tot_e / 1e6:.0f}M pages</text>
<line class="por" x1="{L + pw + 2}" x2="{L + pw + 9}" y1="{y(1):.1f}" y2="{y(1):.1f}" stroke-width="2"/>
<line class="eng" x1="{L + pw + 2}" x2="{L + pw + 9}" y1="{y(0.86):.1f}" y2="{y(0.86):.1f}" stroke-width="2"/>
<text class="tick" x="{L + pw / 2}" y="{H - 10}" text-anchor="middle">Index row groups (chunks)</text>
</svg>
"""
with open(out, "w") as f:
    f.write(svg)
print(n, half_p, half_e, tot_p, tot_e)
