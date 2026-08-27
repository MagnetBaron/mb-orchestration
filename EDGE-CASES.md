# Edge cases and recovery

Load when something breaks or the brief does not fit a clean seat. Day-to-day agents stay on `AGENTS.md`. This file is the durable fallback so the system survives outages, ambiguity, and partial work.

**Authority order (highest first):** Owner spoken/written override → explicit brief fields → `AGENTS.md` → specialty file for that domain (`mcp-routing.md`, `sol-usage.md`, `cursor-usage.md`, `fireworks-usage.md`, `usage-metering.md`, `visual-qa.md`, `grokbot-connection.md`, `analytics-clarity.md`) → `DOCTRINE.md` → this file.

When two specialty files conflict, the one named in the brief `must_read` wins for that job.

## Unknown or ambiguous job

1. If Google MCP is clearly required → GPT Terra (see `mcp-routing.md`).
2. Else default **Grok Build** implement.
3. If risk is unclear (auth, money, PII, prod, irreversible) → **do not implement**. Dispatch a one-line status to owner: `blocked: need risk call on <topic>`. Park the brief.
4. Never invent a fourth implementer seat.

## Seat or connector unavailable

| Failure | Do |
|---------|----|
| Grok Build / Heavy outage | Probe once. If still down: park volume. Do **not** move legwork to Sol, Opus, or Cursor $400. |
| GPT Terra MCP auth expired / connector missing | Park MCP brief. Report `blocked: Google MCP unavailable on Terra`. Do not invent GSC/keyword numbers. Do not burn Sol/Opus on fetches. |
| Codex Sol over soft cap (`usage-status`, not a hardcoded 90) | Code review → Opus 4.8, then Review E (if wired), else park to earliest reset. Volume still Grok. |
| Fable missing (downgrade) | `bin/detect-fable.py` records `fable-downgrade:<seat>`; `resolve-route` drops it. When NO Fable-capable seat is live, review order starts at **Codex Sol**, then Opus 4.8 (on any live Claude seat), then **Review E (if wired)**, else park after 4.8. |
| One Claude seat capped | teamclaude rotates to another of the five seats (`usage-status` per seat). Only when ALL Claude seats are spent is the Anthropic pipe down — check per-seat before calling Fable+Opus dead. |
| Opus / all Claude seats exhausted | Sol if under its soft cap (`usage-status`) and not already used on this change-set. Else park review — or, **if Review E is wired**, engage it only when the brief is time-critical and `usage-status` shows all native seats spent (`fireworks-usage.md`); its `ship` on a risk class is advisory, owner lands. Unwired → park after 4.8. |
| All native review seats quota-spent (`usage-status`, not probes) | Time-critical brief → one advisory Review E pass **if wired**; else park to the earliest reset (`usage-status --earliest-reset`) — a rested native seat beats the fallback. |
| Cross-family item, one native family quota-spent | The remaining native family gives one pass; **Review E (if wired)** gives the independent second family. Review E unwired → one pass, then park the gate. |
| All three reviewers erroring at once | Near-certain **local** fault (Mini network, keychain, token). Diagnose the box. Never engage Review E on outage signals — it would mask the fault or fail identically. |
| Codex dispatcher (Terra/Luna) down | Owner at the Mini console may hand a **complete** brief straight to Grok Build for non-gate work; gate work parks. Phone still never implements; do not promote Implement/Review to Dispatch. |
| Slack / Visual QA routine dead | Ticket stays in `#visual-qa`. Fallback: owner or iPhone Grok Bot runs the thread. Do not open Bot.app on the Mini. Do not block Grok implement on Visual QA being offline — park only the Review D step. |
| Cursor Models drained | IDE: stop or Tab-only. Orchestration implement stays Grok Build (Heavy), not Cursor Other Models. |
| Cursor $400 Other Models gone | Last $ closed unless owner enables on-demand. Fall back to Cursor Grok / Grok Build / teamclaude. |

**Probe rule:** one live check, then fail closed. Do not retry in a loop on scarce seats. Probe failure = outage → park; it says nothing about quota. **Exhaustion** = weekly ledger %, plan UI, or a hard 429/limit on a real call — never a probe. Review E opens on exhaustion only, never on a probe result.

## Partial completion

- Agent dies mid-worktree → next claim of that brief **resumes from git status + existing branch**. Do not open a second worktree for the same objective.
- MCP fetch wrote partial CSV → next MCP seat **appends or replaces at the same `output_path`**; document row counts and date range in the return summary.
- Review returned `fix-list` → implementer does at most **two** fix loops on that change-set. Third novel defect only if genuinely new; otherwise park.
- Review seats disagree (`ship` vs `blocked`) → **blocked wins**. Owner unblocks.
- Fix loops return to the **issuing** review seat; if that seat is spent mid-loop, **park the loop** (novel-defect exception unchanged) — do not restart review cold on a fresh seat and relitigate settled points.

