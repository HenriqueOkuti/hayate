# Decisions

One file per decision, `NNNN-short-title.md`, copied from [0000-template.md](0000-template.md). The timeline ([../timeline.md](../timeline.md)) says when each one is due.

## Accepted

- [0001: Stack](0001-stack.md): Python for ML, TS/Go at the edges.
- [0002: Label depth and scope](0002-label-depth.md): Tiers 1-2 (330 labels), Genres excluded, SCD nodes kept and flagged.
- [0003: Teacher](0003-teacher.md): Sonnet 5.5 through headless `claude -p` on the Claude Code plan, prompt v2, Opus 5.5 as reference; publishing Claude-made labels still open.
- [0004: Taxonomy prompting](0004-taxonomy-prompting.md): one flat pass with all 330 labels in the cached system prompt and a schema enum of ids; no hierarchical pass.
- [0005: Page sample](0005-page-sample.md): raw Common Crawl 2026-39, 10k pt + 10k en, max 3 per domain, two-stage sampling proportional to size.
- [0006: Extractor](0006-extractor.md): trafilatura with resiliparse as fallback, chosen by tier-1 student F1 on val.
- [0007: Tier-1 implementation](0007-tier1-implementation.md): scikit-learn hashing and TF-IDF, one linear layer over all labels trained in PyTorch on the GPU; not fastText, not one-vs-rest SGD.
- [0009: Mascot rig tool](0009-mascot-rig.md): layered WebP with CSS keyframes and a tiny JS blink; no runtime, all MIT.
- [0010: Reference sample v0](0010-reference-sample.md): no human labeling; the labels two of three panel members (Sonnet, Opus, Gemini Argon) agree on, for the 300 holdout pages; reported as agreement, never accuracy.
- [0011: Splits and label-set version](0011-splits-and-label-set.md): components of related domains (brand, same or near-duplicate text) split by fixed hash, holdout to test, pilot to train; one relabeling run `bulk-v2` with a manifest.

## Pending

| # | Question | Due | Inputs |
| --- | --- | --- | --- |
| 0008 | Reference hardware for headline latency numbers | Weekend 7 (Nov 28–29) | [measurement.md](../measurement.md) |
