# mb-orchestration

Tight multi-CLI coding policy for Magnet Baron.

**Grok implements. Non-Grok frontier reviews. Codex dispatches. Cursor $400 is last.**

## Files

| File | Load when |
|------|-----------|
| [AGENTS.md](./AGENTS.md) | **Every** Codex / Cursor / shared agent session |
| [CLAUDE.md](./CLAUDE.md) | Claude Code (`@AGENTS.md` + pins) |
| [DOCTRINE.md](./DOCTRINE.md) | Designing the system only — not every turn |
| [teamclaude.routes.example.json](./teamclaude.routes.example.json) | teamclaude setup |
| [install.md](./install.md) | First wire-up |

## What we took from the long architecture doc

Kept as standing law:

- Unspent quota at reset = waste; abundant bucket does volume
- Roles over models; lead/dispatch does not do legwork
- Legwork-or-stop (never burn scarce buckets on false outages)
- Brief schema; refill on completion; worktree isolation
- Risk-gated cross-family review; diff not transcript; two-loop max

Deferred (source system had these; you adopt later):

- Full overnight land-to-prod without phone approval
- EA board-compaction daemons / idle watchdogs
- Machine load/memory gates and landing mutex (add when parallel volume needs them)
- Automated usage % (providers still mostly manual)

## Published peers

Same ideas, heavier context: [fable-foreman](https://github.com/olsenbrands/fable-foreman), [master-workflow](https://github.com/luckeyfaraday/master-workflow), [fable-orchestrator](https://github.com/mar3co/fable-orchestrator), [cli-agent-orchestrator](https://github.com/awslabs/cli-agent-orchestrator).

## Setup

See [install.md](./install.md).
