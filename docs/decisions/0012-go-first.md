# 0012: Go first, Python only where it is still needed

- **Status:** accepted
- **Date:** 2026-11-14
- **Updates:** [0001](0001-stack.md)

## Context

Decision 0001 put all of Phase 1 in Python and kept Go for the Phase 2 request path. That was the agent's recommendation; Henrique works mainly in Go and was against a Python-heavy stack from the start. The first latency result ([results/bench-tier1-v1.md](../../results/bench-tier1-v1.md)) showed the cost: tier 1 takes 1.7 ms per page at batch 1, and three quarters of that is scikit-learn building character n-grams as Python strings. The latency side of the Phase 1 trade-off curve was measuring Python, not the model, which is the revisit condition 0001 named ("if the Go serving path becomes the main deliverable").

## Options considered

1. **Keep 0001.** Phase 1 latency stays a Python number; Go arrives in Phase 2. The curve would mislead on exactly the point it exists to show.
2. **Go for everything that serves,** Python for all training. Inference, latency benchmarks and the request path in Go, loading weights exported by Python.
3. **Go first, training included, with [GoMLX](https://github.com/gomlx/gomlx).** GoMLX (Apache-2.0, v0.28.0) has autodiff and AdamW, CUDA through XLA PJRT plugins it installs itself, a pure-Go CPU backend, ONNX import for fine-tuning pretrained models, and pure-Go Hugging Face tokenizers (README, read 2026-11-14). Tested on 2026-11-14 ([research note](../research/2026-11-14-gomlx-fit-test.md)): CUDA runs on the 4070 under WSL2, tier 1 trains in Go with an embedding bag at least as well as the PyTorch head, a Model2Vec model and multilingual-e5-small run in Go with the same outputs as Python, and the encoder fine-tunes. go-huggingface's Unigram tokenizer was wrong (greedy, and no Precompiled normalizer) and had to be fixed. The first draft of this record said no Go training stack existed; that was wrong, and Henrique pointed to GoMLX.

## Decision

Option 3, in order:

- **Now:** everything that runs at inference time, and every latency number on the trade-off curve, is Go, starting with tier 1 ([#82](https://github.com/HenriqueOkuti/hayate/issues/82)). Each Go model must give the same labels as its Python reference on every test page before its latency counts.
- **From W08:** new training is written in Go with GoMLX first. Tier 2 (static embeddings and a linear head) is the first job, and porting tier-1 training to GoMLX checks the embedding-bag question. Python is used for a new piece of work only after GoMLX was tried for it and the reason it failed is written down.
- **Existing Python** (labeling driver, splits, evaluation, tier-1 training) keeps working and is replaced as its Go version passes the same tests, not rewritten in one go.

## Consequences

- Each tier needs a Go loader and a parity test. For tier 1 that means reimplementing scikit-learn's hashing featurizer exactly. Models trained in GoMLX need no export step at all.
- Evaluation numbers must not move when code moves languages: a Go port of the metrics has to reproduce the Python results files before it replaces them.
- The Python latency numbers stay as references, never on the headline curve.
- The Phase 2 request-path server reuses the same Go packages, so it starts with working inference.
- Tokenizers for tiers 2 and 3 are Hayate's own Go code (a Unigram Viterbi and the normalizer chain), with a parity test against the tokenizers library; go-huggingface supplies downloads only.
- Revisit if GoMLX cannot train a tier at a reasonable speed on the 4070, or a tier has no feasible Go inference path.
