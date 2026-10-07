# Research notes: IAB Content Taxonomy and teacher-LLM labeling

Access date for all sources: **2026-10-07**, unless noted otherwise. All sources are public.

Provenance note:
- No AWS or other cloud account tools were used.
- Some GitHub repo metadata (file tree, commit dates) was first pulled with the locally installed `gh` CLI. That CLI may carry the user's GitHub login, though it only read a public repo. Those facts were then re-checked on the public github.com web pages (commit history of the 3.1 file, `Taxonomy Mappings` folder listing).
- The TSV files, Hugging Face license tags and arXiv metadata came from unauthenticated public HTTP endpoints (raw.githubusercontent.com, huggingface.co/api, export.arxiv.org).
Facts I could not confirm against a primary source are marked **UNVERIFIED**. They are also collected in the last section.

---

## 1. IAB Tech Lab Content Taxonomy

### Current version
- **Content Taxonomy 3.1 is the current version.** The IAB Tech Lab standards page (last updated 2026-02-11) dates it **December 2024** and says it adds "Thriller" to the genre category. It was open for public comment until 2025-01-24. The page does not mention a 3.2 or 4.0. [S1]
- In the GitHub repo, the file `Content Taxonomies/Content Taxonomy 3.1.tsv` was first committed on 2024-12-09, in a burst of 6 commits that day. The public commit history then shows 8 more edits on 2025-01-27, 2025-01-29, 2025-01-31 (3 commits, e.g. "adding back auto racing scd", "fixes for label names given leaf name"), 2025-03-04 ("fix inconsistencies") and 2025-07-22 (2 commits, incl. "Re-adding Music T2"). That makes 14 commits in total, confirmed on the public commits page https://github.com/InteractiveAdvertisingBureau/Taxonomies/commits/main/Content%20Taxonomies/Content%20Taxonomy%203.1.tsv. **The file changes after the release with no new version number**, so the project must pin a commit SHA, not just "3.1". [S2]
  - Repo HEAD on `main`: commit `de757836`, 2025-09-23 (last push).
  - sha256 of `Content Taxonomy 3.1.tsv` at HEAD on 2026-10-07: `7212cdc496ba347a03e703b1932bdcdd4fd29089b058f4edeb4d3da1f1222ea7`.

### Version history (from [S1], cross-checked against repo files [S2])
| Version | Date | Notes |
|---|---|---|
| 1.0 | (legacy) | Deprecated since July 2020. Should not be used without SCD flags. [S1][S3] |
| 2.0 | Nov 2017 | Large overhaul. |
| 2.1 | Oct 2020 | Adds the SCD ("Special Category Data") sensitivity flag. [S3] |
| 2.2 | Dec 2020 | Adds GARM brand-safety/suitability categories under "Sensitive Topics". [S3] |
| 3.0 (+ "Descriptive Vectors") | Jun 2022 | **Breaking change.** It removes parent categories and is restructured for video, news, podcasts, games and apps. "Content Taxonomy 3.0 may not be used alongside earlier versions." [S1][S3][S4] |
| 3.1 | Dec 2024 | Small update: adds "Thriller", "Musicals"→"Musical", "Software and Applications"→"Computer Software and Applications", and moves "Maps & Navigation". It ships with CTV and Podcast genre mappings. [S1], diff computed locally from [S2] |

The versioning policy is semver-like: a major version means breaking changes, and a minor version adds rows without changing the hierarchy. [S4]

### Category counts (computed by me from the TSVs at HEAD [S2])
I counted rows with a non-empty Unique ID and bucketed each row by its deepest filled tier.

| File | Total rows | Tier 1 | Tier 2 | Tier 3 | Tier 4 | SCD-flagged rows |
|---|---|---|---|---|---|---|
| Content Taxonomy 3.1 | **704** | 37* | 323 | 275 | 69 | 63 |
| Content Taxonomy 3.0 | 703 | 36 | 322 | 275 | 70 | 64 |
| Content Taxonomy 2.2 | 1,196 | 50 | 560 | 524 | 60 | 64 |

\* In 3.1, the row `80DV8O Communication` has an empty parent and Tier 1 = "Communication". In 3.0 the same row sits at Technology & Computing > Computing > Computer Software and Applications > Communication. This looks like an **errata bug in the 3.1 file**, so the real number of Tier-1 categories is probably **36**.

