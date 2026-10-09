# Stack

What the project uses, why, and how to run it. The decision itself is recorded in [decisions/0001-stack.md](decisions/0001-stack.md).

## In one paragraph

**Python** does all the ML work: data, teacher labeling, training, evaluation and micro-benchmarks. Training libraries, model formats and research code all live there, and fighting that would cost more weekends than it saves. Python code stays **plain**: functions, dataclasses, type hints and small scripts. No frameworks, so it reads like Go. **TypeScript/JavaScript and Go** come in where they fit naturally and match what you know:

- k6 load tests (JS);
- a possible small review UI (TS);
- the Phase 2 request-path server (Go), which loads the exported model files.

## Concepts, mapped to things you know

| ML term | Think of it as |
| --- | --- |
| Model | A function whose behavior comes from learned parameters (big arrays of floats) instead of hand-written logic |
| Training | Fitting those parameters to examples, like an optimizer tuning config values against a test suite |
| Teacher → student distillation | A big, slow, smart function labels data; a tiny, fast function is trained to imitate its answers |
| Tokenizer | A lexer: text → a list of integer token IDs |
| Embedding | A function (often just a lookup table) mapping text to a fixed-length float vector |
| Linear head | One matrix multiply: vector → one score per category |
| Sigmoid + threshold | Score → probability (0–1) → yes/no per category. Multi-label means each category decides independently. |
| Inference | Calling the trained function |
| Epoch / batch | One pass over the training data / items processed together for speed |
| ONNX | A portable compiled model file, roughly "WASM for models". ONNX Runtime executes it from Python, Go, JS, C++ … |
| int8 quantization | Storing weights as int8 instead of float32: ~4× smaller and faster on CPU, with a small accuracy loss |
| F1 | Combines precision ("when it says X, is it right?") and recall ("does it find all the X?") into one number |

## Tooling (the project itself)

| Tool | Role | Analogy |
| --- | --- | --- |
| Python 3.12 (`.python-version`) | Language. 3.12 because ML wheels lag newer Python releases | — |
| [uv](https://docs.astral.sh/uv/) | Python versions, virtualenv, dependencies, lockfile | pnpm + nvm, or `go mod` |
| [ruff](https://docs.astral.sh/ruff/) | Lint + format | eslint + prettier / gofmt + vet |
| pytest | Tests | vitest / `go test` |
| [pydantic](https://docs.pydantic.dev/) | Typed schemas and validation (teacher output, configs) | Zod |
| markdownlint-cli2 (npm, dev only) | Markdown lint | — |
| Docker | The "small VPS" benchmark profile ([measurement.md](measurement.md)) | — |
| Make | `make lint`, `make fix` | — |

## Libraries by stage

These are added to `pyproject.toml` when first used, not up front.

| Stage | Libraries | Why |
| --- | --- | --- |
| Data | `duckdb`, `pyarrow`, `httpx`, `warcio`/`fastwarc`, `trafilatura`, `resiliparse`, `datasets` | DuckDB queries the Common Crawl Parquet index and our own files with SQL. httpx does range reads. Both extractors get compared. |
| Teacher (local) | **Ollama** for the pilot; **vLLM** only if bulk throughput needs it | Ollama: one-command install, JSON-schema `format`, OpenAI-compatible API. vLLM: much higher batch throughput, xgrammar-constrained decoding. Both run on the 4070 under WSL2. |
| Teacher (API) | `anthropic` SDK (Message Batches + structured outputs) | 50% batch discount and schema-valid output |
| Tier 1 | `scikit-learn` | `HashingVectorizer` + linear models, maintained (unlike fastText) |
| Tier 2 | `model2vec`, `sentence-transformers` | Static embedding models and distillation |
| Tier 3 | `torch` (CUDA), `transformers`, `sentence-transformers` | Fine-tune on the GPU |
| Export + CPU inference | `optimum`, `onnxruntime` (+ `openvino` to compare) | ONNX int8 for CPU |
| Evaluation | `scikit-learn` metrics, `numpy`, `matplotlib` | Standard metrics and the trade-off plot |
| Benchmarks | Own harness (`perf_counter_ns`, raw timings → Parquet), Docker, k6 (JS) | Raw timings give true p99. k6 does open-model load for request benchmarks. |

**Not used, on purpose:**

- **Experiment trackers (MLflow, W&B):** for one person on weekends, results as JSON in `results/`, tagged with the git commit and config, are enough.
- **Notebooks in the pipeline:** every step is a script with a config, so it can be rerun.
- **pandas:** DuckDB SQL + pyarrow cover it.
- **LangChain-style frameworks:** the teacher is one HTTP call with a schema.

## Conventions

- **One script per pipeline step** in `scripts/`. Each takes `--config configs/<name>.toml` and writes outputs under `data/` (large, ignored) or `results/` (small, committed). Logic lives in `src/hayate/`; scripts stay thin.
- **Data formats:**
  - **Parquet** for tables (pages, labels, splits, timings).
  - **JSONL** for raw teacher responses (append-only and easy to inspect).
  - Every file records the config and code version that produced it.
- **Configs are TOML** (read with the stdlib `tomllib`).
- **Model artifacts** go to `artifacts/<student>/<run-id>/` in a portable format:
  - ONNX for neural students;
  - plain weight arrays plus a JSON hash spec for tier 1, so Go can reimplement it in a few lines.

## How to run

```bash
uv sync                      # create .venv and install locked deps
uv run python scripts/<step>.py --config configs/<step>.toml
uv run pytest
make lint                    # markdownlint + ruff check + ruff format --check
make fix                     # auto-fix what can be fixed
npm install                  # once, for the Markdown linter
```

First-time setup: install [uv](https://docs.astral.sh/uv/getting-started/installation/), then `uv sync` installs Python 3.12 (from `.python-version`) and the locked dependencies from `uv.lock` into `.venv/`. Add a library with `uv add <pkg>` (or `uv add --dev <pkg>` for tooling such as pytest) when a step first needs it, and commit `pyproject.toml` and `uv.lock` together.

| Step | Script | Config | Output |
| --- | --- | --- | --- |
| Taxonomy fetch and label set | `scripts/fetch_taxonomy.py` | `configs/taxonomy.toml` | `data/taxonomy/`: the pinned TSV (sha256-checked) and `labels.json` ([decision 0002](decisions/0002-label-depth.md)) |

## Where TS and Go fit

| Where | Language | When | Notes |
| --- | --- | --- | --- |
| Progress blog | TS (Astro 7, in `site/`) | Now | Markdown posts in `site/src/content/blog/`. `make site` runs it locally with drafts. GitHub Actions deploys it to Pages on every push to `main`. |
| HTTP load tests | JS (k6) | Phase 2 | Already installed. Uses arrival-rate executors. |
| Human review tool | TS (small local page) or a plain CLI | Weekend 4 | Decided then. Reads teacher JSONL and writes review decisions. |
| Request-path server (fetch → extract → infer) | Go | Phase 2 | The realistic serving language. Tier 1 is easy to port. ONNX Runtime has Go bindings (community `onnxruntime_go`; ONNX Runtime 1.30 reportedly added official ones, *unverified*). A Go port of trafilatura exists (*check its version and license*). |
