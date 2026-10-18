# Teacher pilot (W03, #4 and #54)

Run 2026-10-18 with Claude Code 2.1.302, Ollama 0.40.6 and Antigravity 1.4.2. Every run's code commit is in [teacher-pilot.json](teacher-pilot.json), written by `scripts/teacher_report.py` from the run outputs in `data/labels/` (not committed). Earlier experiments on 20 to 100 pages, with subagents and other vendors, are on [#4](https://github.com/HenriqueOkuti/hayate/issues/4).

## Setup

- **Teachers:**
  - Sonnet 5.5 and Opus 5.5 through headless `claude -p` from an empty directory, with tools off, no settings or MCP servers, and 25 pages per call (Claude Code plan).
  - Gemini 4 Argon (low effort) through `agy -p`, the Antigravity CLI, with 10 pages per call and a one-line "no tools, no plan" instruction added to the prompt (Henrique's Google subscription).
  - Gemma 4 12B (Apache-2.0, 4-bit QAT) through Ollama on the RTX 4070 SUPER, with 5 pages per call.
- **Answers:** every teacher is held to the same JSON schema (label ids are an enum of the 330 labels, at most 5 per page) and the same validation. No API keys are used.
- **Pages:** each page gives the teacher its URL, title, meta description and the first 3,000 characters of the trafilatura text (resiliparse if trafilatura gave under 200). One run uses resiliparse text instead, to test the extractor. Code: `src/hayate/teacher/`, `scripts/label_pages.py`, `configs/teacher.toml`.
- **Prompts** (`configs/teacher/`):
  - `v0` is the plain prompt of the earlier experiments.
  - `v1` adds the fixes asked for on #4: child over parent, few secondary labels, a 0.5 floor on secondaries, and empty for no-topic pages.
  - `v2` keeps those fixes and adds that product, shop, service and section pages do have a topic, because `v1` left real pages empty.
- **Page samples:**
  - A development sample of 500 pages (seed 20261018, 250 pt and 250 en).
  - A holdout of 300 pages (seed 7) that shares no domain with it. `v2` was written after reading `v1`'s output on the development pages, so the holdout is the fair check for it.
- **Repeats:** 20% (development) or 34% (holdout) of batches labeled a second time, with the same pages shuffled within the batch. That gives 100 repeat pages per run (30 for Argon), so the repeat intervals are rough.
- **Reference teachers:** Opus and Argon labeled the first 100 development pages with `v2`. Agreement between models is not accuracy.
- **Metrics:** two empty answers count as Jaccard 1. Intervals are 95% bootstrap over pages.

## Results

Label shape (main pass):

| Run | Pages | Labels per page | Empty pages | Pages with a parent and its child | Secondaries under 0.5 | Mean top confidence |
| --- | --- | --- | --- | --- | --- | --- |
| Sonnet `v0`, development | 500 | 1.96 | 8.4% | 12.6% | 395 of 520 | 0.64 |
| Sonnet `v1`, development | 500 | 1.12 | 13.4% | 0.8% | 80 of 127 | 0.65 |
| Sonnet `v2`, development | 500 | 1.25 | 3.4% | 0.6% | 94 of 140 | 0.64 |
| Sonnet `v0`, holdout | 300 | 2.13 | 7.7% | 15.0% | 276 of 361 | 0.62 |
| Sonnet `v2`, holdout | 300 | 1.20 | 4.3% | 0% | 47 of 72 | 0.63 |
| Sonnet `v2`, holdout, resiliparse text | 300 | 1.24 | 4.7% | 0.3% | 64 of 86 | 0.63 |
| Opus `v2`, development | 100 | 1.38 | 1% | 0% | 2 of 39 | 0.70 |
| Argon `v2`, development | 100 | 1.67 | 1% | 1% | 1 of 68 | 0.87 |
| Gemma `v2`, development | 500 | 1.59 | 2.0% | 5.8% | 5 of 307 | 0.85 |
| Gemma `v2`, holdout | 300 | 1.62 | 2.3% | 6.0% | 2 of 192 | 0.84 |

Repeat consistency, shuffled repeat:

| Run | Tier-2 Jaccard | Tier-2 same top | Tier-1 Jaccard | Tier-1 same top |
| --- | --- | --- | --- | --- |
| Sonnet `v0`, development | 0.76 (0.70 to 0.82) | 0.78 | 0.82 | 0.86 |
| Sonnet `v1`, development | 0.81 (0.75 to 0.88) | 0.82 | 0.87 | 0.87 |
| Sonnet `v2`, development | 0.79 (0.71 to 0.85) | 0.82 | 0.83 | 0.87 |
| Sonnet `v0`, holdout | 0.76 (0.71 to 0.82) | 0.81 | 0.84 | 0.86 |
| Sonnet `v2`, holdout | 0.79 (0.72 to 0.86) | 0.80 | 0.89 | 0.90 |
| Sonnet `v2`, holdout, resiliparse text | 0.82 (0.75 to 0.88) | 0.83 | 0.91 | 0.91 |
| Argon `v2`, development (30 pages) | 0.92 (0.86 to 0.98) | 0.90 | 0.94 | 0.90 |
| Gemma `v2`, development | 0.55 (0.49 to 0.62) | 0.65 | 0.69 | 0.76 |
| Gemma `v2`, holdout | 0.49 (0.42 to 0.56) | 0.58 | 0.69 | 0.73 |

Paired over the same repeat pages, the change in Tier-2 repeat Jaccard is:

| Comparison | Holdout | Development pages |
| --- | --- | --- |
| Sonnet `v2` minus Sonnet `v0` | +0.03 (-0.06 to +0.13) | +0.02 (-0.07 to +0.12) |
| Gemma minus Sonnet, both `v2` | -0.31 (-0.40 to -0.22) | -0.23 (-0.33 to -0.14) |

Agreement between teachers, all on prompt `v2`, on the same 100 development pages (Sonnet and Gemma also on all 500 and on the holdout):

| Pair | Tier-2 Jaccard | Tier-2 same top | Tier-1 Jaccard | Tier-1 same top |
| --- | --- | --- | --- | --- |
| Opus and Argon | 0.73 (0.67 to 0.79) | 0.69 | 0.84 | 0.83 |
| Opus and Sonnet | 0.70 (0.63 to 0.78) | 0.68 | 0.81 | 0.80 |
| Argon and Sonnet | 0.68 (0.61 to 0.75) | 0.70 | 0.81 | 0.81 |
| Opus and Gemma | 0.47 (0.40 to 0.54) | 0.50 | 0.69 | 0.70 |
| Argon and Gemma | 0.43 (0.36 to 0.50) | 0.49 | 0.66 | 0.73 |
| Sonnet and Gemma, 500 development pages | 0.45 (0.41 to 0.48) | 0.51 | 0.63 | 0.70 |
| Sonnet and Gemma, holdout | 0.42 (0.38 to 0.47) | 0.48 | 0.59 | 0.63 |
| Sonnet `v0` and Opus | 0.58 (0.52 to 0.65) | 0.65 | 0.73 | 0.78 |

Sonnet `v2` on the holdout, trafilatura text against resiliparse text: Tier-2 Jaccard 0.81 (0.77 to 0.84), same top 0.84; Tier 1 0.89 and 0.91.

**Cost and speed:**

- **Sonnet `v2` on the holdout** (fresh pages, so not distorted by the prompt cache): about 1.18k tokens per page (830 cache writes, 310 cache reads, 35 output) and a median 7.3 s per 25-page call. The list-price equivalent is about $3.7 per 1,000 pages; nothing is billed on the plan.
- **Development reruns:** they read most of their input from the prompt cache left by an earlier run of the same pages, so their cost figures are not representative.
- **Argon:** about 2.3k tokens per page (including about 14k tokens of agent overhead per call) and 10 s per 10-page call.
- **Gemma:** about 9.5 s per 5-page call on the 4070, about 1.9 s per page, against about 0.3 s per page for Sonnet.

All 337 calls of the final runs returned valid output on the first attempt (4,230 page labelings), with no rate-limit or usage-limit error.

## What it shows

- **`v2` fixes the label shape, and it holds on the holdout.** Parent-and-child pairs go from 13 to 15% of pages to under 1%, labels per page from about 2 to 1.2, and empty pages stay rare (about 4%) and are mostly real no-topic pages (terms of service, password and account pages, a directory listing). `v1` over-pruned: about half of the pages it left empty but `v0` labeled had a clear topic (a travel article, product pages).
- **No prompt makes Sonnet more consistent.** Repeat agreement is about 0.76 to 0.81 Tier-2 Jaccard and 0.82 to 0.89 at Tier 1 whatever the prompt. Earlier same-input repeats (an identical batch replayed from the cache) gave higher numbers and measured only sampling noise.
- **The three frontier models agree about equally with each other.** Opus, Argon and Sonnet agree at 0.68 to 0.73 Tier-2 Jaccard and 0.81 to 0.84 at Tier 1, with no sign of the two Claude models clustering. `v2` brings Sonnet into that band (0.70 against Opus, from 0.58 with `v0`). Argon is the most self-consistent (0.92 on 30 pages) and the most confident; Sonnet ignores the 0.5 floor for secondaries, while Opus and Argon follow it.
- **The local Gemma 4 12B is a much weaker teacher.** It agrees with each frontier model at only 0.42 to 0.47 Tier-2 Jaccard, agrees with itself on a repeat at 0.49 to 0.55 (against Sonnet's 0.79), gives Tier-1 parents with their children on 6% of pages, and reports high confidence (0.85) regardless. It is free and its labels are open, but it is about 6 times slower per page than Sonnet on this GPU.
- **The extractor does not change the teacher's labels.** Sonnet's labels from resiliparse text agree with its trafilatura labels (0.81 Tier-2 Jaccard) as closely as Sonnet agrees with itself on a rerun (0.79). The choice between the two (decision 0006) can rest on the student's F1 and on speed: trafilatura takes a median 16 ms per page against 1 ms for resiliparse.
- **Throughput is not the limit.** At the holdout rate, 20k pages is about 24M tokens and, with 8 calls in parallel, roughly 15 minutes. How much of the plan's usage that takes was not measured: the runs did not read the usage meter.

## Not done

- **Plan usage at scale:** the runs hit no limits, but the plan's usage meter was not read before and after.
- **Argon on the holdout:** Argon ran on the development pages only; its prompt was not tuned there, so this matters less than it did for Sonnet.
- **Accuracy:** only the W04 gold sample can measure it.
