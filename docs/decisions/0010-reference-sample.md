# 0010: Reference sample v0, a panel instead of a human

- **Status:** accepted
- **Date:** 2026-11-13

## Context

Every number so far compares one model with another. Weekend 4 ([#5](https://github.com/HenriqueOkuti/hayate/issues/5)) was planned as a human-checked gold sample: about 300 pages reviewed by hand, so the teacher's accuracy would be measured and the students could later be scored against a person ([measurement.md](../measurement.md)). A review tool for it was built and then dropped the same day: Henrique is the only possible reviewer, and he decided he will not label pages by hand, not 300 and not 30. A plan that depends on work nobody will do is not a plan, so the question became what the best reference is with no human in it. Constraints: public data, no API keys (labeling runs on personal subscriptions, [0003](0003-teacher.md)), and prompt `v2` was written after reading the teacher's output on the 500 development pages of the [pilot](../../results/teacher-pilot.md), so those pages can't score it fairly.

## Options considered

### Reference

1. **A three-model panel from two vendors, on the pilot's holdout.** Sonnet 5.5 (already run), Opus 5.5 and Gemini 4 Argon label the same 300 pages (150 pt, 150 en, on domains the prompt was not tuned on); the reference is the labels at least two of the three give. Cheap, repeatable, and the cross-vendor member turns "Claude agreeing with Claude" into something a little stronger. It measures agreement, not accuracy: a mistake all three share is invisible.
2. **The panel plus a 15-minute human yes/no check** of the teacher's top label on 100 pages. The only option that puts a human-anchored number in the write-up. Declined by the only reviewer.
3. **A public human-labeled set through a crosswalk** (for example MN-DS news topics mapped to IAB Tier 1, [data.md](../data.md)). Human labels nobody here has to make, but news only, Tier 1 only, in English, and the hand-made crosswalk adds its own noise. About a weekend of work.
4. **No reference: student against teacher only.** Enough for the trade-off curve, but then nothing checks the teacher at all, and a single-model reference inherits that model's quirks.

### Scoring a panel member

1. **Against the full panel's majority.** Simple, but each member is scored against a vote that includes its own, which flatters it.
2. **Against what the other members agree on** (leave one out). No member votes on its own score. Fewer pages have a reference, since two members must agree instead of two of three, and each member ends up with its own reference on its own pages, so the rows only compare on the pages where all three have one.

### Pages with no agreement

1. **Leave them out and report the coverage.** Honest about what the reference is, but the pages left out are the hard ones, so every score is a little flattered.
2. **Count them as "no topic".** Wrong: disagreement is not the absence of a topic, and it would punish any prediction on them.
3. **Fall back to one member's label.** Makes the reference that member's opinion exactly where it is least reliable.

## Decision

- **Reference:** the three-model panel (option 1) on the 300 holdout pages, all on prompt `v2`. Runs `holdout-v2` (Sonnet), `holdout-opus-v2` and `holdout-argon-v2`, made with `scripts/label_pages.py`; config in [configs/panel.toml](../../configs/panel.toml).
- **Rule:** a label is in the reference when at least two members give it, at Tier 2 and, with each member's labels rolled up first, at Tier 1. A page is **agreed** (a Tier-2 label has the votes), **tier1_only** (only a Tier-1 category has them), **none** (two members gave no labels, so the reference is "no topic") or **split** (no reference). Code: `src/hayate/evaluation/panel.py`.
- **Scoring:** a page with no reference at a tier is left out of that tier's score, and the coverage is reported beside every score. Panel members are scored leave-one-out, against what the other two agree on, and compared with each other only on the pages where all three have such a reference. Labels in the reference are ordered by votes and then by the rank members give them, not by confidence, because members use different confidence scales. Other runs of a member's model (Sonnet `v0`, Sonnet on resiliparse text) are scored with that member left out. Students are scored against the full panel and, since they are trained on Sonnet's labels, also with Sonnet left out. `scripts/panel_report.py` writes the reference to `data/labels/panel-v0/reference.jsonl` and the report to `results/panel-v0.json`.
- **Words:** these numbers are **agreement with the panel**, or fidelity. Nothing in the docs, the blog or the write-up calls them accuracy, and "gold" is not used for this sample.
- **The public human-labeled crosswalk (option 3)** stays open as a Phase 2 check. It is the only route left to a human-anchored number.

## Consequences

- No hand labeling, and weekend 4 becomes a machine run of a few minutes on existing subscriptions.
- The project can no longer say how often the teacher or a student is right, only how closely each agrees with three frontier models. The teacher-noise ceiling in the write-up becomes "how far frontier models agree with each other", measured, instead of "how far the teacher is from a person".
- Two of the three members are Anthropic models. If Sonnet scores higher against the others than Argon does, part of that can be family resemblance; the pairwise numbers show how much.
- Members differ in batch size and backend as well as model (25 pages per call for the Claude models, 10 for Argon), and the Opus and Argon holdout runs were made four weeks after the Sonnet run, on newer CLI versions.
- The holdout pages are a test set. Their domains must go to the test split in weekend 5 and never into training, and reading the panel's disagreements to write a new teacher prompt would spend the sample as a test set for that prompt.
- Revisit if a second cross-vendor member becomes available without an API key (a `codex exec` adapter was planned on [#6](https://github.com/HenriqueOkuti/hayate/issues/6)), which would allow a panel with one model per vendor from three vendors, or if anyone ever volunteers a human check.