- The 3.x Tier-1 list: Attractions, Automotive, Books and Literature, Business and Finance, Careers, Crime, Disasters, Education, Entertainment, Events, Family and Relationships, Fine Art, Food & Drink, **Genres** (a media-genre subtree, used mostly for CTV and podcasts), Healthy Living, Hobbies & Interests, Holidays, Home & Garden, Law, Medical Health, Personal Celebrations & Life Events, Personal Finance, Pets, Politics, Pop Culture, Real Estate, Religion & Spirituality, Science, Sensitive Topics, Shopping, Sports, Style & Fashion, Technology & Computing, Travel, Video Gaming, War and Conflicts.
- In 2.2, the Tier-1 rows also include non-topic "vector" dimensions (Content Channel, Content Type, Content Media Format, Content Language, Content Source, Content Source Geo, Brand Suitability and Risk). That explains the larger row count. In 3.x these dimensions moved to a separate file, `Content Taxonomy 3.0 Descriptive Vectors.tsv`, which covers Content Environment, Content Purpose, Content Source, Content Form Factor, Brand Suitability and Risk (Floor/High/Medium/Low), and the Language and Source Geo extensions. [S2][S3]
- **Secondary sources get the size wrong.** ppc.land and Mixpeek say "~400 categories in 2.x → 1,500+ in 3.x", and another Mixpeek post says "700+ in 3.1". Only the last figure matches the files. Use the files, not press coverage. [S10][S11]
- Practical note for this project: about 700 topical labels in 4 tiers. Tier 1 has about 36 labels and Tiers 1+2 together have about 360. The "Genres" subtree and the SCD-flagged nodes may be worth excluding or handling separately for web pages.

### Distribution format
- **Only TSV.** The repo has no official JSON. The `Taxonomies` repo has `Content Taxonomies/*.tsv`, `Audience Taxonomies/*.tsv`, `Ad Product Taxonomies/*.tsv` and `Taxonomy Mappings/*.tsv`, plus `implementation.md`. The repo has no tagged releases. [S2]
  - Repo URL: https://github.com/InteractiveAdvertisingBureau/Taxonomies
  - Raw file: `https://raw.githubusercontent.com/InteractiveAdvertisingBureau/Taxonomies/<SHA>/Content%20Taxonomies/Content%20Taxonomy%203.1.tsv`
- TSV layout: 2 header rows ("Relational ID System … Tiered Categories … Extension", then `Unique ID, Parent, Name, Tier 1, Tier 2, Tier 3, Tier 4, Extension`). IDs are alphanumeric strings. Most are numeric, but some are not (e.g. `WQC6HR`, `80DV8O`). Treat IDs as strings. The `Extension` column carries `SCD`. [S2][S3]
- OpenRTB/AdCOM usage: categories go in `cat` with `cattax=2` for Content Taxonomy 2.x and later. [S3]
- An old repo, `InteractiveAdvertisingBureau/taxonomy`, was last pushed in 2017 and is obsolete. [S2b]

### License and usage terms
- The `Taxonomies` README "License" section says: "OpenRTB Specification the IAB Tech Lab is licensed under a Creative Commons Attribution 3.0 License". This boilerplate was evidently copied from the OpenRTB repo. Contributions to the taxonomies are licensed to IAB Tech Lab under CC BY 3.0 "and … may be used and made available to the public under the terms of such license". The GitHub API reports no SPDX license for the repo. [S4]
- The general IAB Tech Lab website Terms of Use are restrictive: personal use only, no redistribution, no derivative works, no commercial use. However, they state that materials under a "Separate License" are governed by that license instead. [S5]
- **Interpretation (not legal advice):** the taxonomy files on GitHub are most plausibly under **CC BY 3.0**. CC BY allows copying, redistribution and derivatives, including commercial ones, **with attribution** and a link to the license. A personal research repo may use the taxonomy to label data and publish labels or models that reference category IDs.
  - **Recommendation: do not vendor the file. Download it with a pinned commit SHA and a sha256 check.** The README license wording is ambiguous because it names OpenRTB, and the site ToS is restrictive. Downloading avoids redistributing IAB material and still gives exact reproducibility. If a copy is ever vendored, add CC BY 3.0 attribution ("IAB Tech Lab Content Taxonomy 3.1, © IAB Technology Laboratory, CC BY 3.0, source URL @ SHA").
  - "IAB" and "IAB Tech Lab" are trademarks. Do not imply endorsement or certification. [S5]

### Mapping files (in `Taxonomy Mappings/`) [S2][S1]
- `Content 1.0 to Content 2.0.tsv`, `Content 2.0 to Content 2.1.tsv` (Nov 2023)
- `Content 1.0 to Ad Product 2.0.tsv`, `Ad Product 2.0 to Content 1.0.tsv`, `Ad Product 2.0 to Content 2.1.tsv`, `Content 2.1 to Ad Product 2.0.tsv` (the 2.1→AP2.0 file was renamed and finalized in Aug 2025; its comment period closed 2025-09-10 [S12])
- `Ad Product 2.0 to 1.1.tsv`, `Ad Product 1.1 to Ad Product 2.0.md`
- `CTV Genre Mapping.tsv`, `Podcast Genre Mapping.tsv` (Dec 2024)
- **There is no official Content 2.x → 3.0/3.1 mapping file.** IAB instead points to an open-source mapper donated by Mixpeek (`github.com/mixpeek/iab-mapper`, BSD-2-Clause, last push 2025-10-09). It uses exact and fuzzy matching, BM25, embedding kNN and optional LLM re-ranking, and produces confidence-scored mappings. [S1][S10][S11]

