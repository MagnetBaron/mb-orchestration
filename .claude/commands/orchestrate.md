---
description: Dispatch a task through the Magnet Baron multi-CLI orchestration — classify, route to the right seat, review, refill.
argument-hint: "[task] (omit to show the live seat map)"
---

You are running the Magnet Baron orchestration **dispatch policy**. This command is shared verbatim across Claude Code, Codex, and Cursor — the contract lives in the repo. **Entry point is always Codex** (`AGENTS.md`, `DOCTRINE.md` §Roles): only Codex assigns seats and drives implement-via-others. What you may do depends on which host you are:

- **Codex** → full dispatch: classify, stamp review, brief, assign the seat, gate, refill.
- **Claude Code / Cursor (not Codex)** → run the no-arg status, and classify + stamp + draft a brief, then **hand the brief to Codex**. Do not assign other seats and do not implement work that is not already your own seat's job. Never re-home dispatch onto an IDE or review seat.

Contract: read `~/git/mb-orchestration/AGENTS.md`; when routing review, `~/git/mb-orchestration/DOCTRINE.md` §Review depth (the single-source class map — do not re-summarize it). Domain files (load by domain, under `~/git/mb-orchestration/`): `mcp-routing.md` · `sol-usage.md` · `cursor-usage.md` · `fireworks-usage.md` · `usage-metering.md` · `visual-qa.md` · `grokbot-connection.md` · `analytics-clarity.md` · `skills/README.md` · `skills/registry.json` · `EDGE-CASES.md`.

TASK: $ARGUMENTS
*(If the line above shows the literal token `$ARGUMENTS`, the task is the message the user sent with this command. If no task was given, show status.)*

## If no TASK
Run `python3 ~/git/mb-orchestration/usage-status.py`, print the seat map (live / spent / next reset) and the backlog (per `EDGE-CASES.md`, if one is configured), ask what to dispatch, then stop.

## Otherwise (Codex dispatches; a non-Codex host drafts + hands to Codex)
1. **Classify** by task class using the `DOCTRINE.md` §Review depth **table rows** (that section is the single source — read it; do not classify against a taxonomy re-listed here). Class from touched paths/resources, not the brief's claim; ambiguity rounds up.
2. **Stamp `review:`** at the floor from that table (none · self-check · single-frontier · cross-family). The `AGENTS.md` risk gate only raises it (auth/money/PII/prod/irreversible · multi-service · Grok-conflict/flaky). `user said ship` = land, not spend a frontier.
3. **Pick the implement seat** per `AGENTS.md` §Seats: **Grok Build** by default · **GPT Terra** for Google-MCP bulk · **Sol/Opus** for MCP *judgment* only (`mcp-routing.md`). Storefront pixels → **Grok Build implements, then** a Review D Slack ticket once a visitor preview URL exists (`visual-qa.md`). Review D (Website Visual QA) and Heat Map (Clarity, `analytics-clarity.md`) are review/input seats — **never implementers**. Legwork-or-stop: never dump volume on Sol/Opus/Cursor $.
4. **Select skills without loading them.** For Dart, Flutter, or iOS-accessibility work, inspect only each installed skill's `name` and `description` frontmatter plus `skills/registry.json`. Select the smallest matching set. Dispatch never invokes or reads a specialized `SKILL.md` body. Unrelated work gets `skills: []`.
5. **Brief** (required, paths only — no pasted dumps): objective · must_read · must_not_touch · output_path · done_when · effort · skills (+attack_angle for reviews). Every selected skill name must have its exact `~/.agents/skills/<name>/SKILL.md` in `must_read`. Missing field → don't dispatch; ask the owner.
6. **Route reviews by `usage-status`, not guesswork.** Order: **Fable (if present) → Codex Sol → Opus 4.8 → Review E (Fireworks, if wired) → stop.** Cross-family = one pass each from two families (Fable + 4.8 are one family). Exhaustion, Review E engagement, and quota-vs-outage rules live in `AGENTS.md` §Risk gate + `fireworks-usage.md` — follow them there; do not re-summarize.
7. **Land gates + refill:** one green test bound to the commit tip · one landing lock for main · Review D on pixels · owner gates for publish/send/spend/auth/authority-expansion. On completion, claim the next brief or state why idle — never invent makework.

Finish with a one-line status: seat used (or "briefed → Codex") · review verdict(s) · landed/parked · next.
