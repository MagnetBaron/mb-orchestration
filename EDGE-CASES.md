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
| Grok Build returns the exact provider transport error `402 Payment Required: Grok Build usage balance exhausted` (or exact `HTTP 402: Grok Build usage balance exhausted`) | Record `grok-heavy` with `bin/record-429.sh`, then resolve again. The configured implementation-only overflow is Cursor Agent with exact model `cursor-grok-4.6-xhigh` on the included Cursor Models seat, but it is eligible only while the `grok-heavy` usage row is ledger-backed `spent` **and** that exact Cursor route is `live_verified`; healthy Grok or catalog-only/failed Cursor evidence parks the overflow. This exception is quota evidence, not an outage and not permission to use Cursor Other Models. Generic 402/payment/auth text and completions discussing the phrase write nothing. |
| GPT Terra MCP auth expired / connector missing | Park MCP brief. Report `blocked: Google MCP unavailable on Terra`. Do not invent GSC/keyword numbers. Do not burn Sol/Opus on fetches. |
| Codex Sol over its reserve line (`usage-status` shows tier `reserve`, not a hardcoded 90) | Code review PREFERS a live Fable/Opus seat (Sol is deprioritized, **not** removed). If Sol is the only usable reviewer, Sol reviews — a reserve/soft cap never strands real quota. Park only on genuine exhaustion (a recorded 429). Volume still Grok. |
| Metered $ seat considered while included capacity is live | Do not touch Cursor Other Models / Review E while any `included` seat is usable (`usage-status` billing) — that is API spend the system should avoid. Metered is a last resort only. |
| Fable missing (downgrade) | `bin/detect-capability.py` validates and records `fable-downgrade:<seat>`; the marker lowers the anonymous declared Fable ceiling and live TeamClaude capability must reconcile with it. When NO Fable-capable account is live, review order is unchanged: **Opus 5** (on any live Claude account), then **Codex Sol**, then **Review E (if wired)**. Park only when the required gate remains unsatisfied after that usable chain. Fable absence never opens Review E. |
| One Claude account capped | teamclaude rotates to another freshly probed account eligible for the exact requested model. Missing accounts are degraded capacity, not a fleet-wide stop; only when every observed capable account is spent is that model family down. Shared 5h/shared-weekly exhaustion bars every model on the account, while a family-only cap bars only that family. |
| **teamclaude absent — Anthropic transport unavailable** | `bin/detect-agents.py` reports `rotation: unavailable` (also surfaced by `usage-status`), and current Anthropic routing **parks** because bare `claude` is auth-blocked and there is no separately verified direct-account route. Static inventory must not synthesize one or five accounts. This is a runtime transport gap, not proof that subscriptions disappeared. Restore routing by installing TeamClaude and importing the intended accounts; the live adapter will report a smaller subset as degraded and reject capacity beyond the declared ceiling. |
| Opus / all Claude seats exhausted | Sol remains usable even at its soft cap when needed and when it was not already used on this change-set. If one native pass is insufficient, **Review E (if wired)** may fill the independent-family slot only while Sol remains usable. Review E unwired → keep the valid Sol pass and park only the still-unsatisfied gate. |
| All native review seats quota-spent (`usage-status`, not probes) | Park to the earliest reset (`usage-status --earliest-reset`). Review E alone never satisfies a review gate, and `user said ship` grants landing authority rather than metered spend. |
| Cross-family item, one native family quota-spent | The remaining native family gives one pass; **Review E (if wired)** gives the independent second family. Review E unwired → one pass, then park the gate. |
| All three reviewers erroring at once | Near-certain **local** fault (Mini network, keychain, token). Diagnose the box. Never engage Review E on outage signals — it would mask the fault or fail identically. |
| Requested dispatcher spent/unavailable | `resolve-route --intake-provider …` selects the first usable configured fallback and records requested/effective identity plus reason. No user permission loop. If no qualified fallback remains, park. |
| Codex pipe down (Sol + Terra + Luna together) | ONE Codex outage, not three. Codex dispatch candidates and Sol review disappear together; route dispatch/review to live non-Codex providers. Park MCP volume. Do not cascade to Review E on outage alone. |
| Claude pipe down (Opus 5 + Opus 4.8 + Fable) | ONE Anthropic outage. Claude dispatch candidates and Anthropic review disappear together; choose a live non-Claude dispatcher. Cross-family gate may still park if only one review family remains. |
| Restricted or unknown artifact class | PARK with `requires_user_permission:false`. Never repeatedly ask the operator to authorize transfer. The immutable minimum covers credentials, secrets/tokens, restricted PII/data, customer data, and production data/exports. Config may add restrictions but cannot remove or reclassify that floor; restricted wins conflicts at runtime. Ordinary configured repo artifacts remain preauthorized regardless of which agent authored them. |
| Review D code-owned pixel binding, CLI/profile, or browser prerequisite absent | `bin/grok-agent.py` reports PARK before prompt reads when the binding is absent. Do not treat packet rendering, CLI smoke, or WebFetch as pixels; park only Review D while unrelated implementation may continue. |
| Live-audit wakes but storefront returns Access Denied or no valid screenshots | Return `blocked` with the observed reason. This proves wake/gating only, not visual coverage or a working store audit. Do not guess a verdict or retry into Admin/auth paths. |
| Cursor Models drained | If Grok Build is healthy, implementation stays on Grok Build. If both included pools are provider-confirmed exhausted, park; do not cross into Cursor Other Models automatically. |
| Cursor $400 Other Models gone | Last $ closed unless owner enables on-demand. Implementation falls back only to a live included Cursor Grok or Grok Build route; TeamClaude remains dispatch/review capacity, not a coding fallback. |

