# Magnet Baron orchestration

Day-to-day contract for Codex, Claude Code, Grok Build, Cursor. Deep doctrine: `DOCTRINE.md`. Visual QA: `visual-qa.md`, `grokbot-connection.md`. Pools: `sol-usage.md`, `cursor-usage.md`, `fireworks-usage.md`. Metering: `usage-metering.md` (run `usage-status`, don't hardcode resets). MCP: `mcp-routing.md`. Failures: `EDGE-CASES.md`.

**Authority:** Owner override → brief fields → this file → specialty file for the domain → `DOCTRINE.md` → `EDGE-CASES.md`.

## Seats

| Seat | Tool | Does | Does not |
|------|------|------|----------|
| **Dispatch** | Codex CLI (Terra/Luna) | Queue, assign, status, risk gate | Implement, long review, desktop app |
| **Implement** | Grok Build CLI (`grok`) | Code, tests, Shopify volume, research *without* Google MCP | Grok Bot; Google MCP if connector missing |
| **MCP volume** | Codex **GPT Terra** | Google MCP bulk: GSC, Drive, DataForSEO/Trends | Dispatch-only Luna; default coder |
| **MCP / review judgment** | Codex **Sol** or **Opus 4.8** | Interpret MCP outputs; Sol also Review B | Row-dump fetch loops |
| **Cloud standing** | Grok Bot (xAI VM) | Inbox / scheduled work off the Mini | Same change-set as Build |
| **Review D** | Grok Bot **Website Visual QA** | Storefront preview via Slack | Admin, SimGym, publish |
| **Review A** | Fable 5 (while included) | Hard PR / architecture | Daily typing |
| **Review B** | GPT-5.6 Sol **on Codex** | Diff review when Fable empty | Cursor Sol ($400) |
| **Review C** | Opus 4.8 | Claude reliability pass; MCP judgment | Default implementer |
| **Review E** *(fallback — unwired)* | Fireworks API, pinned open-frontier reasoning model | Last-resort diff review at confirmed quota exhaustion; 2nd family for a cross-family gate | Implement, dispatch, MCP, architecture, Visual QA, sole gate on a risk class, any diff with secrets/PII |
| **IDE** | Cursor **Grok 4.6 / Composer** | Tab + agent on Cursor Models | Other Models until last |
| **Last $** | Cursor Ultra **Other Models $400** | Claude/GPT/Gemini in Cursor after other buckets | Default anything |

**Entry point is always Codex.** Luna/Terra assign; they do not implement or manage after handoff.

**Google MCP:** Opus and appropriate GPT models. **Not** assumed on Grok. Route per `mcp-routing.md`.

**Legwork-or-stop:** volume runs on Grok or GPT-Terra MCP lanes, or parks. Never dump legwork on Sol/Opus/Cursor $ because a probe failed. See `EDGE-CASES.md` for outages.

**No desktop apps** after first device-auth. One implementer process on a 16 GB Mini. Grok Bot.app stays quit on the worker.

## Brief (required)

`objective` · `must_read` · `must_not_touch` · `output_path` · `done_when` · `effort`  
Reviews also: `attack_angle`. Missing field → no dispatch. Paths only; no pasted dumps.

`effort`: `setup` | `low` | `medium` | `high` | `review`.

## Risk gate → review

Two dials: **depth** (how much review) and **order** (which seat). Dispatch stamps `review:` on every brief; the risk gate only raises it, never lowers. Class is read from the diff's paths/resources, not the brief's claim; ambiguity rounds up.

**Depth floor by task class:** stamp `review:` from the class map in `DOCTRINE.md` §Review depth — load that section when routing; it is the single source, not re-summarized here (a lossy copy over-spends frontiers and drops Review D). The risk gate only ever **raises** the floor.

Levels: **none** (Grok, or skip) · **self-check** (implementer's own tests bound to `done_when`, not a second model) · **single-frontier** (first live seat) · **cross-family** (one pass each from two families).

Raise if: auth/money/PII/prod/irreversible · multi-service · Grok conflict/flaky tests. `user said ship` = land, not spend a frontier. **none** / **self-check** still keep the landing lock, tip-bound green test, Review D pixels, and owner publish/send gates.

**Order** (single-frontier = first live seat; cross-family = one pass from **each of two families**):
**Fable (if present) → Codex Sol → Opus 4.8 → Review E (Fireworks, if wired) → stop.**
If Fable missing, start at Sol. Fable + Opus 4.8 are **one** family (Anthropic); Sol is OpenAI; Review E is independent open-weight. Cross-family needs two *different* families — never two Anthropic passes. One frontier pass per change-set **except** the cross-family pair.

**Exhaustion opens the next seat only on quota evidence** — `usage-status` shows the seat spent or soft-capped (a recorded 429 or ledger %), never a probe. Probe failure, timeout, or auth error → fail closed, park (`EDGE-CASES.md`). **Review E** engages only when `usage-status` shows all native review seats spent or soft-capped **and** the brief is time-critical, or as the second family when one native family is quota-spent and only one remains (never on a mere outage); never as sole gate on a risk class (its `ship` there is advisory — owner lands). Unwired → park after 4.8. Detail: `fireworks-usage.md`, `usage-metering.md`.

When Sol is needed for **both** code review and MCP judgment the same week: code-review risk gate wins the Sol slot; MCP judgment goes to Opus if Sol is spent or already used on that change-set.

**Review D** when storefront *pixels* change. Slack `#visual-qa`.

## Dispatch (Codex CLI)

1. Needs **Google MCP**? → GPT Terra (bulk) or Sol/Opus (judgment only). See `mcp-routing.md`.
2. Else default **Grok Build** for implement.
3. Standing non-repo → Grok Bot. Theme/layout → Build then Review D.
4. Product copy: MCP research packet first (if needed), then Grok write.
5. Ambiguous risk → park and ask owner (`EDGE-CASES.md`). Do not invent seats.
6. On completion: refill or state why idle. Never implement from phone.
7. Route reviews by `usage-status` seat state (spent / capped / next reset), never by guesswork.
8. Supervise at the checkpoints you already run, not continuously: past-budget lane with no park note → `stalled:`; return outside scope or into `must_not_touch` → reject + re-scope; two loops, no novel defect → park + escalate. Run `usage-status` before any reroute — a whole-pipe outage is one outage, diagnose don't cascade. No watcher daemon (`EDGE-CASES.md`).

## Implement (Grok Build)

1 worktree · 1 branch · named file scope. Style-match; no drive-bys. Return: summary, files, tests run, risks. Never same change-set as Bot. Do not invent GSC/keyword numbers; consume `must_read` snapshots from MCP seats. Resume existing branch on retry; no second worktree for the same objective.

## Review (Fable / Codex Sol / 4.8 / Fireworks Review E / Website Visual QA)

Code seats read **git diff**. Visual QA reads the **preview URL**. Output: `ship` | `fix-list` | `blocked`. **`blocked` wins** if reviews disagree. Max two fix loops then park unless a novel defect. Cross-family = one pass each from two families, **sequential**, one machine reviewer at a time; Review E is an off-box HTTP call, never a Mini process. Fix loops return to the issuing seat; a seat spent mid-loop → park the loop.

## Hard bans

- Fable/Sol/Opus as daily coder · Opus 5 default · two frontier passes from the **same family** on one branch (the cross-family gate pair — one pass each from two families — is the only two-pass case) · Cursor Other Models early · Opus/Sol as bulk MCP fetchers · Grok inventing Google metrics without connector/snapshot · Build+Bot on one change-set · inventing makework · two implementer CLIs on 16 GB · Grok Bot.app open on the worker · Visual QA in Shopify Admin or SimGym · moving legwork to scarce seats on outage · Review E before confirmed exhaustion or on an outage/probe signal · Review E as implementer or sole land-gate · counting Fable + Opus 4.8 as two families · sending secrets/PII to a third-party inference host