### Content Taxonomy vs Audience vs Ad Product taxonomies [S4][S3][S6]
| Taxonomy | Describes | Current version | Size (my count) |
|---|---|---|---|
| **Content** | The "aboutness" of a page, app, video or podcast. Used for contextual targeting and brand safety/suitability. | 3.1 (Dec 2024) | 704 topical nodes + separate vectors file |
| **Audience** | Audience *segments* (people), for the Data Transparency Standard. Tier 1 = Demographic / Interest / Purchase Intent. | 1.1 (Oct 2020) | ~1,558 rows (Demographic 197, Interest 497, Purchase Intent 864) |
| **Ad Product** | The product or service *advertised in a creative*. Used for publisher ad blocking (`bcat`) and measurement. | 2.0 | ~583 rows |

The Content Taxonomy is the right one for this project. The Audience Taxonomy is about users, which is a non-goal here. The Ad Product Taxonomy is about ads.

### Official labeled examples
- **None found.** IAB publishes no labeled page→category dataset, only the taxonomy, mappings and implementation guidance. The repo's `implementation.md` even says "we are not providing descriptions for every item". [S3]
- Public proxies and related datasets:
  - Jin, Kadam, Wanvarie (2021), *Bootstrapping Large-Scale Fine-Grained Contextual Advertising Classifier from Wikipedia*, arXiv:2102.06429. It maps IAB categories to the Wikipedia category graph (wiki2cat) and describes coarse IAB Tier-1 eval sets of 2,127 and 1,501 documents (from Jin et al. 2020). **UNVERIFIED** whether those eval sets can still be downloaded. [P25]
  - Kamen (2025), *Order from Chaos: Comparative Study of Ten Leading LLMs on Unstructured Data Categorization*, arXiv:2510.13885. It tests 10 LLMs zero-shot on **IAB 2.2** with 8,660 human-annotated samples and reports an average accuracy of only about 34% and F1 of about 41%, with models over-producing categories. **This is a useful warning about teacher label noise on IAB.** **UNVERIFIED** whether the dataset was released. [P27]

---

## 2. Teacher-LLM labeling: best practices and papers

### Papers (all titles, authors and years verified with the arXiv API on 2026-10-07)
**LLMs as annotators (quality vs humans)**
- [P1] Gilardi, Alizadeh, Kubli (2023). *ChatGPT Outperforms Crowd-Workers for Text-Annotation Tasks.* https://arxiv.org/abs/2303.15056 (PNAS 2023)
- [P2] Zhu, Zhang, Haq, Hui et al. (2023). *Can ChatGPT Reproduce Human-Generated Labels? A Study of Social Computing Tasks.* https://arxiv.org/abs/2304.10145
- [P3] Ding, Qin, Liu, Chia et al. (2022/ACL 2023). *Is GPT-3 a Good Data Annotator?* https://arxiv.org/abs/2212.10450 (the "is X a good annotator" paper)
- [P4] Wang, Liu, Xu, Zhu et al. (2021). *Want To Reduce Labeling Cost? GPT-3 Can Help.* https://arxiv.org/abs/2108.13487
- [P5] He, Lin, Gong, Jin et al. (2023). *AnnoLLM: Making Large Language Models to Be Better Crowdsourced Annotators.* https://arxiv.org/abs/2303.16854 (explain-then-annotate prompting)
- [P6] Huang, Kwak, An (2023). *Is ChatGPT better than Human Annotators? Potential and Limitations of ChatGPT in Explaining Implicit Hate Speech.* https://arxiv.org/abs/2302.07736
- [P7] Törnberg (2023). *ChatGPT-4 Outperforms Experts and Crowd Workers in Annotating Political Twitter Messages with Zero-Shot Learning.* https://arxiv.org/abs/2304.06588
- [P8] Pangakis, Wolken, Fasching (2023). *Automated Annotation with Generative AI Requires Validation.* https://arxiv.org/abs/2306.00176. Performance varies a lot by task, so validate against a human sample for each task and category.
- [P9] Reiss (2023). *Testing the Reliability of ChatGPT for Text Annotation and Classification: A Cautionary Remark.* https://arxiv.org/abs/2304.11085. Outputs change with prompt wording and temperature.
- [P10] Tan, Li, Wang, Beigi et al. (2024). *Large Language Models for Data Annotation and Synthesis: A Survey.* https://arxiv.org/abs/2402.13446
- [P11] Bansal, Sharma (2023). *Large Language Models as Annotators: Enhancing Generalization of NLP Models at Minimal Cost.* https://arxiv.org/abs/2306.15766

