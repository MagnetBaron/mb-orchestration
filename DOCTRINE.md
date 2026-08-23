# Multi-bucket doctrine (trimmed)

Distilled from a production multi-provider architecture. Keep this out of every agent context; load only when designing or debugging the system. Day-to-day agents use `AGENTS.md` only.

## Economics

Unspent quota at reset is waste. Buckets are asymmetric:

| Class | Your seats | Job |
|-------|------------|-----|
| **Abundant volume** | Grok Super Heavy / Build / Bot | All legwork |
| **Scarce judgment** | Claude (Fable while included, else Opus 4.8); Codex Sol for review only | Verify, land-gate, hard review |
| **Dispatcher** | Codex Terra/Luna | Queue, assign, status — never implement |
| **Last $** | Cursor Other Models $400 | Only after others are spent |

**Legwork-or-stop:** volume work (builds, sweeps, mass reads, research fan-out) runs on Grok or parks with a note. Never silently move legwork onto Claude/Codex/Cursor $ because a probe failed. Verify outages with a live lane before rerouting.

## Roles (not models)

```
OWNER — spend, credentials, destructive ops, authority expansion
  └─ DISPATCH (Codex phone) — queue, risk gate, assign, report
       ├─ IMPLEMENT (Grok) — code in worktrees; never lands alone on high risk
       └─ REVIEW (Fable → Sol → Opus 4.8) — git diff; ship | fix-list | blocked
```

One lead/dispatcher at a time for phone control. Pod-leader / multi-landing authority is optional later; start without it.

## Brief schema (required fields)

`objective` · `must_read` · `must_not_touch` · `output_path` · `done_when` · `effort`  
Review seats also need `attack_angle`.

No field → do not dispatch. Point at paths; never paste large diffs into the brief.

## Concurrency

- Default question: which **disjoint** lanes can run now?
- Ceiling, not target. Prefer fewer deeper lanes when faster.
- **1 lane = 1 worktree = 1 branch = named file scope** (dispatcher creates the worktree).
- Full test suite / main landing: **exactly one at a time** (machine semaphore / lock).
- After a concurrency bug: fix the seam (brief, scope), do not freeze the fleet.

## Refill law

On every completion: claim next ready brief or explain idle. Idle beside a non-empty useful queue is a defect. Empty queue → idle is correct. Never invent makework.

## Reset-aware placement

1. **Pre-reset:** drain surplus (especially Grok weekly, Claude non-frontier if surplus) on real backlog.
2. **Post-reset:** fire staged volume campaigns when the bucket refreshes.
3. **Mid-cycle:** do not conserve abundant capacity; freezing pushes work onto scarce buckets.

Usage % is usually manual (provider UI). Keep live % only in a backlog header, never in doctrine files.

## Safety gates (adopt in order)

1. Risk gate (see `AGENTS.md`) before frontier review spend
2. Worktree isolation + file claims
3. One green test command bound to exact commit tip (when the repo has it)
4. One landing lock for main
5. Cross-family review on escalation categories (auth, money, PII, secrets, untrusted shell)
6. Max two fix/review loops, then park unless a **novel** defect appears

## Explicit non-goals (for now)

- Full overnight autonomous land-to-prod without your approval on phone
- EA daemon / launchd board-compaction (source system had this; optional later)
- Provider-neutral orchestration framework before a second surface needs it
- Treating Opus 5 as default (pin 4.8)
- Using Cursor $400 as a worker pool

## Gaps inherited from the source system

- No reliable usage API → manual ledger + availability probes only
- Reset kickoff is judgment unless you add cron
- Verification capacity saturates before workers — scale review seats before more implementers
- False "worker down" probes can burn scarce buckets — probes fail closed
