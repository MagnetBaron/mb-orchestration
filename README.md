# mb-orchestration

**Policy + tooling repo for Magnet Baron multi-CLI work.**

One dispatcher per run assigns seats; abundant volume implements; scarce judgment reviews; a metered
independent family backs up review. Who fills each role is **config, not prose** — a new user ports
the system by editing `config/`, running `bin/doctor.py`, and getting the same routing with no policy
edits.

**Requested intake dispatches when usable; recorded exhaustion activates a configured fallback.** Sol, Opus 5, Opus 4.8, Fable, Terra, Luna, and Grok are tested dispatch targets. Reviewer selection flexes around dispatcher and authors. Grok remains preferred implementation; Terra runs Google-MCP volume; Opus 5 + Sol are the normal cross-family gate. Ordinary repo handoffs are preauthorized; restricted data parks.

| Repo | URL | Opens as |
|------|-----|----------|
| **This policy** | https://github.com/MagnetBaron/mb-orchestration | Workspace — `AGENTS.md` + `CLAUDE.md` |
| **teamclaude fork** | https://github.com/MagnetBaron/teamclaude | Multi-seat Claude proxy source |
| **QA idle handoff** | https://github.com/MagnetBaron/qa-idle-handoff (private) | Exclusive idle-mini QA workers |

## Honest limits (what this does *not* do yet)

Two boundaries an evaluating owner should know up front — both are current-by-design, not oversights:

- **Cross-family review autonomy needs ≥2 review families.** The strongest safety gate is one pass from each of two *different* families (Anthropic + OpenAI, or a native family + the independent Review E). With fewer than two live families — a plan downgrade, or a solo/one-family setup — **risk-class work (money, auth, PII, secrets) PARKS pending a human** instead of auto-shipping: the discipline is unchanged, the routing just collapses toward a single seat and hands the call to the owner (`EDGE-CASES.md`).
- **Unattended land-to-prod is a current non-goal.** The executor is gated — `bin/run-brief.py` is **dry-run only** (it prints the plan and shells nothing, and fails closed without an explicit run); landing, publish, send, and spend stay behind owner gates. Overnight autonomous land-to-prod without human approval is an explicit non-goal (`DOCTRINE.md` §Explicit non-goals).

## Layout

| Path | What |
|------|------|
| `AGENTS.md` | Day-to-day contract — **every** agent session |
| `CLAUDE.md` | Claude Code loader (Opus 5 is the Anthropic gate; Opus 4.8 is a time-bounded fallback) |
| `DOCTRINE.md` | Design doctrine — load when designing/debugging the system |
| `EDGE-CASES.md` | Outages, ambiguity, partial work, owner unreachable |
| `USER-GUIDE.md` | **Humans only** — plan choice, AI-family-per-task, subscription calculator. **Never loaded into agent context.** |
| `config/` | Single source of truth (below) |
| `bin/` | Scripts that read config and never guess (below) |
| `skills/` | Progressive skill routers (four public gateways; 44 private leaves) |
| `model-evals/` | Synthetic role-eval cases and admin runbook |
| `docs/` | Evidence-backed audits (not operational) |
| domain files | `mcp-routing.md` · `sol-usage.md` · `cursor-usage.md` · `fireworks-usage.md` · `usage-metering.md` · `visual-qa.md` · `visual-qa-slack.md` · `grokbot-connection.md` · `analytics-clarity.md` · `marketplace-intelligence.md` · `luna-close-loop.md` · `qa-idle-handoff.md` |
| `install.md` · `SETUP-BOTS.md` · `FUTURE.md` | First wire-up, worker-machine handoff, deferred multi-Mini |

### `config/` — edit these, not prose

| File | Holds |
|------|-------|
| `providers.json` | Agents/providers, capability levels, families, detection, model pins |
| `model-registry.json` | Canonical model/route/ranking catalog (identity, lifecycle, route state, evidence, per-role quality vs selection) |
| `subscriptions.json` | The plans you pay for — **the one file a new user edits** |
| `connectors.json` | Vetted MCP/analytics/store/Slack authorization ceiling and public bindings; live proof comes from the runtime inventory |
| `integration-adapters.json` | Safe runtime-manifest adapters, aliases, session-only Grok Bot/Cursor capability map, TTL, and explicit provider-to-runtime map; connector config remains the authorization ceiling |
| `entrypoints.json` | Entry surfaces, user profiles, per-run dispatcher fallback order |
| `handoff-policy.json` | Ordinary preauthorization and extensible restricted classes; `bin/handoff_policy.py` enforces the non-removable minimum and restricted-wins runtime behavior |
| `usage-windows.json` | Reset anchors + soft caps per seat |
| `review-depth.json` | Review floor by task class (machine source; DOCTRINE explains) |
| `monitoring.json` | Retention (default 1yr), cost policy, reserve defaults, data sources, observability |
| `roles.json` | Role definitions that load inside seats (not a model catalog) |
| `skills.json` | Registry that vets which in-repo plugin skills (`plugins/magnet-baron-skills/`, via `.claude-plugin/marketplace.json`) a role may bind — kind, required capability, hosts; fail-closed in `generate-roles.py` |
| `orchestration.schema.json` | Published JSON-Schema contract (validated by doctor) |
| `examples/{solo-pro,two-sub,agency}/` | Per-user layers proving 1→N scale — `MB_CONFIG_DIR=config/examples/<x> python3 bin/doctor.py` |

