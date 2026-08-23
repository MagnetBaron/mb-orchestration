# Install

## Per project

```bash
curl -fsSL https://raw.githubusercontent.com/MagnetBaron/mb-orchestration/main/AGENTS.md -o AGENTS.md
curl -fsSL https://raw.githubusercontent.com/MagnetBaron/mb-orchestration/main/CLAUDE.md -o CLAUDE.md
```

Codex reads `AGENTS.md`. Claude Code reads `CLAUDE.md` which imports `AGENTS.md`.

## Global (home)

```bash
# Codex
mkdir -p ~/.codex
cp AGENTS.md ~/.codex/AGENTS.md

# Claude
mkdir -p ~/.claude
cp CLAUDE.md ~/.claude/CLAUDE.md
# ensure AGENTS.md is reachable from Claude import path, or paste the table into CLAUDE.md
```

## teamclaude

1. Install and login each seat: `teamclaude login`
2. Merge `teamclaude.routes.example.json` into `~/.config/teamclaude.json`
3. `teamclaude server` then `teamclaude run -- --model opus-4.8`

## Optional published harnesses (not required)

If you want a heavier skill/plugin layer later:

| Project | Role |
|---------|------|
| [olsenbrands/fable-foreman](https://github.com/olsenbrands/fable-foreman) | Fable/Opus lead + Grok/Codex workers + blind verify |
| [luckeyfaraday/master-workflow](https://github.com/luckeyfaraday/master-workflow) | Worker → cross-model reviewer until score ≥ 9 |
| [mar3co/fable-orchestrator](https://github.com/mar3co/fable-orchestrator) | Fable architect, Grok/Codex implement lanes |
| [RichardAtCT/agent-routing-skills](https://github.com/RichardAtCT/agent-routing-skills) | Claude skills + routing matrix vs Codex/Grok |
| [awslabs/cli-agent-orchestrator](https://github.com/awslabs/cli-agent-orchestrator) | tmux multi-CLI supervisor |

This repo intentionally stays **prompt-thin**. Prefer AGENTS.md over loading full plugin trees into every context.
