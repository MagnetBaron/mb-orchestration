# Multi-bucket doctrine (trimmed)

Distilled from a production multi-provider architecture. Keep this out of every agent context; load only when designing or debugging the system. Day-to-day agents use `AGENTS.md` only. Visual QA details: `visual-qa.md`.

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
  └─ DISPATCH (Codex Terra/Luna) — queue, risk gate, assign, report
       ├─ IMPLEMENT (Grok Build) — code in worktrees; never lands alone on high risk
       ├─ REVIEW D (Grok Bot Website Visual QA) — Slack ticket + shopifypreview.com; app quit on Mini
       └─ REVIEW A–C (Fable → Sol → Opus 4.8) — git diff; ship | fix-list | blocked
```

One lead/dispatcher at a time. Codex remains the only entry point.

## Brief schema (required fields)

`objective` · `must_read` · `must_not_touch` · `output_path` · `done_when` · `effort`  
Review seats also need `attack_angle`.

No field → do not dispatch. Point at paths; never paste large diffs into the brief.

## Shopify scale

Same Codex entry scales to more **basic product edits** without extra Visual QA:

- Title / body / metafield / price / SKU / tags → Codex → Grok Build or Shopify MCP skills → done. No Review D.
- Many SKUs, same template → one catalog lane, not N preview walks.
- Theme, section, PDP chrome, CSS → add Review D Slack ticket after a visitor preview URL exists.
- Publish and SimGym stay owner/human. Review D never auto-scales into Admin.

## Concurrency

- Default question: which **disjoint** lanes can run now?
- Ceiling, not target. Prefer fewer deeper lanes when faster.
- **1 lane = 1 worktree = 1 branch = named file scope** (dispatcher creates the worktree).
- Full test suite / main landing: **exactly one at a time**.
- Review D is off-box; it does not count as a second implementer on the Mini.

## Refill law

On every completion: claim next ready brief or explain idle. Idle beside a non-empty useful queue is a defect. Empty queue → idle is correct. Never invent makework.

## Reset-aware placement

1. **Pre-reset:** drain surplus on real backlog.
2. **Post-reset:** fire staged volume campaigns when the bucket refreshes.
3. **Mid-cycle:** do not conserve abundant capacity.

## Safety gates (adopt in order)

1. Risk gate before frontier review spend
2. Worktree isolation + file claims
3. One green test command bound to exact commit tip (when the repo has it)
4. One landing lock for main
5. Cross-family review on auth, money, PII, secrets, untrusted shell
6. Max two fix/review loops, then park unless a **novel** defect appears
7. Visual QA only on allowlisted hosts via visitor preview; never Admin cookies on the Bot computer

## Explicit non-goals (for now)

- Full overnight autonomous land-to-prod without phone approval
- Official `grok` CLI → named Grok Bot (does not exist; use Slack)
- Grok Bot.app as a worker process on the 16 GB Mini
- SimGym or collaborator accounts for Website Visual QA
- Treating Opus 5 as default (pin 4.8)
- Using Cursor $400 as a worker pool
