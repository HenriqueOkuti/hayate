# Panel reference v0 (W04, #5)

Run 2026-11-13. The numbers are in [panel-v0.json](panel-v0.json), written by `scripts/panel_report.py` from the label runs in `data/labels/` (not committed); each run's code commit, CLI version, resolved model and batch size are under `runs` there. The design is [decision 0010](../docs/decisions/0010-reference-sample.md).

**No human checked these labels.** Everything here is agreement between models. A mistake the three models share is invisible, so nothing below is accuracy.

## Setup

- **Pages:** the 300 holdout pages of the [teacher pilot](teacher-pilot.md) (150 pt, 150 en, one page per domain, on domains the prompt was not tuned on). The pilot already used them to confirm prompt `v2` and the extractor check, so they are not untouched.
- **Panel:** three models from two vendors, all on prompt `v2` with the same page input (URL, title, description and the first 3,000 characters of the trafilatura text).
  - Sonnet 5.5, run `holdout-v2`, from the pilot (2026-10-18, Claude Code 2.1.302, 25 pages per call, no thinking tokens).
  - Opus 5.5, run `holdout-opus-v2` (2026-11-13, Claude Code 2.1.325, 25 pages per call, 2,676 thinking tokens over the run).
  - Gemini 4 Argon at low thinking effort, run `holdout-argon-v2` (2026-11-13, Antigravity 1.5.2, 10 pages per call, with a no-tools sentence added to the prompt).
- **Calls:** all 56 calls of the two new runs returned valid output on the first attempt. Each member labeled the same 100 pages a second time, shuffled within the batch.
- **Reference:** a label is in the reference when at least two of the three give it, at Tier 2 and, with labels rolled up first, at Tier 1. Its labels are ordered by votes, then by the rank the members give them.
- **Metrics:** micro precision, recall and F1 over labels, and whether the first label matches, with 95% bootstrap intervals over pages. The intervals hold the reference fixed; they do not include its own run-to-run noise.

## Results

**The reference.** On every page, either two members share at least one Tier-2 label (287 pages) or at least two give no labels (13 pages, reference "no topic"). So every page has a reference. That is a low bar: all three share a label on 233 pages, give the same first label on 190, and give identical label sets on 101. The reference has 1.47 labels per page on the 287 pages; over all 300, Sonnet gives 1.20, Opus 1.40 and Argon 1.76.

**Pairs of members**, all 300 pages. F1 between two runs is capped by their different label counts (at about 0.81 for Sonnet and Argon), so the first-label column is the cleaner comparison.

| Pair | Tier-2 F1 | Tier-2 same first label | Tier-1 F1 | Tier-1 same first label |
| --- | --- | --- | --- | --- |
| Opus and Argon | 0.77 (0.75 to 0.80) | 0.78 (0.73 to 0.83) | 0.87 (0.84 to 0.89) | 0.88 (0.85 to 0.92) |
| Sonnet and Opus | 0.72 (0.68 to 0.76) | 0.75 (0.70 to 0.80) | 0.85 (0.82 to 0.88) | 0.85 (0.81 to 0.89) |
| Sonnet and Argon | 0.67 (0.64 to 0.71) | 0.69 (0.64 to 0.74) | 0.81 (0.78 to 0.83) | 0.81 (0.76 to 0.85) |

Paired over the same pages, the Tier-2 first-label match of Sonnet and Argon is lower than that of Opus and Argon by 0.09 (0.04 to 0.14) and lower than that of Sonnet and Opus by 0.06 (0.01 to 0.11). Opus and Argon against Sonnet and Opus is not resolved: 0.03 (-0.03 to 0.09).

**Each member against its own repeat**, 100 pages:

| Member | Tier-2 F1 | Tier-2 same first label | Tier-1 F1 |
| --- | --- | --- | --- |
| Sonnet | 0.81 (0.73 to 0.87) | 0.80 (0.72 to 0.87) | 0.90 (0.86 to 0.95) |
| Opus | 0.86 (0.81 to 0.91) | 0.89 (0.83 to 0.95) | 0.92 (0.88 to 0.96) |
| Argon | 0.86 (0.81 to 0.90) | 0.84 (0.76 to 0.91) | 0.91 (0.88 to 0.94) |

**Each member against what the other two agree on**, on the 243 pages where all three members have such a reference. Each member still has its own reference (the labels the other two share), so precision, recall and F1 follow the label counts: Argon gives 439 labels on these pages against a reference of 266.

