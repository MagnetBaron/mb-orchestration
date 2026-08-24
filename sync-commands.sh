#!/usr/bin/env bash
# Distribute the single canonical /orchestrate command to Claude Code, Codex, and Cursor.
# Canonical source: .claude/commands/orchestrate.md  — edit THAT, never the copies.
# Re-run after cloning on a new machine, or if a host replaced its symlink with a stale copy.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CANON="$REPO/.claude/commands/orchestrate.md"
[ -f "$CANON" ] || { echo "canonical missing: $CANON" >&2; exit 1; }

mkdir -p "$HOME/.codex/prompts" "$HOME/.claude/commands" "$REPO/.cursor/commands"

# Global hosts: absolute symlinks
ln -sf "$CANON" "$HOME/.codex/prompts/orchestrate.md"
ln -sf "$CANON" "$HOME/.claude/commands/orchestrate.md"
# Cursor project command: RELATIVE symlink so it survives repo moves/clones
ln -sf ../../.claude/commands/orchestrate.md "$REPO/.cursor/commands/orchestrate.md"

rc=0
for f in \
  "$HOME/.codex/prompts/orchestrate.md" \
  "$HOME/.claude/commands/orchestrate.md" \
  "$REPO/.cursor/commands/orchestrate.md"; do
  if [ "$f" -ef "$CANON" ]; then echo "OK      $f"; else echo "BROKEN  $f" >&2; rc=1; fi
done
[ $rc -eq 0 ] && echo "/orchestrate distributed to Claude Code, Codex, Cursor."
exit $rc
