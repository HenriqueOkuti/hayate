# 0013: Tier-2 tokenizer and embedding table

- **Status:** accepted
- **Date:** 2026-11-14

## Context

Tier 2 (W08, [#9](https://github.com/HenriqueOkuti/hayate/issues/9)) is static embeddings plus a linear head. A static model's tokenizer is tied to its embedding table, and Model2Vec lets the vocabulary be chosen when the table is distilled, so tier 2 can either take the stock `potion-multilingual-128M` with its Unigram tokenizer, or build its own vocabulary from the train pages with a tokenizer designed for Go speed. Constraints: serving is Go ([0012](0012-go-first.md)), latency is measured on one thread, the vocabulary may only come from train pages, and choices are made on val. The comparison is in [research/2026-11-14-tier2-tokenizer.md](../research/2026-11-14-tier2-tokenizer.md).

## Options considered

1. **Stock potion, fit-test Go tokenizer:** val Tier-2 F1 0.500, but 2.3 ms per page to tokenize in Go. Too slow to be the sub-millisecond tier.
2. **Stock potion, Go trie tokenizer:** the same tokens and F1, 0.32 ms p50 and 0.98 ms p99 per page end to end, 512 MB table. Best quality; needs the precompiled character map for exact parity (499 of 500 pages now).
3. **Train-page words only:** 54,166 words distilled from bge-m3, unknown words dropped, a hash-map tokenizer. Val F1 0.480 (paired -0.020, -0.033 to -0.007, against option 2), 0.05 ms p50 and 0.16 ms p99, 55 MB.
4. **Train-page words with a subword fallback:** between the two on speed (0.08 ms) but below option 3 on F1 (0.474) and six times its table; dominated.

## Decision

W08 builds tier 2 on **option 2**, stock `potion-multilingual-128M` with Hayate's Go trie tokenizer, since it is the best on val and already sub-millisecond at p50. **Option 3** goes on the trade-off curve as a second, cheaper tier-2 point: it matches tier1-v2-17's quality at a tenth of its latency. Before W08 settles, it tries Tokenlearn on the train-page vocabulary, which is what lifts potion over a plain distillation (5.5 points); if that brings the words-only table within val noise of potion, it becomes the main tier-2 build.

## Consequences

- W08 needs the real precompiled character map (or a parity check on many more pages) before potion's latency and F1 are recorded, and a double-array trie is the next tokenizer speed-up to try.
- Two tier-2 points instead of one: more to train and report, but the curve gets a point between tier 1 and potion.
- Revisit if Tokenlearn on our vocabulary closes the gap, if a test-set score disagrees with these val results, or if the 512 MB table is too large for the target instance.
