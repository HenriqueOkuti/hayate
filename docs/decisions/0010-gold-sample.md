# 0010: Gold sample v0

- **Status:** accepted
- **Date:** 2026-11-13

## Context

Every number so far compares one model with another. Weekend 4 ([#5](https://github.com/HenriqueOkuti/hayate/issues/5)) needs a human-checked sample so the teacher's accuracy is measured, and so the students can later be scored against a person ([measurement.md](../measurement.md)). The plan asked for about 300 pages, stratified by language and Tier 1, with a blind subset to measure how much the reviewer anchors on the teacher's answer. Constraints: one reviewer (Henrique) with about a day; 330 labels that no one knows by heart; page text stays out of the repo; and prompt `v2` was written after reading the teacher's output on the 500 development pages of the [pilot](../../results/teacher-pilot.md), so those pages can't score it fairly.

## Options considered

### Pages

1. **The pilot's holdout: 300 pages, 150 pt and 150 en, on domains the prompt was not tuned on.** A plain random draw per language, so teacher-versus-human F1 is an unbiased estimate for the page sample. Sonnet `v2` labels already exist, with a repeat pass on 100 pages, and so do Sonnet `v0`, Gemma and resiliparse-text labels for the same pages. Not stratified by Tier 1: the teacher's top labels cover 30 of the 36 Tier-1 categories, from 24 pages (Business and Finance) down to 1 (Crime).
2. **A fresh sample stratified by the teacher's Tier 1.** Even coverage per category, but it needs teacher labels on a large pool to stratify on (the bulk run, weekend 5), the overall F1 then needs reweighting, and 300 pages over 36 categories is still about 8 pages each, too few for per-category numbers.
3. **The panel's disagreement queue** (pages where three vendors split, planned on [#6](https://github.com/HenriqueOkuti/hayate/issues/6)). The most informative pages per hour of review, but a biased sample: it measures the hard cases, not the teacher's accuracy.

### Blind subset

1. **The 100 pages the teacher labeled twice, with the reveal on the same page.** The reviewer answers with the teacher's labels hidden, locks the answer, then sees the labels and gives a final answer. This gives an unanchored human answer on exactly the pages where the teacher's own repeat noise is known, and the final answer still benefits from the teacher catching what the reviewer missed. The repeat pages are 62 en and 38 pt, not an even split.
2. **A fresh random 100, balanced by language, never revealed.** A cleaner split, but no repeat pass on those pages without a new teacher run on a newer Claude Code version, and the gold labels on blind pages would rest on one unaided pass over 330 labels.
3. **A smaller blind set (30 to 50 pages).** Less review time, but the interval on the anchoring difference gets too wide to read.

### Tool

1. **A local page served by a small Python script** (standard-library HTTP server, one HTML file, no new dependency). Type-ahead search over the labels, keyboard shortcuts, resumable, and the server holds back the teacher's labels on blind pages until the blind answer is locked.
2. **A terminal CLI.** No browser, but choosing among 330 labels and reading 3,000 characters of page text in a terminal is slow.
3. **A TypeScript app** (the other candidate in [stack.md](../stack.md)). A nicer stack for UI work, but a build step and a second language for a tool with one page and three endpoints.
4. **An annotation product** (Label Studio and similar). Far more than is needed, and the blind-then-reveal flow would still have to be built.

## Decision

- **Pages:** the holdout run `holdout-v2` (option 1). The reviewer sees what the teacher was sent (URL, title, description and the same first 3,000 characters), with the rest of the extracted text behind a fold and a link to the live page.
- **Rules:** the reviewer follows the teacher's prompt rules, shown in the tool: at most 5 labels, the main topic first, a child instead of its Tier-1 parent, no labels for a page with no topic. The tool enforces the first three. A page that can't be judged is skipped and left out.
- **Blind subset:** the 100 repeat pages (option 1), mixed into the review order by a seeded hash. Both the blind answer and the final answer are kept; a blind answer can't be changed after the reveal. A misclick can be marked as a slip, which removes that page from the blind scoring but never allows a second blind answer.
- **Order:** blind and assisted pages are mixed rather than all blind pages first. Blind-first would tie the blind answers to the hours when the reviewer knows the taxonomy least; mixed order means later blind answers follow many pages of the teacher's labels, so the report also gives the blind numbers by thirds of the review order.
- **Tool:** the local page (option 1): `scripts/review_gold.py`, `src/hayate/review/`, config in [configs/gold.toml](../../configs/gold.toml). Decisions go to an append-only `data/gold/v0/reviews.jsonl` beside the frozen tasks, with the teacher's labels in the tasks file. Each row records the page's position in the order, the time the page was visible, and whether the reviewer opened the text behind the fold or the live page, so pages judged on more than the teacher saw can be separated later. The page ignores a held or too-quick save, so a slip can't accept the teacher's labels on page after page.
- **Scoring, fixed before any result exists:** `scripts/gold_report.py` writes `results/gold-v0.json`: micro precision, recall and F1 at Tier 2 and Tier 1 with 95% bootstrap intervals, the top-label match, and per-Tier-1 support.
  - **Teacher accuracy is a range, not one number:** F1 against the final answers on all pages is the optimistic bound (the reviewer saw the teacher's labels, preselected on assisted pages), and F1 against the blind answers is the pessimistic one. They are reported together.
  - **Labels scored:** all of the teacher's labels as a set. One variant only: the top label plus secondaries with confidence of at least 0.5, the floor in the prompt's rule 4. No other threshold gets tuned on this sample.
  - **Anchoring:** on the 100 blind pages, F1 against the final answers minus F1 against the blind answers (paired), and assisted F1 minus blind F1 on separate pages, as the equal-weight mean of the per-language differences because of the uneven split. Both are upper bounds: they also contain corrections where the teacher caught something the reviewer missed.
  - **Other teachers** (Sonnet `v0`, Gemma, resiliparse text) are scored against the blind answers only, since every final answer was made looking at Sonnet `v2`'s labels and would favor it, each with a paired difference to Sonnet `v2` on the same pages.

## Consequences

- No new teacher run and no plan usage: the review can start now.
- The gold pages are a test set. Their domains must go to the test split in weekend 5 and never into training or prompt tuning.
- One reviewer means the "human" is one person's reading of an ambiguous taxonomy. The blind answers measure anchoring, not how far two people would agree; a second reviewer on a subset would.
- The assisted-versus-blind comparison is between two different sets of pages (200 and 100), so expect an interval of roughly plus or minus 0.1 on the difference; the paired one on the blind pages is tighter.
- The reviewer's own repeat noise is not measured, and reading the gold disagreements to write a new teacher prompt would spend this sample as a test set for that prompt.
- Rare categories stay thin, so per-category numbers from v0 are a sanity check only. A stratified top-up (v1), fed by the bulk labels and the panel's disagreement queue, is the fix once weekend 5 has run.
- The decisions are not committed (`data/` is ignored). They hold page ids and label ids but no page text, so publishing them later is possible; that is a separate call.
