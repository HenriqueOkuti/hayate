---
title: "Weekend 4: nobody wanted to grade the teacher"
description: "The human-checked sample is cancelled: Henrique refuses to label 300 pages by hand, so three big models vote instead, and I learn what a vote can and can't tell me."
pubDate: 2026-11-13
weekend: 4
tags: [labeling, evaluation, decision]
draft: true
---

Last time I promised that Henrique would check about 300 pages by hand, so my teacher would finally be graded by a human. He looked at 300 pages and 330 possible labels, and announced he could not imagine ever doing that manually. So, two weekends late (life happened), three big models graded each other instead.

![Hayate-chan grins smugly and holds up three round voting paddles, two cyan and one orange, with her other hand on her hip, on a pale cream background with a faint orange circle behind her](../../assets/weekend-04.png)

## What we did

- **Built a review tool, then deleted it the same day.** It was a nice little local page: label search, keyboard shortcuts, a blind mode. Then Henrique admitted he would never open it. A plan that depends on work nobody will do is not a plan, so [decision 0010](https://github.com/HenriqueOkuti/hayate/blob/main/docs/decisions/0010-reference-sample.md) replaced the human with a panel.
- **Assembled the panel.** Sonnet 5.5, my teacher, had already labeled the 300 holdout pages (pages from sites no prompt was tuned on). Opus 5.5 and Google's Gemini 4 Argon, at low thinking effort, labeled the same pages with the same prompt. That is three models from two companies, and it took under five minutes on Henrique's subscriptions.
- **Let them vote.** A label goes into the reference for a page when at least two of the three give it. If two say the page has no topic, the reference is "no topic".
- **Scored each model against the other two,** never against a vote that includes its own.
- **Banned a word.** No human checked any of this, so nothing here is *accuracy*. It is *agreement*: how often models say the same thing. If all three share a blind spot, the vote has it too.

My labels have two levels: Tier 1 is the broad category ("Automotive"), Tier 2 the specific topic under it ("Auto Repair"). The numbers below are Tier 2 unless they say otherwise.

## What surprised us

**The panel always reaches a verdict.** On 287 pages, two models share at least one label. On the other 13, at least two say there is no topic. Not one page was left hanging. It is a low bar, though: all three give exactly the same labels on only 101 pages.

**We nearly published a ranking that wasn't there.** The first draft said Sonnet agrees least with the other two: its first label matched theirs on 75% of pages, against 81% for Opus and 79% for Argon. An [ML-review agent](https://github.com/HenriqueOkuti/hayate/tree/main/.claude/agents) recomputed everything and caught it. Each model was being scored on different pages: only the pages where *the other two* agree. Opus and Argon agree with each other most, so Sonnet's set kept exactly the pages where Sonnet was the odd one out. On the 243 pages where all three can be scored, Sonnet matches on 89% and Opus on 88%. That is twice in two weekends that the reviewer has saved me from a number that was too interesting.

**Different models agree almost as well as one model agrees with itself.** Two different models give the same first label on 69 to 78% of pages. One model, run twice on the same pages, matches itself on 80 to 89%. So much of the "disagreement between teachers" is each teacher's own wobble.

## Numbers

Pairs of models, all 300 pages, share of pages with the same first label (95% intervals in parentheses):

| Pair | Tier 2 | Tier 1 |
| --- | --- | --- |
| Opus and Argon | 78% (73 to 83) | 88% (85 to 92) |
| Sonnet and Opus | 75% (70 to 80) | 85% (81 to 89) |
| Sonnet and Argon | 69% (64 to 74) | 81% (76 to 85) |

Each model against what the other two agree on, on the 243 pages where that exists for all three:

| Model | Same first label, Tier 2 | Same first label, Tier 1 | Labels given on these pages |
| --- | --- | --- | --- |
| Sonnet 5.5 | 89% (85 to 93) | 91% (88 to 95) | 298 |
| Opus 5.5 | 88% (83 to 91) | 91% (88 to 95) | 343 |
| Gemini 4 Argon | 83% (78 to 88) | 89% (85 to 93) | 439 |

Sonnet and Argon are the pair that agrees least, and that gap holds up when measured page by page. The setups differ beyond the model: 25 pages per call for the Claude models and 10 for Argon, and the Sonnet run is four weeks older than the other two. Two of the three votes also come from the same company, so this panel can't rule out a habit that Claude models share. Gemma 4 12B, the open model on Henrique's GPU, matches the panel's first label on 49% of pages, far behind, as before.

Rebuilt from a second run of all three models on 100 pages, the reference gets exactly the same labels on 71 of them. My answer key wobbles too.

Full write-up: [panel-v0.md](https://github.com/HenriqueOkuti/hayate/blob/main/results/panel-v0.md).

## Next weekend

Bulk labeling: Sonnet labels all 20,000 pages, and they get split into training, validation and test sets by website, with the 300 panel pages locked into the test set. After that I finally start learning.
