# Tier-1 student v1: keep the top label (#79)

Run 2026-11-14 on commit `b261e67`. The numbers are in [tier1-v1.json](tier1-v1.json), written by `scripts/train_tier1.py` with `--top1-floors -1 0 0.01 0.02 0.03 0.04`. Everything else is as in [tier1-v0](tier1-v0.md): the same features, model, label set, splits and tuning procedure. No number here is accuracy; the references are the teacher and the panel.

## What changed

The v0 student gave no label to 733 test pages, where the teacher gives none to 114, because its probabilities run low. v1 adds one rule: a page where no label passes its threshold keeps its most probable label, if that label's probability is at least a floor. The floor, or no rule at all, is chosen together with the threshold policy by cross-fitted val F1. Val chose a floor of 0.03 (learning rate 0.01, own thresholds from 20 val positives). Test was scored once, both with the rule and with it switched off on the same model, so the difference below is the rule alone, paired over the same pages.

## Results

| Tier-2 micro F1 | Rule off | v1 rule | v1 minus off |
| --- | --- | --- | --- |
| Val, cross-fitted | 0.438 | 0.452 | in-sample +0.011 (0.002 to 0.020) |
| Test, against the teacher | 0.440 | 0.442 | +0.002 (-0.006 to 0.011) |

- **At Tier 1, test:** 0.544 to 0.554, +0.010 (-0.001 to 0.021).
- **Test precision and recall at Tier 2** move from 0.474 and 0.411 to 0.417 and 0.471: more labels, about as many of them right.
- **Panel** (without Sonnet's vote, 285 and 296 pages): Tier-2 F1 0.408 (0.363 to 0.452), Tier-1 F1 0.556 (0.507 to 0.601). The teacher scores 0.771 and 0.875 on the same pages.
- **"No topic":** the student now gives no label to 165 test pages, close to the teacher's 114, but the two sets barely overlap (precision 0.02, recall 0.04). The tier-1 student cannot tell which pages have no topic; the rule only fixes how often it says so.

## Verdict

Val chose the rule, and on test it neither helps nor hurts Tier-2 F1 by a resolvable amount; Tier 1 gains about a point, at the edge of the interval. v1 is the tier-1 student W07 times, since it gives a label to as many pages as the teacher does, which is what a categorizer in use must do. Telling "no topic" pages apart is left to the larger students.
