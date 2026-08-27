# Magnet Baron orchestration

Day-to-day contract for every CLI agent (Codex, Claude Code, Grok Build, Cursor, and any agent you
register). Deep doctrine: `DOCTRINE.md`. Failures: `EDGE-CASES.md`. Domain files load by domain:
`mcp-routing.md` · `sol-usage.md` · `cursor-usage.md` · `fireworks-usage.md` · `usage-metering.md` · `visual-qa.md` · `grokbot-connection.md` · `analytics-clarity.md`.

**Account state is config, not prose.** Who exists, what plan backs them, which MCP lives where, and
when a seat resets are read from `config/` by `bin/` scripts — never hardcoded here. When something
changes, edit `config/`, run `bin/doctor.py`, and the routing re-derives; prose here is invariant policy only.

- `config/providers.json` — agents/providers, capability levels, families, detection
- `config/subscriptions.json` — the plans you pay for (the one file a new user edits)
- `config/connectors.json` — live MCP/analytics/store/Slack bindings (no stale IDs in prose)
- `config/entrypoints.json` — entry surfaces (user choice) + the one dispatcher
- `config/usage-windows.json` + `config/review-depth.json` — reset anchors + review floors
- `bin/usage-status.py` · `bin/resolve-route.py` · `bin/drain-plan.py` · `bin/doctor.py` · `bin/detect-agents.py` · `bin/detect-capability.py` · `bin/usage-record.py` · `bin/dashboard.py` · `bin/smoketest.py`
- Config layers by `$MB_CONFIG_DIR` then `config/` — the reference `config/` is ONE example; a user points `MB_CONFIG_DIR` at their own subscriptions/entrypoints/windows (`config/examples/` shows 1→N).

> `USER-GUIDE.md` is for humans choosing plans. It is NOT operational and must never be loaded into an agent's context.

