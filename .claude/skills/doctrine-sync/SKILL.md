---
name: doctrine-sync
description: Build or refresh the Magnet Baron doctrine Map-of-Content index (second-brain index) from the orchestration markdown. Use to turn the scattered .md files into a navigable, linked _index.md, or after doctrine changes so the knowledge base stays discoverable without loading every file into context.
license: proprietary
allowed-tools: Bash(python3 .claude/skills/doctrine-sync/scripts/build_index.py*), Read, Write, Grep, Glob
---

# Doctrine sync (second-brain Map of Content)

Turn the repo's markdown doctrine into a navigable index without loading every
file into context. The index is the retrieval layer a second brain sits on:
`_index.md` links to each note with a one-line summary, grouped by area.

## Run it

```
python3 .claude/skills/doctrine-sync/scripts/build_index.py
```

- Scans repo markdown (skips `.git`, `.claude`, `.cursor`, `node_modules`),
  extracts each file's title + first prose line, writes `_index.md` at repo root.
- Deterministic and idempotent — no timestamps, entries sorted; re-running only
  changes real content, so the diff is meaningful.
- Options: `--root <dir>` (scan another repo, e.g. a sibling vault), `--out <path>`.

## How to use it well

1. Run the script (heavy lifting happens off-context; only its output is read).
2. Review the `_index.md` diff, commit it. Git stays the source of truth — the
   index is **derived**, never authoritative, and links only (never inlines file
   bodies).
3. Regenerate after doctrine changes, or on a schedule (a Routine / cron).

## Token story

The script reads files off disk and writes the index; the agent sees only the
resulting diff, not the file bodies. This is the on-demand, low-burn pattern:
the vault stays on disk; retrieval returns paths + summaries, and specific notes
are read only when a task needs them.

## Next in this line (build when needed)

`vault-search` (grep/BM25 retrieve → paths + snippets, never the whole vault),
`capture-note` (write to inbox, classify into the DOCTRINE §Review-depth "vault
category", stamp the review floor), `decision-log` (ADR for routing/quota calls).
See `mb-orchestration/skills-eval.md` §4 and §7.2.
