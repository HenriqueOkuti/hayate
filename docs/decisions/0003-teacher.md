# 0003: Teacher

- **Status:** accepted
- **Date:** 2026-10-18

## Context

Every student learns from the teacher's labels, so the teacher sets the ceiling. It has to label 20k to 100k pt and en pages into the 330 labels of [0002](0002-label-depth.md) with valid ids, at a cost that fits a hobby budget, and it has to be measured for consistency before bulk labeling (W05, [#6](https://github.com/HenriqueOkuti/hayate/issues/6)). Licensing matters too: [labels.md](../labels.md) notes that the big providers forbid using outputs to train competing models, so the default before the pilot was that published labels or weights come from an Apache or MIT teacher.

Evidence: the pilot report [results/teacher-pilot.md](../../results/teacher-pilot.md) (800 pages, 3 prompts, Sonnet, Opus, Gemini 4 Argon and a local Gemma 4 12B, shuffled repeats, a holdout of unseen domains) and the earlier experiments on [#4](https://github.com/HenriqueOkuti/hayate/issues/4) (subagents, 8 models from 3 vendors on 10 pages, with no vendor effect visible at that size).

## Options considered

1. **Sonnet 5.5 through headless `claude -p` on the Claude Code plan.** Valid output on every call, about 1.2k tokens and 0.3 s of call time per page, no per-token bill. Repeat Tier-2 Jaccard about 0.79, and 0.70 against Opus. Publishing its labels needed a call on the provider terms (see Decision).
2. **Sonnet 5.5 or Haiku 5.5 through the API.** Same quality, batch and cache discounts, but a per-token bill and an API key, which the project avoids ([CLAUDE.md](../../CLAUDE.md)). Same licensing limit.
3. **Claude Code subagents spawned from a session.** What the first experiments used: about 6.6k tokens per page of overhead, the orchestrating session fills up, and agents with tools took shortcuts that only a transcript check caught.
4. **A local open-weight model on the 4070:** Gemma 4 12B (Apache-2.0, 4-bit) through Ollama, run on the same pages ([#54](https://github.com/HenriqueOkuti/hayate/issues/54)). Free, and its labels are open, but much weaker: 0.42 to 0.47 Tier-2 Jaccard against each frontier model, 0.49 to 0.55 against itself on a repeat, Tier-1 parents with their children on 6% of pages, and about 6 times slower per page.
5. **Gemini 4 Argon through the Antigravity CLI** (personal subscription). In the frontier band with Sonnet and Opus (0.68 to 0.73 Tier-2 Jaccard between any two of the three), the most self-consistent on a small repeat, but about twice Sonnet's tokens per page, its own plan's limits, and the same closed-model terms.

## Decision

Sonnet 5.5 through headless `claude -p` (option 1) is the teacher for training labels, with prompt `configs/teacher/prompt-v2.txt`, 25 pages per call, tools off and the label ids enforced by a JSON schema. Prompt `v2` gives the cleanest label shape (1.2 labels per page, no parent-and-child pairs, about 4% empty pages, all holding on a holdout of unseen domains) and the closest agreement with Opus; no prompt changed repeat consistency measurably. Labels keep their raw confidences; any confidence threshold is a training-time choice.

Opus 5.5 is the reference teacher on a subset (about 2% of pages, per the #6 plan). A cross-vendor panel on a stratified subset (#6) measures vendor bias, with Gemini 4 Argon as the Google member (Gemini 3.1 Pro is no longer offered through `agy`). The local Gemma 4 12B is not used: it is too far from the frontier models to serve as a teacher, though the Ollama backend stays for a stronger open model later.

**Publishing** (Henrique, 2026-10-18): labels made by Claude, and students trained on them, may be published. The provider-terms note in [labels.md](../labels.md) stays as context; an open-weight teacher remains the fallback if that changes; given option 4's results, the candidate would be a larger one such as GPT-OSS 120B through `agy` (see #4), not a 12B model on the 4070.

## Consequences

- W05 can start on the existing driver (`scripts/label_pages.py`): 20k pages is about 24M tokens and roughly 15 minutes with 8 parallel calls, if the plan's usage allows; that was not measured.
- One flat prompt with all 330 labels works and stays cheap, which is evidence for 0004 (single pass against hierarchical), though a hierarchical pass was not tried.
- Teacher noise is real: Sonnet agrees with itself at about 0.79 Tier-2 Jaccard. Students should be judged against the W04 human gold sample, not only against the teacher.
- Revisit if the W04 gold sample shows Sonnet's accuracy well below Opus or another vendor, if plan limits block bulk labeling, or if the provider terms change.