**Authority:** Owner override → brief fields → this file → specialty file for the domain → `DOCTRINE.md` → `EDGE-CASES.md`. (Account facts come from `config/`; when a policy and a config fact seem to conflict, the config fact is the current reality — fix config, don't override policy in prose.)

## Entry surface vs dispatcher (you control where you work; one user-assigned seat dispatches)

Where a request is **typed** is the user's choice — any entry surface in `config/entrypoints.json`
(Claude Code, Codex CLI, Cursor, phone). Who **assigns seats, runs the risk gate, and fans work out to
the tree** is ONE dispatcher, **user-assigned** in `config/entrypoints.json` `dispatcher.provider` —
here the Claude orchestration surface (`opus-4.8`), but any `dispatch`-capable provider the user owns
may hold it. Dispatch is configurable **data, not an identity**: exactly one dispatcher at a time, and
reassigning it is a one-line `dispatcher.provider` edit + `can_dispatch` flip (only the holder moves;
the single-dispatcher invariant is unchanged). The system's *one* absolute is the Opus-5.0 block
(§Hard bans); everything else — the dispatcher included — is config. Full framing: `DOCTRINE.md` §Roles.

- **Dispatcher surface** (`can_dispatch: true`) → full dispatch: classify, stamp review, brief, assign, gate, refill, and **fan work OUT to the tree** (sub-agents — other profiles/seats — plus the specialist seats). It **preserves its own account by dispatching, not implementing**: it never runs implement/review on its own account (read-only legwork via a sub-agent is fine); it delegates.
- **Any other surface** → run status, classify + stamp + **draft a brief, then hand it to the assigned dispatcher**. Never self-assign other seats; never implement outside your own seat; never re-home dispatch onto a surface the user did not assign. (Here **Codex is a worker/review seat** — GPT Terra MCP volume + Sol review, cross-family gate #2 — dispatch-capable but not the assigned dispatcher; a user owning no Claude seat may assign a Codex/GPT surface, `config/examples/two-sub`.)

## Seats (roles are invariant; providers are config)

Roles below are durable; the **current provider** for each is the binding in `config/providers.json`
(`bin/detect-agents.py` = live here, `bin/resolve-route.py` to route). Capability levels frontier · sole · terra · luna are the routing tiers; providers at a level are replaceable.

| Role (invariant) | Level | Current provider(s) — see providers.json | Does not |
|------|------|------|------|
| **Dispatch** | frontier | Claude orchestration surface — Opus 4.8 *(the seat the user assigned in entrypoints.json; fans to sub-agents + seats)* | Implement/review on its OWN account; long solo jobs; desktop app |
| **Implement** | terra | Grok Build | Google MCP without a connector; Grok Bot change-sets |
| **MCP volume** | terra | Codex GPT Terra (· Luna coordination) | Being the dispatcher; default coder |
| **MCP / review judgment** | sole/frontier | Codex Sol · Opus 4.8 | Row-dump fetch loops |
| **Cloud standing / Review D** | terra | Grok Bot Website Visual QA | Admin, SimGym, publish, implement |
| **Analytics input** | terra | Grok Bot Heat Map | Review verdicts, implement, settings |
| **Gate 1 (Anthropic)** | frontier | Opus 4.8 (routed across Claude seats by teamclaude) | Default implementer |
| **Gate 2 (OpenAI)** | sole | Codex Sol (under reserve line) | Cursor Sol (different meter) |
| **Architecture only** | frontier | Fable 5 *(optional; architecture only — §Risk gate)* | Any gating verdict; daily coding |
| **Review E** | frontier | independent-family slot — Fireworks today, local open-weight later *(unwired)* | Implement, dispatch, MCP, sole gate on a risk class, any diff with secrets/PII |
| **IDE** | terra | Cursor Grok / Composer | Other Models until last |
| **Last $** | terra | Cursor Other Models $400 | Default anything |

**Claude is five seats, not one.** Max + 2 Team-premium (Fable-capable) + 2 Pro (Opus overflow),
rotated by teamclaude; `bin/resolve-route.py` counts **Fable available only while a Fable-capable seat
is live and not downgraded** (`bin/detect-capability.py`), so the review order never goes stale on a
plan change. (No teamclaude on the box → no rotation; degraded to one account — `EDGE-CASES.md`.)

**Google MCP** rides only the providers `config/connectors.json` `available_on` lists (today Opus +
appropriate GPT), never assumed on Grok — route per `mcp-routing.md`. **Legwork-or-stop:** volume runs
on Grok or a GPT-Terra MCP lane, else parks — never dumped on Sol/Opus/Cursor $ on a probe fail
(outages: `EDGE-CASES.md`). **No desktop apps** after device-auth; one implementer process on the 16 GB Mini; Grok Bot.app stays quit on the worker.

## Usage economics (never strand)

Per-seat policy lives in `config/usage-windows.json` (`drain`, `reserve_pct`, `intake`, `billing`);
`bin/drain-plan.py` computes the live plan. Rules the router already enforces:

- **Never strand.** A soft cap / reserve is a *priority demotion that yields*, not a stop. A `reserve`-tier seat is still USABLE. The system parks only for genuine exhaustion (a recorded 429) or an unsatisfiable safety gate — **never** because a self-imposed cap sat on real quota.
- **The intake/reserve seat codes last (never strand).** When every worker seat is spent, the intake/reserve seat — a subscription worker held with headroom (`codex-plan` in the reference) — implements as a last resort, so usable quota never strands. Reserves protect that seat's *own* headroom, sized to need + margin (`bin/drain-plan.py --reserve`), never to block it from coding. The **dispatcher** is separate — it preserves its account by delegating (§Entry surface), not coding on it — *except* where a user owns no other seat (solo-pro, or a two-sub user who assigned their Codex plan), where the dispatcher's plan is also last-resort coder (an accepted 1-/2-subscription reality).
- **Minimize API $.** `included` (subscription) seats before `metered` ($). Metered pools (Cursor Other Models, Review E) drain LAST — only when no included capacity remains.
- **Use before lost.** Drain soon-to-reset weekly/monthly quota before it resets to waste; rolling windows refill, so they wait.
- **No mid-turn swaps.** Pick a seat with enough runway to finish the task (`resolve-route --task-seconds N`); bring a just-reset account in at the NEXT task boundary.
- **Capability-aware.** An implement/review seat must actually have the needed capability (browser/connector/family) — derived from `config/providers.json` + `config/connectors.json`, not assumed.

## Brief (required)

`objective` · `must_read` · `must_not_touch` · `output_path` · `done_when` · `effort` (`setup` | `low` | `medium` | `high` | `review`)
Reviews also: `attack_angle`. Missing field → no dispatch. Paths only; no pasted dumps.

## Risk gate → review

Two dials: **depth** (how much review) and **order** (which seat). Dispatch stamps `review:` on every
brief and the risk gate only raises it, never lowers; class is read from the diff's paths/resources (not the brief's claim), ambiguity rounding up.

**Depth floor by task class** is defined once, machine-readable, in `config/review-depth.json`
(explained in `DOCTRINE.md` §Review depth). **Do not eyeball it — run the router:**

```
bin/resolve-route.py --class <class> --scale routine|elevated [--risk auth,money,…] [--implement] [--pixels]
```

It returns the depth, the live review chain (or a park reason), the implement seat, and the gates —
deterministically, from `config/` + recorded usage. Levels: **none** · **self-check** · **single-frontier** · **cross-family**.

Raise if: auth/money/PII/prod/irreversible · multi-service · Grok conflict/flaky tests. `user said ship` = land, not spend a frontier. **none** / **self-check** still keep the landing lock, tip-bound green test, Review D pixels, and owner publish/send gates.

**Order** (single-frontier = first live seat; cross-family = one pass from **each of two families**):
**Opus 4.8 → Codex Sol → Review E (if wired) → stop** (`config/providers.json` `review_order` — the
Anthropic, OpenAI, and independent-family seats). Cross-family needs two *different* families (never two
Anthropic passes); **Fable is NOT in the gating order** (architecture only — Fable + Opus 4.8 are one family). One frontier pass per change-set **except** the cross-family pair.

**Exhaustion opens the next seat only on quota evidence** — `usage-status` shows the seat spent or
soft-capped (a recorded 429 or ledger %), never a probe; probe failure, timeout, or auth error → fail
closed, park (`EDGE-CASES.md`). **Review E** engages only at confirmed exhaustion of the native seats
(or as the second family when one native family is quota-spent), never on a mere outage, and never
sole-gates a risk class — its `ship` there is advisory, owner lands; unwired → park after 4.8 (`fireworks-usage.md`).

When Sol is needed for **both** code review and MCP judgment the same week: code-review risk gate wins the Sol slot; MCP judgment goes to Opus if Sol is spent or already used on that change-set.

**Review D** when storefront *pixels* change. Slack `#visual-qa` (channel binding in `config/connectors.json`).

**Autonomy limits (disclosed).** Cross-family autonomy needs **≥2 review families**: with fewer (a downgrade or a solo/one-family setup) risk-class work — money, auth, PII, secrets — **parks pending a human** rather than auto-shipping (the routing collapses toward one seat; the discipline holds). And **unattended land-to-prod is a current non-goal** — the executor is gated: `bin/run-brief.py` is **dry-run only** (it plans, shells nothing) and fails closed without an explicit run; landing/publish/send stay behind owner gates (`DOCTRINE.md` §non-goals).

## Dispatch (the Claude orchestration surface)

The dispatcher (defined in §Entry surface vs dispatcher — user-assigned; here the Claude orchestration surface) **fans work OUT to the tree** — sub-agents (other Claude seats via teamclaude) + the specialist seats below — and delegates every implement/review job rather than running one on its own account. Its steps:

1. **Implement seat:** Google-MCP bulk → GPT Terra, MCP *judgment* → Sol/Opus (`mcp-routing.md`); else **Grok Build**. Standing non-repo → Grok Bot; theme/layout → Build then Review D; product copy → MCP packet (if needed) then Grok write.
2. **Brief** every job (fields above) and **stamp `review:`** at the router's floor; ambiguous risk → park + ask owner. Do not invent seats.
3. **Route reviews** with `bin/resolve-route.py` (which reads `bin/usage-status.py`), never by guesswork.
4. **Refill + supervise** at the checkpoints you already run (never a daemon): on completion claim the next brief or say why idle (never implement from phone); past-budget lane with no park note → `stalled:`; a return outside scope or into `must_not_touch` → reject + re-scope; two loops with no novel defect → park + escalate; run `usage-status` before any reroute — a whole-pipe outage is ONE outage, don't cascade (`EDGE-CASES.md`).

## Implement (Grok Build)

1 worktree · 1 branch · named file scope. Style-match; no drive-bys. Return: summary, files, tests run, risks. Never same change-set as Bot. Do not invent GSC/keyword numbers; consume `must_read` snapshots from MCP seats. Resume existing branch on retry; no second worktree for the same objective.

## Review (Opus 4.8 / Codex Sol / Review E / Website Visual QA)

Code seats read **git diff**. Visual QA reads the **preview URL**. Output: `ship` | `fix-list` | `blocked`. **`blocked` wins** if reviews disagree. Max two fix loops then park unless a novel defect. Cross-family = one pass each from two families, **sequential**, one machine reviewer at a time; Review E is an off-box HTTP call, never a Mini process. Fix loops return to the issuing seat; a seat spent mid-loop → park the loop.

## Standing-config changes (this repo included)

A change to `config/`, a cron/LaunchAgent, an MCP config, or a Bot routine is `standing-config` (floor
`single-frontier`, never lower). **Run `bin/doctor.py` (+ `bin/smoketest.py` if scripts changed) before landing** — a broken registry mis-routes every later job.

## Hard bans

- Fable/Sol/Opus as daily coder · **Opus 5.0 as default or reviewer** — the one hard invariant; 5.1+ are NOT blocked (pin Opus 4.8; `bin/doctor.py` refuses a 5.0 build exactly, via `mborch.is_opus5_zero`) · two frontier passes from the **same family** on one branch (the cross-family pair is the only two-pass case) · Cursor Other Models early · Opus/Sol as bulk MCP fetchers · Grok inventing Google metrics without connector/snapshot · Build+Bot on one change-set · inventing makework · two implementer CLIs on 16 GB · Grok Bot.app open on the worker · Visual QA in Shopify Admin or SimGym · moving legwork to scarce seats on outage · Review E before confirmed exhaustion or on an outage/probe signal · Review E as implementer or sole land-gate · counting Fable + Opus 4.8 as two families · sending secrets/PII to a third-party inference host · **hardcoding a live ID, tier, reset time, or connector location in prose instead of `config/`** · **parking or stopping work while a usable (reserve/intake) seat still has real quota** (a self-imposed cap is never a stop) · **draining a metered $ seat while included subscription capacity is available** · **any surface acting as dispatcher when the user did not assign it** (exactly one, per `entrypoints.dispatcher.provider`; a non-dispatcher surface drafts + hands over — §Entry surface) · **the assigned dispatcher masquerading as the worker** — running implement/review on its OWN account instead of fanning work out to sub-agents + seats (read-only legwork sub-agents are fine) · **swapping the serving account mid-turn** (pick a seat with runway; rotate at the next task boundary).
