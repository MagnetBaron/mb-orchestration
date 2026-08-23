# Magnet Baron orchestration

Day-to-day contract for Codex, Claude Code, Grok Build, Cursor. Deep doctrine: `DOCTRINE.md`. Visual QA: `visual-qa.md`. Pools: `sol-usage.md`, `cursor-usage.md`. MCP: `mcp-routing.md`. Failures: `EDGE-CASES.md`.

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

Code review if: auth/money/PII/prod data/irreversible · multi-service · Grok conflict/flaky tests · user said ship.

Code order: **Fable (if present) → Codex Sol → Opus 4.8 → stop**. If Fable missing, start at Sol. One frontier pass per change-set. Sol weekly: `sol-usage.md` (90%, reset Sun 10 PM CT).

When Sol is needed for **both** code review and MCP judgment the same week: code-review risk gate wins the Sol slot; MCP judgment goes to Opus if Sol is spent or already used on that change-set.

**Review D** when storefront *pixels* change. Slack `#visual-qa`.

## Dispatch (Codex CLI)

1. Needs **Google MCP**? → GPT Terra (bulk) or Sol/Opus (judgment only). See `mcp-routing.md`.
2. Else default **Grok Build** for implement.
3. Standing non-repo → Grok Bot. Theme/layout → Build then Review D.
4. Product copy: MCP research packet first (if needed), then Grok write.
5. Ambiguous risk → park and ask owner (`EDGE-CASES.md`). Do not invent seats.
6. On completion: refill or state why idle. Never implement from phone.

## Implement (Grok Build)

1 worktree · 1 branch · named file scope. Style-match; no drive-bys. Return: summary, files, tests run, risks. Never same change-set as Bot. Do not invent GSC/keyword numbers; consume `must_read` snapshots from MCP seats. Resume existing branch on retry; no second worktree for the same objective.

## Review (Fable / Codex Sol / 4.8 / Website Visual QA)

Code seats read **git diff**. Visual QA reads the **preview URL**. Output: `ship` | `fix-list` | `blocked`. **`blocked` wins** if reviews disagree. Max two fix loops then park unless a novel defect.

## Hard bans

- Fable/Sol/Opus as daily coder · Opus 5 default · dual frontiers same branch · Cursor Other Models early · Opus/Sol as bulk MCP fetchers · Grok inventing Google metrics without connector/snapshot · Build+Bot on one change-set · inventing makework · two implementer CLIs on 16 GB · Grok Bot.app open on the worker · Visual QA in Shopify Admin or SimGym · moving legwork to scarce seats on outage
