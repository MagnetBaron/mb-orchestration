# Magnet Baron orchestration

Day-to-day contract for every CLI agent (Codex, Claude Code, Grok Build, Cursor, and any agent you
register). Deep doctrine: `DOCTRINE.md`. Failures: `EDGE-CASES.md`. Domain files load by domain:
`mcp-routing.md` · `sol-usage.md` · `cursor-usage.md` · `fireworks-usage.md` · `usage-metering.md` · `visual-qa.md` · `grokbot-connection.md` · `analytics-clarity.md` · `qa-idle-handoff.md`. Selective skill routers: `skills/README.md`, `skills/registry.json`.

**Account state is config, not prose.** Who exists, what plan backs them, which MCP lives where, and
when a seat resets are read from `config/` by `bin/` scripts — never hardcoded here. When something
changes, edit `config/`, run `bin/doctor.py`, and the routing re-derives; prose here is invariant policy only.

- `config/providers.json` — agents/providers, capability levels, families, detection
- `config/model-registry.json` — model identity, routes, lifecycle, route state, per-role rankings
- `config/subscriptions.json` — the plans you pay for (the one file a new user edits)
- `config/connectors.json` — live MCP/analytics/store/Slack bindings (no stale IDs in prose)
- `config/entrypoints.json` — entry surfaces, user profiles, and per-run dispatcher fallback order
- `config/handoff-policy.json` — preauthorized ordinary artifacts + fail-closed restricted classes
- `config/usage-windows.json` + `config/review-depth.json` — reset anchors + review floors
- `bin/usage-status.py` · `bin/resolve-route.py` · `bin/model-registry.py` · `bin/drain-plan.py` · `bin/doctor.py` · `bin/detect-agents.py` · `bin/detect-capability.py` · `bin/usage-record.py` · `bin/dashboard.py` · `bin/smoketest.py`
- Config layers by `$MB_CONFIG_DIR` then `config/` — the reference `config/` is ONE example; a user points `MB_CONFIG_DIR` at their own subscriptions/entrypoints/windows (`config/examples/` shows 1→N).

> `USER-GUIDE.md` is for humans choosing plans. It is NOT operational and must never be loaded into an agent's context.

