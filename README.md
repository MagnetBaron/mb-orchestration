# mb-orchestration

**Policy + tooling repo for Magnet Baron multi-CLI work.**

One dispatcher assigns seats; abundant volume implements; scarce judgment reviews; a metered
independent family backs up review. Who fills each role is **config, not prose** — a new user ports
the system by editing `config/`, running `bin/doctor.py`, and getting the same routing with no policy
edits.

**Codex dispatches. Grok implements. GPT Terra runs Google-MCP volume. Sol/Opus/Fable judge. Website Visual QA via Slack. Cursor Other Models $400 is last. Review E (independent open-weight, unwired) is the review backstop.**

## Layout

| Path | What |
|------|------|
| `AGENTS.md` | Day-to-day contract — **every** agent session |
| `CLAUDE.md` | Claude Code loader (pins Opus 4.8, forbids Opus 5) |
| `DOCTRINE.md` | Design doctrine — load when designing/debugging the system |
| `EDGE-CASES.md` | Outages, ambiguity, partial work, owner unreachable |
| `USER-GUIDE.md` | **Humans only** — plan choice, AI-family-per-task, subscription calculator. **Never loaded into agent context.** |
| `config/` | Single source of truth (below) |
| `bin/` | Scripts that read config and never guess (below) |
| domain files | `mcp-routing.md` · `sol-usage.md` · `cursor-usage.md` · `fireworks-usage.md` · `usage-metering.md` · `visual-qa.md` · `visual-qa-slack.md` · `grokbot-connection.md` · `analytics-clarity.md` · `luna-close-loop.md` |
| `install.md` · `SETUP-BOTS.md` · `FUTURE.md` | First wire-up, worker-machine handoff, deferred multi-Mini |

### `config/` — edit these, not prose

| File | Holds |
|------|-------|
| `providers.json` | Agents/providers, capability levels, families, detection, model pins, forbidden models |
| `subscriptions.json` | The plans you pay for — **the one file a new user edits** |
| `connectors.json` | Live MCP/analytics/store/Slack bindings (no stale IDs in prose) |
| `entrypoints.json` | Entry surfaces (user choice) + the one dispatcher |
| `usage-windows.json` | Reset anchors + soft caps per seat |
| `review-depth.json` | Review floor by task class (machine source; DOCTRINE explains) |
| `monitoring.json` | Retention (default 1yr), cost policy, reserve defaults, data sources |
| `roles.json` | Role definitions that load inside seats |
| `orchestration.schema.json` | Published JSON-Schema contract (validated by doctor) |
| `examples/{solo-pro,two-sub,agency}/` | Per-user layers proving 1→N scale — `MB_CONFIG_DIR=config/examples/<x> python3 bin/doctor.py` |

### `bin/` — scripts

| Script | Does |
|--------|------|
| `usage-status.py` | Script-computed seat reset/limit status; tri-state tier (available/reserve/spent) |
| `resolve-route.py` | **Deterministic router**: class + live state → seat + review chain; never-strand, minimize-$, no mid-turn swaps |
| `drain-plan.py` | Use-it-or-lose-it drain order + reserve sizing (maximize subscription value) |
| `doctor.py` | Validate the whole setup (schema + referential integrity + prose hygiene) |
| `detect-agents.py` | Auto-detect installed CLI agents; discover/register unregistered ones (modular) |
| `detect-capability.py` | Bidirectional (downgrade+upgrade) capability detection; disable-auto-downgrade levers |
| `usage-record.py` | Gather usage history (retained, default 1yr); learn reset windows; prune |
| `dashboard.py` | Self-contained HTML telemetry dashboard (usage, drain order, health score) |
| `subscription-calculator.py` | Recommend a plan from habits or `--from-history` utilization |
| `generate-roles.py` | Render host-native Claude/Grok agent files + Codex TOML from the registry |
| `connectors.py` | Render paste-ready bot allowlists/tickets from `connectors.json` |
| `record-429.sh` | Record a real 429 into the ledger (never a timeout) |
| `mborch.py` · `routing.py` | Shared: layered config resolution (`MB_CONFIG_DIR`) · drain/allocation scoring |
| `test_generate.py` | Unit tests for the role registry |

## Quick start

```bash
git clone https://github.com/MagnetBaron/mb-orchestration.git
git clone https://github.com/MagnetBaron/teamclaude.git   # multi-Claude-seat rotation
cd mb-orchestration
python3 bin/doctor.py        # validate config integrity + prose hygiene
python3 bin/smoketest.py     # walk the whole path (13 checks)
python3 bin/usage-status.py  # live seat map
./sync-commands.sh           # distribute /orchestrate to Claude Code, Codex, Cursor
```

Port to a different user: edit `config/subscriptions.json` (your plans), `config/entrypoints.json`
(your dispatcher/surfaces), `config/connectors.json` (your MCP/stores), set anchors in
`config/usage-windows.json`, then `python3 bin/doctor.py`. See `install.md` and `USER-GUIDE.md`.

Daily: the dispatcher is the only entry point that assigns seats (default Codex; configurable). When something breaks, agents read `EDGE-CASES.md`.
