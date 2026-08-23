# Edge cases and recovery

Load when something breaks or the brief does not fit a clean seat. Day-to-day agents stay on `AGENTS.md`. This file is the durable fallback so the system survives outages, ambiguity, and partial work.

**Authority order (highest first):** Owner spoken/written override → explicit brief fields → `AGENTS.md` → specialty file for that domain (`mcp-routing.md`, `sol-usage.md`, `cursor-usage.md`, `visual-qa.md`) → `DOCTRINE.md` → this file.

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
| Codex Sol ≥ 90% weekly | Code review → Opus 4.8 if risk gate still requires frontier. Else park review. Volume still Grok. |
| Fable missing (downgrade) | Review order starts at **Codex Sol**. Then Opus 4.8. |
| Opus / teamclaude exhausted | Sol if under 90% and not already used on this change-set. Else park review. |
| Slack / Visual QA routine dead | Ticket stays in `#visual-qa`. Fallback: owner or iPhone Grok Bot runs the thread. Do not open Bot.app on the Mini. Do not block Grok implement on Visual QA being offline — park only the Review D step. |
| Cursor Models drained | IDE: stop or Tab-only. Orchestration implement stays Grok Build (Heavy), not Cursor Other Models. |
| Cursor $400 Other Models gone | Last $ closed unless owner enables on-demand. Fall back to Cursor Grok / Grok Build / teamclaude. |

**Probe rule:** one live check, then fail closed. Do not retry in a loop on scarce seats.

## Partial completion

- Agent dies mid-worktree → next claim of that brief **resumes from git status + existing branch**. Do not open a second worktree for the same objective.
- MCP fetch wrote partial CSV → next MCP seat **appends or replaces at the same `output_path`**; document row counts and date range in the return summary.
- Review returned `fix-list` → implementer does at most **two** fix loops on that change-set. Third novel defect only if genuinely new; otherwise park.
- Review seats disagree (`ship` vs `blocked`) → **blocked wins**. Owner unblocks.

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

- Sol weekly reset (Sun 10 PM CT): in-flight Sol review may finish; **new** Sol reviews follow the post-reset 0% ledger.
- Cursor billing month roll: Other Models $400 refreshes; do not start Last $ jobs speculative before real need.
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

Model names and plan tiers change. Update `AGENTS.md` seat table and the specialty file for that meter. Do not leave agents on deleted model IDs. Pin what the owner currently pays for (today: Opus 4.8, GPT-5.6 Sol/Terra/Luna, Grok 4.6 / Build, Cursor Ultra Other Models $400).
