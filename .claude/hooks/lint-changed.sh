#!/usr/bin/env bash
# PostToolUse hook (Edit|Write): lint the file that was just changed.
# Markdown -> markdownlint-cli2, Python -> ruff. On failure, print the errors
# to stderr and exit 2 so Claude sees them and fixes the file.
set -uo pipefail

f=$(jq -r '.tool_input.file_path // .tool_response.filePath // empty')
[ -n "$f" ] && [ -f "$f" ] || exit 0

root="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$root" || exit 0
rel="${f#"$root"/}"

case "$rel" in
  node_modules/*|*/node_modules/*|docs/research/*|.venv/*) exit 0 ;;
esac

if ! out=$("$root"/.claude/hooks/no-emoji.sh "$rel" 2>&1); then
  printf '%s\n' "$out" >&2
  exit 2
fi

case "$rel" in
  *.md)
    out=$(python3 .claude/hooks/no-hard-wrap.py "$rel" 2>&1) || {
      printf '%s\n' "$out" >&2
      exit 2
    }
    out=$(npx --no-install markdownlint-cli2 --no-globs "$rel" 2>&1) || {
      printf 'markdownlint failed for %s (run `make fix` or fix by hand):\n%s\n' "$rel" "$out" >&2
      exit 2
    }
    ;;
  *.py)
    out=$( { uvx -q ruff@0.16.10 check "$rel" && uvx -q ruff@0.16.10 format --check "$rel"; } 2>&1) || {
      printf 'ruff failed for %s (run `make fix` or fix by hand):\n%s\n' "$rel" "$out" >&2
      exit 2
    }
    ;;
esac
exit 0
