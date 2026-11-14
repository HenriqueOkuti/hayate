# Research notes: can Go carry training and inference for tiers 1 to 3?

Project: Hayate, issue [#86](https://github.com/HenriqueOkuti/hayate/issues/86). Question: does GoMLX, or another Go option, fit what decision [0012](../decisions/0012-go-first.md) asks of it, tested with real runs rather than READMEs.

Run date: **2026-11-14**, on the i7-13700F and RTX 4070 SUPER under WSL2. Versions: GoMLX v0.28.34 (XLA PJRT CUDA plugin from JAX 0.12.0.1, CUDA 13; PJRT CPU v0.117.2), go-huggingface v0.4.32, onnx-gomlx v0.5.31, parquet-go v0.32.0, Go 1.27.1. The code is in `go/exp/gomlx/` (its own Go module, so its dependencies stay out of `go/tier1`). The Python references are `scripts/model2vec_reference.py` and `scripts/e5_reference.py`, run with `uv run --with` so nothing is added to the project.

## Summary

| Need | Go path | Result |
| --- | --- | --- |
| GPU training at all | GoMLX, XLA CUDA backend | Works under WSL2; a float32 4096 x 4096 product in 4.7 ms (about 29.5 TFLOP/s, TF32) |
| Tier 1 training (sparse hashed features) | GoMLX: `Gather` + `ScatterSum` embedding bag, AdamW | Works; 1.4 s per epoch, val loss and F1 at least as good as the PyTorch head |
| Tier 1 data pipeline | parquet-go, `go/tier1` featurizer | Works; reads the 20k sample in 0.8 s, featurizes it in 4.2 s; IDF equal to Python's to 9e-16 |
| Tier 2 (Model2Vec static embeddings) | go-huggingface download, own Unigram and normalizer | Exact after two fixes: same token ids on 200/200 texts, embeddings within 3e-8 |
| Tier 3 (small encoder) inference | onnx-gomlx on multilingual-e5-small | Matches ONNX Runtime: cosine 0.99999994 on CPU, 0.9999999 on GPU |
| Tier 3 fine-tuning | onnx-gomlx graph inside a GoMLX trainer | Gradients flow; loss falls every step; 75 ms per step for 20 x 256 tokens |

So every tier has a working Go path. The weak spot is not GoMLX itself but go-huggingface's tokenizers, which got the Model2Vec tokenizer wrong in two ways.

## 1. GPU and CPU backends

- `GOMLX_BACKEND=xla:cuda` downloaded and installed the CUDA PJRT plugin and NVIDIA libraries on first use (about 2.5 GB into `~/.cache/go-xla` and `~/.local/lib/go-xla`), then ran. The first call compiles (0.8 s for the matrix product).
- The GPU result of the product differs from the CPU one by 0.02%: XLA uses TF32 for float32 matrix products by default. Fine for training; latency numbers stay on the CPU in Go (decision 0012), so this does not touch them.
- The pure-Go backend (`GOMLX_BACKEND=go`) needs nothing installed and ran the same product at about 105 GFLOP/s, a usable fallback for small jobs.

## 2. Tier 1, all in Go (`cmd/tier1-train`)

- **Data:** parquet-go reads `pages.parquet` (20,000 rows) and `splits-v1.parquet` in 0.8 s; the teacher labels are JSON lines.
- **Features:** the parity-checked `go/tier1` featurizer builds the inputs and hashed counts for all pages in 4.2 s on one core. The IDF fitted in Go on the train pages equals the one scikit-learn fitted, to 9e-16, and the learned label set equals the PyTorch run's.
- **Model:** an embedding bag from GoMLX ops: gather the weight rows of a batch's non-zero features, multiply by the TF-IDF values, scatter-sum into per-page logits. Batches are padded to a multiple of 65,536 entries so XLA compiles only a few shapes. Binary cross-entropy, AdamW (learning rate 0.01, no weight decay, as tier1-v1), early stopping on val loss.
- **Gotchas met:** a sub-scope may be entered only once per graph (`scope.In("head")` twice panics), and GoMLX does not broadcast across ranks (the `[317]` bias needs `InsertAxes(bias, 0)`).
- **Result on val**, both heads scored by the same Go code (micro F1 at the best single global threshold, threshold chosen on val, so this compares pipelines and is not a test result):

| | GoMLX head | PyTorch head (tier1-v1) |
| --- | --- | --- |
| Val binary cross-entropy | 0.01365 | 0.01478 |
| Val micro F1, best global threshold | 0.478 | 0.422 |
| Epochs, time | 11 (best of 14), 28 s | 3 at the chosen learning rate |

The PyTorch head stopped at epoch 3 at the same learning rate, where GoMLX kept improving to epoch 11, so the gap most likely reflects a difference in Adam defaults or initialization in the PyTorch run, not a Go advantage. It shows that a Go-trained tier 1 is at least as good, and it is a reason to retrain tier 1 in Go rather than port the PyTorch weights.

## 3. Tier 2, Model2Vec in Go (`cmd/tier2-check`)

Model: `minishlab/potion-multilingual-128M` (one float32 `embeddings` tensor, 500,353 x 256; Unigram tokenizer with a Precompiled normalizer, about 30 Replace rules, Strip and Metaspace). Reference: Python `model2vec` 0.10.0 on 200 test-page inputs of 1,000 characters.

- **go-huggingface's tokenizer as shipped:** 0 of 200 texts tokenized like Python, at 115 ms per text. Two causes:
  1. Its Unigram model is greedy longest-match, not Viterbi. On "Faith" it picked `▁Fai` + `th` (score -22.74) over `▁F` + `aith` (-21.30).
  2. It has no `Precompiled` normalizer (SentencePiece's character map) and skips it silently, so for example `™` was not turned into `TM` and became unknown.
- **Fixes, in `cmd/tier2-check`:** a Viterbi over the vocabulary scores (unknown pieces scored at the minimum minus 10 and fused, as the tokenizers library does), the normalizer chain built from `tokenizer.json` with Precompiled approximated by NFKC and Rust's Unicode `\s` widened for Go's regexp, and Metaspace (prepend `▁`, no split).
- **After the fixes:** the same token ids on 200 of 200 texts, embeddings within 3e-8. Encoding takes 1.6 ms per 1,000-character text against 0.53 ms for Python's Rust tokenizer; the Viterbi still tries pieces up to 186 characters long from every position, which a trie would cut.
- NFKC standing in for Precompiled matched on these 200 texts; the real character map can differ on rare characters, so the W08 tokenizer needs a larger parity check or the charsmap itself.

## 4. Tier 3, a small encoder through onnx-gomlx (`cmd/tier3-check`)

Model: `intfloat/multilingual-e5-small`, its published `onnx/model.onnx`. Reference: ONNX Runtime (CPU) in Python, 20 test-page inputs of 256 tokens, mean-pooled and normalized.

- **Inference:** the converted graph gives the same embeddings: lowest cosine 0.99999994 and largest difference 1.1e-7 on XLA CPU; 0.9999999 and 8e-5 on the GPU (TF32). A forward pass of 20 x 256 tokens takes 26 ms on the GPU and 535 ms on XLA CPU.
- **Fine-tuning:** the encoder graph plus a linear head to 317 labels, inside a GoMLX trainer with AdamW on every weight: the loss fell on each of 8 steps (0.713 to 0.650) against fixed pseudo-labels, at 75 ms per step after an 11 s compile, using about 1.6 GB of GPU memory. So W09 can fine-tune in Go.
- The tokenizer for e5 (XLM-R SentencePiece, Unigram) is the same family as tier 2's, so the fixed Viterbi tokenizer applies; mmBERT-small (Gemma's BPE tokenizer) was not tested.

## 5. Not tested, and alternatives

- **mmBERT-small** and other encoders through onnx-gomlx; only e5-small was converted.
- **Alternatives** were not needed: onnxruntime-go (inference only, C library) and hugot (pipelines on GoMLX or ONNX Runtime) stay as fallbacks if onnx-gomlx fails on a model.
- **Speed of Go-side tokenization** for tiers 2 and 3 needs a trie before it goes on the latency curve.

## Consequences for the plan

- Decision 0012 holds: W08 (tier 2) and W09 (tier 3) can be done in Go with GoMLX, and tier 1 can be retrained in Go.
- The tokenizer is the part to own: a Go Unigram tokenizer with a Viterbi, the full normalizer chain and a parity test against the tokenizers library, reused by tiers 2 and 3. The two go-huggingface bugs are worth reporting upstream.
