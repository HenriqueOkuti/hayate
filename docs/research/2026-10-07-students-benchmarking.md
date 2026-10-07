# Research notes: student models, CPU runtimes, benchmarking, cost, evaluation

For: `categorizer` (distill an LLM into a tiny, fast multi-label web-page categorizer; PT+EN first, later ID/VI/TH).
Compiled: 2026-10-07. Public sources only. Every fact has a URL; anything not checked against a primary source is marked **UNVERIFIED**.
All URLs accessed 2026-10-07 unless noted.

---

## 1. Tiny linear students

### fastText (supervised mode)

| Item | Finding | Source |
|---|---|---|
| Paper | Joulin, Grave, Bojanowski, Mikolov, "Bag of Tricks for Efficient Text Classification", arXiv 1607.01759 (v1 6 Jul 2016; EACL 2017) | https://arxiv.org/abs/1607.01759 |
| Model | Bag of words + word n-grams, averaged embeddings, linear classifier; n-grams hashed into **10M bins (bigrams only) or 100M bins otherwise**; hierarchical softmax over a Huffman tree | https://ar5iv.labs.arxiv.org/html/1607.01759 |
| Headline speed claim | Trains on >1B words in <10 min on a multicore CPU; classifies ~half a million sentences among 312K classes in <1 min | https://arxiv.org/abs/1607.01759 |
| Inference timing (Table 5, YFCC100M tag prediction, **test on a single thread**) | fastText h=50: test 48 s; h=50+bigram: 50 s; h=200: 1m29s; h=200+bigram: 1m37s (vs Tagspace 6h-15h). Derived: with ~0.5M test items (per abstract) this is roughly **0.1-0.2 ms/item single-thread, with 312K output classes**. Our label space is ~hundreds, so expect far less (derived estimate, not a reported number). | https://ar5iv.labs.arxiv.org/html/1607.01759 |
| Training speed (sentiment, Table 2) | 1-10 s per epoch on AG...Amazon datasets with 20 threads, vs hours/days for char-CNN/VDCNN on a K40 GPU | same |
| Multi-label | `-loss ova` (one-vs-all, independent binary classifiers); predict with `k=-1, threshold=t`. Tutorial advises lowering lr (example `-lr 0.5`). | https://fasttext.cc/docs/en/supervised-tutorial.html |
| Quantization (.ftz) | `fasttext quantize` → `.ftz`, product quantization ("FastText.zip", Joulin et al. arXiv 1612.03651, Dec 2016): about 2 orders of magnitude less memory, "only slightly inferior" accuracy. Options `-cutoff -retrain -qnorm -qout -dsub`. | https://arxiv.org/abs/1612.03651 ; https://github.com/facebookresearch/fastText |
| Autotune | `-autotune-modelsize 2M` searches quantization params for best F1 at a size cap; `-autotune-metric f1:__label__X` or `recallAtPrecision:30`; default duration 5 min | https://fasttext.cc/docs/en/autotune.html |
| License | MIT | https://github.com/facebookresearch/fastText |
| **Maintenance** | **Repo archived (read-only) by owner on 19 Mar 2024**; last commit 2024-03-13 (GitHub API). PyPI `fasttext` 0.9.3 released 12 Jun 2024 (previous 0.9.2 was Apr 2020); classifiers still say Python 2.7/3.4-3.6, "Alpha". Community fork `fasttext-numpy2` (0.10.4, Nov 2024) exists to fix NumPy 2 compatibility. | https://github.com/facebookresearch/fastText ; https://pypi.org/project/fasttext/ ; https://pypi.org/project/fasttext-numpy2/ |

Implication: fastText still works and is the canonical sub-ms baseline, but it is unmaintained. Pin the version, and keep a maintained alternative (sklearn/VW, or a small custom hashed-bag-of-ngrams model) for the same "student 1" tier.

### Vowpal Wabbit

| Item | Finding | Source |
|---|---|---|
| Status | Not archived; last push 2026-09-28; latest release **9.11.9 (2026-09-27)** (GitHub API) | https://github.com/VowpalWabbit/vowpal_wabbit ; https://api.github.com/repos/VowpalWabbit/vowpal_wabbit/releases/latest |
| Features | Hashing trick (bounded feature space), online learning, reductions, active learning, contextual bandits; memory bounded independent of data size | https://github.com/VowpalWabbit/vowpal_wabbit |
| License | BSD-style 3-clause text in LICENSE (copyright Microsoft / Yahoo!); GitHub's API reports `NOASSERTION` | https://raw.githubusercontent.com/VowpalWabbit/vowpal_wabbit/master/LICENSE |
| Multi-label | VW has `--multilabel_oaa` / `--csoaa` reductions: **UNVERIFIED** (not on the README; check the VW wiki). | — |
| Speed | README says "fast", comparable to other online learners, but gives no numbers | same |

