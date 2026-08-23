# Claude Code

@AGENTS.md

## Claude-only

- Default model: **opus-4.8** (not opus-5)
- Fable 5: review / architecture only; never default implementer
- Route through **teamclaude** when multiple seats exist
- Use 5h windows (seat state via `usage-status`, never LLM-estimated); do not stack all work on one account
- After downgrade to Pro / Team Standard: no included Fable — **Sol → 4.8 → Review E (Fireworks, if wired) → stop**. teamclaude `mb/sync-plan` blocks `*fable*` automatically; do not hand-edit routes.
