# Research notes: a custom tokenizer for tier 2?

Project: Hayate, issue [#91](https://github.com/HenriqueOkuti/hayate/issues/91). Question: should tier 2 use its own tokenizer and vocabulary instead of the stock Model2Vec one, and what would it gain in speed, size and quality? Run date: **2026-11-14**, on the i7-13700F and RTX 4070 SUPER under WSL2. Decision: [0013](../decisions/0013-tier2-tokenizer.md).

## Summary

| Variant | Val Tier-2 F1, cross-fitted | Paired against potion | Go total per page, p50 / p99 | Table (float32) |
| --- | --- | --- | --- | --- |
| potion-multilingual-128M, fit-test tokenizer (map lookups) | 0.500 | | 2.28 / 8.88 ms | 512 MB |
| potion-multilingual-128M, trie tokenizer (same tokens) | 0.500 | | 0.32 / 0.98 ms | 512 MB |
| Plain bge-m3 distillation, its own 250k pieces | 0.445 | -0.055 (-0.068 to -0.042) | not timed | 256 MB |
| Train-page words first, Unigram fallback | 0.474 | -0.027 (-0.040 to -0.014) | 0.08 / 0.34 ms | 300 MB |
| Train-page words only | 0.480 | -0.020 (-0.033 to -0.007) | 0.05 / 0.16 ms | 55 MB |

So: the stock model is the best quality, and a trie makes its tokenizer about 8 times faster with identical tokens. A vocabulary of our own words is a fifth of potion's time and a tenth of its memory, for 2 points of val F1. For scale, tier1-v2-17 scores 0.483 by the same rule-off cross-fitted measure, at 0.52 / 1.40 ms per page; words-only tier 2 matches that at a tenth of the time.

## How the variants were built

- **The probe** (`scripts/tier2_probe.py`, [results/tier2-probe-v0.json](../../results/tier2-probe-v0.json)) embeds each page as the l2-normalized mean of its token rows, as Model2Vec does, and trains one linear head to the 317 labels (binary cross-entropy, Adam with epsilon 1e-7, learning rate and epoch by val loss). It then fits one temperature and per-label thresholds, cross-fitted on val halves split by component, with no top-label floor. The input is tier 1's: URL words, title, description and 3,000 characters of text, tokenized whole (potion's `tokenizer.json` truncates at 512 tokens; that was switched off for every variant). Only train and val pages are read. One seed; the paired intervals resample val pages.
- **potion-multilingual-128M** (MIT) is a Model2Vec distillation of BAAI/bge-m3, further trained with Tokenlearn on 2 million C4 passages in 101 languages; 500,353 rows of 256 dimensions ([model card](https://huggingface.co/minishlab/potion-multilingual-128M), [Tokenlearn release](https://minish.ai/blog/2025-05-31-tokenlearn-release/)). bge-m3's own vocabulary is 250,002 pieces, so about 250k rows were added; the Tokenlearn post's example adds 250,000 frequent corpus words, which fits, but no source states it for this model.
- **Plain distillation:** `model2vec.distill("BAAI/bge-m3", pca_dims=256)` (model2vec 0.10.0), the control: same teacher as potion, no Tokenlearn, no added words. It is 5.5 points below potion, which is roughly what Tokenlearn and the added vocabulary are worth here.
- **Train-page vocabulary:** the 54,166 words (NFKC, lowercased, `\w+`) that occur on at least 3 train pages, passed to `distill(..., vocabulary=...)`. In model2vec 0.10 this adds the words to the teacher's subword vocabulary as whole-word pieces, each embedded by running the teacher on it ([distillation code](https://raw.githubusercontent.com/MinishLab/model2vec/main/model2vec/distill/distillation.py)); it does not replace the subwords. The model2vec docs say a domain vocabulary "can have a significant impact on performance" but publish no numbers ([docs](https://minish.ai/packages/model2vec/distillation)).
- **Word-first tokenizer** (ours, the same in Python and Go): NFKC, lowercase, `\w+` words; a vocabulary word is one token; any other word is segmented by the Unigram model on its own, or dropped (words only). 93% of val words are in the vocabulary. Dropping the rest scores 0.480 against 0.474 for segmenting them (not compared paired), and it leaves a table of only the 54,166 word rows.

## Go tokenizers

`go/exp/tier2tok` and `go/cmd/tier2-tokbench` ([results/tier2-tokbench.json](../../results/tier2-tokbench.json)): 500 test-page inputs, one page at a time on one pinned thread, timing tokenize, pool and a 256 x 317 linear head. Test pages are used for parity and latency only, as for tier 1.

- **Parity:** the word tokenizers give Python's token ids on 500 of 500 pages. The potion tokenizer gives them on 499 of 500 pages with each search; the one page differs because Go stands in NFKC for SentencePiece's precompiled character map (the same swap changes that page in Python too). W08 needs the real character map, or a larger check, before potion's numbers are final.
- **Trie:** the fit test's Viterbi looks up every substring up to the longest piece for the current character in a map (pieces reach 186 characters), so tokenizing costs 2.2 ms per page. One walk of a byte trie finds the same candidates in the same order, so the segmentation is identical (a unit test compares the two searches on 2,000 random strings; on the 500 pages both match Python equally often), and tokenizing drops to 0.26 ms. A double-array trie should go further: Perplexity reports moving Hugging Face's Unigram from a hash-map trie to a double-array one cut p50 from 155 to 68 us at 514 tokens ([blog](https://www.perplexity.ai/hub/blog/improving-unigram-tokenizer-cpu-performance); a company post, not a paper).
- **Where the time goes** (p50 per page): potion with the trie, tokenize 263 us, then pool and head about 60 us; words only, tokenize 17 us, pool and head about 30 us. Pooling is a gather of a few hundred 256-float rows, so the smaller table also helps the cache.

## Not tested

- **Tokenlearn on our own vocabulary:** potion's lead over the plain distillation suggests Tokenlearn is worth about as much as the vocabulary; training a words-only table with Tokenlearn on train pages could close the gap to potion while keeping the speed. That is a W08 experiment (it needs teacher embeddings of the train pages, a GPU job of minutes).
- **Other vocabulary sizes and frequency cut-offs,** other teachers, int8 or float16 tables, and test-set numbers: none were run. The two go-huggingface tokenizer bugs found in #86 stay fixed in Hayate's own code and are not reported upstream (Henrique's call).
