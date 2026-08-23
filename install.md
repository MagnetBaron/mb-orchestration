# Install

## 0. Get the repos onto the machine

Desktop clients (GitHub Desktop, Cursor Open Folder, Claude Code, Codex) should clone from the **Magnet Baron** org so they stay write-enabled:

```bash
git clone https://github.com/MagnetBaron/mb-orchestration.git
git clone https://github.com/MagnetBaron/teamclaude.git
```

GitHub Desktop: File → Clone repository → MagnetBaron → `mb-orchestration` and `teamclaude`.

Open **mb-orchestration** as the project/workspace. Codex reads `AGENTS.md`. Claude Code reads `CLAUDE.md`. Cursor reads the same files from the folder root.

## 1. Copy policy into other project folders (optional)

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
```

## 2. teamclaude (Claude seats)

Source of truth for the proxy: https://github.com/MagnetBaron/teamclaude  
(upstream is KarpelesLab/teamclaude; use the Magnet Baron fork for clones.)

1. `npm install -g @karpeleslab/teamclaude` or run from the local `teamclaude` clone
2. `teamclaude login` per seat (Max, premium team ×2, standard team)
3. Merge `teamclaude.routes.example.json` from this repo into `~/.config/teamclaude.json`
4. `teamclaude server` then `teamclaude run -- --model opus-4.8`
5. After plan downgrade: delete the Fable route

No four Claude desktop apps. CLI + proxy only after first device-auth.

## 3. Ordered adoption

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