| Member | Precision | Recall | Tier-2 F1 | Tier-2 same first label | Tier-1 same first label |
| --- | --- | --- | --- | --- | --- |
| Sonnet | 0.88 | 0.81 | 0.84 (0.81 to 0.87) | 0.89 (0.85 to 0.93) | 0.91 (0.88 to 0.95) |
| Opus | 0.76 | 0.94 | 0.84 (0.81 to 0.87) | 0.88 (0.83 to 0.91) | 0.91 (0.88 to 0.95) |
| Argon | 0.60 | 0.98 | 0.74 (0.72 to 0.77) | 0.83 (0.78 to 0.88) | 0.89 (0.85 to 0.93) |

On each member's own pages (every page where its other two share a label: 285 for Sonnet, 263 for Opus, 258 for Argon) the Tier-2 F1 is 0.74, 0.78 and 0.71. Those three numbers are on different pages and must not be compared: Sonnet's set is the largest because Opus and Argon agree with each other most, which keeps exactly the pages where Sonnet is the odd one out.

**Other runs on the same pages.** The two Sonnet variants are scored against what Opus and Argon agree on (285 pages), Gemma against the full panel (300 pages), so Gemma's row is on a different footing.

| Run | Precision | Recall | Tier-2 F1 | Tier-2 same first label | Tier-1 F1 |
| --- | --- | --- | --- | --- | --- |
| Sonnet `v2` (the teacher) | 0.76 | 0.71 | 0.74 (0.70 to 0.77) | 0.76 | 0.85 (0.82 to 0.88) |
| Sonnet `v2` on resiliparse text | 0.78 | 0.76 | 0.77 (0.73 to 0.81) | 0.77 | 0.87 (0.84 to 0.90) |
| Sonnet `v0` (the plain prompt) | 0.54 | 0.91 | 0.68 (0.65 to 0.71) | 0.74 | 0.79 (0.76 to 0.82) |
| Gemma 4 12B `v2` | 0.45 | 0.52 | 0.48 (0.44 to 0.52) | 0.49 | 0.66 (0.62 to 0.70) |

**Stability of the reference.** Built again from the three repeat passes on the 100 repeat pages, the reference's labels match the first build at Tier-2 F1 0.87 (0.83 to 0.92), and the label set is identical on 71 pages.

## What it shows

- **The panel gives a reference for every page**, so students can be scored on all 300 pages. The reference is itself noisy: a rerun reproduces its label sets exactly on about 7 pages in 10.
- **Sonnet and Opus are level against the rest of the panel.** On the common pages both match the other two's first label on 88 to 89% of pages, with the same F1. Nothing here says the teacher should have been Opus. Argon is a few points lower on the first label, with overlapping intervals, and gives the most labels per page.
- **Sonnet and Argon are the pair that agrees least**, by 6 to 9 points of first-label match, and that difference holds up paired over pages. Sonnet is the member that differs from the others in setup too: run four weeks earlier, on an older CLI version, with no thinking tokens.
- **Different models agree almost as well as one model agrees with itself.** Pairs match on the first label for 69 to 78% of pages; a single model matches its own repeat on 80 to 89%. Much of the disagreement between teachers is run-to-run noise.
- **Prompt `v2` matches a `v2`-prompted panel more closely than `v0` does** (Tier-2 F1 0.74 against 0.68). Part of that is by construction: Opus and Argon were prompted with `v2`, so their agreement has `v2`'s shape (few labels, no parent with its child), and `v0`'s extra labels cost it precision.
- **The extractor still does not matter to the teacher.** Sonnet on resiliparse text agrees with Opus and Argon (who read trafilatura text) at least as well as Sonnet on trafilatura text; the difference is the size of rerun noise.
- **Gemma stays far behind** every frontier model, as in the pilot.
- **Tier 1 is much firmer than Tier 2.** Most disagreement is about which child of a category fits, not about the category.

## Caveats

- **Agreement, not accuracy.** No human labels exist in this project. Where frontier models share a habit or a blind spot, the reference has it too.
- **Two of the three votes are Anthropic's,** and the one cross-vendor member ran at low thinking effort. This is not evidence against a bias shared by Claude models.
- **Members differ in more than the model:** batch size, backend, thinking use, date and CLI version, as listed under Setup.
- **Differences of a few points are not resolved.** Each member's labels change from run to run (the repeat table), and the intervals do not include the reference's own noise.
- **Scoring a student against the full panel scores it partly against its teacher's vote,** since Sonnet is a member. Student results should also be reported with Sonnet left out.
- **Per-language and per-category differences are not supported** at 150 pages per language (Sonnet's Tier-2 F1 on its own pages is 0.75 for Portuguese and 0.72 for English, with overlapping intervals).
- **The holdout domains must stay out of training.** Nothing enforces that yet; the weekend 5 split code has to.
