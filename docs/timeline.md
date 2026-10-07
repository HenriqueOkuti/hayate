# Timeline

Weekend cadence. The plan assumes **about one working day per weekend**
(~6–8 h). Each weekend has a single "done when" outcome. If a weekend is
missed, everything shifts by one; the dates are not deadlines. Buffer weekends
absorb slips.

Status keys: `todo` · `doing` · `done` · `skipped`.

## Phase 1: first trade-off curve (PT + EN)

Goal by mid-December 2026: three students on one accuracy vs latency plot,
measured locally.

| # | Weekend | Work | Done when | Status |
| --- | --- | --- | --- | --- |
| 1 | Oct 10–11 | Repo setup: git, `uv` env, taxonomy download with SHA/sha256 check. Decide label depth and scope (decision 0002). | `scripts/` fetches and verifies the taxonomy; label set frozen | todo |
| 2 | Oct 17–18 | Page sample: DuckDB query on the CC index (PT + EN, per-domain cap), WARC range fetch, extraction with trafilatura **and** resiliparse | ~20k pages with URL, HTML pointer and both texts in `data/` | todo |
| 3 | Oct 24–25 | Teacher pilot: prompt + JSON schema; 500 pages on a local open model (4070) and one API model; measure tokens, cost, agreement, repeat consistency. Decide the teacher (0003). | Pilot report in `results/`; teacher chosen | todo |
| 4 | Oct 31–Nov 1 | Human-checked sample: a simple review tool; check ~300 pages (with a blind subset) | Gold sample v0 saved, teacher-vs-human F1 known | todo |
| 5 | Nov 7–8 | Bulk labeling (≥ 20k pages, scale toward 100k if cheap), splits by domain | Versioned label set + train/val/test splits | todo |
| 6 | Nov 14–15 | Evaluation harness (all metrics in [measurement.md](measurement.md)) + **tier-1 student** (hashed n-grams) | First F1 numbers vs teacher and vs human | todo |
| 7 | Nov 21–22 | Benchmark harness: micro-benchmarks, Docker "small VPS" profile, raw timings → percentiles | Tier-1 latency p50/p99 at batch 1 and 32 | todo |
| 8 | Nov 28–29 | **Tier-2 student** (Model2Vec / static embeddings + linear head) | Tier 2 on the plot | todo |
| 9 | Dec 5–6 | **Tier-3 student**: fine-tune a small encoder on the GPU, export ONNX int8 | Tier 3 on the plot | todo |
| 10 | Dec 12–13 | Write-up v0: the trade-off curve, what broke first as the model shrank, the teacher-noise ceiling | `results/` report + updated README | todo |
| — | Dec 19–20 | **Buffer** | | |
| — | Dec 26 – Jan 3 | Holiday break | | |

## Phase 2: making it realistic (Jan–Feb 2027)

Rough order. Each item takes one or two weekends.

- **End-to-end request benchmark:** offline → local replay with `tc netem` →
  polite live fetch.
- **Fast path:** a URL + title + meta-description-only model as the cache-miss
  fallback, checked against Curlie URL labels.
- **Scale and noise:** 100k → 1M teacher labels; hard vs soft labels;
  stronger-teacher subset; candidate-set labels. Answers "how much does
  teacher noise limit the student?"
- **Knee of the curve:** sweep student size and input length.
- **Calibration and per-category thresholds.**
- Optional cloud calibration run (personal account) to fix the cost axis.

## Phase 3: open questions (Mar 2027 →)

- **Drift:** relabel a newer CC crawl, measure decay, and try incremental
  updates (online linear models, refreshed head) against full retraining.
- **Southeast Asian languages:** Indonesian, Vietnamese and Thai with little
  data. Zero-shot transfer first (SIB-200 for checks), then small teacher-
  labeled sets.
- **Coverage/freshness simulation:** URL/domain cache hit rates over a crawl
  timeline.

## Rules of thumb

- End each weekend with a short blog post in `site/src/content/blog/` (copy
  the previous one; set `weekend:` and `draft: false` when ready).
- Start each weekend by updating this table and reading the last decision
  record. End it with the "done when" artifact committed, even if partial.
- Spend money only after a pilot measures the real cost. Keep each paid run
  under a budget written in the decision record.
- Prefer finishing a thin end-to-end slice over polishing one stage.
