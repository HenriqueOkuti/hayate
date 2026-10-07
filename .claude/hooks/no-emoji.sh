#!/usr/bin/env bash
# Fail if any given file (or, with no args, any tracked text file) contains emoji.
# Project rule: no emojis anywhere (docs, code, blog, commits). See CLAUDE.md.
set -uo pipefail
cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}" || exit 0
EMOJI='[\x{1F000}-\x{1FAFF}\x{2600}-\x{27BF}\x{2B00}-\x{2BFF}\x{2300}-\x{23FF}\x{FE0F}\x{200D}]'
if [ "$#" -gt 0 ]; then files=("$@"); else mapfile -t files < <(git ls-files | grep -vE '(^|/)package-lock\.json$|\.(png|jpg|jpeg|gif|webp|ico)$'); fi
hits=$(grep -nIP "$EMOJI" -- "${files[@]}" 2>/dev/null)
if [ -n "$hits" ]; then
  printf 'Emoji found (project rule: no emojis anywhere):\n%s\n' "$hits" >&2
  exit 1
fi
