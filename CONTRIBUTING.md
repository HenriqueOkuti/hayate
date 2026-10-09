# Contributing

Hayate is a one-person project, but every change follows the same path so the history stays readable and the checks stay meaningful. These rules apply to Henrique and to any agent working in the repo.

## Flow

1. **Issue first.** Every change starts from an issue made with a template in `.github/ISSUE_TEMPLATE/` (task, research question or decision). Put it on the [Hayate roadmap board](https://github.com/users/HenriqueOkuti/projects/2) (new issues are added automatically). Phase work gets its phase as the milestone (`Phase 1`, `Phase 2`, `Phase 3`), the same **Phase** on the board, and one area label. Weekend steps are named in the title (`W01: ...`), not by milestone. Work outside the research phases (repo, process, tooling) is **Housekeeping**: the `housekeeping` label, Phase set to Housekeeping, no milestone. Fill in the board's Start and Target dates too.
2. **Branch.** Create a branch from `main` named `<issue>-<slug>`: the issue number, then a few lowercase words joined by hyphens. Example: `2-taxonomy-fetch`.
3. **Commit.** Commit as often as you like on the branch; the commits are squashed on merge.
4. **Pull request.** Open a PR into `main` using the template. The body starts with `Closes #N`.
5. **Merge.** Squash-merge once the checks pass. The issue closes.
6. **Clean up.** Merged branches never stay around. GitHub deletes the remote branch on merge (repo setting "Automatically delete head branches"); delete the local copy with `git switch main && git pull && git fetch --prune && git branch -D <branch>`. A squash merge makes a new commit on `main`, so `git branch -d` always refuses ("not fully merged"); check the PR shows as merged (`gh pr view <N> --json state`) before forcing with `-D`. If a merged branch is still on GitHub for any reason, delete it with `git push origin --delete <branch>`.

## Branch rules on `main`

A repository ruleset protects `main`, with no bypass for anyone:

- Changes land only through a pull request. No direct pushes.
- The `lint`, `test`, `site` and `conventions` checks must pass, on a branch that is up to date with `main`.
- Squash merge only, so history is linear: one commit per PR.
- No force pushes and no deletion.
- Approvals are set to 0, since GitHub does not let the author approve their own PR.

## Commit messages and PR titles

The PR title becomes the commit subject on `main`, with `(#N)` appended by GitHub. Write it as a plain imperative sentence:

- Starts with a capital letter and a verb: `Add`, `Fix`, `Remove`, `Use`, `Record`.
- 72 characters or fewer, no trailing period.
- No type prefix such as `feat:` or `docs:`; the issue's labels carry the area.

Good: `Add taxonomy fetch script with SHA-256 check`. Bad: `feat(data): added the taxonomy script.`

Commit and PR bodies say what changed and why, one line per paragraph or list item. Branch commit messages end up in the squash commit body, so keep them clean too.

## Never in commits or PRs

- Emojis.
- Hard-wrapped prose.
- Claude attribution: no `Co-Authored-By: Claude` trailer and no "Generated with Claude Code" line.
- Page text, the IAB taxonomy file, data or model artifacts (`.gitignore` covers them).
- Anything from an employer or other private source (see the hard boundary in [CLAUDE.md](CLAUDE.md)).

## Checks

| Check | Runs | What it enforces |
| --- | --- | --- |
| `lint` | Every PR and push to `main` | `make lint`: markdownlint, ruff, no emojis, no hard wrapping |
| `test` | Every PR and push to `main` | `uv sync --locked` and `uv run pytest`: the Python tests pass against the committed `uv.lock` |
| `site` | Every PR and push to `main` | The blog in `site/` builds (`npm ci && npm run build`) |
| `conventions` | Every PR | Branch name, PR title, `Closes #N`, no emojis or Claude attribution in the title, body or commits (`.github/scripts/check-pr.sh`) |

Run `make lint` locally before pushing; `make fix` repairs most failures.

## Dependencies

Dependabot (`.github/dependabot.yml`) opens a weekly grouped PR for GitHub Actions and one for npm (root tooling and `site/`). Those PRs skip the branch-name, PR title and `Closes #N` checks (their titles are generated) but must pass everything else. Use the latest major version of an action when adding a new one.

When a security alert sits in a transitive dependency that its parent pins, force the patched version with `overrides` in the root `package.json` (currently `smol-toml` and `katex`, both under `markdownlint-cli2`). Remove an override once the parent package ships the fix.
