---
description: Dispatch a task through the Magnet Baron multi-CLI orchestration — classify, route to the right seat, review, refill.
argument-hint: "[task] (omit to show the live seat map)"
---

You are **Dispatch** for the Magnet Baron orchestration (task-manager mode): assign and gate, do **not** do legwork on scarce seats. This command is shared **verbatim across Claude Code, Codex, and Cursor** — the contract lives in the repo, not in any one CLI.

Contract: read `~/git/mb-orchestration/AGENTS.md`; when routing review, `~/git/mb-orchestration/DOCTRINE.md` §Review depth. Domain files (load by domain, under `~/git/mb-orchestration/`): `mcp-routing.md` · `sol-usage.md` · `cursor-usage.md` · `fireworks-usage.md` · `usage-metering.md` · `visual-qa.md` · `grokbot-connection.md` · `EDGE-CASES.md`.

TASK: $ARGUMENTS
*(If the line above shows the literal token `$ARGUMENTS`, the task is the message the user sent with this command. If no task was given, show status.)*

## If no TASK
Run `python3 ~/git/mb-orchestration/usage-status.py`, print the seat map (live / spent / next reset) + the current queue, ask what to dispatch, then stop.

## Otherwise, dispatch it
1. **Classify** by class — DOCTRINE §Review depth rows / vault categories (shopify-catalog, seo-ops, content-blog, inventory-ops, kit-research, storefront-theme, agent-infra, software-platform, legal-hr, marketing-email, analytics-reports, sourcing-print, fulfillment-ops). Class from touched paths/resources, not the brief's claim; ambiguity rounds up.
2. **Stamp `review:`** from the depth floor (none · self-check · single-frontier · cross-family). The risk gate only raises it (auth/money/PII/prod/irreversible · multi-service · Grok-conflict/flaky). `user said ship` = land, not spend a frontier.
3. **Pick the implement seat** per `AGENTS.md` §Seats: Grok Build by default · GPT Terra for Google-MCP bulk · Sol/Opus for MCP *judgment* only (`mcp-routing.md`) · storefront pixels → Grok Bot Review D via Slack `#visual-qa` (`grokbot-connection.md`). Legwork-or-stop: never dump volume on Sol/Opus/Cursor $.
4. **Brief** (required, paths only — no pasted dumps): objective · must_read · must_not_touch · output_path · done_when · effort (+attack_angle for reviews). Missing field → don't dispatch; ask the owner.
5. **Route reviews by `usage-status`, not guesswork.** Order: **Fable (if present) → Codex Sol → Opus 4.8 → Review E (Fireworks, if wired) → stop.** Cross-family = one pass each from two families (Fable + 4.8 are one family). Exhaustion opens the next seat only on quota evidence (`usage-status` shows spent/soft-capped), never a probe/timeout — those park (`EDGE-CASES.md`).
6. **Land gates + refill:** one green test bound to the commit tip · one landing lock for main · Review D on pixels · owner gates for publish/send/spend/auth/authority-expansion. On completion, claim the next brief or state why idle — never invent makework.

**Use this host's native seats** (Codex profiles · `grok` CLI · Claude Code Agent/skill bridges · Cursor models) per `AGENTS.md` §Seats, routed by `usage-status`. **Entry point is Codex** — if you are *not* Codex and the task needs multiple seats, stamp the brief and hand it to Codex; do not re-home dispatch onto an IDE or review seat. Two frontier passes only for the cross-family gate. Finish with a one-line status: seat used · review verdict(s) · landed/parked · next.
