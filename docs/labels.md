# Labels: taxonomy and teacher

Snapshot 2026-10-07. Sources and details are in
[research/2026-10-07-taxonomy-teacher.md](research/2026-10-07-taxonomy-teacher.md).

## Taxonomy: IAB Tech Lab Content Taxonomy 3.1

- **Current version:** 3.1 (Dec 2024). Source:
  [InteractiveAdvertisingBureau/Taxonomies](https://github.com/InteractiveAdvertisingBureau/Taxonomies),
  file `Content Taxonomies/Content Taxonomy 3.1.tsv` (TSV only).
- **Pin by commit SHA and sha256**, not by version name. The file was edited
  8 times after release without a version bump. sha256 at repo HEAD
  `de757836` (2025-09-23):
  `7212cdc496ba347a03e703b1932bdcdd4fd29089b058f4edeb4d3da1f1222ea7`.
- **Size:** 704 nodes: Tier 1 has 37 (really 36; row `80DV8O` looks
  misfiled), Tier 2 has 323, Tier 3 has 275, Tier 4 has 69. Tiers 1–2 together
  give about 360 labels.
- **IDs are strings** (e.g. `80DV8O`).
- **Flags and subtrees:**
  - `Extension=SCD` marks 63 sensitive nodes.
  - The **Genres** subtree is for CTV/podcasts and probably gets excluded.
  - Descriptive Vectors (content type, brand suitability) are out of scope.
- **License:** most likely CC BY 3.0. The README wording is copied
  boilerplate, and the site terms are stricter. **Download at a pinned SHA;
  don't vendor the file.** Credit IAB Tech Lab and don't imply endorsement.
- **Not used:** the Audience taxonomy (describes people, a non-goal) and the
  Ad Product taxonomy (describes ads).
- **No official labeled examples exist.** Kamen 2025
  ([arXiv:2510.13885](https://arxiv.org/abs/2510.13885)) found 10 LLMs
  zero-shot on IAB 2.2 at about 41% F1, over-assigning categories. Expect a
  noisy teacher.

## Teacher output contract

```json
{"labels": [{"id": "<IAB unique ID>", "confidence": 0.0-1.0}]}
```

- At most 5 labels per page.
- `id` is a JSON-schema **enum of valid IDs** (structured output on API
  models, constrained decoding on open models).
- Each record stores the model ID, prompt version, taxonomy SHA, sampling
  settings and token usage.
- **Prompting the ~700 labels:**
  1. Start with the full list (~8k tokens) in a **cached** prefix.
  2. Compare against a hierarchical pass (pick Tier 1, then the subtree).
  3. Infer–retrieve–rank ([arXiv:2401.12178](https://arxiv.org/abs/2401.12178))
     is the fallback.
- **Confidence:**
  - Verbalized confidence for every page. It is overconfident.
  - On a 5–10k subset, run k=3–5 samples or a second teacher, to measure
    consistency and calibrate the scores.

## Teacher choice

| Option | Cost | Notes |
| --- | --- | --- |
| Local open-weight model on the RTX 4070 SUPER (12 GB) | Free (electricity) | Fits ~8–14B models at 4-bit, e.g. Gemma 4 12B (Apache-2.0). Qwen3.8-27B (Apache-2.0) does **not** fit at 4-bit. Weaker than the API models, but its labels are **publishable**. |
| Claude Haiku 5.5, batch + cached prefix | ~$115 / 1M pages | $0.10/$0.50 per MTok, batch 50% off. Thinking can be disabled at effort ≤ high. |
| Claude Sonnet 5.5 / Opus 5.5 (reference teacher on a subset) | ~$2.3k / ~$3.8k per 1M pages | Use on 50–100k pages for a few hundred dollars. Opus 5.5 can't disable thinking, so use `effort: low`. |
| Gemini 3.1 Flash-Lite / gpt-5-mini | ~$300 per 1M pages | Gemini Flash prices double on 2027-01-01. |

Cost assumes 1,000 tokens in and 100 out per page. The Claude tokenizer adds
about 30%, and thinking tokens bill as output, so **measure on a pilot first**.

**Terms (not legal advice):** Anthropic, OpenAI and Google forbid using
outputs to train *competing* models. A tiny fixed-taxonomy classifier in a
personal repo is low risk, but publishing its labels or weights counts as
distribution.

- **Default:** labels or weights that will be published come from an Apache
  or MIT teacher. API models serve as a reference.
- **Avoid as the published teacher:**
  - Gemma ≤ 3: a model distilled from it inherits the Gemma terms.
  - Llama 4: a published student must be named "Llama…".
