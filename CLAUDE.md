# Agent guide

Hayate is a personal research project by Henrique. Read the [README](README.md) for what it is and [docs/timeline.md](docs/timeline.md) for what is next.

## Hard boundary

This is an independent personal project, not affiliated with any company. Private context, if any, lives in `CLAUDE.local.md` (git-ignored, never committed).

- Never use, request or reference any employer's or other private data, code, repositories, infrastructure, credentials or internal documents.
- Use only public data (Common Crawl and other openly licensed corpora) and public models. Industry knowledge must come from public sources.
- Don't use connected-account tools (cloud MCP servers, logged-in CLIs) to gather information, even read-only. It may not be clear whose account they belong to. Use public web pages, and ask Henrique if an account is really needed.

## Project Claude setup (`.claude/`)

| Kind | Name | Use it for |
| --- | --- | --- |
| Skill | `/weekend-start` | Open a session: where things stand, today's plan |
| Skill | `/weekend-wrap` | Close a session: timeline, decisions, blog draft, preflight |
| Skill | `/new-decision` | Write a numbered record in `docs/decisions/` |
| Skill | `/blog-post` | Draft a post in `site/src/content/blog/` (always `draft: true`) |
| Skill | `/preflight` | Lint, boundary and no-data checks before committing |
| Skill | `/research <topic>` | Public-sources research filed in `docs/research/` |
| Agent | `researcher` | One research question, public sources only |
| Agent | `docs-keeper` | Keep docs consistent; small fixes |
| Agent | `ml-reviewer` | Check experiments for leakage, test tuning, bad latency method |
| Workflow | `research-fanout` | 2–4 sub-questions in parallel + fact-check (~9 agents) |
| Workflow | `docs-audit` | Find and verify doc contradictions or staleness (~8 agents) |

- `settings.json` denies the AWS and Cloudflare tools, disables the AWS advisor plugin here, and asks before `git commit`, `git push`, `gh` and the GitHub MCP tools.
- A hook lints every edited Markdown or Python file (markdownlint, ruff, no emojis, no hard wrapping), and blocks with the errors until they're fixed.
- Workflows spawn several agents, so run them only when Henrique asks.
- Personal overrides go in `.claude/settings.local.json` (git-ignored).

## Roadmap and issues

- The plan is [docs/timeline.md](docs/timeline.md); status lives on the [Hayate roadmap board](https://github.com/users/HenriqueOkuti/projects/2) (Todo, Doing, Done, Skipped; the Order field is the sequence). Each timeline step links its issue.
- Follow [CONTRIBUTING.md](CONTRIBUTING.md): one branch and PR per issue (branch `<issue>-<slug>`, PR body starts with `Closes #N`), PR title as a plain imperative commit subject of 72 characters or fewer, squash merge only. `main` is protected with no bypass, so never try to push to it directly.
- New work gets an issue from a template in `.github/ISSUE_TEMPLATE/` (task, research question, decision), a milestone (`W01`...`W10`, `Phase 2`, `Phase 3`), an area label and a phase label, and goes on the board.
- Issues and PR bodies follow the same writing rules as docs: no emojis, no hard wrapping.

## Working conventions

- Stack and how to run things: [docs/stack.md](docs/stack.md).
- Record decisions in [docs/decisions/](docs/decisions/README.md).
- Run `make lint` before finishing; Markdown and Python must both pass.
- **No emojis anywhere:** docs, code, blog posts, commit messages, PR text. `make lint` and the edit hook enforce it (`.claude/hooks/no-emoji.sh`).
- **No hard-wrapped prose:** write each paragraph and list item as one line, in Markdown files, issue and PR bodies, templates and commit message bodies. Never wrap at a fixed width, even next to old wrapped text. `make lint` and the edit hook enforce it for Markdown (`.claude/hooks/no-hard-wrap.py`); `make fix` unwraps.
- Never commit page text, the IAB taxonomy file, data or model artifacts; `.gitignore` covers them.
- **No Claude attribution:** commits and PRs never carry a `Co-Authored-By: Claude` trailer, a "Generated with Claude Code" line or any other Claude signature.
- Don't commit or push unless asked.
