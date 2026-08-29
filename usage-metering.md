# Usage metering — reset times and limits by script, not by guess

Two failure modes this file closes:

1. **Hardcoded reset times** scattered through prose go stale the moment a plan changes.
2. **An LLM guessing remaining quota** from token counts is unreliable and spends tokens to do it.

So: **the only place a reset time lives is `config/usage-windows.json`**, and **the only way to read a seat's status is the `bin/usage-status.py` script** — never a hardcoded clock time, never an agent eyeballing a dashboard.

## Files

| File | Role | Written by |
|------|------|-----------|
| `config/usage-windows.json` | Source of truth: each seat's window kind, reset anchor, soft cap, `$` cap | Owner (rarely — only when a plan/window changes) |
| `config/usage-ledger.json` | Live state: `spent_until` / `pct` per seat + `fable-downgrade:<seat>` markers. Gitignored | `bin/record-429.sh` (on a real 429), `bin/detect-capability.py`, or the owner — **never a probe/timeout, never an LLM** |
| `config/usage-ledger.example.json` | Format reference | committed |
| `bin/usage-status.py` | Reads both, computes the next reset, prints state | — |

Seats now include the **five separate Claude accounts** (Max, 2× Team-premium, 2× Pro), each its own
rolling window, so `usage-status` shows true aggregate Claude/Fable capacity instead of one blob.

## Limit determination order (highest authority first)

1. **Hard machine signal** — a real `429` / usage-limit error `bin/record-429.sh` recorded into `config/usage-ledger.json` as `spent_until`. Authoritative: the seat is spent until that instant.
2. **Computed window** — `usage-status` rolls the `config/usage-windows.json` anchor forward to the next reset. No clock time is written in prose; it is computed each run.
3. **Owner/manual %** — a number the owner noted from the provider UI into `config/usage-ledger.json`, compared to `soft_cap_pct`. Fallback only.
4. **LLM estimation is not a source.** Never infer "we're probably rate-limited" from token usage. If there is no recorded signal, the seat is treated as available by its window — and a real call that 429s is what flips it, recorded by the wrapper.

This is the machine version of the QUOTA-vs-OUTAGE rule (`EDGE-CASES.md`): only a recorded quota signal marks a seat spent; a probe/timeout never does.

## Commands

```
python3 bin/usage-status.py                  # table: each seat, state, next reset
python3 bin/usage-status.py --json           # machine-readable, for dispatch to consume
python3 bin/usage-status.py --earliest-reset # soonest reset among spent/capped seats
python3 bin/usage-status.py --seat claude-max
python3 bin/resolve-route.py --class <c> --scale <s>  # deterministic route using the above
```
(run from the orchestration repo root)

- **Dispatch** runs `usage-status` (via `resolve-route`) before routing a review, instead of judging limits by hand.
- "**Park to the earliest reset**" (`EDGE-CASES.md`) = `usage-status --earliest-reset`, not a remembered time.
- **Review E** engages only when `usage-status` shows every native review seat spent (plus the other triggers in `fireworks-usage.md`).
- **Fable downgrades**: `bin/detect-capability.py` writes a `fable-downgrade:<seat>` marker that `resolve-route` honors immediately (drops the seat from Fable-capable) — no prose edit needed.

## Rules

- Never write a reset day/time/date in any other file. Point at `usage-status`; edit `config/usage-windows.json`.
- A `null` anchor means the owner has not set it (e.g. the Grok weekly weekday, the Cursor billing day). `usage-status` says "unset" rather than inventing one — set it in `config/usage-windows.json` when known.
- `bin/record-429.sh` records a **real** `429`/limit as `spent_until = <next reset instant>` so parking and `--earliest-reset` are automatic. A probe failure or timeout writes **nothing** (outage, not exhaustion — `EDGE-CASES.md`).
- Do not build a cron that polls providers for makework (`DOCTRINE.md` non-goals). Record signals from calls you were already making.
