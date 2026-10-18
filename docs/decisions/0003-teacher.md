# 0003: Teacher

- **Status:** accepted
- **Date:** 2026-10-18

## Context

Every student learns from the teacher's labels, so the teacher sets the ceiling. It has to label 20k to 100k pt and en pages into the 330 labels of [0002](0002-label-depth.md) with valid ids, at a cost that fits a hobby budget, and it has to be measured for consistency before bulk labeling (W05, [#6](https://github.com/HenriqueOkuti/hayate/issues/6)). Licensing matters too: [labels.md](../labels.md) notes that the big providers forbid using outputs to train competing models, so the default before the pilot was that published labels or weights come from an Apache or MIT teacher.

Evidence: the pilot report [results/teacher-pilot.md](../../results/teacher-pilot.md) (800 pages, 3 prompts, Sonnet and Opus, shuffled repeats, a holdout) and the earlier experiments on [#4](https://github.com/HenriqueOkuti/hayate/issues/4) (subagents, 8 models from 3 vendors on 10 pages, with no vendor effect visible at that size).

## Options considered

1. **Sonnet 5.5 through headless `claude -p` on the Claude Code plan.** Valid output on every call, about 1.2k tokens and 0.3 s of call time per page, no per-token bill. Repeat Tier-2 Jaccard about 0.79, and 0.70 against Opus. Publishing its labels needed a call on the provider terms (see Decision).
2. **Sonnet 5.5 or Haiku 5.5 through the API.** Same quality, batch and cache discounts, but a per-token bill and an API key, which the project avoids ([CLAUDE.md](../../CLAUDE.md)). Same licensing limit.
3. **Claude Code subagents spawned from a session.** What the first experiments used: about 6.6k tokens per page of overhead, the orchestrating session fills up, and agents with tools took shortcuts that only a transcript check caught.
4. **A local open-weight model on the 4070** (Gemma 4 12B or similar, Apache-2.0). Free and publishable, but weaker on a 330-label list, and not run: no runtime is installed yet.

## Decision

Sonnet 5.5 through headless `claude -p` (option 1) is the teacher for training labels, with prompt `configs/teacher/prompt-v2.txt`, 25 pages per call, tools off and the label ids enforced by a JSON schema. Prompt `v2` gives the cleanest label shape (1.2 labels per page, no parent-and-child pairs, about 4% empty pages, all holding on a holdout of unseen domains) and the closest agreement with Opus; no prompt changed repeat consistency measurably. Labels keep their raw confidences; any confidence threshold is a training-time choice.

Opus 5.5 is the reference teacher on a subset (about 2% of pages, per the #6 plan). A cross-vendor panel on a stratified subset (#6) measures vendor bias.

**Publishing** (Henrique, 2026-10-18): labels made by Claude, and students trained on them, may be published. The provider-terms note in [labels.md](../labels.md) stays as context; an open-weight teacher (option 4, or GPT-OSS 120B through `agy`, see #4) remains the fallback if that changes.

## Consequences

- W05 can start on the existing driver (`scripts/label_pages.py`): 20k pages is about 24M tokens and roughly 15 minutes with 8 parallel calls, if the plan's usage allows; that was not measured.
- One flat prompt with all 330 labels works and stays cheap, which is evidence for 0004 (single pass against hierarchical), though a hierarchical pass was not tried.
- Teacher noise is real: Sonnet agrees with itself at about 0.79 Tier-2 Jaccard. Students should be judged against the W04 human gold sample, not only against the teacher.
- Revisit if the W04 gold sample shows Sonnet's accuracy well below Opus or another vendor, if plan limits block bulk labeling, or if the provider terms change.