**Distilling LLM labels into small classifiers / label noise**
- [P12] Pangakis, Wolken (2024). *Knowledge Distillation in Automated Annotation: Supervised Text Classification with LLM-Generated Training Labels.* https://arxiv.org/abs/2406.17633. Across 14 tasks, classifiers fine-tuned on LLM labels perform comparably to ones fine-tuned on human labels.
- [P13] Xia, Wang, Li, Yu et al. (2025, ACL 2025). *Prompt Candidates, then Distill: A Teacher-Student Framework for LLM-driven Data Annotation* (CanDist). https://arxiv.org/abs/2506.03857. The teacher outputs a candidate label *set* when uncertain, and the student is distilled from it. More noise-tolerant.
- [P14] Ye, Shah, Zhang, Chava (2025). *Calibrating Pre-trained Language Classifiers on LLM-generated Noisy Labels via Iterative Refinement* (SiDyP). https://arxiv.org/abs/2505.19675
- [P15] Wang, Tan, Guo, Li (2023). *Noise-Robust Fine-Tuning of Pretrained Language Models via External Guidance.* https://arxiv.org/abs/2311.01108. Uses LLM confidence to guide training on noisy labels.
- [P16] Smith, Fries, Hancock, Bach (2022). *Language Models in the Loop: Incorporating Prompting into Weak Supervision.* https://arxiv.org/abs/2205.02318
- [P17] Hinton, Vinyals, Dean (2015). *Distilling the Knowledge in a Neural Network.* https://arxiv.org/abs/1503.02531 (soft targets)
- [P18] Hsieh, Li, Yeh, Nakhost et al. (2023). *Distilling Step-by-Step!* https://arxiv.org/abs/2305.02301 (rationales as extra supervision. Less relevant for sub-ms students.)

**Consistency and confidence**
- [P19] Wang, Wei, Schuurmans, Le et al. (2022). *Self-Consistency Improves Chain of Thought Reasoning in Language Models.* https://arxiv.org/abs/2203.11171. Sample N times and use the vote share as a confidence or soft label.
- [P20] Kadavath, Conerly, Askell, Henighan et al. (2022). *Language Models (Mostly) Know What They Know.* https://arxiv.org/abs/2207.05221
- [P21] Lin, Hilton, Evans (2022). *Teaching Models to Express Their Uncertainty in Words.* https://arxiv.org/abs/2205.14334
- [P22] Tian, Mitchell, Zhou, Sharma et al. (2023). *Just Ask for Calibration: Strategies for Eliciting Calibrated Confidence Scores from Language Models Fine-Tuned with Human Feedback.* https://arxiv.org/abs/2305.14975. For RLHF models, verbalized confidence is often better calibrated than token probabilities.
- [P23] Xiong, Hu, Lu, Li et al. (2023). *Can LLMs Express Their Uncertainty? An Empirical Evaluation of Confidence Elicitation in LLMs.* https://arxiv.org/abs/2306.13063. Verbalized confidence tends to be overconfident. Combining sampling consistency with verbalized confidence helps.
- [P24] Farr, Cruickshank, Manzonelli, Clark et al. (2024). *LLM Confidence Evaluation Measures in Zero-Shot CSS Classification.* https://arxiv.org/abs/2410.13047. Confidence *ensembles* work best for finding mislabeled items.
- [P26] Zhao, Wallace, Feng, Klein et al. (2021). *Calibrate Before Use: Improving Few-Shot Performance of Language Models.* https://arxiv.org/abs/2102.09690 (label-prior bias in logprobs)

**Structured output**
- [P28] Willard, Louf (2023). *Efficient Guided Generation for Large Language Models* (Outlines). https://arxiv.org/abs/2307.09702. Constrained decoding against a regex or JSON schema, useful for open-weight teachers.
- [P29] Tam, Wu, Tsai, Lin et al. (2024). *Let Me Speak Freely? A Study on the Impact of Format Restrictions on Performance of Large Language Models.* https://arxiv.org/abs/2408.02442. Strict format constraints can hurt reasoning. Classification is less affected, but measure it.

