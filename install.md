# Install

## 0. Get the repos onto the machine

```bash
git clone https://github.com/MagnetBaron/mb-orchestration.git
git clone https://github.com/MagnetBaron/teamclaude.git
```

Open **mb-orchestration** as the workspace. Claude Code reads `CLAUDE.md` and is the dispatcher in this
setup (the user-assigned Claude orchestration surface); Codex reads `AGENTS.md` as a worker/review seat.
Then follow `SETUP-BOTS.md` for the machine wire-up — the dispatcher fans the setup work out to the
worker seats.

## 1. Validate the setup first

```bash
cd mb-orchestration
python3 bin/doctor.py        # config integrity + prose hygiene
python3 bin/smoketest.py     # walk the whole path (must be 13/13)
python3 bin/detect-agents.py # which providers are live on THIS machine
```

`doctor` green means the registry is internally consistent; `smoketest` green means the routing,
metering, fallback, and role generation all work. Do this before wiring anything else.

## 2. Configure for THIS user (the portability layer)

Everything user-specific is in `config/` — edit these, not prose:

1. `config/subscriptions.json` — the plans you pay for. Fable grants live here (`grants.fable`).
2. `config/entrypoints.json` — your entry surfaces and the one dispatcher (`dispatcher.provider`).
   The dispatcher is user-assigned (the Claude orchestration surface in this reference setup); point
   `dispatcher.provider` at any dispatch-capable provider you own and flip that surface's `can_dispatch`.
3. `config/connectors.json` — your MCP connectors, Shopify stores, analytics login, Slack channel.
4. `config/usage-windows.json` — set the anchors you know (Grok weekly weekday/time, Cursor billing day).
5. `python3 bin/doctor.py` — confirm no orphaned providers or drift.

## 3. teamclaude (Claude seats)

Source: https://github.com/KarpelesLab/teamclaude — multi-account Claude proxy with automatic
quota-based rotation (tracks per-model caps, so a seat out of one model still serves others). The
MagnetBaron fork adds the clone URL + `mb/` overlay.

1. `npm install -g @karpeleslab/teamclaude`
2. From the clone: `./mb/install-local.sh`
3. `teamclaude import` for the seat already in Claude Code, then `mb-teamclaude-login` once per additional seat (Max + 2 Team-premium + 2 Pro = five seats total)
4. `teamclaude service install` and `teamclaude alias --install`
5. `teamclaude run -- --model opus-4.8`

Do not merge exclusive named routes. `mb/sync-plan.mjs` (LaunchAgent every 6h) blocks `*fable*` when no seat can serve it and unblocks it if a seat gains Fable again. Plan downgrades need no manual route edit — and `bin/detect-capability.py` cross-checks it. No four Claude desktop apps.

## 4. Review D + Heat Map (Grok Bots)

Policy: `visual-qa.md` / `analytics-clarity.md`. Owner creates the named bots and the one public
`#visual-qa` channel once (binding in `config/connectors.json`). Daily handoff is Slack. Render the
paste-ready allowlist/ticket with `bin/connectors.py --render …`. Delivery details: `visual-qa-slack.md`.

## 5. Google MCP

Owner connects Search Console, Drive, and DataForSEO (or equivalent) on the providers listed in
`config/connectors.json` `mcp_connectors.*.available_on` (today Codex GPT + Claude/Opus). Grok is not
assumed to have these. Route per `mcp-routing.md`.

## 6. Slash command `/orchestrate` (Claude Code · Codex · Cursor)

One canonical file, symlinked into each CLI's command dir — **edit the canonical, never the copies**.

- Canonical (edit here): `.claude/commands/orchestrate.md`
- Claude Code — repo `.claude/commands/` (+ `~/.claude/commands/` global). `/orchestrate <task>`
- Codex — `~/.codex/prompts/orchestrate.md`. `/orchestrate <task>`
- Cursor — `.cursor/commands/orchestrate.md` (relative symlink; travels with the repo). `/orchestrate <task>`

Provision or repair the symlinks on any machine:

```bash
./sync-commands.sh
```

No-arg `/orchestrate` prints the live seat map (`bin/usage-status.py`); with a task it classifies,
stamps depth (`bin/resolve-route.py`), and routes. **Only the assigned dispatcher surface assigns
seats** — any other host (Codex included) shows status and drafts a brief, then hands it to the
assigned dispatcher.

## 7. Ordered adoption

1. `bin/doctor.py` + `bin/smoketest.py` green
2. `config/` filled for this user; `AGENTS.md` live
3. Brief schema enforced (`effort` included)
4. Worktrees for parallel Grok jobs
5. Risk gate + `bin/resolve-route.py` for the review chain
6. teamclaude (login + plan-sync agent; no exclusive Fable route)
7. Slack `#visual-qa` + Website Visual QA / Heat Map bots (owner)
8. Google MCP on the providers `connectors.json` lists (owner)
9. Usage metering: anchors in `config/usage-windows.json`; read state with `bin/usage-status.py`
10. `EDGE-CASES.md` known to the dispatcher for outages
