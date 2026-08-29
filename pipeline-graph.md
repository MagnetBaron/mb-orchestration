# Pipeline graph — the brief lifecycle as an inspectable state machine

The router (`bin/resolve-route.py`) is a stateless per-decision function: *class + live
seat state → depth, review chain, implement seat, gates*. This file is the other half —
the **stateful** lifecycle a brief moves through, made a machine object instead of prose in
the dispatcher's head. The durable record is `bin/runledger.py` (append-only
`data/run-ledger.jsonl`); routing-quality telemetry is `bin/observe.py`
(`data/orchestration-events.jsonl`, privacy-safe, never authority); the dry-run view is `bin/run-brief.py`; the invocation recipes are
`config/seat-exec.json`. The event/status vocabulary and the fix-loop cap below are the
constants in `bin/runledger.py` (`EVENTS`, `FIX_LOOP_CAP`) — that script is the source of
truth; this doc explains it.

This is STATE + a PLANNER, never a daemon and never an actor — consistent with the
`DOCTRINE.md` non-goals ("no watcher daemon", "not a meta-agent", "policy only"). Correction
happens at the checkpoints `EDGE-CASES.md` already defines, not by polling.

## States and transitions

```
                 created ──▶ classified ──▶ routed ──▶ implemented
                                                            │
                                          (review depth?)   │
                              none / self-check ────────────┼──────────────▶ gated
                                                            ▼
                                                       (review-verdict)
                                              ship ──────────────────────▶ gated
                                              fix-list ──▶ fixing ──┐
                                              blocked ──▶ blocked   │  (back to ISSUING seat)
                                                   ▲                │
                                                   └── implemented ◀┘  (fix loop, ≤ FIX_LOOP_CAP)
                                                                     │
                                   gated ──▶ landed        park ◀────┘ (cap hit, no novel defect)
                                     │                       ▲
                                     └── gate unmet ─────────┘
```

- **Events** (append-only, `runledger.EVENTS`): `created` · `classified` · `routed` ·
  `implemented` · `review-verdict` (`ship`|`fix-list`|`blocked`) · `gated` · `landed` · `parked`.
- **Statuses** (folded): `new → created → classified → routed → implemented →`
  `review-passed | fixing | blocked → gated → landed | parked`. `landed`/`parked` are terminal.
- A verdict `fix-list` increments `fix_loops` and returns to `fixing`; the next `implemented`
  re-enters review at the **issuing** seat.

## Guards (each is machine-checkable from the fold)

- **Fix-loop cap** — `fix_loops ≤ FIX_LOOP_CAP` (2). Third loop only for a **novel** defect;
  otherwise `parked` (AGENTS.md §Review; EDGE-CASES.md §Partial completion). `fold()` exposes
  `fix_loops` and `fix_loop_exhausted`.
- **Review-starvation** — at **≥3** lanes in `implemented`/`fixing` (awaiting a verdict), Build
  claims only `none`/`self-check` briefs until the queue drains
  (`runledger.awaiting_review_count`; DOCTRINE.md §Refill law).
- **Landing lock** — exactly one lane at `gated → landed` on main at a time (DOCTRINE.md
  §Concurrency, §Safety gates). One green test bound to the commit tip stays required even at
  `none`/`self-check`.
- **Owner / human / Review-D gates** — carried on the `gated` step from the decision's
  `gates` (`owner_gate`, `human_gate`, `review_d_pixels`). `blocked` wins over `ship` on
  disagreement; the owner unblocks.
- **Cross-family** — a money/auth/PII/secrets lane needs one pass from **two different**
  families before `landed`; unsatisfiable → `parked` (never a self-imposed cap while quota
  exists — that is a `park` only on genuine exhaustion).

## EXECUTOR — deferred, and why

`run-brief.py` plans; it never acts. A live executor (shell the seats, drive worktrees, land)
is **out of scope and gated** pending an owner go/no-go, because it is a different risk class:

1. **First component that ACTS.** Everything today decides or records; an executor writes and
   lands. New failure mode: wrong action, not just wrong advice.
2. **Gates are advisory, not interlocked.** The repo emits gate booleans; nothing here refuses
   a land when one is unmet. Autonomous landing needs the gates machine-**interlocked**.
3. **Runaway spend/quota.** Unattended fan-out burns subscription quota fast (a measured
   20-agent swarm run ≈ $60 vs ≈ $9 single-agent). Needs enforced **per-run caps** + the
   **never-a-metered-host** guard (`config/seat-exec.json` `never_metered_host`; a diff must
   never reach a metered inference host — secrets/PII ban).
4. **Concurrency the repo lacks.** Real worktree/branch/merge coordination beyond "1 lane = 1
   worktree" discipline; uncoordinated merges risk **silent data loss**.
5. **Brushes a non-goal.** A live supervisor/watchdog edges toward the "no daemon / not a
   meta-agent" line — an executor must stay checkpoint-driven, not a standing process.
6. **Untestable off the Mini.** The subscription CLIs live on the one worker machine, so an
   executor can only be validated in prod — no clean CI surface.
7. **Security surface.** Shelling briefs and handling diffs is a real attack surface (prompt
   injection into a shelled command, a diff carrying secrets) — hard requirement: **never a
   metered/third-party host**, subscription CLIs only.

**Go/no-go to ever enable it (all required):** gates interlocked (a land is refused when a
gate is unmet) · per-run spend/quota caps enforced **and tested** · concurrency proven on
throwaway branches · metered-host guard verified (no diff can reach a metered host) · Mini-only
validation accepted · scoped **smallest-first** (implement-only; review + land stay
human-gated). Until then: dry-run planner only.
