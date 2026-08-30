---
description: Dispatch a task through the Magnet Baron multi-CLI orchestration — classify, route to the right seat, review, refill.
argument-hint: "[task] (omit to show the live seat map)"
---

You are running the Magnet Baron orchestration **per-run dispatch policy**. `/orca` is the preferred trigger; `/orchestrate` is an identical compatibility alias. Establish and validate the authoritative control checkout before doing anything else:

```bash
test -f "${ORCA_REPO:-$HOME/git/mb-orchestration}/AGENTS.md" &&
test -f "${ORCA_REPO:-$HOME/git/mb-orchestration}/.claude/commands/orchestrate.md" &&
orca_origin="$(git -C "${ORCA_REPO:-$HOME/git/mb-orchestration}" remote get-url origin)" &&
orca_trusted="${ORCA_TRUSTED_ORIGIN:-https://github.com/MagnetBaron/mb-orchestration}" &&
orca_origin="${orca_origin%/}" && orca_origin="${orca_origin%.git}" &&
orca_trusted="${orca_trusted%/}" && orca_trusted="${orca_trusted%.git}" &&
case "$orca_origin" in
  https://github.com/*) orca_origin="github.com/${orca_origin#https://github.com/}" ;;
  git@github.com:*) orca_origin="github.com/${orca_origin#git@github.com:}" ;;
  ssh://git@github.com/*) orca_origin="github.com/${orca_origin#ssh://git@github.com/}" ;;
  *) false ;;
esac &&
case "$orca_trusted" in
  https://github.com/*) orca_trusted="github.com/${orca_trusted#https://github.com/}" ;;
  git@github.com:*) orca_trusted="github.com/${orca_trusted#git@github.com:}" ;;
  ssh://git@github.com/*) orca_trusted="github.com/${orca_trusted#ssh://git@github.com/}" ;;
  *) false ;;
esac &&
test "$orca_origin" = "$orca_trusted"
```

Run every orchestration script from that checkout. Do not substitute another orchestration repository merely because it exists locally.

This command is shared across Claude Code, Codex, Cursor, and the native agent skill tree. Identify the provider/model that received the user's request and pass it as `--intake-provider`: `opus-5`, `opus-4.8`, `fable-5`, `codex-sol`, `codex-terra`, `codex-luna`, `grok-build`, or a registered known non-dispatch surface such as `cursor-grok`.

Resolver honors a tested dispatch-qualified intake while live and usable. Recorded unavailability activates configured fallback. A known non-dispatch intake relays an ordinary brief to a qualified provider without gaining authority. Unknown identities park. Exactly one effective dispatcher is recorded per run.

Prefer another implementer when usable. Implementers/authors cannot review their own artifact. Effective dispatcher may review an artifact it did not author, but that pass is artifact-only; another reviewer independently checks dispatch intent/risk. Ordinary minimum-necessary repo artifacts are preauthorized by `config/handoff-policy.json`; restricted/unknown data parks without a permission loop.

Contract: read the authoritative checkout's `AGENTS.md`; for routing, `config/review-depth.json` (machine floor) with `DOCTRINE.md` §Review depth (the human explanation). Live model/route identity is `config/model-registry.json` via `bin/model-registry.py` and `bin/resolve-route.py`. Domain files load from that same checkout by domain: `mcp-routing.md` · `sol-usage.md` · `cursor-usage.md` · `fireworks-usage.md` · `usage-metering.md` · `visual-qa.md` · `grokbot-connection.md` · `analytics-clarity.md` · `skills/README.md` · `skills/registry.json` · `EDGE-CASES.md`.

TASK: $ARGUMENTS
*(If the line above shows the literal token `$ARGUMENTS`, the task is the message the user sent with this command. If no task was given, show status.)*

## If no TASK
Run `python3 "${ORCA_REPO:-$HOME/git/mb-orchestration}/bin/usage-status.py"`, print the seat map (live / spent / next reset) and the backlog (per `EDGE-CASES.md`, if one is configured), ask what to dispatch, then stop.

## Otherwise (resolve requested intake to one effective dispatcher)
1. **Classify** by task class. Run the router instead of eyeballing prose:
   `python3 "${ORCA_REPO:-$HOME/git/mb-orchestration}/bin/resolve-route.py" --class <class> --scale routine|elevated --intake-provider <provider> --artifacts <comma-separated-classes> [--risk auth,money,PII,prod,irreversible,multi-service,grok-conflict,flaky-tests,secrets,untrusted-shell] [--implement] [--pixels]`
   It returns requested/effective dispatcher, fallback/relay reason, handoff gate, authors, depth, conflict-aware review chain, implement seat, and gates. Use `brief,repo-source,diff,test-output` for ordinary repo implementation. Only `live_verified` registry routes resolve.
2. **Stamp `review:`** at the floor the router reports (none · self-check · single-frontier · cross-family). The `AGENTS.md` risk gate only raises it. `user said ship` = land, not spend a frontier.
3. **Pick the implement seat** per `AGENTS.md` §Seats / the router's `--implement` plan: **Grok Build** by default · **GPT Terra** for Google-MCP bulk · **Sol/Opus** for MCP *judgment* only (`mcp-routing.md`). Storefront pixels → **Grok Build implements, then** a Review D Slack ticket once a visitor preview URL exists (`visual-qa.md`; render the ticket with `bin/connectors.py`). Review D and Heat Map are review/input seats — **never implementers**. Legwork-or-stop: never dump volume on Sol/Opus/Cursor $.
4. **Select only the router.** Dart, Flutter, or native iOS accessibility implementation gets `skills: [mobile-dev-router]`; explicit Cloudflare platform work gets `cloudflare-dev-router`; Obsidian vault/Bases/Canvas/CLI work gets `knowledge-vault-router`; React specialty, generic MCP builder, or measured web-performance work gets `engineering-dev-router`. Dispatch does not inspect the private leaf descriptions or bodies. A dedicated native iOS accessibility review may directly select only `ios-accessibility`. Unrelated work gets `skills: []`.
5. **Brief** (required, paths only — no pasted dumps): objective · must_read · must_not_touch · output_path · done_when · effort · skills (+attack_angle for reviews). A matching brief includes `~/.agents/skills/<router>/SKILL.md`; its receiver selects one primary leaf plus at most one distinct validation leaf from the private library. A direct accessibility review includes `~/.codex/skill-library/mobile/ios-accessibility/SKILL.md`. Missing field → don't dispatch; ask the owner.
6. **Route reviews by the router, not a fixed list.** It excludes authors, prefers a reviewer independent from the dispatcher, and uses Opus 4.8 only as a time-bounded fallback. A dispatcher review is artifact-only. Cross-family requires two independence groups and unique physical invocations. Exhaustion / Review E / quota-vs-outage rules live in `AGENTS.md` + `fireworks-usage.md`.
7. **Land gates + refill:** one green test bound to the commit tip · one landing lock for main · Review D on pixels · owner gates for publish/send/spend/auth/authority-expansion · `bin/doctor.py` green before landing a `standing-config`/`config/` change. On completion, claim the next brief or state why idle — never invent makework.

Finish with a one-line status: requested intake → effective dispatcher · implementer · review scope/verdict(s) · handoff allowed/parked · landed/parked · next.
