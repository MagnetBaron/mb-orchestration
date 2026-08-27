# Multi-bucket doctrine (trimmed)

Distilled from a production multi-provider architecture. Keep this out of every agent context;
load only when designing or debugging the system. Day-to-day agents use `AGENTS.md` only.

The invariant here is the **shape** — capability levels, families, gates. The **contents** —
which providers, plans, connectors, and windows exist — live in `config/` and are read by `bin/`
scripts, so this doctrine never goes stale on a market or plan change. Specialty maps load by
domain: `mcp-routing.md`, `sol-usage.md`, `cursor-usage.md`, `fireworks-usage.md`,
`usage-metering.md`, `visual-qa.md`, `grokbot-connection.md`, `analytics-clarity.md`, `EDGE-CASES.md`.

## Economics

Unspent quota at reset is waste. Buckets are asymmetric (current providers in `config/providers.json`):

| Class | Capability level | Job |
|-------|------------------|-----|
| **Abundant volume** | terra | Grok Build/Bot — code, listings, non-Google research, standing Bot work |
| **MCP volume** | terra | GPT Terra — Google MCP fetches to `output_path` |
| **Scarce judgment** | frontier / sole | Opus 4.8 (Anthropic gate) + Codex Sol — verify, land-gate, hard review; Fable = optional architecture only, out of gating |
| **Dispatcher** | luna | Codex Terra/Luna — queue, assign, status — never implement |
| **Last $** | terra | Cursor Other Models $400 — only after others are spent |
| **Metered fallback** | frontier | Review E (independent family, unwired) — last-resort / cross-family second family. No reset — the drain law never applies. |

**Claude capacity is five rolling seats, not one bucket** (`config/subscriptions.json`): Max + 2
Team-premium (Fable) + 2 Pro (Opus overflow). teamclaude rotates them and tracks per-model caps,
so aggregate Claude capacity ≫ any single account and Fable survives one seat capping.

**Legwork-or-stop:** volume runs on Grok, or on GPT Terra when Google MCP is required, or parks with a note. Never silently move legwork onto Sol/Opus/Cursor $ because a probe failed. Verify outages with one live check, then fail closed (`EDGE-CASES.md`).

## Reserve, never-strand, and cost (drain economics)

Per-seat drain policy (`config/usage-windows.json`: `drain`, `reserve_pct`, `intake`, `billing`) turns the
above into an executable order (`bin/drain-plan.py`, `bin/resolve-route.py`):

- **A reserve is a priority tier, not a wall.** The intake/dispatch seat holds headroom so dispatch never starves — but that headroom **yields** the moment nothing else is live. There is no state where usable quota exists and the engine stops for a *self-imposed* cap. Genuine exhaustion (a recorded 429) and an unsatisfiable safety gate are the only stops. `soft_cap` semantics are subsumed: a cap lowers priority, never removes availability.
- **Dispatch codes last, but it codes.** Reserves protect dispatch's own throughput sized to observed consumption × margin; when every worker is spent, the intake seat implements. With one or two subscriptions the dispatch account is also the coder — by design, not by exception.
- **Subscription tokens before API dollars.** `included` capacity is drained before any `metered` seat (Cursor Other Models, Review E). Metered spend is a last resort, and its use while included capacity is available is a defect the dashboard scores.
- **Use it before you lose it.** Weekly/monthly buckets near reset with capacity unused are drained first; rolling windows refill and can wait. This is the reset-aware placement below, made concrete.
- **Turn-boundary rotation.** Seats are chosen with runway to finish the task; a freshly reset account is brought in at the next boundary, never mid-turn.

Capabilities (browser/connector/family) and model **prowess** are data (`config/providers.json` +
`config/connectors.json`): the router assigns by what a seat *can do* and how strong it is, not by
habit. A new or upgraded model (Opus 5.1, Fable 5.1, a Fable/Sol successor) slots in by binding to a
capability level — one config edit (`providers.json` §model_slot_in), no code or prose change.

## Roles (not models) — and entry vs dispatch

```
OWNER — spend, credentials, destructive ops, authority expansion
  └─ DISPATCH (one config-bound provider; default Codex Luna) — queue, risk gate, assign, report
       ├─ IMPLEMENT (Grok Build) — code/listings in worktrees; never lands alone on high risk
       ├─ MCP VOLUME (GPT Terra) — Google connector fetches → output_path snapshots
       ├─ REVIEW D (Grok Bot Website Visual QA) — Slack + preview URL; app quit on Mini
       ├─ REVIEW (Opus 4.8 → Sol → Review E) — git diff or MCP judgment; ship | fix-list | blocked; Fable = optional architecture only
       └─ REVIEW E (independent family, if wired) — last-resort / cross-family 2nd family; off-box
```

