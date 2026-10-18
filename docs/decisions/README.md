# Decisions

One file per decision, `NNNN-short-title.md`, copied from [0000-template.md](0000-template.md). The timeline ([../timeline.md](../timeline.md)) says when each one is due.

## Accepted

- [0001: Stack](0001-stack.md): Python for ML, TS/Go at the edges.
- [0002: Label depth and scope](0002-label-depth.md): Tiers 1-2 (330 labels), Genres excluded, SCD nodes kept and flagged.
- [0003: Teacher](0003-teacher.md): Sonnet 5.5 through headless `claude -p` on the Claude Code plan, prompt v2, Opus 5.5 as reference; publishing Claude-made labels still open.
- [0004: Taxonomy prompting](0004-taxonomy-prompting.md): one flat pass with all 330 labels in the cached system prompt and a schema enum of ids; no hierarchical pass.
- [0005: Page sample](0005-page-sample.md): raw Common Crawl 2026-39, 10k pt + 10k en, max 3 per domain, two-stage sampling proportional to size.
- [0009: Mascot rig tool](0009-mascot-rig.md): layered WebP with CSS keyframes and a tiny JS blink; no runtime, all MIT.

## Pending

| # | Question | Due | Inputs |
| --- | --- | --- | --- |
| 0006 | Extractor: trafilatura vs resiliparse (judged by student F1) | Weekend 6 | Tier-1 results |
| 0007 | Tier-1 implementation: sklearn/custom hashed model vs fastText (archived) | Weekend 6 | [models.md](../models.md) |
| 0008 | Reference hardware for headline latency numbers | Weekend 7 | [measurement.md](../measurement.md) |