**Large and hierarchical label sets**
- [P30] Zhang, Yang, Xu, Li et al. (2024). *TELEClass: Taxonomy Enrichment and LLM-Enhanced Hierarchical Text Classification with Minimal Supervision.* https://arxiv.org/abs/2403.00165
- [P31] D'Oosterlinck, Khattab, Remy, Demeester et al. (2024). *In-Context Learning for Extreme Multi-Label Classification* (Infer–Retrieve–Rank). https://arxiv.org/abs/2401.12178
- [P32] Sun, Li, Li, Wu et al. (2023). *Text Classification via Large Language Models* (Clue And Reasoning Prompting). https://arxiv.org/abs/2305.08377
- [P25] Jin, Kadam, Wanvarie (2021), arXiv:2102.06429 (IAB-specific, see §1)
- [P27] Kamen (2025), arXiv:2510.13885 (IAB 2.2 LLM benchmark, see §1)

### Practical recipe distilled from the above (my synthesis, not a single source)
1. **Put the taxonomy in a cached prefix.** All 704 nodes of 3.1 as `id<TAB>full path` come to about 32 KB, roughly 8k tokens. Names only are about 14 KB, roughly 4k tokens (my measurement). Put the list in the system prompt and use prompt caching, because it is identical for every page.
2. **Label hierarchically or by retrieval for about 700 labels.** Options:
   - (a) A single pass with the full list in context. This is feasible with modern long-context models and caching.
   - (b) A two-stage pass: pick Tier 1, then choose within the selected subtrees [P30].
   - (c) Infer–retrieve–rank: the LLM free-texts topics, embeddings retrieve candidate nodes, and the LLM ranks them [P31].
   Option (c) cuts prompt size and hallucinated IDs.
3. **Use structured output.** Use a JSON schema whose `id` field is an **enum of valid IDs**, so invalid IDs are impossible. Return a list of `{id, confidence}` with a cap (e.g. ≤5 labels) to fight the "category inflation" that Kamen found [P27]. Native structured output is available from Anthropic, OpenAI and Gemini. Use constrained decoding (Outlines/xgrammar) for open models [P28]. Re-check accuracy with and without the constraint [P29].
4. **Confidence.** Verbalized confidence is cheap but overconfident [P23]. Self-consistency (k samples at temperature > 0, with the vote share as a soft label) is more reliable but costs k times as much [P19]. Logprobs are available only from some APIs and open models, and need calibration [P26]. Plan: label everything once with verbalized confidence. Then, on a subset of about 5–10k pages, run k=3–5 samples and/or a second teacher model to measure self-consistency and to calibrate the verbalized scores (e.g. with isotonic regression) [P22][P24].
5. **Validate per category against humans** [P8][P9]. Freeze the prompt, model ID and temperature, and log everything. Candidate-set labels [P13] and noise-robust training [P14][P15] are the obvious ablations for the open question "does noise limit the student?".
6. **Turn off or minimize thinking.** For Claude 5.5-generation models, thinking is "Adaptive (always on)" for Opus 5.5 and adaptive for Sonnet/Haiku 5.5, and thinking tokens are billed as output. Set effort low or disable thinking where the model allows it, or the ~100-token output assumption breaks. [S7b]

---

## 3. Candidate teacher models: pricing and terms

### Anthropic Claude (primary source: platform.claude.com pricing and models pages [S7][S7b]; claude.com/pricing [S7c])
Model IDs verified: `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5` (plus `claude-fable-5-1`). All have a 1M-token context and a June 2026 knowledge cutoff.

| Model | Input $/MTok | Output $/MTok | Cache hit $/MTok | Batch in / out |
|---|---|---|---|---|
| Claude Haiku 5.5 (prompt ≤100k) | 0.10 | 0.50 | 0.01 | 0.05 / 0.25 |
| Claude Haiku 5.5 (prompt >100k) | 0.50 | 2.50 | 0.05 | 0.25 / 1.25 |
| Claude Sonnet 5.5 | 2 | 10 | 0.20 (table) / 0.10 (text)† | 1 / 5 |
| Claude Opus 5.5 | 4 | 20 | 0.20 | 2 / 10 |
| Claude Fable 5.1 | 10 | 50 | 0.25 | 5 / 25 |

- Batch API: **50% off** input and output. It stacks with prompt caching. [S7]
- † The pricing page is internally inconsistent for the Sonnet 5.5 cache-hit price. The table says $0.20, and the prose says "5% … $0.10 USD on Claude Sonnet 5.5".
- Tokenizer: Claude 4.7 and later models use a newer tokenizer that produces "approximately 30% more tokens for the same text". **Budget about 1,300 tokens for a "1,000-token" page.** [S7]
- The models page describes Haiku 5.5 as "for high-volume, latency-sensitive tasks such as classification, extraction, and routing". [S7b]

### OpenAI (primary source: developers.openai.com/api/docs/pricing [S8])
Selected models, short context (≤272K):

