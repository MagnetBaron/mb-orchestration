# mb-orchestration

**Policy repo for Magnet Baron multi-CLI work.**

**Codex dispatches. Grok implements code/listings. GPT Terra runs Google MCP volume. Sol/Opus judge. Website Visual QA via Slack. Cursor Other Models $400 is last.** Fireworks **Review E** is the unwired last-resort / independent-family review backup.

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
| [mcp-routing.md](./mcp-routing.md) | Google MCP, product research, bulk analytics |
| [EDGE-CASES.md](./EDGE-CASES.md) | Outages, ambiguity, partial work, owner unreachable |
| [visual-qa.md](./visual-qa.md) | Storefront pixel review / allowlist |
| [visual-qa-slack.md](./visual-qa-slack.md) | How the Bot receives the Slack ticket |
| [sol-usage.md](./sol-usage.md) | Codex $200 Sol: soft cap + weekly window (via `usage-status`) |
| [cursor-usage.md](./cursor-usage.md) | Cursor Ultra pools vs $400 vs Heavy |
| [fireworks-usage.md](./fireworks-usage.md) | Review E (Fireworks): last-resort review trigger, model pin, wrapper contract |
| [usage-metering.md](./usage-metering.md) | Reset times + limits by script, not hardcoded or LLM-guessed |
| [usage-windows.json](./usage-windows.json) · [usage-status.py](./usage-status.py) | Window/cap source of truth + tool: next reset, seat state |
| [luna-close-loop.md](./luna-close-loop.md) | Luna forwards done/parked/blocked only |
| [SETUP-BOTS.md](./SETUP-BOTS.md) | First machine: Codex hands this to Grok, Cursor, Claude |
| [DOCTRINE.md](./DOCTRINE.md) | Designing the system only |
| [teamclaude.routes.example.json](./teamclaude.routes.example.json) | teamclaude setup |
| [install.md](./install.md) | First wire-up |
| [FUTURE.md](./FUTURE.md) | Humans only — multi-Mini |
| [roles/](./roles/) | Cross-CLI role registry: capability levels (`frontier` / `sole` / `terra` / `luna`); current seats are aliases |

## Setup

1. Clone as above.
2. Codex opens this repo and pastes the packet in `SETUP-BOTS.md` to Grok Build, Cursor, and Claude Code.
3. Owner wires Slack Visual QA, Google MCP on Codex/Claude seats, and optional Luna close-loop.

Daily: Codex is still the only entry point. When something breaks, agents read `EDGE-CASES.md`.