### scikit-learn HashingVectorizer + SGDClassifier

| Item | Finding | Source |
|---|---|---|
| Version | Docs show scikit-learn 1.9.1 | https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.text.HashingVectorizer.html |
| Defaults | `n_features=2**20`, `alternate_sign=True`, `ngram_range=(1,1)`, `analyzer` in {word, char, char_wb}, `norm='l2'` | same |
| Pros/cons | Stateless (no vocab, `partial_fit`/streaming friendly, tiny pickle). No inverse transform (hard to interpret), collisions possible ("rarely an issue" at e.g. 2**18), no IDF without a separate TfidfTransformer | same |
| Multi-label | Wrap `SGDClassifier`/`LogisticRegression` in `OneVsRestClassifier` (standard sklearn pattern; the docs page itself does not cover it) | https://scikit-learn.org/stable/modules/multiclass.html (not fetched in this pass) |
| Speed | No official per-item latency figure. In Python, per-call overhead (tokenizing via regex, scipy sparse construction) likely dominates for single items: **UNVERIFIED, needs measurement**. | — |

Practical note (opinion): `char_wb` 2-5-grams make a language-agnostic baseline that matters for Thai (no spaces between words). fastText's whitespace tokenization needs a Thai word segmenter first.

---

## 2. Static embeddings (+ linear head)

| Model | Params / size | Dim | Languages | License | Reported speed / quality | Source |
|---|---|---|---|---|---|---|
| Model2Vec (method/library, MinishLab) | potion-base-8M: 7.56M params (~8 MB file) | 256 (potion) | EN for potion-base-* | MIT | "up to 500x faster on CPU", "up to 50x smaller"; distillation needs no data, ~30 s on CPU; latest release v0.9.0 (2026-08-12) | https://github.com/MinishLab/model2vec ; https://huggingface.co/api/models/minishlab/potion-base-8M |
| potion-multilingual-128M | 128.09M params (it is mostly an embedding table) | 256 | **101 languages** (card); teacher **BAAI/bge-m3** | MIT | "orders of magnitude faster", no numbers | https://huggingface.co/minishlab/potion-multilingual-128M |
| Model2Vec MTEB (EN) | — | — | — | — | MTEB avg: all-MiniLM-L6-v2 55.93; potion-base-32M 52.13; potion-base-8M 51.08. **Classification**: 69.25 / 71.70 / 70.34 (potion ≥ MiniLM on classification) | https://github.com/MinishLab/model2vec/blob/main/results/README.md |
| Model2Vec MMTEB | — | — | — | — | potion-multilingual-128M: mean(TaskType) 40.40, Classification 52.36, MultiLabelClassification 15.95 | same |
| Model2Vec training-throughput (classification head, CPU) | — | — | — | — | samples/s: TF-IDF 108,434; model2vec+logreg 17,925; model2vec full fine-tune 24,744; SetFit(MiniLM) 716. Average accuracy over 14 datasets: SetFit 82.6, m2v+logreg 78.0, m2v fine-tune 79.2 | same |
| static-retrieval-mrl-en-v1 (sentence-transformers) | EmbeddingBag | 1024 (Matryoshka) | EN | Apache-2.0 | **107,419 sentences/s on CPU** (i7-13700K, GooAQ queries, tuned batch size) vs all-MiniLM-L6-v2 1,739/s and all-mpnet-base-v2 270/s. ~87.4% of mpnet's NanoBEIR | https://huggingface.co/blog/static-embeddings |
| static-similarity-mrl-multilingual-v1 | EmbeddingBag(105,879 × 1024) ≈ 108M values; "0 active params" | 1024, MRL down to 32 | **51 tags incl. pt, id, vi, th**; bert-base-multilingual-uncased tokenizer | Apache-2.0 | ~125x faster on CPU than multilingual-e5-small; ~92.3% of e5-small on STS, 86.52% on classification | https://huggingface.co/sentence-transformers/static-similarity-mrl-multilingual-v1 ; https://huggingface.co/blog/static-embeddings |
| Blog post | Tom Aarsen, "Train 400x faster Static Embedding Models with Sentence Transformers", 15 Jan 2025 | | | | | https://huggingface.co/blog/static-embeddings |
| WordLlama | default ~16 MB, 256-d; Matryoshka 64-1024 | 64-1024 | Not stated (likely EN-centric, **UNVERIFIED**); can load Model2Vec multilingual | MIT | Recycles LLM token-embedding codebooks (LLaMA 2/3 70B, phi-3); benchmark chart only, no numbers in text; v0.3.9; last news 2025-02-01 | https://github.com/dleemiller/WordLlama |

