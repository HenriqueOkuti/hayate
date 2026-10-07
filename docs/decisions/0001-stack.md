# 0001: Stack

- **Status:** accepted
- **Date:** 2026-10-07

## Context

The project is ML-heavy: data processing, LLM labeling, training, evaluation
and latency benchmarks. The owner works mainly in TS/JS and Go and reads
Python. Work happens on weekends on one machine: i7-13700F, RTX 4070 SUPER,
WSL2.

## Options considered

1. **All Python.** Every ML library is there, but it is the owner's least
   familiar language.
2. **Python for ML, TS/Go at the edges.** Python where the ecosystem forces
   it; JS for k6, TS for a review UI, Go for the request-path server.
3. **Go or TS as the main language.** Training and model export would need
   Python anyway, and the rest would be fighting the ecosystem.

## Decision

Option 2. Python 3.12 with uv, ruff, pytest and pydantic; plain code with no
ML frameworks beyond the libraries listed in [stack.md](../stack.md). Models
are exported in portable formats (ONNX, or plain weights) so that non-Python
code can serve them.

## Consequences

- Phase 1 is entirely Python.
- Go enters with the Phase 2 request benchmark. A Go server also gives a
  realistic serving latency that Python can't.
- Python 3.12 is pinned, not the system's 3.14, until the ML wheels catch up.
- Revisit if the Go serving path becomes the main deliverable.
