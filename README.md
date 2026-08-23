# mb-orchestration

**v1 + Review D + MCP routing.** Tight multi-CLI policy for Magnet Baron.

**Codex dispatches. Grok implements code/listings. GPT Terra runs Google MCP volume. Sol/Opus judge. Website Visual QA via Slack. Cursor Other Models $400 is last.**

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
| [mcp-routing.md](./mcp-routing.md) | Google MCP, product research, bulk analytics seats |
| [visual-qa.md](./visual-qa.md) | Storefront pixel review / allowlist |
| [visual-qa-slack.md](./visual-qa-slack.md) | How the Bot receives the Slack ticket |
| [sol-usage.md](./sol-usage.md) | Codex $200 Sol: 90% week, Sun 10 PM CT |
| [cursor-usage.md](./cursor-usage.md) | Cursor Ultra pools vs $400 vs Heavy |
| [luna-close-loop.md](./luna-close-loop.md) | Luna forwards done reports only |
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
