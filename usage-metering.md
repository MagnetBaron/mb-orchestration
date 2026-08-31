# Usage metering — reset times and limits by script, not by guess

Two failure modes this file closes:

1. **Hardcoded reset times** scattered through prose go stale the moment a plan changes.
2. **An LLM guessing remaining quota** from token counts is unreliable and spends tokens to do it.

So: **configured window schedules live only in `config/usage-windows.json`**, provider-observed per-event reset instants live only as `spent_until` in the gitignored ledger, and **the only way to read a seat's status is the `bin/usage-status.py` script** — never a hardcoded clock time, never an agent eyeballing a dashboard.

## Files

| File | Role | Written by |
|------|------|-----------|
| `config/usage-windows.json` | Source of truth: each seat's window kind, reset anchor, soft cap, `$` cap | Owner (rarely — only when a plan/window changes) |
| `config/usage-ledger.json` | Live state: `spent:true`, optional `spent_until`, or `pct` per seat + `fable-downgrade:<seat>` markers. Gitignored | `bin/record-429.sh` (on a real 429, or the exact provider-confirmed Grok Build usage-exhausted 402), `bin/detect-capability.py`, or the owner — **never a probe/timeout, generic 402, or LLM completion** |
| `config/usage-ledger.example.json` | Format reference | committed |
| `bin/usage-status.py` | Reads both, computes the next reset, prints state | — |

The five configured Claude rows are a declared inventory ceiling (Max, 2× Team-premium,
2× Pro), not live capacity. `usage-status` attaches one identity-free TeamClaude receipt;
runtime routing uses its fresh model-specific eligible count and treats a smaller observed
fleet as degraded capacity rather than resurrecting missing named seats.

## Limit determination order (highest authority first)

1. **Hard machine signal** — a real `429` / usage-limit error, or the exact Grok Build `402 Payment Required: Grok Build usage balance exhausted` transport error, recorded by `bin/record-429.sh` into `config/usage-ledger.json` as `spent:true`. When a provider-derived reset is known, `spent_until` carries it. When the Grok response proves exhaustion but exposes no reset, `spent_until:null` keeps the seat parked with reset unknown instead of inventing a five-hour recovery. The 402 exception is accepted only for the registered `grok-heavy` seat; generic payment/auth/error prose is not exhaustion.
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
- **Fable downgrades**: `bin/detect-capability.py` writes a validated `fable-downgrade:<seat>` marker. The privacy-safe adapter uses marker count to lower the declared Fable ceiling; TeamClaude's anonymous live capability must reconcile with that ceiling. It does not claim to map an anonymous runtime account back to the named marker.

## Rules

- Never hardcode a reset day/time/date in prose or policy. Put configured schedules in `usage-windows.json`; let the recorder place provider-observed event resets in the gitignored ledger; read both through `usage-status`.
- A `null` anchor means the owner has not set it (e.g. the Grok weekly weekday, the Cursor billing day). `usage-status` says "unset" rather than inventing one — set it in `config/usage-windows.json` when known.
- `bin/record-429.sh` validates the seat against `usage-windows.json` before any write, holds a PID/token-owned same-directory lock, writes a private temporary file, and atomically renames it into place. `record-429.sh`, `usage-record.py`, and `detect-capability.py` bound lock acquisition, never steal a live owner's lock, and safely quarantine/reclaim a dead-PID or sufficiently old malformed lock after a killed writer. An unknown seat or malformed ledger fails without replacing the ledger.
- It records a **real** `429`/limit, plus only the exact provider-confirmed Grok Build usage-exhausted 402, as `spent:true`. Pass `MB_429_RESET` when the provider supplies a future UTC reset. Without reset evidence, only a seat whose entire configured schedule is a five-hour rolling window gets a `now+5h` default; weekly, monthly, mixed, and no-reset seats record `spent_until:null`, so they stay parked until verified recovery instead of auto-unparking early. A probe failure, timeout, generic 402, auth failure, or completion writes **nothing** (outage/non-evidence, not exhaustion — `EDGE-CASES.md`).
- Do not build a cron that polls providers for makework (`DOCTRINE.md` non-goals). Record signals from calls you were already making.