| Model | Input | Cached | Output | Batch in / out |
|---|---|---|---|---|
| gpt-6-astra | 10.00 | 1.00 | 50.00 | 5.00 / 25.00 |
| gpt-6.1-sol | 2.00 | 0.10 | 10.00 | 1.00 / 5.00 |
| gpt-6-luna | 0.10 | 0.01 | 0.50 | 0.05 / 0.25 |
| gpt-5.4-mini | 0.75 | 0.075 | 4.50 | 0.375 / 2.25 |
| gpt-5-mini | 0.25 | 0.025 | 2.00 | 0.125 / 1.00 |
| gpt-5-nano | 0.05 | 0.005 | 0.40 | 0.025 / 0.20 |

- Batch and Flex are about 50% off. These rows were extracted through a summarizing fetch of the pricing page, so **re-check the exact numbers before use**.

### Google Gemini (primary source: ai.google.dev/gemini-api/docs/pricing [S9])
Paid tier, per 1M tokens:

| Model | Input | Output | Cache | Batch in / out |
|---|---|---|---|---|
| gemini-3.1-pro-preview (≤200k) | 2.00 | 12.00 | 0.20 | 1.00 / 6.00 |
| gemini-3.8-flash / 3.7 / 3.6 | 0.75 | 3.75 | 0.075 | 0.375 / 1.875 |
| gemini-3.5-flash-lite | 0.30 | 2.50 | 0.03 | 0.15 / 1.25 |
| gemini-3.1-flash-lite | 0.25 | 1.50 | 0.025 | 0.125 / 0.75 |
| gemini-2.5-flash-lite | 0.10 | 0.40 | 0.01 | 0.05 / 0.20 |

- **3.x Flash prices double on 2027-01-01** (e.g. 3.8-flash goes to $1.50/$7.50).
- Batch is 50% off.
- Free-tier content "used to improve our products". Paid-tier content is not. **Use the paid tier for anything you might publish.**

### DeepSeek API (open-weight models, MIT) [S13]
| Model | Input (cache miss) | Output | Off-peak |
|---|---|---|---|
| `deepseek-flash` (V4.1-Flash) | $0.30 | $1.20 | 50% off: $0.15 / $0.60 |
| `deepseek-v4-pro` | $1.32 | $3.96 | 50% off: $0.66 / $1.98 |

### Open-weight models: licenses (HF API license tags pulled 2026-10-07 [S14], plus license texts)
| Family / latest | License | Training other models on outputs? |
|---|---|---|
| **Qwen3.8-27B** (2026-08-05) | Apache-2.0 | Unrestricted (Apache). |
| Qwen3.8-Flash-Next | "qwen-community-1.0" | Display the model name if >100M MAU or >$20M/month revenue. A separate license is needed for "Model as a Service / AI Work Assistant" businesses. **No clause on training on outputs.** [S15] |
| Qwen3.8-2.4T-A95B | "qwen3.8-max" | Similar to the above, with a $50M revenue threshold. [S15] |
| **Gemma 4** (E2B/E4B/12B/26B-A4B/31B) | **Apache-2.0** (first Gemma under Apache) | Unrestricted. [S16][S16b] |
| Gemma 1–3n | Gemma Terms of Use (modified 2026-04-01) | **A model trained via distillation or synthetic data from Gemma outputs is a "Model Derivative"** and inherits the Gemma terms and Prohibited Use Policy. "Outputs are not deemed Model Derivatives", and Google claims no rights in outputs. **A student distilled from Gemma 3 would carry the Gemma terms.** [S16] |
| **Llama 4** (Scout/Maverick, Apr 2025; still the latest on HF `meta-llama`) | Llama 4 Community License | Allowed, but if a model trained on Llama outputs is **distributed**, its name must **start with "Llama"**. Also requires "Built with Llama", a NOTICE file and AUP compliance. A license is needed above 700M MAU. [S17] |
| **Mistral** Large 3 (675B, Dec 2025), Small 4 (119B-A6B, 2026), Ministral 3 | Apache-2.0 | Unrestricted. Mistral-Medium-3.5 is "other" (a modified license). [S14] |
| **gpt-oss-20b / 120b** (OpenAI, Aug 2025) | Apache-2.0 | Unrestricted. [S14] |
| **DeepSeek V4 / V4.1** | MIT | Unrestricted. [S14] |

### "Don't train a competing model" terms (API providers)
- **Anthropic Commercial Terms** (effective 2025-06-17), §D.4: the customer may not "access the Services to build a competing product or service, including to train competing AI models … except as expressly approved by Anthropic". The customer **owns Outputs**. [S18]
- **OpenAI** Services Agreement / Business Terms: the customer may not, "except for a Permitted Exception, use Output to develop artificial intelligence models that compete with" OpenAI. Secondary sources say the Permitted Exception covers models "primarily intended to categorize, classify, or organize data (e.g., embeddings or classifiers), provided those models are not distributed or sold commercially to third parties". **UNVERIFIED on the primary text**: openai.com returned 403 and the OSA PDF was not text-extractable. [S19][S19b]
- **Gemini API Additional Terms** (modified 2026-04-28): "You may not use the Services to develop models that compete with the Services (e.g., Gemini API or Google AI Studio)." Also, do not train on Grounding-with-Search results or Maps data. [S20]

