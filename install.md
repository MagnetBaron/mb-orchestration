# Install

## 1. Copy policy into projects

```bash
curl -fsSL https://raw.githubusercontent.com/MagnetBaron/mb-orchestration/main/AGENTS.md -o AGENTS.md
curl -fsSL https://raw.githubusercontent.com/MagnetBaron/mb-orchestration/main/CLAUDE.md -o CLAUDE.md
```

Codex → `AGENTS.md`. Claude Code → `CLAUDE.md` (imports AGENTS).

Optional global:

```bash
mkdir -p ~/.codex ~/.claude
cp AGENTS.md ~/.codex/AGENTS.md
cp CLAUDE.md ~/.claude/CLAUDE.md
# place AGENTS.md where Claude @import can resolve, or inline the table
```

## 2. teamclaude

1. `teamclaude login` per seat
2. Merge `teamclaude.routes.example.json` into `~/.config/teamclaude.json`
3. `teamclaude server` then `teamclaude run -- --model opus-4.8`
4. After plan downgrade: delete the Fable route

## 3. Ordered adoption (from the source checklist, cut to your reality)

1. **Buckets classified** — Grok abundant; Claude+Sol scarce judgment; Codex Terra/Luna dispatch; Cursor $400 last
2. **AGENTS.md live** in repos you touch from phone/Codex
3. **Brief schema** enforced by dispatch (refuse incomplete briefs)
4. **Worktrees** for any parallel Grok jobs
5. **Risk gate + reviewer order** before frontier spend
6. **teamclaude routes** for Claude seats
7. **Usage ledger** (manual % in backlog header only)
8. **Pre/post-reset** drain of Grok / surplus Claude mid-tier — judgment, not cron yet
9. Later only: landing mutex, full-suite semaphore, CAO/tmux multi-CLI, fable-foreman if you want a skill runtime

## 4. Optional heavy harnesses

| Project | When |
|---------|------|
| [olsenbrands/fable-foreman](https://github.com/olsenbrands/fable-foreman) | Need Claude skill pack + blind verify |
| [luckeyfaraday/master-workflow](https://github.com/luckeyfaraday/master-workflow) | Automated worker→reviewer score loop |
| [awslabs/cli-agent-orchestrator](https://github.com/awslabs/cli-agent-orchestrator) | Parallel CLI processes in tmux |

Prefer this repo’s thin files until context pressure forces a plugin.
