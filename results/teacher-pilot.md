# Teacher pilot (W03, #4)

Run 2026-10-18 from commit `5656019` with Claude Code 2.1.302. Numbers come from [teacher-pilot.json](teacher-pilot.json), written by `scripts/teacher_report.py` from the run outputs in `data/labels/` (not committed). Earlier experiments on 20 to 100 pages, with subagents and other vendors, are on [#4](https://github.com/HenriqueOkuti/hayate/issues/4).

## Setup

- **Teacher call:** headless `claude -p` from an empty directory, tools off, no settings or MCP servers, `--json-schema` (label ids are an enum of the 330 labels, at most 5 per page), `--output-format json`. Pages go in on stdin, 25 per call: URL, title, meta description and the first 3,000 characters of the trafilatura text (resiliparse if trafilatura gave under 200). Runs on the Claude Code plan; the driver refuses to start if an API key is set. Code: `src/hayate/teacher/claude.py`, `scripts/label_pages.py`, `configs/teacher.toml`.
- **Prompts** (`configs/teacher/`): `v0` is the plain prompt of the earlier experiments. `v1` adds the fixes asked for on #4: child over parent, few secondary labels, a 0.5 floor on secondaries, empty for no-topic pages. `v2` keeps those and adds that product, shop, service and section pages do have a topic, because `v1` left real pages empty.
- **Pages:** a development sample of 500 (seed 20261018, 250 pt and 250 en) and a holdout of 300 (seed 7) that shares no domain with it. `v2` was written after reading `v1`'s output on the development pages, so the holdout is the fair check for it.
- **Repeats:** 20% (development) or 34% (holdout) of batches labeled a second time, the same pages shuffled within the batch. That is 100 repeat pages in 4 batches per run, so the repeat intervals are rough.
- **Opus 5.5** labeled the first 100 development pages with `v2` as a reference. Agreement with Opus is agreement with another model, not accuracy.
- Two empty answers count as Jaccard 1. Intervals are 95% bootstrap over pages.

## Results

Label shape (main pass):

| Run | Pages | Labels per page | Empty pages | Pages with a parent and its child | Secondaries under 0.5 |
| --- | --- | --- | --- | --- | --- |
| Sonnet `v0`, development | 500 | 1.96 | 8.4% | 12.6% | 395 of 520 |
| Sonnet `v1`, development | 500 | 1.12 | 13.4% | 0.8% | 80 of 127 |
| Sonnet `v2`, development | 500 | 1.25 | 3.4% | 0.6% | 94 of 140 |
| Sonnet `v0`, holdout | 300 | 2.13 | 7.7% | 15.0% | 276 of 361 |
| Sonnet `v2`, holdout | 300 | 1.20 | 4.3% | 0% | 47 of 72 |
| Opus `v2`, development | 100 | 1.38 | 1% | 0% | 2 of 39 |

Repeat consistency, Sonnet, shuffled repeat:

| Run | Tier-2 Jaccard | Tier-2 same top | Tier-1 Jaccard | Tier-1 same top |
| --- | --- | --- | --- | --- |
| `v0`, development | 0.76 (0.70 to 0.82) | 0.78 | 0.82 | 0.86 |
| `v1`, development | 0.81 (0.75 to 0.88) | 0.82 | 0.87 | 0.87 |
| `v2`, development | 0.79 (0.71 to 0.85) | 0.82 | 0.83 | 0.87 |
| `v0`, holdout | 0.76 (0.71 to 0.82) | 0.81 | 0.84 | 0.86 |
| `v2`, holdout | 0.79 (0.72 to 0.86) | 0.80 | 0.89 | 0.90 |

Paired over the same repeat pages, `v2` minus `v0` in Tier-2 repeat Jaccard is +0.03 (-0.06 to +0.13) on the holdout and +0.02 (-0.07 to +0.12) on the development pages: no measurable difference.

Sonnet `v2` against Opus `v2` on 100 development pages: Tier-2 Jaccard 0.70 (0.63 to 0.78), same top 0.68; Tier 1 0.81 and 0.80. Sonnet `v0` against the same Opus labels: 0.58 and 0.65 at Tier 2, 0.73 and 0.78 at Tier 1.

Cost and speed, Sonnet `v2` on the holdout (fresh pages, so not distorted by the prompt cache): about 1.18k tokens per page (830 cache writes, 310 cache reads, 35 output), median 7.3 s per 25-page call, list-price equivalent about $3.7 per 1,000 pages (nothing is billed on the plan). The development reruns read most of their input from the prompt cache left by an earlier run of the same pages, so their cost figures are not representative. All 108 calls of the final runs returned valid output on the first attempt (2,700 page labelings, 3.1M tokens), with up to 8 calls in parallel in bursts of 15 to 30 s and no rate-limit or usage-limit error.

## What it shows

- **`v2` fixes the label shape, and it holds on the holdout.** Parent-and-child pairs go from 13 to 15% of pages to under 1%, labels per page from about 2 to 1.2, and empty pages stay rare (about 4%) and are mostly real no-topic pages (terms of service, password and account pages, a directory listing). `v1` over-pruned: about half of the pages it left empty but `v0` labeled had a clear topic (a travel article, product pages).
- **No prompt makes Sonnet more consistent.** Repeat agreement is about 0.76 to 0.81 Tier-2 Jaccard and 0.82 to 0.89 at Tier 1 whatever the prompt. Earlier same-input repeats (an identical batch replayed from the cache) gave higher numbers and measured only sampling noise.
- **`v2` moves Sonnet closer to Opus** (Tier-2 Jaccard 0.70 against 0.58 for `v0`), mostly by dropping the parent-and-child pairs and weak secondaries that Opus does not give. Sonnet agrees with Opus a little less than with itself on a rerun (0.70 against 0.79).
- **Sonnet ignores the 0.5 floor for secondaries; Opus follows it.** Dropping Sonnet's weak secondaries after the fact does not bring it closer to Opus (Tier-2 Jaccard 0.70 to 0.69), so the raw confidences are kept and any threshold is a training-time choice.
- **Throughput is not the limit.** At the holdout rate, 20k pages is about 24M tokens and, with 8 calls in parallel, roughly 15 minutes. How much of the plan's usage that takes was not measured: the runs did not read the usage meter.

## Not done

- **Local open model on the 4070:** not run; no runtime is installed. It matters for labels that could be published.
- **Plan usage at scale:** the runs hit no limits, but the plan's usage meter was not read before and after.
- **Accuracy:** only the W04 gold sample can measure it.