### `bin/` — scripts

| Script | Does |
|--------|------|
| `usage-status.py` | Script-computed seat reset/limit status; tri-state tier (available/reserve/spent) |
| `resolve-route.py` | **Deterministic router**: class + live state + registry → seat + review chain; never-strand, minimize-$, no mid-turn swaps |
| `model-registry.py` | Validate the model catalog; inventory; fail-closed role resolution; generate `generated/model-matrix.md` |
| `model-eval.py` | Score normalized JSONL eval receipts (correctness + token efficiency; latency recorded, weight 0) |
| `drain-plan.py` | Use-it-or-lose-it drain order + reserve sizing (maximize subscription value) |
| `doctor.py` | Validate the whole setup (schema + referential integrity + prose hygiene) |
| `detect-agents.py` | Auto-detect installed CLI agents; discover/register unregistered ones (modular) |
| `detect-capability.py` | Bidirectional (downgrade+upgrade) capability detection; disable-auto-downgrade levers |
| `usage-record.py` | Gather usage history (retained, default 1yr); learn reset windows; prune |
| `observe.py` | Append-only routing-quality log + analysis (privacy-safe; never grants authority) |
| `dashboard.py` | Self-contained HTML telemetry dashboard (usage, drain order, health score) |
| `subscription-calculator.py` | Recommend a plan from habits or `--from-history` utilization |
| `generate-roles.py` | Render host-native Claude/Grok agent files + Codex TOML from the registry |
| `connectors.py` | Render paste-ready bot allowlists/tickets from `connectors.json` |
| `detect-integrations.py` | Refresh/check the per-runtime plugin/MCP/app inventory; atomic cache under `$MB_DATA_DIR`, with process-only session overlays |
| `record-429.sh` | Record a real 429 into the ledger (never a timeout) |
| `mborch.py` · `routing.py` | Shared: layered config resolution (`MB_CONFIG_DIR`) · drain/allocation scoring |
| `test_generate.py` | Unit tests for the role registry |
| `test_model_registry.py` | Unit tests for fail-closed routing, independence, stale evidence, receipt scoring |
| `test_observability.py` | Unit tests for the event schema, redaction, concurrent append, and analysis honesty |

## Quick start

```bash
git clone https://github.com/MagnetBaron/mb-orchestration.git
git clone https://github.com/MagnetBaron/teamclaude.git   # multi-Claude-seat rotation
# private — after GitHub auth:
git clone https://github.com/MagnetBaron/qa-idle-handoff.git
cd mb-orchestration
python3 bin/doctor.py        # validate config integrity + prose hygiene
python3 bin/smoketest.py     # walk the whole path
python3 bin/usage-status.py  # live seat map
./sync-commands.sh           # distribute /orca (+ /orchestrate alias) to every host
```

Port to a different user: edit `config/subscriptions.json` (your plans), `config/entrypoints.json`
(your profiles/surfaces/fallbacks), `config/connectors.json` (your MCP/stores), set anchors in
`config/usage-windows.json`, then `python3 bin/doctor.py`. See `install.md` and `USER-GUIDE.md`.

Daily: invoke `/orca` (or the identical `/orchestrate` compatibility alias), then pass the intake provider or profile. Resolver records exactly one effective dispatcher, any fallback, authors, review scope, and handoff gate. Routing-quality telemetry is append-only in `data/orchestration-events.jsonl` (gitignored); analyze with `python3 bin/observe.py report`. It never logs task bodies and never changes a routing decision. When something breaks, agents read `EDGE-CASES.md`.

Before capability-sensitive routing, refresh safe local state with
`python3 bin/detect-integrations.py --refresh`. A dispatcher that can enumerate its current
callable tools passes a one-runtime overlay with `resolve-route.py --integration-session <file>`
(or `-` for stdin). The overlay is process-scoped and never cached. Suggested/installable,
installed, enabled, configured, blocked/auth-health, and current-session callable states stay
distinct. Unknown, stale, disabled, removed, malformed, or unregistered access never routes.

Website Visual QA has two config-derived Slack routines: visitor-preview review and exact-trigger,
read-only live-storefront audit. Render them with `bin/connectors.py --render visual-qa-ticket
<store>` and `bin/connectors.py --render visual-qa-live-ticket <store>`. The live mode observes only
an exact configured public host and cannot log in, add to cart, submit, purchase, publish, or mutate.
See `visual-qa.md` and `visual-qa-slack.md`; do not replace the two narrow event filters with a broad
listener.
