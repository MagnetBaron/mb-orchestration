# Magnet Baron orchestration

Day-to-day contract for every CLI agent (Codex, Claude Code, Grok Build, Cursor, and any
agent you register). Deep doctrine: `DOCTRINE.md`. Failures: `EDGE-CASES.md`. Domain files
load by domain: `mcp-routing.md` · `sol-usage.md` · `cursor-usage.md` · `fireworks-usage.md` ·
`usage-metering.md` · `visual-qa.md` · `grokbot-connection.md` · `analytics-clarity.md`.

**Account state is config, not prose.** Who exists, what plan backs them, which MCP lives
where, and when a seat resets are read from `config/` by `bin/` scripts — never hardcoded in
these words. When something changes, edit `config/`, run `bin/doctor.py`, and the routing
re-derives. Prose here is invariant policy only.

- `config/providers.json` — agents/providers, capability levels, families, detection
- `config/subscriptions.json` — the plans you pay for (the one file a new user edits)
- `config/connectors.json` — live MCP/analytics/store/Slack bindings (no stale IDs in prose)
- `config/entrypoints.json` — entry surfaces (user choice) + the one dispatcher
- `config/usage-windows.json` + `config/review-depth.json` — reset anchors + review floors
- `bin/usage-status.py` · `bin/resolve-route.py` · `bin/drain-plan.py` · `bin/doctor.py` · `bin/detect-agents.py` · `bin/detect-capability.py` · `bin/usage-record.py` · `bin/dashboard.py` · `bin/smoketest.py`
- Config layers by `$MB_CONFIG_DIR` then `config/` — the reference `config/` is ONE example; a user points `MB_CONFIG_DIR` at their own subscriptions/entrypoints/windows (`config/examples/` shows 1→N).

> `USER-GUIDE.md` is for humans choosing plans. It is NOT operational and must never be loaded into an agent's context.

