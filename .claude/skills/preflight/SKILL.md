---
name: preflight
description: Pre-commit checks for Hayate - lint, boundary (no employer or private material), no data/page text/taxonomy file/secrets staged, docs consistent. Use before committing or pushing, before publishing a blog post, or when the user asks "is this safe to commit".
---

# Preflight

Run every check and report pass/fail for each. Fix only trivial lint problems yourself. Report everything else.

1. **Lint:** `make lint` passes. If the site changed, `make site-build` passes too.
2. **Nothing that must not be committed** (use `git status` and `git diff --cached --stat` under git, or list new files otherwise):
   - no files under `data/` or `artifacts/`, no `.warc.gz`, `.parquet`, `.onnx` or model weights;
   - no IAB taxonomy TSV (it is downloaded at a pinned SHA, never vendored);
   - no crawled page text anywhere, including in tests, fixtures, blog posts and `results/`;
   - no secrets: `.env`, API keys, tokens (grep for `sk-`, `api_key`, `token`, `secret` in the changed files).
3. **Boundary:** the changed files contain nothing about the user's employer or its systems, and nothing that came from a non-public source. Public docs (README, blog) never name the employer.
4. **Docs consistency:** if code or decisions changed, the matching doc and `docs/timeline.md` reflect it. For anything bigger than a quick check, suggest the `docs-keeper` agent.
5. **Results:** any new numbers in `results/` or a post record their config, commit, hardware and taxonomy SHA. If they weren't reviewed yet, suggest the `ml-reviewer` agent.

Reply with a checklist (PASS / FAIL and one line each). If everything passes, say so in one line. Never commit or push as part of this skill.
