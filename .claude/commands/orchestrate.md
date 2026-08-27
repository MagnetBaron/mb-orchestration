---
description: Dispatch a task through the Magnet Baron multi-CLI orchestration — classify, route to the right seat, review, refill.
argument-hint: "[task] (omit to show the live seat map)"
---

You are running the Magnet Baron orchestration **dispatch policy**. This command is shared verbatim across Claude Code, Codex, and Cursor — the contract lives in the repo. **One dispatcher assigns seats** (`config/entrypoints.json` `dispatcher.provider`; default Codex). Where a request is TYPED is the user's choice; who ASSIGNS is config-bound. What you may do depends on your entry surface:

- **Dispatcher surface** (`can_dispatch: true`, default Codex) → full dispatch: classify, stamp review, brief, assign the seat, gate, refill.
- **Any other surface** (Claude Code / Cursor / phone) → run the no-arg status, and classify + stamp + draft a brief, then **hand the brief to the dispatcher**. Do not assign other seats and do not implement work that is not already your own seat's job. Never re-home dispatch onto an IDE or review seat.

Contract: read `AGENTS.md`; for routing, `config/review-depth.json` (machine floor) with `DOCTRINE.md` §Review depth (the human explanation). Domain files load by domain: `mcp-routing.md` · `sol-usage.md` · `cursor-usage.md` · `fireworks-usage.md` · `usage-metering.md` · `visual-qa.md` · `grokbot-connection.md` · `analytics-clarity.md` · `EDGE-CASES.md`.

TASK: $ARGUMENTS
*(If the line above shows the literal token `$ARGUMENTS`, the task is the message the user sent with this command. If no task was given, show status.)*

## If no TASK
Run `python3 bin/usage-status.py`, print the seat map (live / spent / next reset) and the backlog (per `EDGE-CASES.md`, if one is configured), ask what to dispatch, then stop.

## Otherwise (the dispatcher dispatches; a non-dispatcher surface drafts + hands over)
1. **Classify** by task class. Run the router instead of eyeballing prose:
   `python3 bin/resolve-route.py --class <class> --scale routine|elevated [--risk auth,money,PII,prod,irreversible,multi-service,grok-conflict,flaky-tests,secrets,untrusted-shell] [--implement] [--pixels]`
   It returns the depth, the concrete live review chain (or park reason), the implement seat, and the gates. Class from touched paths/resources, not the brief's claim; ambiguity rounds up.
2. **Stamp `review:`** at the floor the router reports (none · self-check · single-frontier · cross-family). The `AGENTS.md` risk gate only raises it. `user said ship` = land, not spend a frontier.
3. **Pick the implement seat** per `AGENTS.md` §Seats / the router's `--implement` plan: **Grok Build** by default · **GPT Terra** for Google-MCP bulk · **Sol/Opus** for MCP *judgment* only (`mcp-routing.md`). Storefront pixels → **Grok Build implements, then** a Review D Slack ticket once a visitor preview URL exists (`visual-qa.md`; render the ticket with `bin/connectors.py`). Review D and Heat Map are review/input seats — **never implementers**. Legwork-or-stop: never dump volume on Sol/Opus/Cursor $.
4. **Brief** (required, paths only — no pasted dumps): objective · must_read · must_not_touch · output_path · done_when · effort (+attack_angle for reviews). Missing field → don't dispatch; ask the owner.
5. **Route reviews by the router (which reads `bin/usage-status.py`), not guesswork.** Order: **Opus 4.8 → Codex Sol → Review E (if wired) → stop** (Fable is OUT of the gating order — owner ruling; architecture only). Cross-family = one pass each from two families (the Anthropic gate is Opus 4.8). Exhaustion / Review E / quota-vs-outage rules live in `AGENTS.md` + `fireworks-usage.md`.
6. **Land gates + refill:** one green test bound to the commit tip · one landing lock for main · Review D on pixels · owner gates for publish/send/spend/auth/authority-expansion · `bin/doctor.py` green before landing a `standing-config`/`config/` change. On completion, claim the next brief or state why idle — never invent makework.

Finish with a one-line status: seat used (or "briefed → dispatcher") · review verdict(s) · landed/parked · next.
