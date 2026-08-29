---
description: Dispatch a task through the Magnet Baron multi-CLI orchestration — classify, route to the right seat, review, refill.
argument-hint: "[task] (omit to show the live seat map)"
---

You are running the Magnet Baron orchestration **dispatch policy**. This command is shared verbatim across Claude Code, Codex, and Cursor — the contract lives in the repo. **Exactly one dispatcher assigns seats** — the surface the user assigned in `config/entrypoints.json` `dispatcher.provider` (here the Claude orchestration surface, `opus-5`; configurable, not a fixed identity — dispatch is user-assigned). It classifies, briefs, assigns, gates, refills, and **fans work OUT to the orchestration tree** — sub-agents (other Claude profiles/seats) plus the specialist seats — and **preserves its own account by dispatching, not implementing** (read-only legwork via a sub-agent is fine). Where a request is TYPED is the user's choice; who ASSIGNS is config-bound. What you may do depends on your entry surface:

- **Dispatcher surface** (`can_dispatch: true` — the assigned dispatcher) → full dispatch: classify, stamp review, brief, assign the seat, gate, refill, and fan work out to sub-agents + seats. Delegate every implement/review job; never run it on the dispatcher's own account.
- **Any other surface** (Codex / Cursor / phone) → run the no-arg status, and classify + stamp + draft a brief, then **hand the brief to the assigned dispatcher**. In this setup Codex is a worker/review seat (GPT Terra MCP volume + Sol review) — dispatch-capable, but not the assigned dispatcher. Do not assign other seats and do not implement work that is not already your own seat's job. Never re-home dispatch onto a surface the user did not assign.

Contract: read `AGENTS.md`; for routing, `config/review-depth.json` (machine floor) with `DOCTRINE.md` §Review depth (the human explanation). Live model/route identity is `config/model-registry.json` via `bin/model-registry.py` and `bin/resolve-route.py`. Domain files load by domain: `mcp-routing.md` · `sol-usage.md` · `cursor-usage.md` · `fireworks-usage.md` · `usage-metering.md` · `visual-qa.md` · `grokbot-connection.md` · `analytics-clarity.md` · `skills/README.md` · `skills/registry.json` · `EDGE-CASES.md`.

TASK: $ARGUMENTS
*(If the line above shows the literal token `$ARGUMENTS`, the task is the message the user sent with this command. If no task was given, show status.)*

## If no TASK
Run `python3 bin/usage-status.py`, print the seat map (live / spent / next reset) and the backlog (per `EDGE-CASES.md`, if one is configured), ask what to dispatch, then stop.

## Otherwise (the assigned dispatcher dispatches + fans to the tree; a non-dispatcher surface drafts + hands over)
1. **Classify** by task class. Run the router instead of eyeballing prose:
   `python3 bin/resolve-route.py --class <class> --scale routine|elevated [--risk auth,money,PII,prod,irreversible,multi-service,grok-conflict,flaky-tests,secrets,untrusted-shell] [--implement] [--pixels]`
   It returns the depth, the concrete live review chain (or park reason), the implement seat, and the gates. Class from touched paths/resources, not the brief's claim; ambiguity rounds up. Only `live_verified` registry routes may resolve; a catalog entry or announcement is not a usable route.
2. **Stamp `review:`** at the floor the router reports (none · self-check · single-frontier · cross-family). The `AGENTS.md` risk gate only raises it. `user said ship` = land, not spend a frontier.
3. **Pick the implement seat** per `AGENTS.md` §Seats / the router's `--implement` plan: **Grok Build** by default · **GPT Terra** for Google-MCP bulk · **Sol/Opus** for MCP *judgment* only (`mcp-routing.md`). Storefront pixels → **Grok Build implements, then** a Review D Slack ticket once a visitor preview URL exists (`visual-qa.md`; render the ticket with `bin/connectors.py`). Review D and Heat Map are review/input seats — **never implementers**. Legwork-or-stop: never dump volume on Sol/Opus/Cursor $.
4. **Select only the router.** Dart, Flutter, or native iOS accessibility implementation gets `skills: [mobile-dev-router]`; explicit Cloudflare platform work gets `cloudflare-dev-router`; Obsidian vault/Bases/Canvas/CLI work gets `knowledge-vault-router`; React specialty, generic MCP builder, or measured web-performance work gets `engineering-dev-router`. Dispatch does not inspect the private leaf descriptions or bodies. A dedicated native iOS accessibility review may directly select only `ios-accessibility`. Unrelated work gets `skills: []`.
5. **Brief** (required, paths only — no pasted dumps): objective · must_read · must_not_touch · output_path · done_when · effort · skills (+attack_angle for reviews). A matching brief includes `~/.agents/skills/<router>/SKILL.md`; its receiver selects one primary leaf plus at most one distinct validation leaf from the private library. A direct accessibility review includes `~/.codex/skill-library/mobile/ios-accessibility/SKILL.md`. Missing field → don't dispatch; ask the owner.
6. **Route reviews by the router (which reads `bin/usage-status.py` and `config/model-registry.json`), not guesswork.** Order: **Opus 5 → Codex Sol → Review E (if wired) → stop** (Fable is OUT of the gating order — rare long-horizon/architecture escalation, same Anthropic family as Opus). Cross-family = one pass each from two families (the Anthropic gate is Opus 5). Exhaustion / Review E / quota-vs-outage rules live in `AGENTS.md` + `fireworks-usage.md`.
7. **Land gates + refill:** one green test bound to the commit tip · one landing lock for main · Review D on pixels · owner gates for publish/send/spend/auth/authority-expansion · `bin/doctor.py` green before landing a `standing-config`/`config/` change. On completion, claim the next brief or state why idle — never invent makework.

Finish with a one-line status: seat used (or "briefed → dispatcher") · review verdict(s) · landed/parked · next.
