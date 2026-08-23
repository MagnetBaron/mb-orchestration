# Usage metering — reset times and limits by script, not by guess

Two failure modes this file closes:

1. **Hardcoded reset times** scattered through prose go stale the moment a plan changes.
2. **An LLM guessing remaining quota** from token counts is unreliable and spends tokens to do it.

So: **the only place a reset time lives is `usage-windows.json`**, and **the only way to read a seat's status is the `usage-status` script** — never a hardcoded clock time, never an agent eyeballing a dashboard.

## Files

| File | Role | Written by |
|------|------|-----------|
| `usage-windows.json` | Source of truth: each seat's window kind, reset anchor, soft cap, `$` cap | Owner (rarely — only when a plan/window changes) |
| `usage-ledger.json` | Live state: `spent_until` / `pct` per seat. Gitignored | Wrapper scripts (on a real 429) or the owner — **never a probe/timeout, never an LLM** |
| `usage-ledger.example.json` | Format reference | committed |
| `usage-status.py` | Reads both, computes the next reset, prints state | — |

## Limit determination order (highest authority first)

1. **Hard machine signal** — a real `429` / usage-limit error a wrapper recorded into `usage-ledger.json` as `spent_until`. Authoritative: the seat is spent until that instant.
2. **Computed window** — `usage-status` rolls the `usage-windows.json` anchor forward to the next reset. No clock time is written in prose; it is computed each run.
3. **Owner/manual %** — a number the owner noted from the provider UI into `usage-ledger.json`, compared to `soft_cap_pct`. Fallback only.
4. **LLM estimation is not a source.** Never infer "we're probably rate-limited" from token usage. If there is no recorded signal, the seat is treated as available by its window — and a real call that 429s is what flips it, recorded by the wrapper.

This is the machine version of the QUOTA-vs-OUTAGE rule (`EDGE-CASES.md`): only a recorded quota signal marks a seat spent; a probe/timeout never does.

## Commands

```
python3 usage-status.py                  # table: each seat, state, next reset
python3 usage-status.py --json           # machine-readable, for dispatch to consume
python3 usage-status.py --earliest-reset # soonest reset among spent/capped seats
```
(run from the orchestration repo root)

- **Dispatch** runs `usage-status` before routing a review, instead of judging limits by hand.
- "**Park to the earliest reset**" (`EDGE-CASES.md`) = `usage-status --earliest-reset`, not a remembered time.
- **Review E (Fireworks)** engages only when `usage-status` shows every native review seat spent (plus the other triggers in `fireworks-usage.md`).

## Rules

- Never write a reset day/time/date in any other file. Point at `usage-status`; edit `usage-windows.json`.
- A `null` anchor means the owner has not set it (e.g. the Grok weekly weekday, the Cursor billing day). `usage-status` says "unset" rather than inventing one — set it in `usage-windows.json` when known.
- Wrappers record a **real** `429`/limit as `spent_until = <next reset instant>` so parking and `--earliest-reset` are automatic. A probe failure or timeout writes **nothing** (outage, not exhaustion — `EDGE-CASES.md`). Probes may trigger a real call, but only its real 429 writes state.
- Do not build a cron that polls providers for makework (`DOCTRINE.md` non-goals). Record signals from calls you were already making.
