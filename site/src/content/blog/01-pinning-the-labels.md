---
title: "Weekend 1: pinning down 330 labels"
description: "Setting up the repo, downloading a taxonomy that keeps changing under its version number, and deciding how deep the labels go."
pubDate: 2026-10-10
weekend: 1
tags: [setup, taxonomy, decision]
draft: false
---

Before a model can learn to put pages into categories, the categories have to stop moving. This weekend was about freezing them: get the taxonomy file, make sure it's always the same file, and decide how much of it Hayate-chan actually uses.

![Hayate-chan grins as she pins the top box of a simple two-level category tree to a corkboard with an orange pushpin, a padlock hanging from it, while flicking one leftover label card away, on a soft peach background](../../assets/weekend-01.png)

## What I did

- **Set up the repo.** A `uv` Python environment, a lint setup that blocks emojis and hard-wrapped Markdown, CI that runs the tests, and a roadmap board where every weekend is one issue and one pull request. It's boring, but it means I never have to wonder later what state things were in.
- **Wrote a taxonomy fetcher.** `scripts/fetch_taxonomy.py` downloads the IAB Content Taxonomy 3.1 file from a fixed git commit and checks its sha256 hash (a fingerprint of the exact bytes). If either one changes, the script refuses to continue.
- **Decided the label depth.** That's [decision 0002](https://github.com/HenriqueOkuti/hayate/blob/main/docs/decisions/0002-label-depth.md): Tiers 1 and 2, minus one subtree, for **330 labels**.

## What surprised me

**"Version 3.1" isn't one file.** The taxonomy was edited eight times after its release without the version number ever changing. Saying "I used IAB 3.1" doesn't tell you which file I had. A commit hash plus a content hash does. Every label file Hayate writes records that pin, so if two runs ever used different label sets, I'll be able to tell.

**The tree is messier than it looks.** It has 704 nodes on four levels. Tier 1 has 37 entries, but one of them (`Communication`) has no children and looks misfiled, so really there are 36. One whole Tier-1 subtree, **Genres**, describes TV and podcast genres rather than what a web page is about, so I dropped it.

**"Sensitive" doesn't mean "weird".** 63 nodes carry a flag marking them as sensitive categories. I expected the flag to mark edge cases I could safely drop. Instead it covers ordinary topics: Christianity, Diseases and Conditions, renting real estate. Dropping them would leave holes in health, religion and law, so they stay in as normal labels. The flag is kept, so I can slice results by it later.

## How deep to go

This was the real decision. A deeper taxonomy is more useful, but harder to label well:

| Option | Labels | Problem |
| --- | --- | --- |
| Tier 1 only | 36 | Too coarse: every student would look good, so the comparison says nothing |
| Tiers 1–2 | 330 | Fine enough to separate the students, still within reach of the data |
| Tiers 1–3 | ~600 | With ~20k pages, many classes get a handful of examples, and the teacher gets noisier |

Remember that the teacher (the big LLM that labels pages) is expected to be wrong a lot: prior work found about 41% F1 on the full IAB tree. F1 is a score that combines "how many of your labels were right" with "how many of the right labels you found". Asking a noisy teacher for 600 fine-grained labels on 20k pages felt like a recipe for learning noise.

So it's Tiers 1–2. A nice side effect: every Tier-2 label has a Tier-1 parent, so each result gives two numbers, a fine-grained one and a rolled-up coarse one, without labeling anything twice. If Tier 2 turns out too noisy, falling back to Tier 1 needs no relabeling, just the roll-up. Deeper topics fold into their parent: a page about vintage cars is just **Cars**.

## Next weekend

Getting the actual pages: 20,000 of them from Common Crawl, half Portuguese and half English.
