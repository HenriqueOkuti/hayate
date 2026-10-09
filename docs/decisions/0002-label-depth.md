# 0002: Label depth and scope

- **Status:** accepted
- **Date:** 2026-10-09

## Context

Every later step (teacher prompt, gold sample, students, metrics) works against one fixed label set, so it has to be frozen before labeling starts. The source is IAB Content Taxonomy 3.1 ([labels.md](../labels.md)), pinned at commit `6dc67c74` with sha256 `7212cdc4...`: 704 nodes, Tier 1 has 37, Tier 2 has 323, Tier 3 has 275, Tier 4 has 69. Constraints: a noisy zero-shot teacher (about 41% F1 on the full IAB tree in prior work), roughly 20k pages for Phase 1, and students small enough to show where accuracy breaks as they shrink.

Two subsets need a call. **Genres** (31 nodes, a Tier-1 subtree) describes CTV and podcast genres, not page topics. **SCD** nodes (63, `Extension=SCD`) are marked sensitive, but are ordinary topics such as Christianity, Diseases and Conditions or Real Estate Renting and Leasing, spread over Medical Health, Religion, Law, Family and others.

## Options considered

1. **Tier 1 only** (36 labels). Least teacher noise and most data per class, but too coarse to show where small students fail.
2. **Tiers 1-2** (330 labels). Fine enough to separate the students, still within reach of the teacher and the data; Tier-2 predictions roll up to Tier 1 for a coarse number.
3. **Tiers 1-3** (about 600 labels). Many classes with a handful of pages each at 20k pages, and a much noisier teacher.

For SCD: keep the nodes as labels with a flag, or drop them (leaving holes in health, religion and law).

## Decision

Option 2, with Genres excluded and SCD nodes kept:

- The label set is every Tier-1 and Tier-2 node outside the Genres subtree: **330 labels** (36 Tier 1, 294 Tier 2), 27 of them SCD.
- Teacher and students predict over these 330 labels. Metrics are reported at Tier 2 and rolled up to Tier 1, so each result has a fine-grained and a coarse number from the same labels.
- SCD nodes stay as ordinary labels. The label set carries the `scd` flag so results can be sliced on it.
- `Communication` (`80DV8O`, a childless Tier-1 row that may be misfiled) stays as a Tier-1 label.
- The set is defined by [configs/taxonomy.toml](../../configs/taxonomy.toml) (`max_tier = 2`, `exclude_tier1 = ["Genres"]`) and built by `scripts/fetch_taxonomy.py` into `data/taxonomy/labels.json`.

## Consequences

- The teacher prompt lists 330 labels instead of about 700, so the cached prefix is roughly half the size.
- Tier-3 and Tier-4 topics fold into their Tier-2 parent; a page about vintage cars is labeled Cars.
- Changing the pinned commit or the config changes the label set, and every label file records the source pin, so mixed label sets are detectable.
- Revisit if Tier-2 per-class data stays too thin after bulk labeling (weekend 5), or if the teacher-vs-human F1 at Tier 2 is too low to learn from (weekend 4). Falling back to Tier 1 needs no relabeling, only the roll-up.