**Authority:** Owner override → brief fields → this file → specialty file for the domain → `DOCTRINE.md` → `EDGE-CASES.md`. (Account facts come from `config/`; when a policy and a config fact seem to conflict, the config fact is the current reality — fix config, don't override policy in prose.)

## Entry surface vs dispatcher (user choice first; exactly one dispatcher per run)

Where a request is **typed** and which model receives it are user choices. Run
`bin/resolve-route.py --intake-provider <provider>` (or select a profile). If that tested,
dispatch-qualified provider has a live route and usable quota, it is the effective dispatcher. A
recorded unavailable/spent state activates the configured fallback order automatically. A known
non-dispatch surface relays an ordinary brief without gaining authority. Unknown identities and
malformed dispatch claims park; they never gain authority from a ranking. Exactly one effective
dispatcher exists **per run**, not globally for every user.

- A dispatch-qualified intake classifies, stamps review depth, briefs, assigns, and gates.
- Prefer another implementer while one is usable; the dispatcher may implement only as a capability-checked fallback.
- A dispatcher may review an artifact it did not author, but that pass is `artifact-only`; at least one other reviewer must independently validate dispatch intent/risk.
- Implementers/authors never review their own artifact. Cross-family gates still need distinct independence groups and physical invocations.
- `config/handoff-policy.json` preauthorizes minimum-necessary ordinary repo artifacts between configured providers. Authorship never creates a permission prompt. Credentials, tokens, restricted PII, customer data, production exports, and unknown classes park without a permission loop.

## Seats (roles are invariant; providers are config)

Roles below are durable; the **current provider** for each is the binding in `config/providers.json`
(`bin/detect-agents.py` = live here, `bin/resolve-route.py` to route, `bin/model-registry.py` for
model/route identity). Capability levels frontier · sole · terra · luna are the routing tiers; providers at a level are replaceable. Only `live_verified` routes may resolve for active dispatch.

| Role (invariant) | Level | Current provider(s) — see providers.json | Does not |
|------|------|------|------|
| **Dispatch** | varies | Per-run selected Sol / Opus 5 / Opus 4.8 / Fable / Terra / Luna / Grok, when live and qualified | More than one effective dispatcher per run; authority from rank alone |
| **Implement** | terra | Grok Build | Google MCP without a connector; Grok Bot change-sets |
| **MCP volume** | terra | Codex GPT Terra (· Luna coordination) | Default coder; MCP without a live connector |
| **MCP / review judgment** | sole/frontier | Codex Sol · Opus 5 | Row-dump fetch loops |
| **Cloud standing / Review D** | terra | Grok Bot Website Visual QA | Admin, SimGym, publish, implement |
| **Analytics input** | terra | Grok Bot Heat Map | Review verdicts, implement, settings |
| **Gate 1 (Anthropic)** | frontier | Opus 5 (routed across Claude seats by teamclaude) | Default implementer |
| **Gate 2 (OpenAI)** | sole | Codex Sol (under reserve line) | Cursor Sol (different meter) |
| **Architecture / long-horizon** | frontier | Fable 5 *(rare escalation; same family as Opus; never a second family)* | Any gating verdict; daily coding |
| **Review E** | frontier | independent-family slot — Fireworks today, local open-weight later *(unwired)* | Implement, dispatch, MCP, sole gate on a risk class, any diff with secrets/PII |
| **IDE** | terra | Cursor Grok / Composer | Other Models until last |
| **Last $** | terra | Cursor Other Models $400 | Default anything |

**Claude is five seats, not one.** Max + 2 Team-premium (Fable-capable) + 2 Pro (Opus overflow),
rotated by teamclaude; `bin/resolve-route.py` counts **Fable available only while a Fable-capable seat
is live and not downgraded** (`bin/detect-capability.py`), so the review order never goes stale on a
plan change. (No teamclaude on the box → no rotation; degraded to one account — `EDGE-CASES.md`.)
Direct `claude` without teamclaude is `auth_blocked` and is not a working route.

**Google MCP** rides only the providers `config/connectors.json` `available_on` lists (today Opus +
appropriate GPT), never assumed on Grok — route per `mcp-routing.md`. **Legwork-or-stop:** volume runs
on Grok or a GPT-Terra MCP lane, else parks — never dumped on Sol/Opus/Cursor $ on a probe fail
(outages: `EDGE-CASES.md`). **No desktop apps** after device-auth; one implementer process on the 16 GB Mini; Grok Bot.app stays quit on the worker.

## Usage economics (never strand)

Per-seat policy lives in `config/usage-windows.json` (`drain`, `reserve_pct`, `intake`, `billing`);
`bin/drain-plan.py` computes the live plan. Rules the router already enforces:

- **Never strand.** A soft cap / reserve is a *priority demotion that yields*, not a stop. A `reserve`-tier seat is still USABLE. The system parks only for genuine exhaustion (a recorded 429) or an unsatisfiable safety gate — **never** because a self-imposed cap sat on real quota.
- **Dispatcher codes last when another coder is usable.** Last-resort coding still requires `implement`/`ide` plus `code` on provider and live route. This is a preference tied to current intake identity, not an absolute provider ban.
- **Minimize API $.** `included` (subscription) seats before `metered` ($). Metered pools (Cursor Other Models, Review E) drain LAST — only when no included capacity remains.
- **Use before lost.** Drain soon-to-reset weekly/monthly quota before it resets to waste; rolling windows refill, so they wait.
- **No mid-turn swaps.** Pick a seat with enough runway to finish the task (`resolve-route --task-seconds N`); bring a just-reset account in at the NEXT task boundary.
- **Capability-aware.** An implement/review seat must actually have the needed capability (browser/connector/family) — derived from `config/providers.json` + `config/connectors.json` + `config/model-registry.json`, not assumed.
- **Quality rank is not selection priority.** A scarce top model can rank first on quality while a cheaper, already-paid, or independence-preserving model remains the operational default.

## Brief (required)

`objective` · `must_read` · `must_not_touch` · `output_path` · `done_when` · `effort` · `skills`
Reviews also: `attack_angle`. Missing field → no dispatch. Paths only; no pasted dumps.

`skills` is always present. Use `skills: []` for unrelated work. Matching work
names exactly one of `mobile-dev-router`, `cloudflare-dev-router`,
`knowledge-vault-router`, or `engineering-dev-router` and adds its exact
`~/.agents/skills/<router>/SKILL.md` path to `must_read`. Dispatch sees only
four concise router descriptions and never reads the 44 private leaf bodies.
The receiving existing seat opens one primary leaf plus at most one distinct
validation leaf from the selected private library. A dedicated native iOS
accessibility review may directly load only `ios-accessibility`. Skills are a
role-loading layer inside seats, never a new seat, tool, credential, or
permission. Do not bind these routers permanently to generic Build or Review
roles; per-brief loading avoids unrelated context.

`effort`: `setup` | `low` | `medium` | `high` | `review`.

## Risk gate → review

Two dials: **depth** (how much review) and **order** (which seat). Dispatch stamps `review:` on every
brief and the risk gate only raises it, never lowers; class is read from the diff's paths/resources (not the brief's claim), ambiguity rounding up.