**Probe rule:** one live check, then fail closed. Do not retry in a loop on scarce seats. Probe failure = outage → park; it says nothing about quota. **Exhaustion** = weekly ledger %, plan UI, a hard 429/limit on a real call, or the exact provider-confirmed Grok Build 402 above — never a probe or generic payment text. Review E opens on exhaustion only, never on a probe result.

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
| Several seats look down at once | before any reroute | Run `usage-status`. A whole-pipe drop (teamclaude = Claude dispatch candidates + Opus/Fable; Codex = Sol/Terra/Luna) is **one** outage — diagnose the box, then resolve another dispatcher; do not cascade to Review E on outage alone. |
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
| Preview/live-audit host not on allowlist | `blocked`. Owner edits `config/connectors.json` if intentional, then runs doctor/tests and re-renders the instructions. |
| Live-audit host is configured but has no CLI run/screenshots/verdict evidence | Mark it `unverified`, not tested/working. Packet rendering is preparation only. Normal execution remains unsupported until the code-owned pixel-input binding exists; only after that binding, the live route/profile gates, and browser/pixels all pass may one safe packet run. Preserve evidence before upgrading the claim. |
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
- The dispatcher forwarding completed `done_when` reports (`luna-close-loop.md`)

Must park until owner:

- Risk-gate items (auth, money, PII, prod data, irreversible, publish)
- Authority expansion (new site on Visual QA allowlist, new MCP connector, new seat)
- Spend: Cursor on-demand, new collaborator accounts, theme publish
- Conflicting review verdicts

## Secrets and destructive ops

- Never put passwords, API keys, session tokens, or Admin URLs in briefs, standing-role rules, or CLI prompt packets.
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

## Observability log failures

Routing quality telemetry (`bin/observe.py`, `data/orchestration-events.jsonl`) never
grants authority and must not change a park into a success.

| Failure | Do |
|---------|----|
| `observe.py` import error or disk/write failure | Routing continues unchanged. `observability.recorded=false` and `write_error` are attached. A park stays a park. |
| Malformed `monitoring.json` observability block | `bin/doctor.py` fails closed. Runtime skips emit and leaves the routing decision intact. |
| `MB_OBSERVABILITY=0` | Disables **default/config** emit only. `--record` / `--record-observability` still emit. `--no-record` always suppresses. |
| Invalid `--class` / unknown scale after parse | Bounded `bootstrap_failure` event is recorded (sanitized, no task body), then the process still fails closed. |
| Argparse failure (missing `--class`, invalid `--scale` choice) | **Unobservable bootstrap.** The process exits before a run exists; nothing is logged. Re-run with a valid invocation. |
| Invalid registry before a decision is computed | Bounded `bootstrap_failure` (`invalid_registry` / `missing_registry`), then fail closed as today. |
| Concurrent prune vs append | Both take the same exclusive lock; accepted events are not dropped. Truncated tails are isolated, then skipped on read. |
| Retention | Emit does **not** auto-prune. Run `bin/observe.py prune` (cron/LaunchAgent is the bounded safe point). Do not treat this as `usage-record.py --snapshot`. |

Never log prompts, diffs, credentials, customer data, or absolute user paths. Actor/run
ids that look like paths or secrets are hashed; UUIDs and explicit pseudonyms stay as-is.

## Park location

Parked work is a brief that stays in the queue with status `parked: <reason>`. Prefer the same backlog the dispatcher already uses (Trello card, queue file, or session note). Do not invent makework to fill idle. Empty useful queue → idle is correct.

## When docs go stale

Model names and plan tiers change. **Edit `config/`, not prose** — `config/providers.json`
(models/families/detection), `config/subscriptions.json` (plans + Fable grants),
`config/connectors.json` (MCP/store bindings), `config/usage-windows.json` (reset anchors) — then run
`bin/doctor.py`. The seat table in `AGENTS.md` is by-reference (roles are invariant; providers come
from config), so it does not need editing when a provider changes. Do not leave a provider on a
deleted model ID; `bin/doctor.py` fails if any provider selects a model listed in `providers.json` `forbidden_models`, and if `config/model-registry.json` is stale or contradictory. Opus 5 is the operational Anthropic gate (not forbidden). A catalog entry is not a usable route — only `live_verified` routes resolve. Once
Review E is wired, pin its model ID in `config/providers.json` (`review-e.model`) per `fireworks-usage.md`.
