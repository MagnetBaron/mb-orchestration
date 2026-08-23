# Multi-bucket doctrine (trimmed)

Distilled from a production multi-provider architecture. Keep this out of every agent context; load only when designing or debugging the system. Day-to-day agents use `AGENTS.md` only.

Specialty maps (load by domain): `mcp-routing.md`, `sol-usage.md`, `cursor-usage.md`, `visual-qa.md`, `EDGE-CASES.md`.

## Economics

Unspent quota at reset is waste. Buckets are asymmetric:

| Class | Your seats | Job |
|-------|------------|-----|
| **Abundant volume** | Grok Super Heavy / Build / Bot | Code, listings, non-Google research, standing Bot work |
| **MCP volume** | Codex GPT Terra (Google MCP) | GSC, Drive, DataForSEO/Trends fetches |
| **Scarce judgment** | Claude (Fable while included, else Opus 4.8); Codex Sol | Verify, land-gate, hard review, MCP interpretation |
| **Dispatcher** | Codex Terra/Luna | Queue, assign, status — never implement |
| **Last $** | Cursor Other Models $400 | Only after others are spent |
| **Metered fallback** | Fireworks **Review E** (unwired) | Last-resort / cross-family second-family diff review. No reset — the drain law never applies. |

**Legwork-or-stop:** volume work runs on Grok, or on GPT Terra when Google MCP is required, or parks with a note. Never silently move legwork onto Sol/Opus/Cursor $ because a probe failed. Verify outages with one live check, then fail closed (`EDGE-CASES.md`).

## Roles (not models)

```
OWNER — spend, credentials, destructive ops, authority expansion
  └─ DISPATCH (Codex Terra/Luna) — queue, risk gate, assign, report
       ├─ IMPLEMENT (Grok Build) — code/listings in worktrees; never lands alone on high risk
       ├─ MCP VOLUME (GPT Terra) — Google connector fetches → output_path snapshots
       ├─ REVIEW D (Grok Bot Website Visual QA) — Slack + shopifypreview.com; app quit on Mini
       ├─ REVIEW A–C (Fable → Sol → Opus 4.8) — git diff or MCP judgment; ship | fix-list | blocked
       └─ REVIEW E (Fireworks, if wired) — last-resort / cross-family 2nd family; off-box; unwired = park after 4.8
```

One lead/dispatcher at a time. Codex remains the only entry point.

**Authority:** Owner → brief → `AGENTS.md` → specialty file → this doctrine → `EDGE-CASES.md`.

## Correlated failure (two pipes, not four seats)

The review seats are not independent. **Fable and Opus 4.8 are one pipe** (Anthropic via teamclaude). **Sol, Terra, and Luna are one pipe** (Codex) — so dispatch shares a pipe with a reviewer. Native review therefore has **two** families, not four seats. Consequences:

- A teamclaude blip looks like Fable **and** Opus 4.8 down at once; a Codex blip looks like Sol **and** dispatch down. That is **one** outage, not two — do not cascade to Review E or Cursor on it (`EDGE-CASES.md`).
- Cross-family (safety gate 5) on only Anthropic + OpenAI means one spent family leaves the pair unsatisfiable. **Review E (Fireworks open-weight) is the first genuinely independent third family** — that, not raw capacity, is why it earns a seat.

## Brief schema (required fields)

`objective` · `must_read` · `must_not_touch` · `output_path` · `done_when` · `effort`  
Review seats also need `attack_angle`.

`effort`: `setup` | `low` | `medium` | `high` | `review`.

No field → do not dispatch. Point at paths; never paste large diffs into the brief.

## Shopify scale

Same Codex entry scales to more **basic product edits** without extra Visual QA:

- Title / body / metafield / price / SKU / tags → Codex → Grok Build (after MCP research packet if needed) → done. No Review D.
- Many SKUs, same template → one catalog lane, not N preview walks.
- Theme, section, PDP chrome, CSS → add Review D Slack ticket after a visitor preview URL exists.
- Publish and SimGym stay owner/human. Review D never auto-scales into Admin.

## Review depth (floor, not ceiling)

Generalizes Shopify scale to every task class. Dispatch stamps `review:` from this floor; the `AGENTS.md` risk gate only raises it. Class is derived from the diff's touched paths/resources, not the brief's claim; ambiguity rounds up one level. This section is the **single source** of the class map — `AGENTS.md` points here rather than duplicating it, and dispatch loads this section when stamping `review:` even though the rest of DOCTRINE is design-time.