**Depth floor by task class** is defined once, machine-readable, in `config/review-depth.json`
(explained in `DOCTRINE.md` §Review depth). **Do not eyeball it — run the router:**

```
bin/resolve-route.py --class <class> --scale routine|elevated --intake-provider <provider> [--profile <name>] [--risk auth,money,…] [--implement] [--artifacts brief,repo-source,diff,test-output] [--pixels]
```

It returns the depth, the live review chain (or a park reason), the implement seat, and the gates —
deterministically, from `config/` + recorded usage + the model registry. Levels: **none** · **self-check** · **single-frontier** · **cross-family**.

Raise if: auth/money/PII/prod/irreversible · multi-service · Grok conflict/flaky tests. `user said ship` = land, not spend a frontier. **none** / **self-check** still keep the landing lock, tip-bound green test, Review D pixels, and owner publish/send gates.

**Order** (single-frontier = first live seat; cross-family = one pass from **each of two families**):
**Opus 5 → Codex Sol → Review E (if wired) → stop** (`config/providers.json` `review_order`, filtered to
`live_verified` routes in `config/model-registry.json`). Cross-family needs two *different* families (never two
Anthropic passes); **Fable is NOT in the gating order** (rare architecture/long-horizon escalation —
Fable + Opus 5 are one family). Opus 4.8 remains the intended time-bounded compatibility fallback
while the id is genuinely available; it is not the operational Anthropic gate and does not resolve
until its route is `live_verified`. One frontier pass per change-set **except** the cross-family pair.

**Exhaustion opens the next seat only on quota evidence** — `usage-status` shows the seat spent or
soft-capped (a recorded 429 or ledger %), never a probe; probe failure, timeout, or auth error → fail
closed, park (`EDGE-CASES.md`). **Review E** engages only at confirmed exhaustion of the native seats
(or as the second family when one native family is quota-spent), never on a mere outage, and never
sole-gates a risk class — its `ship` there is advisory, owner lands; unwired → park after Opus 5 (`fireworks-usage.md`).

When Sol is needed for **both** code review and MCP judgment the same week: code-review risk gate wins the Sol slot; MCP judgment goes to Opus if Sol is spent or already used on that change-set.

**Review D** when storefront *pixels* change. Slack `#visual-qa` (channel binding in `config/connectors.json`).

**Autonomy limits (disclosed).** Cross-family autonomy needs **≥2 review families**: with fewer (a downgrade or a solo/one-family setup) risk-class work — money, auth, PII, secrets — **parks pending a human** rather than auto-shipping (the routing collapses toward one seat; the discipline holds). And **unattended land-to-prod is a current non-goal** — the executor is gated: `bin/run-brief.py` is **dry-run only** (it plans, shells nothing) and fails closed without an explicit run; landing/publish/send stay behind owner gates (`DOCTRINE.md` §non-goals).

