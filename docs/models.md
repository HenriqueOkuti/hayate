# Student models

Snapshot 2026-10-07. Sources and details are in
[research/2026-10-07-students-benchmarking.md](research/2026-10-07-students-benchmarking.md).
The latencies below come from other people's hardware and are only a guide.

| Tier | Candidates | Expected | Role |
| --- | --- | --- | --- |
| 1. Hashed n-gram linear | sklearn `HashingVectorizer` + linear model (OvR), fastText `-loss ova`, Vowpal Wabbit | ≪ 1 ms/page | The sub-ms baseline |
| 2. Static embeddings + linear head | Model2Vec `potion-multilingual-128M` (MIT), `static-similarity-mrl-multilingual-v1` (Apache-2.0, includes pt/id/vi/th) | Probably sub-ms; tokenization dominates | **Main bet** for sub-ms *and* good |
| 3. Small encoder, int8, ONNX/OpenVINO | `multilingual-e5-small` (118M, MIT), `mmBERT-small` (42M non-embedding, MIT) | Several ms/page per core | The accuracy end of the curve |

Notes:

- **fastText** has been archived upstream since 2024-03. Pin it if used, and
  build tier 1 on a maintained library.
- **Thai** has no spaces between words. Character n-grams (`char_wb`) or a
  word segmenter are needed.
- **Model2Vec** can distill a static model from any sentence encoder in about
  30 s on CPU. That lets us distill tier 2 from our own tier-3 model.
- **Encoders not chosen:** ModernBERT is English-only. EuroBERT has no th or
  id.
- **Runtimes:**
  - ONNX Runtime with dynamic int8 (the recommended choice for transformers).
  - OpenVINO int8 was fastest on an i7-13700K in the sentence-transformers
    benchmarks.
  - Always time tokenization separately.
- **Input length** (URL + title + first N tokens) is swept for every tier.
- **The GPU (RTX 4070 SUPER)** is used for fine-tuning tier 3 and for a local
  teacher. All latency numbers are CPU.

## Background

- **Distillation:** Hinton 2015 ([1503.02531](https://arxiv.org/abs/1503.02531)),
  DistilBERT ([1910.01108](https://arxiv.org/abs/1910.01108)) and MiniLM
  ([2002.10957](https://arxiv.org/abs/2002.10957)).
- **Training on LLM labels:**
  - *Distill or Annotate?* ([2305.01645](https://arxiv.org/abs/2305.01645))
  - Pangakis & Wolken 2024 ([2406.17633](https://arxiv.org/abs/2406.17633))
  - CanDist ([2506.03857](https://arxiv.org/abs/2506.03857)): candidate-set
    labels for noisy teachers.
- **Closest precedents:**
  - The FineWeb-Edu classifier ([2406.17557](https://arxiv.org/abs/2406.17557)):
    Llama-3-70B labeled pages, and a small head on a frozen embedding model
    learned those labels.
  - WebOrganizer ([2502.10341](https://arxiv.org/abs/2502.10341)).
