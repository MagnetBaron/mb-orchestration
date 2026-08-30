#!/usr/bin/env bash
# Distribute the canonical orchestration command under both /orca (preferred)
# and /orchestrate (compatibility alias) to Claude Code, Codex, Cursor, and the
# shared native skill tree. Edit .claude/commands/orchestrate.md, never a copy.
set -euo pipefail

MODE="sync"
case "${1:-}" in
  "") ;;
  --check) MODE="check" ;;
  *) echo "usage: $0 [--check]" >&2; exit 2 ;;
esac

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
CANON="$REPO/.claude/commands/orchestrate.md"
[ -f "$CANON" ] || { echo "canonical missing: $CANON" >&2; exit 1; }

TARGET_HOME="${MB_ORCHESTRATION_HOME:-$HOME}"
EXPECTED_REPO="${ORCA_REPO:-$HOME/git/mb-orchestration}"
PRIMARY_CLAUDE_CONFIG="$TARGET_HOME/.claude"
CODEX_PROMPTS="$TARGET_HOME/.codex/prompts"
NATIVE_ORCA="$TARGET_HOME/.agents/skills/orca/SKILL.md"
NATIVE_ORCA_SOURCE="$REPO/skills/orca/SKILL.md"

[ -d "$EXPECTED_REPO" ] || { echo "canonical checkout missing: $EXPECTED_REPO" >&2; exit 1; }
EXPECTED_REPO="$(cd "$EXPECTED_REPO" && pwd -P)"
[ "$REPO" = "$EXPECTED_REPO" ] || {
  echo "refusing non-canonical checkout: $REPO (expected $EXPECTED_REPO)" >&2
  exit 1
}
[ -f "$NATIVE_ORCA_SOURCE" ] || { echo "native skill missing: $NATIVE_ORCA_SOURCE" >&2; exit 1; }
normalize_github_origin() {
  local value="$1"
  value="${value%/}"
  value="${value%.git}"
  case "$value" in
    https://github.com/*) value="github.com/${value#https://github.com/}" ;;
    git@github.com:*) value="github.com/${value#git@github.com:}" ;;
    ssh://git@github.com/*) value="github.com/${value#ssh://git@github.com/}" ;;
    *) return 1 ;;
  esac
  printf '%s\n' "$value"
}
origin_url="$(git -C "$REPO" remote get-url origin 2>/dev/null || true)"
trusted_origin="${ORCA_TRUSTED_ORIGIN:-https://github.com/MagnetBaron/mb-orchestration}"
origin_normalized="$(normalize_github_origin "$origin_url" 2>/dev/null || true)"
trusted_normalized="$(normalize_github_origin "$trusted_origin" 2>/dev/null || true)"
[ -n "$origin_normalized" ] && [ "$origin_normalized" = "$trusted_normalized" ] || {
  echo "refusing untrusted origin: ${origin_url:-missing}" >&2
  exit 1
}

claude_config_dirs=("$PRIMARY_CLAUDE_CONFIG")
add_claude_config() {
  local candidate="$1" seen
  [ -n "$candidate" ] || return 0
  for seen in "${claude_config_dirs[@]}"; do
    [ "$seen" = "$candidate" ] && return 0
  done
  claude_config_dirs+=("$candidate")
}
for config_dir in "$TARGET_HOME"/.claude-*; do
  [ -d "$config_dir" ] || continue
  if [ -f "$config_dir/settings.json" ]; then
    add_claude_config "$config_dir"
  else
    echo "SKIP    $config_dir (no settings.json; not a discovered Claude profile)" >&2
  fi
done
if [ -n "${CLAUDE_CONFIG_DIR:-}" ]; then
  case "$CLAUDE_CONFIG_DIR" in /*) add_claude_config "$CLAUDE_CONFIG_DIR" ;; *) echo "CLAUDE_CONFIG_DIR must be absolute" >&2; exit 2 ;; esac
fi

tmp=""
trap '[ -n "$tmp" ] && rm -f "$tmp"' EXIT
copy_file() {
  local source="$1" dest="$2" dir
  dir="$(dirname "$dest")"
  mkdir -p "$dir"
  if [ -d "$dest" ] && [ ! -L "$dest" ]; then
    echo "refusing directory destination: $dest" >&2
    exit 1
  fi
  tmp="$(mktemp "$dir/.orca.XXXXXX")"
  cp "$source" "$tmp"
  chmod 0644 "$tmp"
  [ -L "$dest" ] && rm -f "$dest"
  mv -f "$tmp" "$dest"
  tmp=""
}

if [ "$MODE" = "sync" ]; then
  mkdir -p "$CODEX_PROMPTS" "$PRIMARY_CLAUDE_CONFIG/commands" \
    "$REPO/.cursor/commands" "$(dirname "$NATIVE_ORCA")"

  # Codex prompts and the shared native /orca skill are real copies: some
  # loader versions do not discover symlinked prompt/skill files reliably.
  copy_file "$CANON" "$CODEX_PROMPTS/orca.md"
  copy_file "$CANON" "$CODEX_PROMPTS/orchestrate.md"
  copy_file "$NATIVE_ORCA_SOURCE" "$NATIVE_ORCA"

  # Claude and Cursor command loaders follow symlinks. Install both names so
  # older muscle memory remains valid while /orca is the preferred trigger.
  for config_dir in "${claude_config_dirs[@]}"; do
    mkdir -p "$config_dir/commands"
    ln -sfn "$CANON" "$config_dir/commands/orca.md"
    ln -sfn "$CANON" "$config_dir/commands/orchestrate.md"
  done
  ln -sfn ../../.claude/commands/orchestrate.md "$REPO/.cursor/commands/orca.md"
  ln -sfn ../../.claude/commands/orchestrate.md "$REPO/.cursor/commands/orchestrate.md"
fi

rc=0
check_copy() {
  local f="$1" source="${2:-$CANON}"
  if [ -f "$f" ] && [ ! -L "$f" ] && cmp -s "$f" "$source"; then
    echo "OK      $f (copy)"
  else
    echo "BROKEN  $f" >&2
    rc=1
  fi
}
check_link() {
  local f="$1"
  if [ -e "$f" ] && [ "$f" -ef "$CANON" ]; then
    echo "OK      $f"
  else
    echo "BROKEN  $f" >&2
    rc=1
  fi
}

check_copy "$CODEX_PROMPTS/orca.md"
check_copy "$CODEX_PROMPTS/orchestrate.md"
check_copy "$NATIVE_ORCA" "$NATIVE_ORCA_SOURCE"
for config_dir in "${claude_config_dirs[@]}"; do
  check_link "$config_dir/commands/orca.md"
  check_link "$config_dir/commands/orchestrate.md"
done
check_link "$REPO/.cursor/commands/orca.md"
check_link "$REPO/.cursor/commands/orchestrate.md"

if [ "$rc" -eq 0 ]; then
  if [ "$MODE" = "sync" ]; then
    echo "/orca distributed from $CANON; /orchestrate retained as an identical alias."
  else
    echo "/orca and /orchestrate are canonical on every discovered host."
  fi
fi
exit "$rc"
