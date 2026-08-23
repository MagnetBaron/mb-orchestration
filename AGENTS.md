# Magnet Baron orchestration

Day-to-day contract for Codex, Claude Code, Grok Build, Cursor. ~100 lines max. Deep doctrine: `DOCTRINE.md` (do not load into every session).

## Seats

| Seat | Tool | Does | Does not |
|------|------|------|----------|
| **Dispatch** | Codex Terra/Luna | Queue, assign, status, risk gate | Implement, long review |
| **Implement** | Grok Build / Bot | All volume: code, tests, research | Solo land high-risk |
| **Review A** | Fable 5 (while included) | Hard PR / architecture | Daily typing |
| **Review B** | GPT-5.6 Sol | Diff review when Fable empty | Phone chatter |
| **Review C** | Opus 4.8 | Claude reliability pass | Default implementer |
| **IDE** | Cursor Models | Tab / Auto | Other Models until last |
| **Last $** | Cursor $400 Other | Only after Grok+Claude+Codex review spent | Default anything |

**Legwork-or-stop:** volume work runs on Grok or parks. Never dump legwork on Claude/Codex/Cursor because a health probe failed — verify live lanes first.

## Brief (required)

`objective` · `must_read` · `must_not_touch` · `output_path` · `done_when` · `effort`  
Reviews also: `attack_angle`. Missing field → no dispatch. Paths only; no pasted dumps.

## Risk gate → review

Review if: auth/money/PII/prod data/irreversible · multi-service · Grok conflict/flaky tests · user said ship.

Order: **Fable → Sol → Opus 4.8 → stop**. One frontier pass per change-set. Post-downgrade: Sol → 4.8 only.

## Dispatch (Codex)

Default assign Grok. On completion: refill next brief or state why idle. Report: status, owner, blocked, next 3 steps. Never implement from phone.

## Implement (Grok)

1 worktree · 1 branch · named file scope. Style-match; no drive-bys. Return: summary, files, tests run, risks.

## Review (Fable / Sol / 4.8)

Read **git diff**, not the worker story. Output: `ship` | `fix-list` | `blocked`. No reimplement unless asked. Max two fix loops then park unless a novel defect.

## Hard bans

- Fable/Sol as daily coder · Opus 5 default · dual frontiers same branch · Cursor Other Models early · inventing makework to burn quota
