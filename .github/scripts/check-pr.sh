#!/usr/bin/env bash
# Check a PR against the repo conventions in CONTRIBUTING.md.
# Inputs (env): BRANCH, TITLE, BODY, BASE, HEAD. Run by .github/workflows/checks.yml.
set -uo pipefail

EMOJI='[\x{1F000}-\x{1FAFF}\x{2600}-\x{27BF}\x{2B00}-\x{2BFF}\x{2300}-\x{23FF}\x{FE0F}\x{200D}]'
fail=0
err() { printf 'FAIL: %s\n' "$1" >&2; fail=1; }

# Branch: <issue>-<slug>, e.g. 2-taxonomy-fetch
[[ "$BRANCH" =~ ^[0-9]+-[a-z0-9]+(-[a-z0-9]+)*$ ]] || err "branch '$BRANCH' must be <issue>-<slug>, e.g. 2-taxonomy-fetch"

# PR title becomes the squash commit subject: plain imperative, capitalized, <= 72 chars, no period.
[ "${#TITLE}" -le 72 ] || err "PR title is ${#TITLE} chars; keep it to 72 or fewer"
[[ "$TITLE" =~ ^[A-Z] ]] || err "PR title must start with a capital letter (imperative: 'Add ...', 'Fix ...')"
[[ "$TITLE" =~ \.$ ]] && err "PR title must not end with a period"
[[ "$TITLE" =~ ^[a-zA-Z]+(\([^\)]*\))?!?:\  ]] && err "PR title must not use a type prefix like 'feat:'; labels carry the area"

# PR body links its issue.
grep -qiE '^(closes|fixes|resolves) #[0-9]+' <<<"$BODY" || err "PR body must start a line with 'Closes #N'"

# No emojis and no Claude attribution in the title, body or any commit message.
msgs=$(git log --format='%B' "$BASE..$HEAD")
all=$(printf '%s\n%s\n%s\n' "$TITLE" "$BODY" "$msgs")
grep -qP "$EMOJI" <<<"$all" && err "emoji found in the PR title, body or a commit message"
grep -qiE 'co-authored-by:.*(claude|anthropic)|generated with .*claude' <<<"$all" && err "Claude attribution found; this repo never signs commits or PRs with Claude"

[ "$fail" -eq 0 ] && echo "PR conventions OK"
exit "$fail"
