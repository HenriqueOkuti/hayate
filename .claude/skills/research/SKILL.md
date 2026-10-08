---
name: research
description: Research a question for Hayate from public sources and file the result as a dated note in docs/research/. Use when a decision or doc needs facts from the web (licenses, prices, papers, model or library versions, dataset terms).
argument-hint: "<question or topic>"
---

# Research

Topic: $ARGUMENTS

1. **Scope.** Check `docs/` and `docs/research/` for what is already known. Write 2–4 sharp sub-questions that the decision actually needs.
2. **Size it:**
   - **One sub-question:** delegate to the `researcher` agent, giving it today's date and a slug for the note.
   - **Several independent sub-questions:** run the saved `research-fanout` workflow with `args: {date: "YYYY-MM-DD", slug: "...", question: "...", topics: ["...", "..."]}`. It researches in parallel, fact-checks the key claims and writes one combined note. Check with the user first, because it spawns several agents.
3. **File it.** Make sure the note exists at `docs/research/<date>-<slug>.md`, with sources and an UNVERIFIED list.
4. **Report** to the user:
   - the key findings in a few bullets;
   - what changes in which doc;
   - which pending decision it feeds.

   Offer to update the topic doc (or hand off to `docs-keeper`).

Public sources only: no logged-in tools or connected accounts.
