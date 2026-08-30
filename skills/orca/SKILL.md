---
name: orca
description: Dispatch a task through the Magnet Baron multi-CLI orchestration by loading the canonical intake-aware policy.
---

# Orca

Resolve the authoritative control checkout from `ORCA_REPO`, defaulting to
`$HOME/git/mb-orchestration`. Verify that it contains `AGENTS.md` and that its
`origin` remote matches `ORCA_TRUSTED_ORIGIN`, defaulting to
`MagnetBaron/mb-orchestration`. Then read
`.claude/commands/orchestrate.md` from that checkout completely and follow it
for the user's current task.

This entry skill grants no extra authority. The canonical command and
repository config determine the effective dispatcher, handoff boundary,
implementer, review chain, and owner gates for each run.