| Task class (vault category) | Routine: single item, reversible | Elevated: bulk ≥50 / new logic / site-wide | Risk-gate hit → |
|---|---|---|---|
| Internal notes, research, kit-research, analytics read, scratch | none | self-check | single-frontier (secrets/PII in the note) |
| Content prose: blog body, product copy, alt text | self-check (voice lint) | self-check + owner proofread | single-frontier |
| Catalog data, non-money: title/body/metafield/SKU/tags | self-check | single-frontier | cross-family |
| Money data: pricing, inventory counts, barcodes, PO/ACH | single-frontier | cross-family | cross-family |
| SEO structural: schema/canonical/redirect/robots/sitemap | self-check (single URL) | single-frontier | cross-family (removals/disavow) |
| Storefront theme / Liquid | self-check + Review D | single-frontier + Review D | cross-family (checkout/auth-adjacent) |
| Repo/app code with green tests | self-check (tests are the reviewer) | single-frontier | cross-family (auth/secrets/untrusted shell) |
| Standing config: webhooks, cron/LaunchAgent, MCP config, Omnisend automation, Bot routine | single-frontier (floor never lower — standing rules self-perpetuate) | single-frontier | cross-family (OAuth/secrets/prod URL) |
| Outbound irreversible: campaign send, publish, URL-removal, fulfillment label/Flow | single-frontier + owner | cross-family + owner | cross-family + owner |
| Legal / HR | cross-family + human | cross-family + human | cross-family + human |

Composition:
- **Gate wins upward, always.** The right column *is* the `AGENTS.md` risk gate, by reference — the matrix holds no risk logic of its own.
- **none / self-check remove *review* only** — landing lock, tip-bound green test, Review D pixels, owner publish/send gates still apply.
- Levels: **none** (Grok, or skip) · **self-check** (implementer tests bound to `done_when`, not a second model) · **single-frontier** (first live seat in the order) · **cross-family** (one pass each from two families; Fable + 4.8 is one family; one native family quota-spent → Review E fills the second slot; none → park).

## Concurrency

- Default question: which **disjoint** lanes can run now?
- Ceiling, not target. Prefer fewer deeper lanes when faster.
- **1 lane = 1 worktree = 1 branch = named file scope** (dispatcher creates the worktree).
- Claims cover **resources**, not just files: a Build branch and a Bot standing routine must not touch the same product range, campaign, or sheet — the real collision is one *resource*, not one change-set. Bot routines declare their surfaces; dispatch overlap-checks them like file scopes.
- Full test suite / main landing: **exactly one at a time**.
- Review D is off-box; it does not count as a second implementer on the Mini.
- MCP volume (Terra) may run beside Grok when scopes and output paths do not collide.

## Refill law

On every completion: claim next ready brief or explain idle. Idle beside a non-empty useful queue is a defect. Empty queue → idle is correct. Never invent makework.

Parked briefs keep status `parked: <reason>` in the same backlog the dispatcher uses.

**Review-starvation guard** (verification saturates before implementers): at **≥3 change-sets awaiting review**, Build claims only `none` / `self-check` briefs until the review queue drains. Pre-reset drain targets the review queue first.

## Reset-aware placement

1. **Pre-reset:** drain surplus on real backlog (Sol toward 90%, Heavy volume).
2. **Post-reset:** fire staged volume campaigns when the bucket refreshes.
3. **Mid-cycle:** do not conserve abundant capacity; do not burn Sol on row dumps.

Reset instants and seat state come from `usage-status` (`usage-metering.md`) — no reset time is hardcoded in these files, and remaining quota is never LLM-estimated.

## Safety gates (adopt in order)

1. Risk gate before frontier review spend
2. Worktree isolation + file claims
3. One green test command bound to exact commit tip (when the repo has it)
4. One landing lock for main
5. Cross-family review on auth, money, PII, secrets, untrusted shell — **one pass each from two reviewer families**; Fable + Opus 4.8 are one family (Anthropic); if only one native family has quota left (the other quota-spent), Review E (Fireworks) may fill the second slot; if none, park
6. Max two fix/review loops, then park unless a **novel** defect appears
7. Visual QA only on allowlisted hosts via visitor preview; never Admin cookies on the Bot computer
8. Google metrics only from MCP connectors or explicit snapshots — never invented

## Explicit non-goals (for now)

- Full overnight autonomous land-to-prod without phone approval
- Official `grok` CLI → named Grok Bot (does not exist; use Slack)
- Grok Bot.app as a worker process on the 16 GB Mini
- SimGym or collaborator accounts for Website Visual QA
- Treating Opus 5 as default (pin 4.8)
- Using Cursor $400 as a worker pool
- Moving volume onto scarce seats when Grok or Terra is down
- Review E (Fireworks) as a routine reviewer, implementer, or MCP seat — review-only, and only at confirmed exhaustion or as a cross-family second family
- A provider-neutral fallback framework — Review E is one wrapper script + `fireworks-usage.md`, nothing more
