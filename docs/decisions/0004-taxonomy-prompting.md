# 0004: Taxonomy prompting

- **Status:** accepted
- **Date:** 2026-10-18

## Context

The teacher has to pick 0 to 5 of the 330 labels of [0002](0002-label-depth.md) for each page. [labels.md](../labels.md) listed three ways to present a label set that size: the full list in a cached prefix, a hierarchical pass (Tier 1 first, then the subtree), or infer-retrieve-rank ([arXiv:2401.12178](https://arxiv.org/abs/2401.12178)) as a fallback. The question was left for the W03 teacher pilot ([results/teacher-pilot.md](../../results/teacher-pilot.md), [#4](https://github.com/HenriqueOkuti/hayate/issues/4), [#54](https://github.com/HenriqueOkuti/hayate/issues/54)).

## Options considered

1. **One flat pass:** all 330 labels as `id | Tier 1 > Tier 2` lines in the system prompt, ids enforced by a JSON-schema enum. One call per batch; the list is about 8k tokens, but it sits in the cached prefix, so its cost per page is small at 25 pages per call.
2. **Hierarchical pass:** pick Tier-1 areas first, then label within their subtrees. Shorter lists per call and a natural fit for the tree, but two calls per batch, a Tier-1 miss is unrecoverable, and pages that span two areas need both subtrees.
3. **Infer-retrieve-rank:** the model writes free-text topics, a retriever maps them to candidate labels, and a second call ranks them. Built for label sets of thousands, with an extra retriever to build and tune.

## Decision

One flat pass (option 1). In the pilot it produced valid ids on every call, Tier-1 agreement between runs and with Opus of 0.80 to 0.89, and, with prompt `v2`, almost no parent-and-child pairs, so a flat list does not confuse the levels. The cost of the list is amortized by the batch and the prompt cache (about 1.2k tokens per page in total). The hierarchical pass and infer-retrieve-rank solve problems the pilot did not show, at the price of extra calls or components; neither was tried.

## Consequences

- One prompt file per version (`configs/teacher/prompt-vN.txt`) with the label list appended at run time; nothing to orchestrate between calls.
- Revisit if the W04 gold sample shows systematic Tier-1 confusions a hierarchical pass could fix, if the label set grows toward Tier 3 (704 nodes), or if a smaller local teacher struggles with the full list.
