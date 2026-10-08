# Timeline

Weekend cadence. The plan assumes **about one working day per weekend** (~6–8 h). Each weekend has a single "done when" outcome. If a weekend is missed, everything shifts by one; the dates are not deadlines. Buffer weekends absorb slips.

Each step is a GitHub issue on the [Hayate roadmap board](https://github.com/users/HenriqueOkuti/projects/2). This file is the plan; the board is the status (Todo, Doing, Done, Skipped). Work happens in one branch and PR per issue, named `<issue>-<slug>`, with `Closes #N` in the PR.

## Phase 1: first trade-off curve (PT + EN)

Goal by mid-December 2026: three students on one accuracy vs latency plot, measured locally.

| # | Weekend | Work | Done when | Issue |
| --- | --- | --- | --- | --- |
| 1 | Oct 10–11 | Repo setup: git, `uv` env, taxonomy download with SHA/sha256 check. Decide label depth and scope (decision 0002). | `scripts/` fetches and verifies the taxonomy; label set frozen | [#2](https://github.com/HenriqueOkuti/hayate/issues/2) |
| 2 | Oct 17–18 | Page sample: DuckDB query on the CC index (PT + EN, per-domain cap), WARC range fetch, extraction with trafilatura **and** resiliparse | ~20k pages with URL, HTML pointer and both texts in `data/` | [#3](https://github.com/HenriqueOkuti/hayate/issues/3) |
| 3 | Oct 24–25 | Teacher pilot: prompt + JSON schema; 500 pages on a local open model (4070) and one API model; measure tokens, cost, agreement, repeat consistency. Decide the teacher (0003). | Pilot report in `results/`; teacher chosen | [#4](https://github.com/HenriqueOkuti/hayate/issues/4) |
| 4 | Oct 31–Nov 1 | Human-checked sample: a simple review tool; check ~300 pages (with a blind subset) | Gold sample v0 saved, teacher-vs-human F1 known | [#5](https://github.com/HenriqueOkuti/hayate/issues/5) |
| 5 | Nov 7–8 | Bulk labeling (≥ 20k pages, scale toward 100k if cheap), splits by domain | Versioned label set + train/val/test splits | [#6](https://github.com/HenriqueOkuti/hayate/issues/6) |
| 6 | Nov 14–15 | Evaluation harness (all metrics in [measurement.md](measurement.md)) + **tier-1 student** (hashed n-grams) | First F1 numbers vs teacher and vs human | [#7](https://github.com/HenriqueOkuti/hayate/issues/7) |
| 7 | Nov 21–22 | Benchmark harness: micro-benchmarks, Docker "small VPS" profile, raw timings → percentiles | Tier-1 latency p50/p99 at batch 1 and 32 | [#8](https://github.com/HenriqueOkuti/hayate/issues/8) |
| 8 | Nov 28–29 | **Tier-2 student** (Model2Vec / static embeddings + linear head) | Tier 2 on the plot | [#9](https://github.com/HenriqueOkuti/hayate/issues/9) |
| 9 | Dec 5–6 | **Tier-3 student**: fine-tune a small encoder on the GPU, export ONNX int8 | Tier 3 on the plot | [#10](https://github.com/HenriqueOkuti/hayate/issues/10) |
| 10 | Dec 12–13 | Write-up v0: the trade-off curve, what broke first as the model shrank, the teacher-noise ceiling | `results/` report + updated README | [#11](https://github.com/HenriqueOkuti/hayate/issues/11) |
| — | Dec 19–20 | **Buffer** | | |
| — | Dec 26 – Jan 3 | Holiday break | | |

## Phase 2: making it realistic (Jan–Feb 2027)

Rough order. Each item takes one or two weekends.

- **End-to-end request benchmark:** offline → local replay with `tc netem` → polite live fetch. ([#12](https://github.com/HenriqueOkuti/hayate/issues/12))
- **Fast path:** a URL + title + meta-description-only model as the cache-miss fallback, checked against Curlie URL labels. ([#13](https://github.com/HenriqueOkuti/hayate/issues/13))
- **Scale and noise:** 100k → 1M teacher labels; hard vs soft labels; stronger-teacher subset; candidate-set labels. Answers "how much does teacher noise limit the student?" ([#14](https://github.com/HenriqueOkuti/hayate/issues/14))
- **Knee of the curve:** sweep student size and input length. ([#15](https://github.com/HenriqueOkuti/hayate/issues/15))
- **Calibration and per-category thresholds.** ([#16](https://github.com/HenriqueOkuti/hayate/issues/16))
- Optional cloud calibration run (personal account) to fix the cost axis. ([#17](https://github.com/HenriqueOkuti/hayate/issues/17))

## Phase 3: open questions (Mar 2027 →)

- **Drift:** relabel a newer CC crawl, measure decay, and try incremental updates (online linear models, refreshed head) against full retraining. ([#18](https://github.com/HenriqueOkuti/hayate/issues/18))
- **Southeast Asian languages:** Indonesian, Vietnamese and Thai with little data. Zero-shot transfer first (SIB-200 for checks), then small teacher- labeled sets. ([#19](https://github.com/HenriqueOkuti/hayate/issues/19))
- **Coverage/freshness simulation:** URL/domain cache hit rates over a crawl timeline. ([#20](https://github.com/HenriqueOkuti/hayate/issues/20))

## Rules of thumb

- End each weekend with a short blog post in `site/src/content/blog/` (copy the previous one; set `weekend:` and `draft: false` when ready).
- Start each weekend by moving its issue to Doing on the board and reading the last decision record. End it with the "done when" artifact committed, even if partial.
- Spend money only after a pilot measures the real cost. Keep each paid run under a budget written in the decision record.
- Prefer finishing a thin end-to-end slice over polishing one stage.
