<p align="center">
  <img src="docs/assets/hayate-peek.png" alt="Hayate, the project mascot: a cyan-haired runner in an orange scarf, peeking curiously over the edge" width="480">
</p>

<h1 align="center">Hayate 疾風</h1>

<p align="center">
  <strong>A web-page categorizer distilled from a big LLM, built to answer in under a millisecond.</strong><br>
  <em>One glance, one cut. Your page is tagged before you blink.</em>
</p>

<p align="center">
  <img alt="Status: planning" src="https://img.shields.io/badge/status-planning-EA580C?style=flat-square">
  <img alt="Target: under 1 ms per page" src="https://img.shields.io/badge/target-%3C1%20ms%20%2F%20page-0E7490?style=flat-square">
  <img alt="Python 3.12" src="https://img.shields.io/badge/python-3.12-0F766E?style=flat-square">
  <img alt="Data: public only" src="https://img.shields.io/badge/data-public%20only-334155?style=flat-square">
  <img alt="Weekend project" src="https://img.shields.io/badge/cadence-weekends-C2410C?style=flat-square">
  <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-64748B?style=flat-square">
</p>

<p align="center">
  <a href="#what-she-does">What she does</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#progress">Progress</a> ·
  <a href="#getting-started">Getting started</a> ·
  <a href="#docs">Docs</a> ·
  <a href="https://henriqueokuti.github.io/hayate/">Blog</a>
</p>

---

## What she does

Give Hayate a web page and she tells you what it's about:

| Page | Hayate says |
| :--- | :--- |
| *"16-week marathon plan for beginners"* | **Sports › Running** |
| *"Hotel review: a week in Alfama, Lisbon"* | **Travel › Hotels** |
| *"Benchmarking int8 inference on ARM laptops"* | **Technology & Computing** |

The catch is that she has to do it **in under a millisecond, on a plain CPU, for almost no money**. This weekend research project finds out how small and fast a page categorizer can get before it stops being accurate. The answer is a **trade-off curve**, not one model.

## How it works

<p align="center">
  <img src="docs/assets/pipeline.svg" alt="Pipeline: public pages, then a big LLM labels them, then tiny models learn to imitate it, then accuracy, speed and cost are measured" width="900">
</p>

A big LLM is accurate but slow and costly. It labels the pages **once**, and small models learn to copy it. There are three student sizes:

| Student | What it is | Expected speed | Role |
| :--- | :--- | :---: | :--- |
| **Tier 1** | Hashed word patterns + a linear layer | ≪ 1 ms | The speed floor |
| **Tier 2** | Fixed word vectors + a linear layer | ~1 ms | The main bet: fast *and* good |
| **Tier 3** | A compact transformer, int8 on CPU | a few ms | The accuracy ceiling |

Each one is scored on **quality** (against the LLM *and* against human checks), **latency** (p50/p99) and **cost per million pages**.

> **Why so fast?** Ad platforms categorize pages ahead of time and cache the
> answer, so serving it is just a lookup. At web scale every millisecond is
> money, and a near-free model can cover the pages the cache missed.

## Progress

| Phase | Status | Target | Goal |
| :--- | :--- | :--- | :--- |
| **0 · Plan** | In progress | Oct 2026 | Research, docs, stack, scaffolding |
| **1 · First curve** | Next | Dec 2026 | Three students on one accuracy vs speed plot, measured locally |
| **2 · Realism** | Later | Feb 2027 | End-to-end request latency, a URL-only fast path, noisy-label effects |
| **3 · Open questions** | Later | 2027 → | Topic drift; Indonesian, Vietnamese and Thai |

Weekend-by-weekend plan: [docs/timeline.md](docs/timeline.md). Live status: the [roadmap board](https://github.com/users/HenriqueOkuti/projects/2). Progress notes go on the [blog](https://henriqueokuti.github.io/hayate/).

## Getting started

These commands set up the dev environment and run the first pipeline step:

```bash
npm install     # Markdown linter (dev tooling)
uv sync         # Python 3.12 environment
make lint       # markdownlint + ruff
uv run python scripts/fetch_taxonomy.py --config configs/taxonomy.toml   # pinned IAB taxonomy -> data/taxonomy/
```

New to the ML side? [docs/stack.md](docs/stack.md) maps the jargon to everyday programming ideas: a tokenizer is a lexer, ONNX is roughly "WASM for models", and so on.

## Docs

| Doc | What's inside |
| :--- | :--- |
| [Timeline](docs/timeline.md) | The weekend-by-weekend plan |
| [Stack](docs/stack.md) | Tools, libraries, how to run things |
| [Labels](docs/labels.md) | The IAB taxonomy and the teacher LLM |
| [Data](docs/data.md) | Where pages come from, text extraction |
| [Models](docs/models.md) | The three student tiers |
| [Measurement](docs/measurement.md) | Quality, speed, cost, local setup |
| [Decisions](docs/decisions/README.md) | What's settled, what's pending |
| [Mascot](docs/mascot.md) | Her canon and how new images are made |
| [Contributing](CONTRIBUTING.md) | Issues, branches, PRs, commit conventions and checks |

## Ground rules

- **Public data and public models only.** No private or proprietary data, ever.
- An independent personal project, not affiliated with any company.
- Categorizes **pages, not people**. No user tracking or profiling.

## License

[MIT](LICENSE), covering the code, docs and mascot art (generated with OpenAI image generation). The IAB taxonomy and crawled pages are not part of this repo and keep their own terms.
