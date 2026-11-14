# 0007: Tier-1 implementation

- **Status:** accepted
- **Date:** 2026-11-14

## Context

Tier 1 is the sub-millisecond baseline: hashed n-grams and a linear model ([models.md](../models.md)). It needs a maintained library, multi-label output over 330 labels, Portuguese and English, and weights a Go server can load later. Training runs on one home machine (i7-13700F, RTX 4070 SUPER, about 23 GB of RAM in WSL).

## Options considered

1. **fastText** (`-loss ova`). Fast and compact, but archived upstream since 2024-03.
2. **scikit-learn one-vs-rest SGD** over `HashingVectorizer` features. Maintained and simple, but it fits 319 separate models, each a pass over the data in its own worker with its own copy. At 2^21 features it held about 5 GB of dense weights per model, kept every core busy and made the desktop lag (tried in W06 and stopped).
3. **scikit-learn hashing and TF-IDF features, with one linear layer over all labels in PyTorch** on the GPU (an `EmbeddingBag` in sum mode). The same model as option 2, trained jointly: one pass per epoch, about 670 MB of weights at 2^18 + 2^18 features, the CPU nearly idle.
4. **Vowpal Wabbit.** Fast and maintained, but another tool and format to learn for the same linear model.

## Decision

Option 3. Featurizing all 20,000 pages takes about 20 seconds and a fit about a minute, with no lag on the desktop. PyTorch is needed for tier 3 anyway. Code: `hayate.students.hashed`, `scripts/train_tier1.py`.

## Consequences

- The model is a weight matrix, a bias and the hashing parameters, so the Go request path (Phase 2) can reproduce it without Python, provided it matches scikit-learn's MurmurHash3 hashing and tokenization exactly.
- GPU training is slightly nondeterministic (atomic adds in the backward pass).
- Revisit if inference latency in W07 is far from sub-millisecond, or if a wider label set needs more capacity than one linear layer.
