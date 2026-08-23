# Magnet Baron orchestration

Day-to-day contract for Codex, Claude Code, Grok Build, Cursor. Deep doctrine: `DOCTRINE.md`. Visual QA: `visual-qa.md`. Pools: `sol-usage.md`, `cursor-usage.md`.

## Seats

| Seat | Tool | Does | Does not |
|------|------|------|----------|
| **Dispatch** | Codex CLI (Terra/Luna) | Queue, assign, status, risk gate | Implement, long review, desktop app |
| **Implement** | Grok Build CLI (`grok`) | All local volume: code, tests, research | Grok Bot, desktop apps |
| **Cloud standing** | Grok Bot (xAI VM) | Inbox / scheduled work off the Mini | Same change-set as Build; no local CLI |
| **Review D** | Grok Bot **Website Visual QA** | Click-through unpublished storefront via Slack ticket | Admin, SimGym, publish, Mini app |
| **Review A** | Fable 5 (while included) | Hard PR / architecture | Daily typing |
| **Review B** | GPT-5.6 Sol **on Codex** | Diff review when Fable empty | Phone chatter; Cursor Sol (that is $400) |
| **Review C** | Opus 4.8 | Claude reliability pass | Default implementer |
| **IDE** | Cursor **Grok 4.6 / Composer** | Tab + agent on Cursor Models pool | Other Models until last |
| **Last $** | Cursor Ultra **Other Models $400** | Claude/GPT/Gemini *inside Cursor* after other buckets | Default anything; not Grok 4.6 |

**Entry point is always Codex.** Luna/Terra assign; they do not implement or manage after handoff.

**Legwork-or-stop:** volume runs on Grok Build or parks. Never dump legwork on Claude/Codex/Cursor Other Models because a probe failed. Bot routines can starve Heavy — keep Bot to standing + Review D only.

**No desktop apps** after first device-auth. One implementer process on a 16 GB Mini. Grok Bot.app stays quit on the worker.

## Brief (required)

`objective` · `must_read` · `must_not_touch` · `output_path` · `done_when` · `effort`  
Reviews also: `attack_angle`. Missing field → no dispatch. Paths only; no pasted dumps.

## Risk gate → review

Code review if: auth/money/PII/prod data/irreversible · multi-service · Grok conflict/flaky tests · user said ship.

Code order: **Fable → Codex Sol → Opus 4.8 → stop**. One frontier pass per change-set. Codex Sol weekly cap: `sol-usage.md` (90%, reset Sun 10 PM CT).

**Review D** when storefront *pixels* change. Not for copy/metafield/SKU-only edits. Slack `#visual-qa` (`visual-qa.md`, `visual-qa-slack.md`).

## Dispatch (Codex CLI)

Default assign **Grok Build**. Standing non-repo → **Grok Bot**. Theme/layout ship → Build then Review D ticket. Cursor Other Models only if owner said so or Last $ is in play. On completion: refill or state why idle. Never implement from phone.

## Implement (Grok Build)

1 worktree · 1 branch · named file scope. Style-match; no drive-bys. Return: summary, files, tests run, risks. Never same change-set as Bot.

## Review (Fable / Codex Sol / 4.8 / Website Visual QA)

Code seats read **git diff**. Visual QA reads the **preview URL**. Output: `ship` | `fix-list` | `blocked`. Max two fix loops then park unless a novel defect.

## Hard bans

- Fable/Sol as daily coder · Opus 5 default · dual frontiers same branch · Cursor Other Models early · treating Cursor Grok as the $400 · Build+Bot on one change-set · inventing makework · two implementer CLIs on 16 GB · Grok Bot.app open on the worker · Visual QA in Shopify Admin or SimGym