**Does this affect a tiny IAB page classifier?** (my reading, not legal advice)
- A sub-ms topic classifier over a fixed taxonomy does not plausibly "compete" with a general-purpose LLM API, and OpenAI's carve-out for classifiers, if confirmed, addresses this case directly. Risk is low for a personal, non-commercial research repo.
- Residual risks:
  - Anthropic's wording ("competing product or service") is broader than "competing model".
  - OpenAI's carve-out excludes *commercially distributed* classifiers.
  - Publishing the labeled dataset or the student weights is a form of distribution.
- **Cleanest option for publishable artifacts:** use an Apache/MIT open-weight teacher (Qwen3.8-27B, Gemma 4, Mistral Large 3/Small 4, gpt-oss-120b, DeepSeek V4) for the released labels. API models can still serve as a quality reference or second teacher. Avoid Gemma ≤3 (derivative clause) and Llama 4 (naming clause) as teachers if student weights will be published.

---

## 4. Teacher labeling cost estimate

Assumptions:
- 1,000 input tokens of page text and 100 output tokens per page.
- Plus an optional taxonomy prefix of about 8k tokens (full paths), either cached (at the model's cache-read price) or uncached.
- Batch = 50% off, which stacks with caching for Anthropic. For others, caching with batch is assumed similar.
- Ignores cache-write cost (amortized), thinking tokens and retries.
- Formula: cost = N × (1000·in + 100·out)/1e6.

| Model | 100k std | 100k batch | 1M std | 1M batch | 1M batch + 8k cached prefix | 1M batch + 8k uncached prefix |
|---|---|---|---|---|---|---|
| Claude Haiku 5.5 | $15 | $7.5 | $150 | $75 | ~$115 | ~$475 |
| Claude Sonnet 5.5 | $300 | $150 | $3,000 | $1,500 | ~$2,300 | ~$9,500 |
| Claude Opus 5.5 | $600 | $300 | $6,000 | $3,000 | ~$3,800 | ~$19,000 |
| OpenAI gpt-5-mini | $45 | $22 | $450 | $225 | ~$325 | ~$1,225 |
| OpenAI gpt-6-luna | $15 | $7.5 | $150 | $75 | ~$115 | ~$475 |
| Gemini 3.1 Flash-Lite | $40 | $20 | $400 | $200 | ~$300 | ~$1,200 |
| Gemini 3.1 Pro (preview) | $320 | $160 | $3,200 | $1,600 | ~$2,400 | ~$9,600 |

Takeaways:
- **The taxonomy prefix, not the page, dominates the input cost** unless it is cached. Use prompt caching or a retrieval/hierarchical prompt.
- With the Claude 4.7+ tokenizer (+~30% tokens), add about 30% to the Claude rows.
- Self-consistency runs multiply the cost by k on the subset only. For example, a 10k-page subset at k=5 on Sonnet 5.5 batch is about $75–115.
- A realistic plan: 1M pages with Haiku 5.5 (batch + cache) for about $100–150, plus a 50–100k-page subset with Sonnet or Opus 5.5 as a stronger reference teacher for about $150–400. **Under $1k total.**
- A self-hosted open-weight teacher instead costs GPU-hours, not tokens. **UNVERIFIED**, not estimated here.

---

## Sources (accessed 2026-10-07)
- [S1] IAB Tech Lab, Content Taxonomy page: https://iabtechlab.com/standards/content-taxonomy/
- [S2] IAB Tech Lab Taxonomies GitHub repo, file tree and commits via the GitHub API: https://github.com/InteractiveAdvertisingBureau/Taxonomies (raw: https://raw.githubusercontent.com/InteractiveAdvertisingBureau/Taxonomies/main/Content%20Taxonomies/Content%20Taxonomy%203.1.tsv)
- [S2b] Old repo: https://github.com/InteractiveAdvertisingBureau/taxonomy
- [S3] implementation.md: https://github.com/InteractiveAdvertisingBureau/Taxonomies/blob/main/implementation.md
- [S4] README (versioning policy, license): https://github.com/InteractiveAdvertisingBureau/Taxonomies/blob/main/README.md
- [S5] IAB Tech Lab Terms of Use: https://iabtechlab.com/terms-of-use/
- [S6] IAB Tech Lab Audience Taxonomy page: https://iabtechlab.com/standards/audience-taxonomy/
- [S7] Anthropic pricing: https://platform.claude.com/docs/en/about-claude/pricing
- [S7b] Anthropic models overview: https://platform.claude.com/docs/en/about-claude/models/overview
- [S7c] https://claude.com/pricing
- [S8] OpenAI API pricing: https://developers.openai.com/api/docs/pricing
- [S9] Gemini API pricing: https://ai.google.dev/gemini-api/docs/pricing
- [S10] ppc.land on the Mixpeek mapper donation: https://ppc.land/open-source-ai-mapper-speeds-taxonomy-migration-in-months-long-manual-process/
- [S11] Mixpeek mapper: https://github.com/mixpeek/iab-mapper ; https://blog.mixpeek.com/migrate-iab-content-taxonomy/
- [S12] MediaPost on the Content 2.1→Ad Product 2.0 mapping: https://www.mediapost.com/publications/article/408092
- [S13] DeepSeek API pricing: https://api-docs.deepseek.com/quick_start/pricing
- [S14] Hugging Face model API (license tags): https://huggingface.co/api/models?author={Qwen,meta-llama,mistralai,google,openai,deepseek-ai}
- [S15] Qwen custom LICENSE files: https://huggingface.co/Qwen/Qwen3.8-Flash-Next/raw/main/LICENSE ; https://huggingface.co/Qwen/Qwen3.8-2.4T-A95B/raw/main/LICENSE
- [S16] Gemma Terms of Use: https://ai.google.dev/gemma/terms
- [S16b] Google Open Source Blog, Gemma 4 under Apache 2.0: https://opensource.googleblog.com/2026/03/gemma-4-expanding-the-gemmaverse-with-apache-20.html
- [S17] Llama 4 Community License: https://dev.meta.ai/llama/llama4/license/
- [S18] Anthropic Commercial Terms: https://www.anthropic.com/legal/commercial-terms
- [S19] OpenAI Services Agreement PDF: https://cdn.openai.com/osa/openai-services-agreement.pdf (fetched but not text-extractable)
- [S19b] ConductAtlas record of the OpenAI Business Terms clause (secondary): https://conductatlas.com/platform/openai/openai-business-terms/provision/CA-P-059973/prohibition-on-using-output-to-develop-competing-ai-models/
- [S20] Gemini API Additional Terms: https://ai.google.dev/gemini-api/terms
- Papers [P1]–[P32]: arXiv links inline in §2. Metadata verified with https://export.arxiv.org/api/query

---

## UNVERIFIED / uncertain
1. **License of the IAB taxonomy files.** The README says CC BY 3.0, but its wording names "OpenRTB Specification". The repo has no LICENSE file or SPDX tag, and the site ToS is restrictive. Treat it as CC BY 3.0 with attribution, but avoid vendoring. Asking support@iabtechlab.com would settle it.
2. **The 3.1 "Communication" root row** (`80DV8O`) is my inference of an errata bug, not confirmed by IAB.
3. **Exact 3.1 release date.** The site says December 2024 but also says public comment ran to 2025-01-24. The file was first committed 2024-12-09 and edited through 2025-07.
4. **No newer Content Taxonomy (3.2/4.0)** as of 2026-10-07. This is based on the standards page (updated 2026-02-11) and the repo (last push 2025-09-23). A newer draft could be in public comment elsewhere.
5. **Whether the Jin et al. 2020 IAB eval sets and the Kamen 2025 dataset are downloadable.**
6. **OpenAI "Permitted Exception" wording** for classifiers and embeddings. Only secondary sources; the primary text was not readable (403 / binary PDF). The OpenAI price rows were also extracted through a summarizing fetch and should be re-checked.
7. **Sonnet 5.5 cache-hit price:** $0.20 (table) vs $0.10 (prose) on Anthropic's pricing page.
8. **Whether prompt-cache hits are reliable inside batch jobs** for each provider. Anthropic says the discounts stack, but hit rates in batch are best-effort. The "cached prefix" column assumes near-100% hits.
9. **Llama 4.5** (reported by one secondary source, June 2026). It does not appear in the `meta-llama` HF org, so this is unverified. Also unverified: any EU-domicile restriction in the Llama 4 AUP for multimodal models (I did not read the AUP).
10. **Gemma 4 Apache-2.0 license text** confirmed via HF tags and the Google blog headline. I did not read the full `/gemma/apache_2` page.
11. Whether **thinking can be fully disabled** on Claude Opus 5.5 ("Adaptive (always on)") and how many thinking tokens a low-effort classification call uses. This could raise the output cost well above 100 tokens per page.
12. Self-hosted open-weight teacher cost (GPU-hours per 1M pages) was not estimated.