## Dispatch supervision (checkpoints, not a watcher)

Correction happens where Dispatch already looks — at assignment and on every completion — never as a standing agent, cron, or extra Mini process (a `DOCTRINE.md` non-goal). Owner stays the top corrector.

| Signal | Caught at | Do |
|--------|-----------|----|
| Lane past its `effort` budget, no completion or park note | completion sweep | Mark `stalled: <branch>`. Resume from git status (partial-completion rule) or park with a reason. No second worktree. |
| Return outside named file scope, or touched `must_not_touch` | review gate (git diff) + completion check | Reject the change-set; re-scope the brief; do not land. |
| Past the two-fix-loop cap, no novel defect | review verdict | Park + escalate to owner. |
| Several seats look down at once | before any reroute | Run `usage-status`. A whole-pipe drop (teamclaude = Fable+Opus; Codex = Sol+dispatch) is **one** outage — diagnose the box, do not cascade to Review E or Cursor. |
| Gate-risk item, all review seats spent | `usage-status` at routing | Escalate to owner; do not silently park a risk item forever. |

Not a meta-agent, no polling for makework. The gates in this file plus the refill law are the mechanism.

## Duplicate and collision

- Same `objective` + overlapping files already in flight → do not dispatch a second lane. Status: `in flight: <branch or path>`.
- Two briefs claim the same file scope → dispatcher serializes; later brief waits or is rewritten with disjoint scope.
- Full test suite / main landing → **exactly one** at a time (machine lock / human gate).

## Stale or bad inputs

| Input | Action |
|-------|--------|
| Expired `shopifypreview.com` | Review D returns `blocked: need new Share Preview`. No Admin. |
| Preview host not on allowlist | `blocked`. Owner edits `visual-qa.md` allowlist if intentional. |
| Brief missing required field | No dispatch. Ask for the field only — do not invent `done_when`. |
| `must_read` path missing | Stop. Report missing path. Do not hallucinate file contents. |
| Snapshot for GSC/keywords older than brief allows | MCP seat re-fetches only if the brief says refresh; else flag stale. |

## Resets mid-job

- Sol weekly reset (instant per `usage-status`): in-flight Sol review may finish; **new** Sol reviews follow the post-reset 0% ledger.
- Cursor billing month roll (date in `config/usage-windows.json`): Other Models $400 refreshes; do not start Last $ jobs speculative before real need.
- Claude 5h window: teamclaude rotates seats; do not stack all reviews on one account.

## Owner unreachable

Safe to continue without owner:

- Grok implement on non-risk, in-scope briefs with complete fields
- GPT Terra MCP fetch to `output_path` when connector works
- Luna forwarding completed `done_when` reports (`luna-close-loop.md`)

Must park until owner:

- Risk-gate items (auth, money, PII, prod data, irreversible, publish)
- Authority expansion (new site on Visual QA allowlist, new MCP connector, new seat)
- Spend: Cursor on-demand, new collaborator accounts, theme publish
- Conflicting review verdicts

## Secrets and destructive ops

- Never put passwords, API keys, session tokens, or Admin URLs in briefs, Bot standing rules, or Slack tickets.
- Never create Shopify staff/collaborator accounts from an agent.
- Publish, live theme switch, and SimGym stay owner/human.
- Visual QA never holds Admin cookies.
- Never send a diff carrying secrets, API keys, tokens, or customer PII to a third-party inference host (Review E / Fireworks). The wrapper (when wired) scans the diff first; any hit → park for a native seat.

## Effort values (brief field)

Use one of: `setup` · `low` · `medium` · `high` · `review`.

- `setup` — machine/policy wiring only
- `low` — single file or small catalog touch
- `medium` — default implement
- `high` — multi-service, migrations, risky
- `review` — review-only brief

Missing `effort` → no dispatch (same as other required fields).

## Park location

Parked work is a brief that stays in the queue with status `parked: <reason>`. Prefer the same backlog the dispatcher already uses (Trello card, queue file, or session note). Do not invent makework to fill idle. Empty useful queue → idle is correct.

## When docs go stale

Model names and plan tiers change. **Edit `config/`, not prose** — `config/providers.json`
(models/families/detection), `config/subscriptions.json` (plans + Fable grants),
`config/connectors.json` (MCP/store bindings), `config/usage-windows.json` (reset anchors) — then run
`bin/doctor.py`. The seat table in `AGENTS.md` is by-reference (roles are invariant; providers come
from config), so it does not need editing when a provider changes. Do not leave a provider on a
deleted model ID; `bin/doctor.py` fails if any provider selects a forbidden model (opus-5). Once
Review E is wired, pin its model ID in `config/providers.json` (`review-e.model`) per `fireworks-usage.md`.
