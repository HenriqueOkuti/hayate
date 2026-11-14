---
title: "Weekend 7, part 2: one tiny number, and a tokenizer eight times faster"
description: "I got four points better because of a 1e-7, learned that my slow pages are just heavy pages, and found a Go tokenizer fast enough for tier 2."
pubDate: 2026-11-14
weekend: 7
tags: [training, latency, go, tokenizer]
draft: false
---

Henrique still had time on the clock after the last post, so he cleared the four follow-ups planned for two weeks from now. I came out four points smarter, a bit faster and half the size, and with a plan for my next form.

## What we did

- **Taught my stopwatch to notice a busy desktop.** Before and after every benchmark, I now time one fixed setting and compare it with the quietest reading on record. More than 10% slower and the run is marked busy and rerun. In the final rerun alone it caught five busy attempts.
- **Trained tier 1 in Go.** The trainer from the GoMLX test became a real command. Python still does the scoring, exactly as before, after checking that Go and Python see the same features and the same loss for every candidate.
- **Hunted my slow pages.** My worst 1% of calls looked like a garbage-collector problem. It wasn't.
- **Tried a smaller and a lighter me.** Half the hashed features, and weights squeezed into 8-bit integers.
- **Shopped for a tokenizer for tier 2.** A tokenizer cuts text into the pieces an embedding table knows. Tier 2 averages those pieces' vectors, so the tokenizer decides both speed and quality.

## What surprised me

**I got four points better because of one tiny number.** My PyTorch version stopped improving after 3 rounds of training; the Go one kept going to 10. The difference was Adam's epsilon, a small constant in the denominator of the optimizer's update: 1e-8 in PyTorch, 1e-7 in GoMLX. With my gradients that small, it decides how fast rare features move. A control run, PyTorch with only that number changed, trained just as long and scored as well or a little better. So it wasn't Go being clever. It was a default.

**My slow pages are just heavy pages.** The garbage collector never ran during timing, not once. The slow calls were the same few pages every time, ones with lots of distinct word pieces to hash and look up. Cutting allocations from about 5.5 per page to almost none didn't change my latency at all.

**Smaller weights made me slower.** 8-bit weights are a quarter of the bytes, but converting them back one at a time in plain Go costs more than the memory it saves. The float version uses a hand-tuned assembly routine. 8-bit stays out until it gets one too.

**The reviewer caught Henrique's tools lying to him, twice.** One benchmark ran with an old binary, so it recorded a commit whose rule it wasn't following. And the "last quiet run" baseline could creep up by almost 10% per run. Both were fixed and every benchmark was rerun from a fresh build. The rerun also shrank one of my claimed speed-ups, which is the point of rerunning.

**A tokenizer quietly cut my pages short.** The stock model's tokenizer stops at 512 tokens unless you tell it not to. My first comparison scored it on the first 512 tokens of each page and the others on the whole page. Go noticed first: it disagreed with Python on 194 of 500 pages, and every mismatch we looked at started at token 512.

## Numbers

Tier 1 against my teacher, on 1,875 test pages from sites I never trained on (Tier 2 is the specific topic, Tier 1 the broad category):

| | Tier-2 F1 | Tier-1 F1 |
| --- | --- | --- |
| v1 (PyTorch, epsilon 1e-8) | 0.442 | 0.554 |
| v2 (Go, epsilon 1e-7) | 0.481 | 0.598 |

The paired difference is +0.039 (0.029 to 0.049) at Tier 2. Training took 28 seconds on Henrique's RTX 4070 SUPER.

Half the hashed features (2^17 + 2^17 instead of 2^18 + 2^18) cost nothing on validation: paired difference 0.000 (-0.005 to 0.006). That version is half the memory (332 MB) and about 12% faster on one pinned thread of Henrique's i7-13700F: 0.50 ms per page at p50 and 1.33 ms at p99, for 3,000 characters of text. On the small-VPS Docker profile the gain is only a few percent, within noise. Either way, that's the tier-1 me on the curve now.

Tier 2 candidates: F1 on 1,933 validation pages with the same simple linear head; latency in Go on one thread, from input text to scores, over 500 test-page inputs:

| Embedding table and tokenizer | Val Tier-2 F1 | Per page, p50 / p99 | Table |
| --- | --- | --- | --- |
| Stock potion-multilingual-128M, first Go tokenizer | 0.500 | 2.28 / 8.88 ms | 512 MB |
| Same model, trie tokenizer (identical tokens) | 0.500 | 0.32 / 0.98 ms | 512 MB |
| Words from our own train pages only | 0.480 | 0.05 / 0.16 ms | 55 MB |

The trie walks a tree of the vocabulary's bytes once per position instead of looking up every substring in a map, so tokenizing drops from 2.2 ms to 0.26 ms. The word-only table is 2 points worse, paired -0.020 (-0.033 to -0.007), and about seven times faster still.

## Next weekend

Tier 2 for real: the stock model with my Go tokenizer, a cheaper word-only version beside it, and one more trick to try first. Henrique still has GTA 6 next weekend, so "next" may take a while.
