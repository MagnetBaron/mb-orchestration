# Install

## 0. Get the repos onto the machine

```bash
git clone https://github.com/MagnetBaron/mb-orchestration.git
git clone https://github.com/MagnetBaron/teamclaude.git
```

Open **mb-orchestration** as the workspace. Every CLI reads the shared per-run routing contract. Pass
its provider identity with `--intake-provider`, or choose a user profile. Resolver selects one effective
dispatcher and records fallback, authors, review scopes, and handoff gate.

## 1. Validate the setup first

```bash
cd mb-orchestration
python3 bin/doctor.py        # config integrity + prose hygiene
python3 bin/smoketest.py     # walk the whole path
python3 bin/detect-agents.py # which providers are live on THIS machine
python3 bin/model-registry.py inventory
```

`doctor` green means the registry is internally consistent; `smoketest` green means the routing,
metering, fallback, and role generation all work. Do this before wiring anything else.

## 2. Configure for THIS user (the portability layer)

Everything user-specific is in `config/` — edit these, not prose:

1. `config/subscriptions.json` — the plans you pay for. Fable grants live here (`grants.fable`).
2. `config/entrypoints.json` — entry surfaces, per-user profiles, and evidence-ranked fallback order.
   `--intake-provider` overrides a profile for one run; valid user selection wins while usable.
3. `config/handoff-policy.json` — keep ordinary artifact preauthorization and restricted classes fail-closed.
4. `config/connectors.json` — your MCP connectors, Shopify stores, analytics login, and Grok CLI role bindings.
5. `config/usage-windows.json` — set the anchors you know (Grok weekly weekday/time, Cursor billing day).
6. `python3 bin/doctor.py` — confirm no orphaned providers or drift.

## 3. teamclaude (Claude seats)

Source: https://github.com/KarpelesLab/teamclaude — multi-account Claude proxy with automatic
quota-based rotation (tracks per-model caps, so a seat out of one model still serves others). The
MagnetBaron fork adds the clone URL + `mb/` overlay.

1. `npm install -g @karpeleslab/teamclaude`
2. From the clone: `./mb/install-local.sh`
3. `teamclaude import` for the seat already in Claude Code, then `mb-teamclaude-login` once per additional seat (Max + 2 Team-premium + 2 Pro = five seats total)
4. `teamclaude service install` and `teamclaude alias --install`
5. `teamclaude run -- --model claude-opus-5`

Do not merge exclusive named routes. `mb/sync-plan.mjs` (LaunchAgent every 6h) blocks `*fable*` when no seat can serve it and unblocks it if a seat gains Fable again. Plan downgrades need no manual route edit — and `bin/detect-capability.py` cross-checks it. No four Claude desktop apps. Direct `claude` without teamclaude is not a working route.

## 4. Review D + Heat Map (Grok CLI agents)

Policy: `visual-qa.md` / `analytics-clarity.md`. Generate and install the named Grok profiles.
Daily handoff is a config-rendered prompt file through `bin/grok-agent.py`; render allowlist,
preview, and live-audit packets with `bin/connectors.py --render …`. Review D and Heat Map remain
parked until their browser/Clarity prerequisites are observed and role-tested. Delivery details:
`visual-qa-cli.md`.

## 5. Google MCP

Owner connects Search Console, Drive, and DataForSEO (or equivalent) on the providers listed in
`config/connectors.json` `mcp_connectors.*.available_on` (today Codex GPT + Claude/Opus). Grok is not
assumed to have these. Route per `mcp-routing.md`.

## 6. `/orca` command and skill (Claude Code · Codex · Cursor · native agent loaders)

One canonical file is distributed under `/orca` (preferred) and `/orchestrate` (compatibility alias) — **edit the canonical, never the copies**.

- Canonical (edit here): `.claude/commands/orchestrate.md`
- Claude Code — `~/.claude/commands/{orca,orchestrate}.md` plus discovered `~/.claude-*` profiles (symlinks)
- Codex — `~/.codex/prompts/{orca,orchestrate}.md` (real copies for loader compatibility)
- Cursor — `.cursor/commands/{orca,orchestrate}.md` (relative symlinks that travel with the repo)
- Native skill loaders — `~/.agents/skills/orca/SKILL.md` (real copy)

`sync-commands.sh` accepts `MB_ORCHESTRATION_HOME` only as a test/install-root override. An explicit
`CLAUDE_CONFIG_DIR` must be absolute. Automatic `~/.claude-*` discovery includes only directories
with `settings.json`; skipped directories are reported rather than silently treated as profiles.
GitHub forks set `ORCA_TRUSTED_ORIGIN` to their expected clone URL; common HTTPS, scp-style SSH, and
`ssh://` GitHub forms normalize to the same identity. Without that explicit override, only
`MagnetBaron/mb-orchestration` is trusted.

Provision or repair the symlinks on any machine:

```bash
./sync-commands.sh
./sync-commands.sh --check
```

The command resolves its control checkout from `ORCA_REPO`, defaulting to `~/git/mb-orchestration`; this prevents another local checkout from silently restoring retired policy. No-arg `/orca` prints the live seat map (`bin/usage-status.py`); with a task it classifies,
stamps depth (`bin/resolve-route.py`), and routes. **Only the effective per-run dispatcher assigns
seats** — any other host (Codex included) shows status and drafts a brief, then hands it to the
effective dispatcher.

If a pre-registry Codex wrapper auto-refreshes `/orca`, update its `ORCA_REPO` default to
`$HOME/git/mb-orchestration` or remove that refresh block before running the sync. Otherwise the
wrapper can restore a retired prompt on the next Codex launch; `./sync-commands.sh --check` detects
the resulting copy drift.

Because Codex prompts and the native skill are loader-compatible real copies, every edit to the
canonical command requires `./sync-commands.sh` followed by `./sync-commands.sh --check` before the
standing-config change lands.

## 7. Ordered adoption

1. `bin/doctor.py` + `bin/smoketest.py` green
2. `config/` filled for this user; `AGENTS.md` live
3. Brief schema enforced (`effort` and `skills` included)
4. Worktrees for parallel Grok jobs
5. Risk gate + `bin/resolve-route.py` for the review chain
6. teamclaude (login + plan-sync agent; no exclusive Fable route)
7. Grok CLI named-agent profiles + role-specific capability evidence (owner)
8. Google MCP on the providers `connectors.json` lists (owner)
9. Usage metering: anchors in `config/usage-windows.json`; read state with `bin/usage-status.py`
10. `EDGE-CASES.md` known to the dispatcher for outages

Prefer this repo’s thin files until context pressure forces a plugin.

## 8. Selective iOS, Flutter, Dart, Cloudflare, vault, and engineering skills

Install the pinned skills listed in `skills/registry.json`. For an existing
leaf-link installation, migrate the leaf playbooks behind the routers once:

```bash
python3 skills/sync.py --migrate-library
```

Then reconcile and verify with:

```bash
python3 skills/sync.py
python3 skills/sync.py --check
```

The sync keeps the 44 leaf playbooks in private non-discovery libraries and
links only the four routers into `~/.agents/skills`. Existing
Grok/Claude/Cursor implementation seats receive a router only on matching
briefs; it reads at most the one or two matching leaf playbooks. Generated
Codex role profiles directly scope iOS accessibility or Dart MCP tools without
placing those instructions or tool schemas in Dispatch. The skill tree does
not create a seat or grant tools.