**Entry surface ≠ dispatcher.** Where a request is typed is the user's choice (`config/entrypoints.json`
entry surfaces). Who assigns seats is exactly one dispatcher. A non-dispatcher surface drafts a
brief and hands it over. Moving the whole system to a user without the default dispatcher is a
one-line `entrypoints.json` edit — the single-dispatcher invariant is unchanged; only the holder moves.

**Authority:** Owner → brief → `AGENTS.md` → specialty file → this doctrine → `EDGE-CASES.md`. Account facts (who/what/when) come from `config/`, read by `bin/` — never re-typed into prose.

## Capability levels (durable) vs providers (replaceable)

Routing requirements are capability **levels** — `frontier`, `sole`, `terra`, `luna` — not models or
model families. Providers bound to a level (`config/providers.json`) are replaceable: swap a model or
backing without touching policy. Roles (`config/roles.json`) are a loading mechanism *inside* a seat;
they never create a seat, change the review order, or grant credentials. `bin/generate-roles.py`
emits host-native Claude/Grok agent files + an owner-applied Codex TOML fragment, and refuses a role
whose seat is not a provider at the role's level.

## Correlated failure (pipes, not independent seats)

The review seats are not independent. **Fable and Opus 4.8 are one pipe** (Anthropic via teamclaude, across the five seats). **Sol, Terra, and Luna are one pipe** (Codex) — so dispatch shares a pipe with a reviewer. Native review therefore has **two** families, not four seats. Consequences:

- A teamclaude blip looks like Fable **and** Opus 4.8 down at once; a Codex blip looks like Sol **and** dispatch down. That is **one** outage, not two — do not cascade to Review E or Cursor on it (`EDGE-CASES.md`). With five Claude seats, "teamclaude down" is rarer than one seat capping — check per-seat state in `usage-status` before calling the whole Anthropic pipe dead.
- Cross-family (safety gate 5) on only Anthropic + OpenAI means one spent family leaves the pair unsatisfiable. **Review E (independent open-weight) is the first genuinely independent third family** — that, not raw capacity, is why it earns a seat.

## Brief schema (required fields)

`objective` · `must_read` · `must_not_touch` · `output_path` · `done_when` · `effort`
Review seats also need `attack_angle`. `effort`: `setup` | `low` | `medium` | `high` | `review`.
No field → do not dispatch. Point at paths; never paste large diffs into the brief.

## Shopify scale

Same entry scales to more **basic product edits** without extra Visual QA:

- Title / body / metafield / price / SKU / tags → dispatch → Grok Build (after MCP research packet if needed) → done. No Review D.
- Many SKUs, same template → one catalog lane, not N preview walks.
- Theme, section, PDP chrome, CSS → add Review D Slack ticket after a visitor preview URL exists.
- Publish and SimGym stay owner/human. Review D never auto-scales into Admin.

## Review depth (floor, not ceiling)

Generalizes Shopify scale to every task class. The floor by class is defined **once, machine-readable,
in `config/review-depth.json`** and applied by `bin/resolve-route.py`; this table is the human
explanation and stays in sync (`bin/doctor.py` checks every class id appears here). Dispatch stamps
`review:` from the floor; the `AGENTS.md` risk gate only raises it. Class is derived from the diff's
touched paths/resources, not the brief's claim; ambiguity rounds up one level.

| Class id (`review-depth.json`) | Routine: single item, reversible | Elevated: bulk ≥50 / new logic / site-wide | Risk-gate hit → |
|---|---|---|---|
| `internal-notes` (research, kit-research, analytics read, scratch) | none | self-check | single-frontier (secrets/PII in the note) |
| `content-prose` (blog body, product copy, alt text) | self-check (voice lint) | self-check + owner proofread | single-frontier |
| `catalog-data` (non-money: title/body/metafield/SKU/tags) | self-check | single-frontier | cross-family |
| `money-data` (pricing, inventory counts, barcodes, PO/ACH) | single-frontier | cross-family | cross-family |
| `seo-structural` (schema/canonical/redirect/robots/sitemap) | self-check (single URL) | single-frontier | cross-family (removals/disavow) |
| `storefront-theme` (theme / Liquid / CSS / PDP) | self-check + Review D | single-frontier + Review D | cross-family (checkout/auth-adjacent) |
| `repo-code` (with green tests) | self-check (tests are the reviewer) | single-frontier | cross-family (auth/secrets/untrusted shell) |
| `standing-config` (webhooks, cron/LaunchAgent, MCP config, `config/`, automation, Bot routine) | single-frontier (floor never lower — standing rules self-perpetuate) | single-frontier | cross-family (OAuth/secrets/prod URL) |
| `outbound-irreversible` (campaign send, publish, URL-removal, fulfillment label/Flow) | single-frontier + owner | cross-family + owner | cross-family + owner |
| `legal-hr` | cross-family + human | cross-family + human | cross-family + human |

