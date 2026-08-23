# mb-orchestration

**v1 frozen.** Tight multi-CLI policy for Magnet Baron.

**Grok implements. Non-Grok frontier reviews. Codex dispatches. Cursor $400 is last.**

## Clone (desktop + CLI)

GitHub Desktop, Cursor, Claude Code, and Codex pick these up from the Magnet Baron org:

| Repo | URL | Opens as |
|------|-----|----------|
| **This policy** | https://github.com/MagnetBaron/mb-orchestration | Workspace — loads `AGENTS.md` + `CLAUDE.md` |
| **teamclaude fork** | https://github.com/MagnetBaron/teamclaude | Multi-seat Claude proxy source |

```bash
git clone https://github.com/MagnetBaron/mb-orchestration.git
git clone https://github.com/MagnetBaron/teamclaude.git
```

Suggested rename in GitHub Settings: `grok-lanes` (old URL keeps redirecting).

## Files

| File | Load when |
|------|-----------|
| [AGENTS.md](./AGENTS.md) | **Every** Codex / Cursor / shared agent session |
| [CLAUDE.md](./CLAUDE.md) | Claude Code (`@AGENTS.md` + pins) |
| [DOCTRINE.md](./DOCTRINE.md) | Designing the system only — not every turn |
| [teamclaude.routes.example.json](./teamclaude.routes.example.json) | teamclaude setup |
| [install.md](./install.md) | First wire-up |
| [FUTURE.md](./FUTURE.md) | Humans only — multi-Mini / active-host (not built) |

## v1 scope (done)

- Seat table and legwork-or-stop
- Brief schema, refill, worktrees, risk-gated review
- Fable → Sol → Opus 4.8; Cursor Other Models last
- teamclaude route example + org fork
- Trimmed doctrine from the multi-bucket architecture note

**Not in v1:** host detection, RAM/CPU allocation across Minis, exclusive-QA lock, landing mutex daemons, usage-meter APIs. See [FUTURE.md](./FUTURE.md).

## Setup

See [install.md](./install.md). One worker machine is enough.
