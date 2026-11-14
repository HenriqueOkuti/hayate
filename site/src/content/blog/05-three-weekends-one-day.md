---
title: "Weekends 5 to 7: three weekends in one day, and a lot less Python"
description: "Twenty thousand labels, my first exam, my first stopwatch, and the day Henrique made me admit I should be serving from Go."
pubDate: 2026-11-14
weekend: 5
tags: [labeling, evaluation, latency, go]
draft: true
---

GTA 6 comes out next weekend, so Henrique did three weekends of work in one day to buy himself the time. By the end I had a full set of labels, my first exam score, my first stopwatch reading, and a new home language.

![Hayate-chan sprints to the right in mid-stride, ponytail and orange scarf streaming behind her, holding a silver stopwatch out toward the viewer with its hand barely past the top, grinning smugly with her fang showing, on a pale cyan background with a large faint orange circle behind her](../../assets/weekend-05.png)

## What we did

- **Labeled all 20,000 pages.** Sonnet 5.5, my teacher, labeled every page on Henrique's Claude Code plan, no API key: 24.7 million tokens, and at most 9 points of the weekly usage meter (other sessions share it, so that is an upper bound). The run hit the 5-hour session limit once, stopped cleanly, and resumed later.
- **Split them so I can't cheat.** Pages are grouped by website before they go into train, validation or test, so I can't memorize a site and get quizzed on it. The reviewer agent found that splitting by domain wasn't enough: copies of the same template, mirrors and bot-check pages sat on dozens of different domains. Grouping by brand and by near-identical text cut the pairs of near-twins across splits from 947 to 2.
- **Took my first exam.** Tier 1 is my smallest form: hashed word and character snippets and one linear layer. "F1" is the score that balances "when I say a label, is it right?" against "do I find all the labels?".
- **Got timed.** A benchmark harness measures every call, on a "small VPS" Docker profile with 2 CPUs and 4 GB.
- **Moved into Go.** Story below.

## What surprised me

**My first version made Henrique's PC lag.** I was training 319 separate models, one per label, on every core, with gigabytes of weights each. He felt it. Training all labels at once on the GPU took about a minute and left the CPU almost idle. The lesson was about the method, not the language.

**But for speed, the language did matter.** Three quarters of my 1.7 ms per page in Python was spent chopping text into character snippets, one Python string at a time. Henrique asked why we were using so much Python when he'd wanted Go from the start. Fair: Python was the coding agent's recommendation back in October, not his. So my tier-1 brain now runs in Go. It gives exactly the same answers as the Python version on all 1,875 test pages (the same features, bit for bit), and it is under a millisecond at the median.

**The coding agent claimed Go couldn't train models. Wrong.** Henrique sent it [GoMLX](https://github.com/gomlx/gomlx), and we tested it on real work: it runs on his 4070, trains my tier-1 layer, loads a ready-made static-embedding model with the same outputs as Python, and runs a small multilingual encoder with the same outputs as ONNX Runtime. Go's Hugging Face tokenizer library got the static model's tokenizer wrong in two ways, so we wrote our own and matched Python on all 200 test texts.

**The reviewer caught the write-ups overselling, again.** They said "2.0 to 3.6 times faster" (it's 1.9 to 3.6), "about 20% slower when busy, at p50 and p99" (p99 ranged 4 to 34%), and "fine-tuning works in Go" (we only showed the trainer runs). All corrected before this post.

## Numbers

Exam score against my teacher, on 1,875 test pages from sites I never trained on (Tier 1 is the broad category, Tier 2 the specific topic):

| | Tier 2 F1 | Tier 1 F1 |
| --- | --- | --- |
| Me (tier 1), against Sonnet | 0.440 | 0.544 |
| Me, against the panel without Sonnet's vote (285 pages) | 0.402 | 0.528 |
| Sonnet itself, against that panel | 0.771 | 0.875 |

So I keep about half of my teacher's agreement with the other frontier models. A later rule that always keeps my best guess moved Tier 2 by +0.002, an interval that includes zero: no real change.

Speed per page at 3,000 characters, one thread, small-VPS profile on an i7-13700F under WSL2, heavy apps closed:

| | One page at a time, p50 / p99 | 32 pages at a time, p50 / p99 |
| --- | --- | --- |
| Python | 1.67 / 3.43 ms | 1.28 / 1.71 ms |
| Go | 0.62 / 1.75 ms | 0.62 / 0.83 ms |

Go is 1.9 to 3.6 times faster at the median across all settings. The two runs were 20 minutes apart with no reference check, and closing Henrique's apps alone sped Python up by 12 to 27%, so read those ratios loosely. "32 at a time" means each page's share of the call; a page still waits for the whole batch.

Full write-ups: [labels](https://github.com/HenriqueOkuti/hayate/blob/main/results/labels-bulk-v2.json), [tier 1](https://github.com/HenriqueOkuti/hayate/blob/main/results/tier1-v0.md), [Python latency](https://github.com/HenriqueOkuti/hayate/blob/main/results/bench-tier1-v1.md), [Go latency](https://github.com/HenriqueOkuti/hayate/blob/main/results/bench-tier1-go.md), [GoMLX test](https://github.com/HenriqueOkuti/hayate/blob/main/docs/research/2026-11-14-gomlx-fit-test.md).

## Next

Nov 21–22 belongs to GTA. On Nov 28–29: retrain my tier-1 layer in Go and find out why it scored better there, teach the benchmark to notice a busy machine, and decide whether tier 2 gets its own tokenizer. Then tier 2, in Go.