**Authority:** Owner override → brief fields → this file → specialty file for the domain → `DOCTRINE.md` → `EDGE-CASES.md`. (Account facts come from `config/`; when a policy and a config fact seem to conflict, the config fact is the current reality — fix config, don't override policy in prose.)

## Entry surface vs dispatcher (you control where you work; one seat assigns)

Where a request is **typed** is the user's choice — any entry surface in `config/entrypoints.json`
(Codex CLI, Claude Code, Cursor, phone). Who **assigns seats and runs the risk gate** is ONE
config-bound dispatcher (`entrypoints.json` `dispatcher.provider`; default Codex Luna).

- **Dispatcher surface** (`can_dispatch: true`) → full dispatch: classify, stamp review, brief, assign, gate, refill.
- **Any other surface** → run status, classify + stamp + **draft a brief, then hand it to the dispatcher**. Never self-assign other seats; never implement outside your own seat; never re-home dispatch onto an IDE or review seat.

A user without the default dispatcher sets `dispatcher.provider` to a provider they own and flips that surface's `can_dispatch` — the single-dispatcher invariant holds; only the holder moves.

## Seats (roles are invariant; providers are config)

Roles below are durable. The **current provider** for each is the binding in `config/providers.json`
— run `bin/detect-agents.py` for what is live here, `bin/resolve-route.py` to route. Capability
levels (frontier · sole · terra · luna) are the routing tiers; providers at a level are replaceable.

| Role (invariant) | Level | Current provider(s) — see providers.json | Does not |
|------|------|------|------|
| **Dispatch** | luna | Codex Luna/Terra | Implement; long review; desktop app |
| **Implement** | terra | Grok Build | Google MCP without a connector; Grok Bot change-sets |
| **MCP volume** | terra | Codex GPT Terra | Dispatch-only Luna; default coder |
| **MCP / review judgment** | sole/frontier | Codex Sol · Opus 4.8 | Row-dump fetch loops |
| **Cloud standing / Review D** | terra | Grok Bot Website Visual QA | Admin, SimGym, publish, implement |
| **Analytics input** | terra | Grok Bot Heat Map | Review verdicts, implement, settings |
| **Review A** | frontier | Fable 5 *(while a live Claude seat grants it — `bin/detect-capability.py`)* | Daily coding |
| **Review B** | sole | Codex Sol (under soft cap) | Cursor Sol (different meter) |
| **Review C** | frontier | Opus 4.8 (routed across Claude seats by teamclaude) | Default implementer |
| **Review E** | frontier | independent-family slot — Fireworks today, local open-weight later *(unwired)* | Implement, dispatch, MCP, sole gate on a risk class, any diff with secrets/PII |
| **IDE** | terra | Cursor Grok / Composer | Other Models until last |
| **Last $** | terra | Cursor Other Models $400 | Default anything |

**Claude is five seats, not one.** Max + 2 Team-premium (Fable-capable) + 2 Pro (Opus overflow, no
Fable), rotated by teamclaude. `bin/resolve-route.py` treats **Fable as available only if a
Fable-capable seat is live and not downgraded** (`bin/detect-capability.py`), so the review order never
goes stale on a plan change.

**Google MCP:** on whichever providers `config/connectors.json` `available_on` lists (today Opus +
appropriate GPT). **Not** assumed on Grok. Route per `mcp-routing.md`.

**Legwork-or-stop:** volume runs on Grok or a GPT-Terra MCP lane, or parks. Never dump legwork on Sol/Opus/Cursor $ because a probe failed. Outages: `EDGE-CASES.md`.

**No desktop apps** after first device-auth. One implementer process on a 16 GB Mini. Grok Bot.app stays quit on the worker.

## Usage economics (never strand)

Per-seat policy lives in `config/usage-windows.json` (`drain`, `reserve_pct`, `intake`, `billing`);
`bin/drain-plan.py` computes the live plan. Rules the router already enforces:

- **Never strand.** A soft cap / reserve is a *priority demotion that yields*, not a stop. A `reserve`-tier seat is still USABLE. The system parks only for genuine exhaustion (a recorded 429) or an unsatisfiable safety gate — **never** because a self-imposed cap sat on real quota.
- **Dispatch codes last.** If every worker seat is spent, the intake/dispatch seat implements (a 2-subscription setup routes coding to dispatch by design). Reserves exist to protect dispatch's *own* headroom, sized to what it needs + margin (`bin/drain-plan.py --reserve`), never to block it from coding.
- **Minimize API $.** `included` (subscription) seats before `metered` ($). Metered pools (Cursor Other Models, Review E) drain LAST — only when no included capacity remains.
- **Use before lost.** Drain soon-to-reset weekly/monthly quota before it resets to waste; rolling windows refill, so they wait.
- **No mid-turn swaps.** Pick a seat with enough runway to finish the task (`resolve-route --task-seconds N`); bring a just-reset account in at the NEXT task boundary.
- **Capability-aware.** An implement/review seat must actually have the needed capability (browser/connector/family) — derived from `config/providers.json` + `config/connectors.json`, not assumed.

## Brief (required)

`objective` · `must_read` · `must_not_touch` · `output_path` · `done_when` · `effort`
Reviews also: `attack_angle`. Missing field → no dispatch. Paths only; no pasted dumps.

`effort`: `setup` | `low` | `medium` | `high` | `review`.

## Risk gate → review

Two dials: **depth** (how much review) and **order** (which seat). Dispatch stamps `review:` on
every brief; the risk gate only raises it, never lowers. Class is read from the diff's
paths/resources, not the brief's claim; ambiguity rounds up.

**Depth floor by task class** is defined once, machine-readable, in `config/review-depth.json`
(explained in `DOCTRINE.md` §Review depth). **Do not eyeball it — run the router:**

```
bin/resolve-route.py --class <class> --scale routine|elevated [--risk auth,money,…] [--implement] [--pixels]
```

It returns the depth, the concrete live review chain (or a park reason), the implement seat, and
the gates — from `config/` + recorded usage signals, deterministically. Levels: **none** · **self-check**
· **single-frontier** · **cross-family**.

Raise if: auth/money/PII/prod/irreversible · multi-service · Grok conflict/flaky tests. `user said ship` = land, not spend a frontier. **none** / **self-check** still keep the landing lock, tip-bound green test, Review D pixels, and owner publish/send gates.

**Order** (single-frontier = first live seat; cross-family = one pass from **each of two families**):
**Fable → Codex Sol → Opus 4.8 → Review E (if wired) → stop** (`config/providers.json` `review_order`).
Fable + Opus 4.8 are **one** family (Anthropic); Sol is OpenAI; Review E is independent open-weight.
Cross-family needs two *different* families — never two Anthropic passes. One frontier pass per
change-set **except** the cross-family pair.

**Exhaustion opens the next seat only on quota evidence** — `usage-status` shows the seat spent or
soft-capped (a recorded 429 or ledger %), never a probe. Probe failure, timeout, or auth error →
fail closed, park (`EDGE-CASES.md`). **Review E** engages only when `usage-status` shows all native
review seats spent/soft-capped **and** the brief is time-critical, or as the second family when one
native family is quota-spent and only one remains (never on a mere outage); never sole gate on a
risk class (its `ship` there is advisory — owner lands). Unwired → park after 4.8. Detail:
`fireworks-usage.md`.

When Sol is needed for **both** code review and MCP judgment the same week: code-review risk gate wins the Sol slot; MCP judgment goes to Opus if Sol is spent or already used on that change-set.

**Review D** when storefront *pixels* change. Slack `#visual-qa` (channel binding in `config/connectors.json`).

## Dispatch (the dispatcher surface)

1. Needs **Google MCP**? → GPT Terra (bulk) or Sol/Opus (judgment only). See `mcp-routing.md`.
2. Else default **Grok Build** for implement.
3. Standing non-repo → Grok Bot. Theme/layout → Build then Review D.
4. Product copy: MCP research packet first (if needed), then Grok write.
5. Ambiguous risk → park and ask owner (`EDGE-CASES.md`). Do not invent seats.
6. On completion: refill or state why idle. Never implement from phone.
7. Route reviews with `bin/resolve-route.py` reading `bin/usage-status.py`, never by guesswork.
8. Supervise at the checkpoints you already run, not continuously: past-budget lane with no park note → `stalled:`; return outside scope or into `must_not_touch` → reject + re-scope; two loops, no novel defect → park + escalate. Run `usage-status` before any reroute — a whole-pipe outage is one outage, diagnose don't cascade. No watcher daemon (`EDGE-CASES.md`).

## Implement (Grok Build)

1 worktree · 1 branch · named file scope. Style-match; no drive-bys. Return: summary, files, tests run, risks. Never same change-set as Bot. Do not invent GSC/keyword numbers; consume `must_read` snapshots from MCP seats. Resume existing branch on retry; no second worktree for the same objective.

## Review (Fable / Codex Sol / Opus 4.8 / Review E / Website Visual QA)

Code seats read **git diff**. Visual QA reads the **preview URL**. Output: `ship` | `fix-list` | `blocked`. **`blocked` wins** if reviews disagree. Max two fix loops then park unless a novel defect. Cross-family = one pass each from two families, **sequential**, one machine reviewer at a time; Review E is an off-box HTTP call, never a Mini process. Fix loops return to the issuing seat; a seat spent mid-loop → park the loop.

## Standing-config changes (this repo included)

A change to `config/`, a cron/LaunchAgent, an MCP config, or a Bot routine is `standing-config`
class (floor `single-frontier`, never lower). **Run `bin/doctor.py` (and `bin/smoketest.py` for a
change touching scripts) before landing** — a broken registry mis-routes every later job.

## Hard bans

- Fable/Sol/Opus as daily coder · **Opus 5 as default or reviewer** (pin Opus 4.8; `bin/doctor.py` fails on any config that selects it) · two frontier passes from the **same family** on one branch (the cross-family pair is the only two-pass case) · Cursor Other Models early · Opus/Sol as bulk MCP fetchers · Grok inventing Google metrics without connector/snapshot · Build+Bot on one change-set · inventing makework · two implementer CLIs on 16 GB · Grok Bot.app open on the worker · Visual QA in Shopify Admin or SimGym · moving legwork to scarce seats on outage · Review E before confirmed exhaustion or on an outage/probe signal · Review E as implementer or sole land-gate · counting Fable + Opus 4.8 as two families · sending secrets/PII to a third-party inference host · **hardcoding a live ID, tier, reset time, or connector location in prose instead of `config/`** · **parking or stopping work while a usable (reserve/intake) seat still has real quota** (a self-imposed cap is never a stop) · **draining a metered $ seat while included subscription capacity is available** · **swapping the serving account mid-turn** (pick a seat with runway; rotate at the next task boundary).
