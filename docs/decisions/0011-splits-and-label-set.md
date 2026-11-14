# 0011: Splits and label-set version

- **Status:** accepted
- **Date:** 2026-11-14

## Context

W05 ([#6](https://github.com/HenriqueOkuti/hayate/issues/6)) turns the 20,000-page sample ([0005](0005-page-sample.md)) into training labels and train/val/test splits. Constraints: the 300 holdout pages are the test set, so their domains never reach training or prompt tuning ([0010](0010-reference-sample.md)); prompt `v2` was tuned on the 500 pilot pages, so they must not be scored on; splits are by domain, with a by-page split reported alongside ([measurement.md](../measurement.md)); every student result must name the exact labels and split it used.

A first split grouped by registered domain only. The `ml-reviewer` check found it leaked anyway: 19 groups of identical text (162 pages) crossed splits, the largest a bot-check page on 48 domains, plus 947 near-duplicate pairs (shared site templates, mirrors on other suffixes). About 1.6% of test pages had a near-twin in train.

## Options considered

### Grouping unit

1. **Registered domain.** Simple, but templates and mirrors on different domains cross splits (the leak above), which flatters every score on easy pages.
2. **Components of related domains.** Join domains that share a brand label across suffixes, an identical page text, or a near-duplicate page (MinHash, exact shingle Jaccard at least 0.8), and split the components. Fixes the leak; the largest component holds 57 pages, so balance barely moves.
3. **Drop the duplicate pages** (bot checks, parked and coming-soon pages) from the sample. Smaller leak, but a categorizer meets these pages in real traffic, and labeling them "no topic" is part of the job.

### Assignment

1. **Fill in hash order to exact targets.** Exact 10% shares, but where the cut falls depends on every other page, so growing the sample moves domains between splits.
2. **Fixed hash threshold per component.** Shares are approximate (whole components land together), but a component's split depends only on its own key and the seed, so it stays put as pages are added.

### Labels

1. **Keep the pilot and holdout labels from W03 and W04** and label only the other 19,200 pages. About 4% cheaper, but mixes CLI versions and dates in one training set.
2. **Relabel all 20,000 pages in one run.** One CLI version, prompt, model and date for every training label.

## Decision

- **Splits (`splits-v1`):** components of related domains (option 2), assigned by fixed hash threshold with seed `20261114`. Components holding a holdout domain go to test and components holding a pilot domain go to train, in both columns, and a component with both is an error. Of the other components, 8% go to test and 10% to val. Result: 16,192 train, 1,933 val and 1,875 test pages, with no component in two splits. The by-page column keeps the forced components and hashes every other page on its own. Code: `hayate.data.splits`, `scripts/make_splits.py`; report: [results/splits-v1.json](../../results/splits-v1.json).
- **Text for duplicate detection:** the text the teacher sees (`text_trafilatura`, with `text_resiliparse` below 200 characters).
- **Label set:** one run, `bulk-v2`, over all 20,000 pages: Sonnet 5.5 through `claude -p`, prompt `v2`, with 5% of batches repeated. Its version is the manifest in `results/labels-bulk-v2.json`, which records the served model ids, CLI version, prompt and taxonomy hashes, file hashes, `label_set_sha256` and the split's `assignment_sha256`. The W04 panel reference stays as built.
- **Scale:** 100k pages is out of scope for W05. It needs a new Common Crawl sample first, and should be decided once the run's plan usage is known.

## Consequences

- Val and test scores lose the easy wins from templates and mirrors. A few near-duplicate pairs can still cross, because MinHash misses some (2 of 3,183 pairs in the reviewer's own check, none involving a holdout page).
- Test is about 9.4% of pages (8.8% for English, 10.0% for Portuguese) rather than exactly 10%. That is accepted in exchange for a split that stays put as the sample grows.
- The by-page and component columns have different test sets, so a gap between them mixes leakage with sampling difference. W06 should report that gap on pages that are test in both columns.
- A future `splits-v2` (for example at 100k pages) keeps the v1 assignment of every v1 page, so nothing trained or tuned on v1 reaches v2 test.
- Revisit if a student shows an unexplained jump between val and test, or if larger near-duplicate clusters show up in a new sample.