## Dispatch (effective provider for this run)

Resolver records requested intake, effective dispatcher, fallback reason, authors, review scopes, and handoff decision. Its steps:

1. **Implement seat:** Google-MCP bulk → GPT Terra, MCP *judgment* → Sol/Opus (`mcp-routing.md`); else **Grok Build**. Standing non-repo → Grok Bot; theme/layout → Build then Review D; product copy → MCP packet (if needed) then Grok write.
2. **Brief** every job (fields above) and **stamp `review:`** at the router's floor; ambiguous risk → park + ask owner. Do not invent seats.
3. **Route reviews** with `bin/resolve-route.py` (which reads `bin/usage-status.py` and the model registry), never by guesswork.
4. **Selective skills** → mobile/Dart/Flutter/iOS accessibility: `mobile-dev-router`; explicit Cloudflare platform work: `cloudflare-dev-router`; Obsidian vault/Bases/Canvas/CLI work: `knowledge-vault-router`; React specialty, generic MCP builder, or measured web-performance work: `engineering-dev-router`. Put only the matching router plus its exact `~/.agents/skills/<router>/SKILL.md` path in the brief. Unrelated dispatch, implementation, and review lanes get `skills: []`.
5. **Refill + supervise** at the checkpoints you already run (never a daemon): on completion claim the next brief or say why idle (never implement from phone); past-budget lane with no park note → `stalled:`; a return outside scope or into `must_not_touch` → reject + re-scope; two loops with no novel defect → park + escalate; run `usage-status` before any reroute — a whole-pipe outage is ONE outage, don't cascade (`EDGE-CASES.md`).
6. Storefront smoke after a visitor preview URL exists → private `qa-idle-handoff` **Run workflow** (exclusive idle mini). Not a second implementer on the 16 GB box. See `qa-idle-handoff.md`.

## Implement (Grok Build)

1 worktree · 1 branch · named file scope. Style-match; no drive-bys. Return: summary, files, tests run, risks. Never same change-set as Bot. Do not invent GSC/keyword numbers; consume `must_read` snapshots from MCP seats. Resume existing branch on retry; no second worktree for the same objective.

## Review (Opus 5 / Codex Sol / Review E / Website Visual QA)

Code seats read **git diff**. Visual QA reads the **preview URL**. Output: `ship` | `fix-list` | `blocked`. **`blocked` wins** if reviews disagree. Max two fix loops then park unless a novel defect. Cross-family = one pass each from two families, **sequential**, one machine reviewer at a time. Implementer is excluded. Dispatcher review is artifact-only and cannot independently attest to its own brief/risk decision. Review E is an off-box HTTP call, never a Mini process.

## Standing-config changes (this repo included)

A change to `config/`, a cron/LaunchAgent, an MCP config, or a Bot routine is `standing-config` (floor
`single-frontier`, never lower). **Run `bin/doctor.py` (+ `bin/smoketest.py` if scripts changed) before landing** — a broken registry mis-routes every later job.

## Hard bans

- Fable/Sol/Opus as daily coder · author reviewing own artifact · dispatcher-only attestation of its own dispatch intent/risk · two frontier passes from the **same family** counted as cross-family · Cursor Other Models early · Opus/Sol as bulk MCP fetchers · Grok inventing Google metrics without connector/snapshot · two QA minis at once · Build+Bot on one change-set · inventing makework · Review E before confirmed exhaustion · counting Fable + Opus as two families · sending restricted artifacts across agents · asking repeatedly for permission to transfer ordinary configured repo artifacts · hardcoding live IDs/tiers/resets · parking while usable quota exists · metered capacity before included capacity · more than one effective dispatcher in one run · authority from a quality rank · mid-turn account swaps · resolving a route that is not `live_verified`.