Composition:
- **Gate wins upward, always.** The right column *is* the `AGENTS.md` risk gate, by reference.
- **none / self-check remove *review* only** — landing lock, tip-bound green test, Review D pixels, owner publish/send gates still apply.
- Levels: **none** (Grok, or skip) · **self-check** (implementer tests bound to `done_when`, not a second model) · **single-frontier** (first live seat in the order) · **cross-family** (one pass each from two families; Fable + 4.8 is one family; one native family quota-spent → Review E fills the second slot; none → park). Run `bin/resolve-route.py` for the concrete live chain.

## Concurrency

- Default question: which **disjoint** lanes can run now?
- Ceiling, not target. Prefer fewer deeper lanes when faster.
- **1 lane = 1 worktree = 1 branch = named file scope** (dispatcher creates the worktree).
- Claims cover **resources**, not just files: a Build branch and a Bot standing routine must not touch the same product range, campaign, or sheet — the real collision is one *resource*. Bot routines declare their surfaces; dispatch overlap-checks them like file scopes.
- Full test suite / main landing: **exactly one at a time**.
- Review D is off-box; it does not count as a second implementer on the Mini.
- MCP volume (Terra) may run beside Grok when scopes and output paths do not collide.

## Refill law

On every completion: claim next ready brief or explain idle. Idle beside a non-empty useful queue is a defect. Empty queue → idle is correct. Never invent makework. Parked briefs keep status `parked: <reason>` in the same backlog the dispatcher uses.

**Review-starvation guard** (verification saturates before implementers): at **≥3 change-sets awaiting review**, Build claims only `none` / `self-check` briefs until the review queue drains. Pre-reset drain targets the review queue first.

## Reset-aware placement

1. **Pre-reset:** drain surplus on real backlog (Sol toward its soft cap, Heavy volume).
2. **Post-reset:** fire staged volume campaigns when the bucket refreshes.
3. **Mid-cycle:** do not conserve abundant capacity; do not burn Sol on row dumps.

Reset instants and seat state come from `bin/usage-status.py` (reading `config/usage-windows.json` + `config/usage-ledger.json`, `usage-metering.md`) — no reset time is hardcoded in these files, and remaining quota is never LLM-estimated.

## Safety gates (adopt in order)

1. Risk gate before frontier review spend
2. Worktree isolation + file claims
3. One green test command bound to exact commit tip (when the repo has it)
4. One landing lock for main
5. Cross-family review on auth, money, PII, secrets, untrusted shell — **one pass each from two reviewer families**; Fable + Opus 4.8 are one family; if only one native family has quota left, Review E (if wired) may fill the second slot; if none, park
6. Max two fix/review loops, then park unless a **novel** defect appears
7. Visual QA only on allowlisted hosts via visitor preview; never Admin cookies on the Bot computer
8. Google metrics only from MCP connectors or explicit snapshots — never invented
9. `bin/doctor.py` green before landing a `standing-config` change (a broken registry mis-routes everything after it)

## Explicit non-goals (for now)

- Full overnight autonomous land-to-prod without phone approval
- Official `grok` CLI → named Grok Bot (does not exist; use Slack)
- Grok Bot.app as a worker process on the 16 GB Mini
- SimGym or collaborator accounts for Website Visual QA
- Treating Opus 5 as default (pin 4.8; enforce via `availableModels`)
- Using Cursor $400 as a worker pool
- Moving volume onto scarce seats when Grok or Terra is down
- Review E as a routine reviewer, implementer, or MCP seat — review-only, and only at confirmed exhaustion or as a cross-family second family
- A provider-neutral fallback framework beyond what `config/providers.json` already expresses (Review E is one wrapper + `fireworks-usage.md`)
