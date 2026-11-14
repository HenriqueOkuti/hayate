# 0006: Extractor

- **Status:** accepted
- **Date:** 2026-11-14

## Context

Every page in the sample has text from two extractors, trafilatura and resiliparse ([0005](0005-page-sample.md)). The choice was to be made by student F1 rather than by the teacher, because the teacher's labels barely depend on the extractor ([teacher pilot](../../results/teacher-pilot.md)). Extraction speed also matters for the processing number in [measurement.md](../measurement.md), but that is measured in W07.

## Options considered

1. **trafilatura**, with resiliparse below 200 characters. Cleaner main text; the teacher read this text, so the labels match it.
2. **resiliparse**, with trafilatura below 200 characters. Much faster in published benchmarks, keeps more boilerplate.
3. **Both** as two student inputs. Doubles the feature cost for a small gain at best.

## Decision

trafilatura, with resiliparse as the fallback. The tier-1 student trained on trafilatura text beats the same model on resiliparse text on val, paired over the same pages, by +0.016 (0.003 to 0.030) Tier-2 F1 and +0.031 (0.016 to 0.046) Tier-1 F1 ([results/tier1-v0.md](../../results/tier1-v0.md)). Test agrees (+0.015 and +0.035) but was not used to choose.

## Consequences

- Every student reads the same text the teacher read, which keeps the distillation clean.
- The comparison leans toward trafilatura for that same reason, and it covers one student. Revisit if tier 2 or tier 3 shows the opposite, or if W07 finds trafilatura's extraction time dominates the processing latency.
