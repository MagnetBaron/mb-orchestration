#!/bin/bash
# SessionStart hook for mb-orchestration — Claude Code on the web.
#
# This repo installs no packages: it is Python 3 stdlib + bash policy files.
# So instead of installing dependencies, the hook "turns on" the orchestration
# by self-verifying its tooling on every remote session:
#   1. usage-status.py runs and prints the live seat map (useful dispatch context)
#   2. roles/generate.py --check validates the capability-level registry (no writes)
#   3. roles/test_generate.py runs the 24 stdlib unit tests
#
# Properties: synchronous, idempotent, non-interactive, no network, no secrets,
# and no working-tree writes (validators/tests write only to tempfiles).
set -uo pipefail

# Remote-only (Claude Code on the web). On a local machine this is a no-op so the
# hook never slows down or interferes with normal CLI sessions.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$REPO" || { echo "session-start: cannot cd to repo ($REPO)" >&2; exit 1; }

if ! command -v python3 >/dev/null 2>&1; then
  echo "session-start: python3 not found on PATH — orchestration tooling needs it" >&2
  exit 1
fi

echo "── mb-orchestration self-check (SessionStart) ──"

fail=0

# 1. Live seat map — shown in full because it is exactly the context a dispatch needs.
if ! python3 usage-status.py; then
  echo "  FAIL  usage-status.py exited non-zero" >&2
  fail=1
fi

# 2. Registry validation (acts as this repo's linter — deterministic, writes nothing).
if check_out=$(python3 roles/generate.py --check 2>&1); then
  echo "  ok    roles registry: ${check_out}"
else
  echo "  FAIL  roles/generate.py --check" >&2
  echo "${check_out}" | sed 's/^/        /' >&2
  fail=1
fi

# 3. Role generator unit tests (unittest; 24 tests; tempfile-only writes).
if test_out=$(python3 roles/test_generate.py 2>&1); then
  ran=$(printf '%s\n' "${test_out}" | grep -oE 'Ran [0-9]+ tests[^)]*' | head -1)
  echo "  ok    roles tests: ${ran:-passed}"
else
  echo "  FAIL  roles/test_generate.py" >&2
  echo "${test_out}" | sed 's/^/        /' >&2
  fail=1
fi

if [ "${fail}" -ne 0 ]; then
  echo "── self-check FAILED — orchestration tooling is not healthy ──" >&2
  exit 1
fi

echo "── self-check passed — orchestration is on ──"
exit 0
