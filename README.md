# mb-orchestration

**v1 + Review D.** Tight multi-CLI policy for Magnet Baron.

**Codex dispatches. Grok implements. Frontier reviews git diffs. Website Visual QA reviews pixels via Slack. Cursor $400 is last.**

## Clone (desktop + CLI)

| Repo | URL | Opens as |
|------|-----|----------|
| **This policy** | https://github.com/MagnetBaron/mb-orchestration | Workspace — `AGENTS.md` + `CLAUDE.md` |
| **teamclaude fork** | https://github.com/MagnetBaron/teamclaude | Multi-seat Claude proxy source |

```bash
git clone https://github.com/MagnetBaron/mb-orchestration.git
git clone https://github.com/MagnetBaron/teamclaude.git
```

## Files

| File | Load when |
|------|-----------|
| [AGENTS.md](./AGENTS.md) | **Every** Codex / Cursor / shared agent session |
| [CLAUDE.md](./CLAUDE.md) | Claude Code |
| [visual-qa.md](./visual-qa.md) | Storefront pixel review / allowlist |
| [visual-qa-slack.md](./visual-qa-slack.md) | How the Bot receives the Slack ticket |
| [SETUP-BOTS.md](./SETUP-BOTS.md) | First machine: Codex hands this to Grok, Cursor, Claude |
| [DOCTRINE.md](./DOCTRINE.md) | Designing the system only |
| [teamclaude.routes.example.json](./teamclaude.routes.example.json) | teamclaude setup |
| [install.md](./install.md) | First wire-up |
| [FUTURE.md](./FUTURE.md) | Humans only — multi-Mini |

## Setup

1. Clone as above.
2. Codex opens this repo and pastes the packet in `SETUP-BOTS.md` to Grok Build, Cursor, and Claude Code.
3. Owner wires Slack delivery once per [visual-qa-slack.md](./visual-qa-slack.md). Quit the app on the worker Mini.

Daily: Codex is still the only entry point.
