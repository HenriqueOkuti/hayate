---
name: new-decision
description: Record a Hayate design decision as a numbered record in docs/decisions/ and update the pending list. Use when a choice is made (taxonomy depth, teacher model, extractor, student implementation, hardware) or the user says "let's decide", "record this decision" or "ADR".
---

# New decision record

1. **Number.** If `docs/decisions/README.md` has a pending row for this question, reuse its number. Otherwise use the next free number after the highest `NNNN-*.md` file.
2. **Write** `docs/decisions/NNNN-short-kebab-title.md` from `0000-template.md`:
   - **Status:** `accepted`, or `proposed` if the user hasn't confirmed yet.
   - **Date:** today.
   - **Context:** the question and the constraints that mattered. Link the doc or research note the facts came from.
   - **Options considered:** 2–4 real options, each with its main trade-off.
   - **Decision:** what was chosen and why, in a few sentences.
   - **Consequences:** what it makes easier or harder, and what evidence would make us revisit it.
3. **Update `docs/decisions/README.md`:** move the row from Pending to Accepted, as `- [NNNN: Title](NNNN-....md): one-line summary`.
4. **Ripple.** If the decision changes a topic doc (`labels.md`, `data.md`, `models.md`, `measurement.md`, `stack.md`) or the timeline, update it in the same change.

Keep the record under a page. If the user hasn't actually decided, write it as `proposed`, lay out the options, and ask.
