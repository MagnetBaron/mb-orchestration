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

Runtime is the npm package (self-updates). The org fork holds the clone URL plus `mb/` overlay.

1. `npm install -g @karpeleslab/teamclaude`
2. From the clone: `./mb/install-local.sh`
3. `teamclaude import` for the seat already in Claude Code, then `mb-teamclaude-login` once per additional seat
4. `teamclaude service install` and `teamclaude alias --install`
5. `teamclaude run -- --model opus-4.8`

Do not merge exclusive named routes. `mb/sync-plan.mjs` (LaunchAgent every 6h) blocks `*fable*` when no seat can serve it and unblocks it if a seat gains Fable again. Plan downgrades need no manual route edit.

No four Claude desktop apps.

## 3. Review D (Website Visual QA)

Policy: [visual-qa.md](./visual-qa.md). Owner creates the named Bot and Slack channel once. Daily handoff is Slack, not Grok Bot.app on the Mini, not `grok` CLI. Delivery: [visual-qa-slack.md](./visual-qa-slack.md).

## 4. Google MCP (for mcp-routing)

Owner connects Search Console, Drive, and DataForSEO (or equivalent) on **Codex GPT** and **Claude/Opus** seats so bulk analytics and product research briefs can run. Grok is not assumed to have these connectors.

## 5. Ordered adoption

1. Buckets classified — Grok abundant; GPT Terra for Google MCP volume; Claude+Sol scarce; Codex Terra/Luna dispatch; Cursor $400 last
2. AGENTS.md live
3. Brief schema enforced (`effort` included)
4. Worktrees for parallel Grok jobs
5. Risk gate + reviewer order (Fable if present → Sol → Opus)
6. teamclaude (login + plan-sync agent; no exclusive Fable route)
7. Slack `#visual-qa` + Website Visual QA Bot (owner)
8. Google MCP on Codex/Claude (owner)
9. Usage ledger (manual % in backlog header only)
10. EDGE-CASES.md known to dispatcher for outages

## 6. Optional heavy harnesses

Prefer this repo’s thin files until context pressure forces a plugin.
