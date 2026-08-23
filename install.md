# Install

## 0. Get the repos onto the machine

```bash
git clone https://github.com/MagnetBaron/mb-orchestration.git
git clone https://github.com/MagnetBaron/teamclaude.git
```

GitHub Desktop: File → Clone repository → MagnetBaron → `mb-orchestration` and `teamclaude`.

Open **mb-orchestration** as the workspace. Codex reads `AGENTS.md`. Claude Code reads `CLAUDE.md`.

Then Codex follows [SETUP-BOTS.md](./SETUP-BOTS.md) — dispatch only.

## 1. Copy policy into other project folders (optional)

```bash
curl -fsSL https://raw.githubusercontent.com/MagnetBaron/mb-orchestration/main/AGENTS.md -o AGENTS.md
curl -fsSL https://raw.githubusercontent.com/MagnetBaron/mb-orchestration/main/CLAUDE.md -o CLAUDE.md
```

Optional global:

```bash
mkdir -p ~/.codex ~/.claude
cp AGENTS.md ~/.codex/AGENTS.md
cp CLAUDE.md ~/.claude/CLAUDE.md
```

## 2. teamclaude (Claude seats)

Source: https://github.com/MagnetBaron/teamclaude

1. `npm install -g @karpeleslab/teamclaude` or run from the local clone
2. `teamclaude login` per seat
3. Merge `teamclaude.routes.example.json` into `~/.config/teamclaude.json`
4. `teamclaude server` then `teamclaude run -- --model opus-4.8`
5. After plan downgrade: delete the Fable route

No four Claude desktop apps.

## 3. Review D (Website Visual QA)

Policy: [visual-qa.md](./visual-qa.md). Owner creates the named Bot and Slack channel once. Daily handoff is Slack, not Grok Bot.app on the Mini, not `grok` CLI.

## 4. Ordered adoption

1. Buckets classified — Grok abundant; Claude+Sol scarce; Codex Terra/Luna dispatch; Cursor $400 last
2. AGENTS.md live
3. Brief schema enforced
4. Worktrees for parallel Grok jobs
5. Risk gate + reviewer order
6. teamclaude routes
7. Slack `#visual-qa` + Website Visual QA Bot (owner)
8. Usage ledger (manual % in backlog header only)

## 5. Optional heavy harnesses

Prefer this repo’s thin files until context pressure forces a plugin.
