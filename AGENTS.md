# Magnet Baron orchestration

Cross-tool contract for Codex, Claude Code, Grok Build, Cursor. Keep this file under ~120 lines.

## Seats

| Seat | Tool | Does | Does not |
|------|------|------|----------|
| **Dispatch** | Codex (Terra/Luna) | Queue, assign, status, risk gate | Implement, long review |
| **Implement** | Grok Build / Bot | Code, tests, refactors, research | Final ship verdict alone on high risk |
| **Review A** | Fable 5 (while included) | Architecture, hard PR review | Daily typing |
| **Review B** | GPT-5.6 Sol | Terminal/agent review when Fable empty | Phone chatter |
| **Review C** | Opus 4.8 | Claude reliability pass | Default implementer |
| **IDE** | Cursor Models only | Tab, Auto, first-party agents | Other Models until last resort |
| **Last $** | Cursor $400 Other Models | Only when Grok + Claude 5h + Codex review are spent | Default anything |

## Risk gate (review required if any true)

- Auth, money, PII, production data, irreversible migrations
- Multi-service / shared contracts
- Grok self-conflict or flaky tests
- User said ship / release

Otherwise: implement → tests → done. One frontier review max per change-set.

## Reviewer order

1. Fable 5 (Max / Premium seats, this month)
2. GPT-5.6 Sol (short diff + verdict only)
3. Opus 4.8 via teamclaude
4. Stop — do not open Cursor Other Models

After plan downgrade (Pro + Team Standard): drop Fable from included routes; Sol then 4.8.

## Dispatch rules (Codex)

- Default assign: **Grok**
- Review assign: **Fable → Sol → 4.8** by remaining quota
- Never implement from the phone agent
- Report: status, owner, blocked reason, next 3 steps

## Implement rules (Grok)

- Worktrees for parallel jobs
- Match existing file style; no drive-by refactors
- Return: summary, files touched, test commands run, open risks

## Review rules (Fable / Sol / 4.8)

- Read **git diff**, not the worker summary
- Output: ship | fix-list | blocked
- No reimplementation unless asked

## Hard bans

- Fable or Sol as daily coder
- Opus 5 as default (prefer 4.8)
- Dual frontiers implementing the same branch
- Cursor Other Models before other pools are empty
- teamclaude not required for non-Claude tools
