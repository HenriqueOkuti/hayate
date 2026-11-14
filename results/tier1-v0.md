# Tier-1 student v0 (W06, #7)

Run 2026-11-14 on commit `fb0d815`. The numbers are in [tier1-v0.json](tier1-v0.json) (main run), [tier1-v0-resiliparse.json](tier1-v0-resiliparse.json), [tier1-v0-bypage.json](tier1-v0-bypage.json) and [compare-tier1-extractor.json](compare-tier1-extractor.json), written by `scripts/train_tier1.py` and `scripts/compare_students.py`. Each file records its inputs (taxonomy, label set and split hashes, panel reference hash) and environment (i7-13700F, RTX 4070 SUPER, torch 2.15.0 with CUDA 13.2, scikit-learn 1.9.1).

**Nothing here is accuracy.** The student is scored against its teacher (distillation fidelity) and against the panel of frontier models (agreement). No human checked any label ([decision 0010](../docs/decisions/0010-reference-sample.md)).

## Setup

- **Labels and splits:** label set `bulk-v2` (Sonnet 5.5, prompt `v2`, all 20,000 pages) and `splits-v1` by component of related domains ([decision 0011](../docs/decisions/0011-splits-and-label-set.md)): 16,192 train, 1,933 val and 1,875 test pages.
- **Input:** URL words, title, meta description and the first 3,000 characters of the trafilatura text (resiliparse below 200 characters), the same page input the teacher saw.
- **Model:** word 1-2 grams and `char_wb` 3-5 grams, each hashed into 2^18 buckets, TF-IDF weighted (fitted on train), then one linear layer to 317 label logits (the labels seen in train), trained jointly with binary cross-entropy on the GPU (AdamW, no weight decay, early stopping on val loss).
- **Decision rule:** one temperature, then a threshold per label; a page's labels are those above their threshold, at most 5, and none means "no topic". A label gets its own threshold only with at least 20 val positives and an F1 gain of at least 0.05 over the global threshold (15 labels did); the rest use the global 0.05.
- **Tuning, on val only:** learning rate (0.003, 0.01, 0.03; 0.01 won) and the minimum support for an own threshold (5, 20, 50, global only; 20 won), both chosen by cross-fitted val F1: thresholds fitted on one half of val and scored on the other, halves split by component. Test was scored once, after the procedure was frozen.
- **Development note:** an earlier version fitted per-label thresholds on as few as 5 val positives. Its val F1 rose while its test F1 fell, which is what prompted the cross-fitting. Val alone shows the same signal (cross-fitted 0.40 at a minimum of 5 against 0.43 at 20 or 50), and the old setting stayed a candidate, so the choice is supported by val; it is still a change made after seeing test.

## Results

**Against the teacher, test (1,875 pages).** Micro F1 with 95% bootstrap intervals over pages.

| | Precision | Recall | F1 |
| --- | --- | --- | --- |
| Tier 2 (labels as given) | 0.474 | 0.411 | 0.440 (0.422 to 0.458) |
| Tier 1 (rolled up) | 0.637 | 0.474 | 0.544 (0.526 to 0.564) |
| Hierarchical (labels plus ancestors) | 0.575 | 0.445 | 0.502 |

- Macro F1 is 0.17 at Tier 2 over the 263 labels with test support, and 0.45 at Tier 1. 155 of those 263 labels are never predicted on test: the long tail of labels with few training pages is where a linear model on 16k pages gives up.
- Exact label-set match: 0.26 of pages.
- Per language, Tier-2 F1 is 0.430 for English and 0.449 for Portuguese.
- The cross-fitted val F1 was 0.438, close to test, so the val estimate was honest.

**Against the panel (300 holdout pages, all in test).** The reference is the panel-v0 votes without Sonnet's, because the student imitates Sonnet and would otherwise be credited for agreeing with its own teacher's vote. Both remaining members (Opus and Argon) must agree, so 285 pages have a Tier-2 reference and 296 a Tier-1 one. The teacher's own `bulk-v2` labels on the same pages are the ceiling.

| | Tier-2 F1 | Tier-1 F1 |
| --- | --- | --- |
| Student | 0.402 (0.357 to 0.449) | 0.528 (0.481 to 0.577) |
| Teacher (Sonnet, `bulk-v2`) | 0.771 (0.733 to 0.809) | 0.875 (0.849 to 0.901) |

The student keeps about half of the teacher's agreement with the panel at Tier 2 and about 60% at Tier 1.

**"No topic" is overused.** The student gives no label to 733 test pages, where the teacher does to 114 (precision 0.13, recall 0.81 for "no topic" as a label). Its probabilities are too low: the most probable label per page has a mean probability of 0.18 and is in the teacher's labels on 48% of pages. One temperature fitted on every cell cannot fix this, because nearly all cells are negatives (ECE over cells with p of at least 0.05 drops only from 0.24 to 0.21 with the temperature). Always keeping the top label when nothing passes its threshold is the obvious next step, chosen on val, for tier1-v1.

**Extractor ([decision 0006](../docs/decisions/0006-extractor.md)).** The same model on resiliparse text scores lower, paired over the same pages: trafilatura minus resiliparse is +0.016 (0.003 to 0.030) Tier-2 F1 and +0.031 (0.016 to 0.046) Tier-1 F1 on val, and +0.015 and +0.035 on test. The teacher read trafilatura text, so this comparison leans toward trafilatura.

**Leakage, by-page split.** A model trained and tuned on the by-page column scores 0.475 Tier-2 F1 on the 277 test pages with a page of the same component in its train set, and 0.418 on the 1,633 without: +0.061 (0.003 to 0.117), +0.086 (0.031 to 0.140) at Tier 1, an unpaired difference stratified by language. Its val score (0.452 cross-fitted) is also higher than the component model's (0.438), because its val leaks too. Splitting by page would have flattered the student.

## Caveats

- Training on the GPU uses atomic adds in the backward pass, so a rerun gives slightly different numbers.
- Training and featurizing times in the JSON are training costs, not inference latency. Latency is W07 (#8).
- The panel is 300 pages, which is why its intervals are about 0.09 wide.
