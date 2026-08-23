# Magnet Baron orchestration

Day-to-day contract for Codex, Claude Code, Grok Build, Cursor. ~100 lines max. Deep doctrine: `DOCTRINE.md` (do not load into every session).

## Seats

| Seat | Tool | Does | Does not |
|------|------|------|----------|
| **Dispatch** | Codex CLI (Terra/Luna) | Queue, assign, status, risk gate | Implement, long review, desktop app |
| **Implement** | Grok Build CLI (`grok`) | All local volume: code, tests, research | Grok Bot, desktop apps |
| **Cloud standing** | Grok Bot (xAI VM) | Scheduled / inbox-style work off the Mini | Same change-set as Build; no local CLI |
| **Review A** | Fable 5 (while included) | Hard PR / architecture | Daily typing |
| **Review B** | GPT-5.6 Sol | Diff review when Fable empty | Phone chatter |
| **Review C** | Opus 4.8 | Claude reliability pass | Default implementer |
| **IDE** | Cursor CLI | Tab-class / Models agents | App + Other Models until last |
| **Last $** | Cursor $400 Other | After Grok+Claude+Codex review spent | Default anything |

**Legwork-or-stop:** volume work runs on Grok Build or parks. Never dump legwork on Claude/Codex/Cursor because a probe failed. Bot routines can starve Heavy — keep Bot to standing work only.

**No desktop apps** after first device-auth. One implementer process on a 16 GB Mini.

## Brief (required)

`objective` · `must_read` · `must_not_touch` · `output_path` · `done_when` · `effort`  
Reviews also: `attack_angle`. Missing field → no dispatch. Paths only; no pasted dumps.

## Risk gate → review

Review if: auth/money/PII/prod data/irreversible · multi-service · Grok conflict/flaky tests · user said ship.

Order: **Fable → Sol → Opus 4.8 → stop**. One frontier pass per change-set. Post-downgrade: Sol → 4.8 only.

## Dispatch (Codex CLI)

Default assign **Grok Build**. Standing non-repo → **Grok Bot** routine. On completion: refill or state why idle. Never implement from phone.

## Implement (Grok Build)

1 worktree · 1 branch · named file scope. Style-match; no drive-bys. Return: summary, files, tests run, risks. Never same change-set as Bot.

## Review (Fable / Sol / 4.8)

Read **git diff**, not the worker story. Output: `ship` | `fix-list` | `blocked`. Max two fix loops then park unless a novel defect.

## Hard bans

- Fable/Sol as daily coder · Opus 5 default · dual frontiers same branch · Cursor Other Models early · Build+Bot on one change-set · inventing makework · running two implementer CLIs on 16 GB
