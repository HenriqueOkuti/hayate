#!/usr/bin/env bash
# Generate one mascot image from the fixed references and the canon block.
#
# The only image inputs are the character references hayate-base.png and
# hayate-sheet.png. Never add another image (derived mascot art, the chibi,
# scenes, style or layout references): describe everything else in words.
# This script takes no image arguments, so it can't be done by accident.
#
# Usage: scripts/mascot_gen.sh NAME SCENE_FILE [WORKDIR]
#   NAME        output name without extension, e.g. weekend-01
#   SCENE_FILE  text file with the scene: pose, framing, props, background, size
#   WORKDIR     scratch folder (default: a temp dir); the repo is never touched
#
# Writes WORKDIR/NAME.png and WORKDIR/NAME.prompt.txt (the full prompt and the
# references, kept next to the image wherever it is committed).
# Needs the Codex CLI with image generation turned on.
set -euo pipefail

name=$1
scene=$2
work=${3:-$(mktemp -d)}
repo=$(cd "$(dirname "$0")/.." && pwd)
mascot="$repo/docs/assets/mascot"

mkdir -p "$work"
cp "$mascot/hayate-base.png" "$mascot/hayate-sheet.png" "$work/"

prompt="$(cat "$mascot/canon.txt")

SCENE:
$(cat "$scene")

The references are on white only to show the design; use the simple background the scene describes. Save the result as $name.png in the current folder."

{
  echo "references: hayate-base.png hayate-sheet.png"
  echo "generated: $(date -u +%Y-%m-%dT%H:%M:%SZ) with codex exec (OpenAI image generation)"
  echo
  echo "$prompt"
} >"$work/$name.prompt.txt"

# Prompt before -i (it takes several values), stdin closed, time capped.
timeout 900 codex exec --skip-git-repo-check -C "$work" -s workspace-write \
  "$prompt" -i "$work/hayate-base.png" "$work/hayate-sheet.png" \
  </dev/null >"$work/$name.log" 2>&1

test -f "$work/$name.png" && echo "$work/$name.png"