Derived: 107K sentences/s on a 16-core desktop CPU for short queries ≈ 9 µs per query across the machine. Web pages are much longer, but static embedding cost is O(tokens) with a table lookup plus a mean, so **tokenization probably dominates** (see §4). Static models are the most likely route to sub-ms with quality above fastText on multilingual text.

---

## 3. Small encoders for CPU

Parameter counts come from HF `safetensors.total` via the HF API (https://huggingface.co/api/models/<id>) unless noted. In multilingual models most parameters sit in the embedding table, which does not cost FLOPs. The non-embedding (transformer) size is what drives latency.

| Model | Total params | Layers / hidden | Languages | Max seq | License | Notes / source |
|---|---|---|---|---|---|---|
| paraphrase-multilingual-MiniLM-L12-v2 | 117.65M | 12 / 384 | "50 languages" tag | 128 | Apache-2.0 | https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 |
| multilingual-e5-small | 117.65M | 12 / 384 | ~100 (XLM-R family). Exact count **UNVERIFIED** on the card | 512 (**UNVERIFIED**) | MIT | Initialized from microsoft/Multilingual-MiniLM-L12-H384; report arXiv 2402.05672 (Feb 2024). https://huggingface.co/intfloat/multilingual-e5-small |
| microsoft/Multilingual-MiniLM-L12-H384 | ~118M (**UNVERIFIED**, no safetensors) | 12 / 384 | XLM-R tokenizer | — | MIT | https://huggingface.co/microsoft/Multilingual-MiniLM-L12-H384 |
| mmBERT-small | 140M total / **42M non-embedding** | 22 layers (stated for base; small **UNVERIFIED**) | pretrain 60 → mid 110 → decay **1,833** langs (FineWeb2) | 8,192 | MIT (HF card metadata) | Gemma 2 tokenizer; HF blog 9 Sep 2025; paper arXiv 2509.06888 (ICML 2026 poster). https://huggingface.co/blog/mmbert |
| mmBERT-base | 307M total / 110M non-embedding | 22 | same | 8,192 | MIT | "2-4x" faster than previous multilingual encoders (blog). Same sources |
| ModernBERT-base / large | 149M / 395M | 22 / 28 | **English (+code) only**, ~2T tokens | 8,192 | Apache-2.0 | arXiv Dec 2024. https://huggingface.co/answerdotai/ModernBERT-base |
| EuroBERT-210m (also 610m, 2.1B) | 310M (HF safetensors total; the name counts non-embedding) | — | 15: en, fr, de, es, zh, it, ru, pl, **pt**, ja, **vi**, nl, ar, tr, hi. **No th, no id** | 8,192 | Apache-2.0 | arXiv 2503.05500 (Mar 2025). https://huggingface.co/EuroBERT/EuroBERT-210m ; https://arxiv.org/html/2503.05500 |
| BERTimbau base / large (PT-BR) | ~110M / ~335M | 12 / 24 | Brazilian Portuguese (brWaC) | 512 | MIT | Souza, Nogueira, Lotufo, BRACIS 2020. https://huggingface.co/neuralmind/bert-base-portuguese-cased |
| XLM-R base | 278.9M | 12 / 768 | 100 (card text; tag says 94) | 512 | MIT | 2.5 TB CC-100. arXiv 1911.02116. https://huggingface.co/FacebookAI/xlm-roberta-base |
| distilbert-base-multilingual-cased | 135.4M | 6 / 768 | 104 (**UNVERIFIED**, not fetched) | 512 | Apache-2.0 | https://huggingface.co/distilbert/distilbert-base-multilingual-cased |
| all-MiniLM-L6-v2 (EN reference) | 22.7M | 6 / 384 | EN | 256 (**UNVERIFIED**) | Apache-2.0 | https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2 |

A distilled multilingual BERT specific to Portuguese (a "DistilBERTimbau"-style model): no well-known official one found in this pass. **UNVERIFIED**, search HF further.

### Distillation literature

| Paper | Key claim | Source |
|---|---|---|
| Hinton, Vinyals, Dean 2015, "Distilling the Knowledge in a Neural Network" (NIPS 2014 DL workshop) | Compress an ensemble's or large model's knowledge into a small model (soft targets with temperature are in the body, not the abstract) | https://arxiv.org/abs/1503.02531 |
| DistilBERT (Sanh et al., Oct 2019) | 40% smaller, 60% faster, keeps 97% of BERT's language understanding; triple loss (MLM + distillation + cosine) | https://arxiv.org/abs/1910.01108 |
| TinyBERT (Jiao et al., Findings EMNLP 2020) | 4-layer: >96.8% of BERT-base on GLUE, 7.5x smaller, 9.4x faster | https://arxiv.org/abs/1909.10351 |
| MiniLM (Wang et al., Feb 2020) | Distils last-layer self-attention (+ value relations); >99% on SQuAD 2.0 / GLUE at 50% compute; works for multilingual | https://arxiv.org/abs/2002.10957 |
| Distilling Step-by-Step (Hsieh et al., Findings ACL 2023) | LLM rationales as extra multi-task supervision; a 770M T5 beats few-shot 540B PaLM using 80% of the data | https://arxiv.org/abs/2305.02301 |
| Distill or Annotate? (arXiv 2305.01645) | Distilling T5-XXL (11B) → T5-Small (60M) is almost always more cost-efficient than annotating more data for the small model | https://arxiv.org/html/2305.01645v3 |
| Knowledge Distillation in Automated Annotation (arXiv 2406.17633) | Supervised classifiers trained on LLM-generated labels; estimated GPT-4 labeling of 6.2M tweets ~ $8,990 vs <$15 for 1K labels + classifier (2024 prices) | https://arxiv.org/pdf/2406.17633 |
| FineWeb-Edu classifier (Penedo et al., arXiv 2406.17557) | **Closest public analog to this repo**: Llama-3-70B-Instruct scored 460K web pages (0-5 educational); 410K annotations used to train a regression head on a frozen Snowflake-arctic-embed-m; then applied to the whole web corpus. Released as HuggingFaceFW/fineweb-edu-classifier (Apache-2.0) | https://arxiv.org/pdf/2406.17557 ; https://huggingface.co/HuggingFaceFW/fineweb-edu-classifier |
| Community ModernBERT re-fit of FineWeb-Edu labels | Binary F1@3: 0.7455 (full fine-tune) vs 0.6490 (reproduced frozen-encoder original). Third-party, **UNVERIFIED** | https://huggingface.co/staghado/edu-modernbert |

---

## 4. CPU inference runtimes and quantization

| Runtime | Latest release (GitHub API) | Key facts | Source |
|---|---|---|---|
| ONNX Runtime | v1.30.0 (2026-09-10) | Docs recommend **dynamic** quantization for transformers/RNNs and static for CNNs. CPU: S8S8 with QDQ is the default and first choice. On AVX2/AVX512 *without VNNI*, U8S8 can saturate (try reduce_range or U8U8); VNNI machines do not need reduce_range. ARM with dot-product instructions performs well and has no saturation problem. Gains are hardware dependent; on older CPUs int8 may be slower. | https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html |
| ORT threading | — | `intra_op_num_threads=0` → one thread per physical core with some affinitization; setting it explicitly removes affinity. Manual pinning via `session.intra_op_thread_affinities`. Spinning is on by default (`allow_spinning`). Confining to one NUMA node gave ~20% in one test. | https://onnxruntime.ai/docs/performance/tune-performance/threading.html |
| HF Optimum | v2.3.0 (2026-08-04) | ONNX export, O1-O4 graph optimization, quantization configs | https://github.com/huggingface/optimum |
| sentence-transformers backends | — | `backend="onnx"/"openvino"`; `export_dynamic_quantized_onnx_model(config in {arm64, avx2, avx512, avx512_vnni})`; `export_static_quantized_openvino_model` (calibration, default SST-2). Benchmarks on i7-13700K: **OpenVINO int8 fastest locally; llama.cpp fastest on an HF cloud CPU instance**. Recommendation: openvino-qint8 if a small accuracy loss is OK, else openvino (Intel) / onnx (others). Numeric speedups appear only in a chart. | https://sbert.net/docs/sentence_transformer/usage/efficiency.html |
| OpenVINO | 2026.4.1 (2026-10-01) | Intel-optimized; static int8 via NNCF/Optimum Intel | https://github.com/openvinotoolkit/openvino |
| CTranslate2 | v4.8.2 (2026-08-31) | MIT. Encoder-only BERT, DistilBERT, **XLM-RoBERTa** supported. INT8/INT16/FP16/BF16/AWQ-INT4; CPU backends MKL, oneDNN, OpenBLAS, Ruy, Apple Accelerate; x86-64 and AArch64 | https://github.com/OpenNMT/CTranslate2 |
| llama.cpp | MIT, active (push 2026-10-07) | GGUF; supports BERT-style embedding models (fastest on cloud CPU per sbert docs above). **Classification-head support for arbitrary encoders is UNVERIFIED.** | https://github.com/ggml-org/llama.cpp |
| HF tokenizers (Rust) | v0.23.2 (2026-09-03) | Rust core with Python/Node bindings, Apache-2.0. Repo README no longer states a text throughput figure (the old "<20 s per GB" claim is **UNVERIFIED** here). | https://github.com/huggingface/tokenizers |

### Reported per-item CPU latencies (all need re-measurement on our hardware)

| Setup | Number | Reliability | Source |
|---|---|---|---|
| all-MiniLM-L6-v2, torch, i7-13700K, batched short queries | 1,739 sentences/s (≈0.58 ms/sentence amortized over all cores) | Good (HF blog) | https://huggingface.co/blog/static-embeddings |
| static-retrieval-mrl-en-v1, same setup | 107,419 sentences/s | Good | same |
| DistilBERT seq-cls, HF Infinity on AWS c6i (Ice Lake), 1-8 physical cores, seq 8-512, bs 1-32 | "down to 1-4 ms latency for sequence lengths up to 64 tokens" (end-to-end incl. tokenization). Infinity was discontinued in Dec 2022. | Vendor blog, Jan 2022 | https://huggingface.co/blog/infinity-cpu-performance |
| mpnet-base(?) bs=1, Ryzen 7 5800H (AVX2, no VNNI), 1 core pinned | torch FP32 p50 32.4 / p99 45.1 ms; ORT FP32 24.8 / 29.2; ORT int8 dynamic **6.1 / 8.4 ms** | Low: single-author arXiv; table does not name model or seq length | https://arxiv.org/html/2602.00899 |
| Fast DistilBERT on CPUs (Intel, 2022) | up to 4.1x over ONNX Runtime (sparsity + quantization); no absolute numbers in the abstract | Vendor paper | https://arxiv.org/abs/2211.07715 |

Takeaway (opinion, consistent with the numbers above): a 6-12-layer 384-d encoder on 256-512 tokens of page text will likely cost **several ms per page per core even with int8**, so it sits well above the sub-ms target. Sub-ms needs fastText/hashed linear models or static embeddings. Encoders give the high-accuracy end of the curve. Truncating input (title + first N tokens) is the main latency lever for encoders.

---

## 5. Benchmark methodology

**Inference micro-benchmarks**
- Warm up (first calls include allocation, graph optimization, page faults), then take many iterations. Report p50/p90/p99/max, not only mean. pytest-benchmark reports min/max/mean/stddev/median/IQR/outliers/ops but **no p99** by default, so use `--benchmark-save-data`/`--benchmark-json` to dump raw timings and compute percentiles yourself. It also offers `--benchmark-disable-gc`, `--benchmark-warmup`, `--benchmark-min-rounds`, `pedantic` mode and `--benchmark-compare-fail` for regression gates. https://pytest-benchmark.readthedocs.io/en/latest/usage.html
- Use `time.perf_counter_ns` in Python. Measure separately: (a) tokenization/feature extraction, (b) model forward, (c) total from extracted text to scores. The README already separates inference from request latency.
- Fix threads explicitly (ORT `intra_op_num_threads`; `OMP_NUM_THREADS`, `MKL_NUM_THREADS`; torch `set_num_threads`). Pin with `taskset`/`numactl` and record physical cores vs vCPUs (on AWS x86, 2 vCPU = 1 physical core with SMT; Graviton vCPU = physical core: **UNVERIFIED in this pass**, see AWS docs). ORT spin-wait inflates CPU use and flatters latency: record the setting. https://onnxruntime.ai/docs/performance/tune-performance/threading.html
- Sweep batch sizes (1, 8, 32, 128...). Batch=1 latency and batched throughput go on separate curves. Sweep input length (tokens), or fix it and report the length distribution.
- Report: CPU model and microarchitecture flags (AVX2/AVX-512/VNNI/AMX, ARM dotprod/SVE), cores/threads, memory, OS/kernel, runtime and versions, quantization config, model hash, taxonomy version (the README already requires much of this). Turbo/frequency scaling and noisy neighbours on cloud VMs add variance: run multiple trials and report the spread.
- CLI-level timing: **hyperfine** gives warmup (`-w`), fixed runs (`-r`), `--prepare` (e.g. cache drop), outlier warnings, JSON/CSV/Markdown export, and `--shell=none` to avoid shell overhead for <5 ms commands. Install refs v1.21.0. https://github.com/sharkdp/hyperfine

**Request / HTTP benchmarks (end-to-end latency)**
- **Coordinated omission**: closed-loop load generators (classic wrk, closed-model k6) wait for a response before sending the next request, so they under-sample slow periods. wrk2 example: one 1.4 s stall gave a corrected p99 of 1.27 s vs an uncorrected ~6 ms (~200x). Fix it with constant-rate (open-model) load where latency is measured from the *scheduled* send time. Use `wrk2 -R <rate> --latency` (HdrHistogram; `--u_latency` shows the uncorrected histogram). https://github.com/giltene/wrk2
- k6: use open-model executors `constant-arrival-rate` / `ramping-arrival-rate`. https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/open-vs-closed/
- Report latency vs offered load (a curve), not a single number at an unknown load. Page fetch time depends on remote sites: keep a recorded corpus/replay for repeatable runs and report live fetch separately.

---

## 6. Cloud prices (for cost per million pages)

### AWS, us-east-1 (N. Virginia), Linux, shared tenancy
On-demand: AWS Price List API (`GetProducts`, effective date 2026-10-01). Spot: `DescribeSpotPriceHistory`, last ~3 h before about 19:00 UTC on 2026-10-07; range across AZs. Public equivalents: https://aws.amazon.com/ec2/pricing/on-demand/ and https://aws.amazon.com/ec2/spot/pricing/ . Spot prices move hourly, so treat them as a snapshot.

| Instance | vCPU / RAM | CPU / GPU | On-demand $/h | Spot $/h (range across AZs, 2026-10-07) |
|---|---|---|---|---|
| c7i.large | 2 / 4 GiB | Intel Sapphire Rapids (AVX-512, AMX) | 0.08925 | 0.0292-0.0333 |
| c7i.xlarge | 4 / 8 GiB | Sapphire Rapids | 0.1785 | 0.0515-0.0740 |
| c8i.large | 2 / 4 GiB | Intel Granite Rapids | 0.09371 | 0.0320-0.0923 |
| c7g.large | 2 / 4 GiB | Graviton3 | 0.0725 | 0.0249-0.0386 |
| c7g.xlarge | 4 / 8 GiB | Graviton3 | 0.1450 | 0.0554-0.1010 |
| c8g.large | 2 / 4 GiB | Graviton4 | 0.07976 | 0.0300-0.0394 |
| c8g.xlarge | 4 / 8 GiB | Graviton4 | 0.15952 | 0.0575-0.0913 |
| c7a.large | 2 / 4 GiB | AMD EPYC 9R14 (Genoa) | 0.10264 | 0.0334-0.0385 |
| g4dn.xlarge | 4 / 16 GiB | 1x NVIDIA T4 | 0.526 | 0.2706-0.3047 |
| g6.xlarge | 4 / 16 GiB | 1x NVIDIA L4 | 0.8048 | 0.5383-0.6891 |
| g5.xlarge | 4 / 16 GiB | 1x NVIDIA A10G | 1.006 | 0.4152-0.5891 |
| g6e.xlarge | 4 / 32 GiB | 1x NVIDIA L40S | 1.861 | ~1.8332 |

### GCP, us-central1 (Iowa)
**Secondary source**: gcloud-compute.com (open-source aggregator of Google SKU prices), fetched 2026-10-07. The official page https://cloud.google.com/compute/vm-instance-pricing renders prices client-side and could not be machine-read, so these figures are **UNVERIFIED against Google's page**.

| Machine type | vCPU / RAM | On-demand $/h | Spot $/h |
|---|---|---|---|
| c4-standard-2 | 2 / 7 GB (Intel Emerald/Granite Rapids) | 0.0969 | 0.058 |
| c4-standard-4 | 4 / 15 GB | 0.1977 | 0.1183 |
| c4a-standard-4 | 4 / 16 GB (Google Axion, Arm) | 0.1796 | 0.085 |
| c3-standard-4 | 4 / 16 GB (Sapphire Rapids) | 0.2016 | 0.0759 |
| t2a-standard-4 | 4 / 16 GB (Ampere Altra, Arm) | 0.154 | 0.0924 |
| g2-standard-4 | 4 / 16 GB + 1x L4 | 0.7068 | 0.4241 |

Sources: https://gcloud-compute.com/c4-standard-4.html (and the same URL pattern for each type).

### Cost formula
`cost_per_M_pages = price_per_hour / (pages_per_second_per_instance × 3600 / 1e6)`

Worked example (illustration, not a measurement): a model at 1 ms/page on one thread, with 2 threads on c7i.large → 2,000 pages/s → 7.2M pages/h → **$0.0124 per M pages on-demand**, ~$0.004 per M at spot. With SMT, 2 vCPUs share one physical core, so 2 threads may not double throughput (measure it). Model inference cost is tiny next to fetch + extraction and teacher labeling, which supports keeping those numbers separate, as the README plans.

Regional note: the later SE Asia languages may justify ap-southeast-1/3 prices (not collected).

---

## 7. Multi-label evaluation

- **Averaging** (scikit-learn): `micro` pools TP/FP/FN over all (sample, label) pairs and is dominated by frequent labels. `macro` is the unweighted mean of per-label F1 (rare labels count equally; it is the arithmetic mean of per-class F, not F of macro-P/R). `weighted` is weighted by support. `samples` is per-document F1 averaged (multilabel only). `average=None` gives per-category F1. `multilabel_confusion_matrix` gives per-label 2x2 tables. Set `zero_division` explicitly for labels with no positives. https://scikit-learn.org/stable/modules/model_evaluation.html
- **Hierarchical metrics** (IAB tiers): hierarchical P/R/F (Kiritchenko, Matwin, Nock, Famili, Canadian AI 2006) expand true and predicted labels with all ancestors (root excluded), then compute set P/R. A partially right answer (correct tier 1, wrong tier 2) earns partial credit. Implemented in the HiClass library. https://hiclass.readthedocs.io/en/v4.9.0/algorithms/metrics.html . Kosmopoulos et al. (arXiv 1306.6802) give a unified view, show pathologies of existing measures, and propose set-based and pair-based alternatives (LCA-based). https://arxiv.org/abs/1306.6802 . Practical option: report flat F1 at tier 1 and at tier 2 separately, plus hF.
- **Calibration**: Guo et al., "On Calibration of Modern Neural Networks" (ICML 2017): modern nets are miscalibrated, and temperature scaling (one parameter) works well. https://arxiv.org/abs/1706.04599 . ECE = bin-count-weighted mean |accuracy - confidence| over bins. It comes from Naeini, Cooper, Hauskrecht, AAAI 2015 (BBQ), which also defines MCE. https://ojs.aaai.org/index.php/AAAI/article/view/9602 (open copy https://pmc.ncbi.nlm.nih.gov/articles/PMC4410090). ECE depends on binning: report the bin count and scheme (uniform vs quantile) and add Brier score (`brier_score_loss`). For multi-label, compute per-label binary ECE/Brier and macro-average. Teacher LLM verbalized confidences also need calibration checks against the human sample.
- **Threshold tuning per category**: Lipton, Elkan, Narayanaswamy (arXiv 1402.1892): for calibrated scores, the F1-optimal threshold = half the optimal F1. With uninformative classifiers, F1 can be maximized by predicting all-positive (a bad incentive for rare labels). https://arxiv.org/abs/1402.1892 . sklearn `TunedThresholdClassifierCV` tunes one decision threshold via internal CV with a chosen scorer, and `cv="prefit"` needs a separate validation set. The docs frame it for binary problems, so for multi-label apply it per label in a one-vs-rest loop. Whether it natively handles multilabel is **UNVERIFIED**. https://scikit-learn.org/stable/modules/classification_threshold.html . Tune thresholds on a validation split, never on test. fastText exposes one global threshold at predict time (`k=-1, threshold`), so per-label thresholds must be applied in post-processing.

---

## UNVERIFIED / uncertain

1. Per-item fastText latency with ~hundreds of labels: derived from 2016 Table 5 (312K classes, single thread); not a reported number for our setting.
2. VW multilabel reductions (`--multilabel_oaa`, `--csoaa`): not confirmed from primary docs in this pass.
3. sklearn HashingVectorizer+SGD single-item latency: no published figure.
4. WordLlama language coverage (likely English-centric).
5. multilingual-e5-small language count and max sequence length (512 assumed); Multilingual-MiniLM param count; distilbert-multilingual language count (104 assumed); all-MiniLM-L6-v2 max seq (256 assumed).
6. mmBERT-small layer count; whether mmBERT's pre-training (60-language) set includes pt/id/vi/th (very likely, not checked); mmBERT license comes from HF card metadata (MIT), not the paper.
7. No official distilled Portuguese-only BERT located.
8. llama.cpp support for encoder classification heads.
9. HF tokenizers throughput claim (<20 s/GB) is no longer in the README.
10. arXiv 2602.00899 CPU latency table (6.1 ms int8): single author; model and sequence length are not named in the table.
11. Third-party ModernBERT FineWeb-Edu F1 numbers.
12. All GCP prices (third-party aggregator). AWS spot prices are a point-in-time snapshot.
13. Graviton vCPU = physical core and x86 vCPU = hyperthread (standard AWS fact, not re-fetched).
14. sklearn `TunedThresholdClassifierCV` native multilabel support (assumed binary-only).
15. Kiritchenko 2006 paper read only via secondary descriptions (HiClass docs), not the full text.

## Source list (all accessed 2026-10-07)

- https://arxiv.org/abs/1607.01759 ; https://ar5iv.labs.arxiv.org/html/1607.01759 (fastText paper)
- https://arxiv.org/abs/1612.03651 (FastText.zip)
- https://github.com/facebookresearch/fastText ; https://api.github.com/repos/facebookresearch/fastText
- https://fasttext.cc/docs/en/supervised-tutorial.html ; https://fasttext.cc/docs/en/autotune.html
- https://pypi.org/project/fasttext/ ; https://pypi.org/project/fasttext-numpy2/
- https://github.com/VowpalWabbit/vowpal_wabbit ; https://raw.githubusercontent.com/VowpalWabbit/vowpal_wabbit/master/LICENSE
- https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.text.HashingVectorizer.html
- https://github.com/MinishLab/model2vec ; https://github.com/MinishLab/model2vec/blob/main/results/README.md
- https://huggingface.co/blog/Pringled/model2vec
- https://huggingface.co/minishlab/potion-multilingual-128M
- https://huggingface.co/blog/static-embeddings
- https://huggingface.co/sentence-transformers/static-similarity-mrl-multilingual-v1
- https://github.com/dleemiller/WordLlama
- https://huggingface.co/api/models/{id} (parameter counts and licenses for the models in §3)
- https://huggingface.co/intfloat/multilingual-e5-small ; https://arxiv.org/abs/2402.05672
- https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
- https://huggingface.co/blog/mmbert ; https://arxiv.org/abs/2509.06888
- https://huggingface.co/answerdotai/ModernBERT-base
- https://huggingface.co/EuroBERT/EuroBERT-210m ; https://arxiv.org/html/2503.05500
- https://huggingface.co/neuralmind/bert-base-portuguese-cased
- https://huggingface.co/FacebookAI/xlm-roberta-base
- https://arxiv.org/abs/1503.02531 ; https://arxiv.org/abs/1910.01108 ; https://arxiv.org/abs/1909.10351 ; https://arxiv.org/abs/2002.10957 ; https://arxiv.org/abs/2305.02301
- https://arxiv.org/html/2305.01645v3 ; https://arxiv.org/pdf/2406.17633 ; https://arxiv.org/pdf/2406.17557
- https://huggingface.co/HuggingFaceFW/fineweb-edu-classifier ; https://huggingface.co/staghado/edu-modernbert
- https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html
- https://onnxruntime.ai/docs/performance/tune-performance/threading.html
- https://sbert.net/docs/sentence_transformer/usage/efficiency.html
- https://github.com/OpenNMT/CTranslate2 ; https://github.com/openvinotoolkit/openvino ; https://github.com/huggingface/optimum ; https://github.com/ggml-org/llama.cpp ; https://github.com/huggingface/tokenizers (release tags via api.github.com)
- https://huggingface.co/blog/infinity-cpu-performance
- https://arxiv.org/abs/2211.07715 ; https://arxiv.org/html/2602.00899
- https://github.com/giltene/wrk2 ; https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/open-vs-closed/
- https://github.com/sharkdp/hyperfine ; https://pytest-benchmark.readthedocs.io/en/latest/usage.html
- AWS Price List API + EC2 DescribeSpotPriceHistory (us-east-1); public pages https://aws.amazon.com/ec2/pricing/on-demand/ , https://aws.amazon.com/ec2/spot/pricing/
- https://gcloud-compute.com/ (c4-standard-2/4, c4a-standard-4, c3-standard-4, t2a-standard-4, g2-standard-4 pages)
- https://scikit-learn.org/stable/modules/model_evaluation.html ; https://scikit-learn.org/stable/modules/classification_threshold.html
- https://hiclass.readthedocs.io/en/v4.9.0/algorithms/metrics.html ; https://arxiv.org/abs/1306.6802
- https://arxiv.org/abs/1706.04599 ; https://ojs.aaai.org/index.php/AAAI/article/view/9602 ; https://arxiv.org/abs/1402.1892
