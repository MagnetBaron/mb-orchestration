#!/bin/bash
# Record ONLY a provider-confirmed 429/usage-limit signal, or the exact Grok Build
# 402 usage-balance-exhausted transport error, into config/usage-ledger.json.
# Never call this for auth failures, timeouts, or generic non-zero exits (those are
# OUTAGE, not exhaustion — EDGE-CASES.md QUOTA-vs-OUTAGE). The 5h default reset applies
# only to rolling-window callers; weekly/monthly callers must pass MB_429_RESET from
# provider/reset evidence rather than treating that default as a discovered reset.
set -euo pipefail

seat="${1:?seat name required (a seat in config/usage-windows.json)}"
message="${2:-}"
if [ -n "${MB_CONFIG_DIR:-}" ]; then
  default_ledger="${MB_CONFIG_DIR%/}/usage-ledger.json"
  default_windows="${MB_CONFIG_DIR%/}/usage-windows.json"
else
  config_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../config" && pwd)"
  default_ledger="$config_dir/usage-ledger.json"
  default_windows="$config_dir/usage-windows.json"
fi
ledger="${MB_USAGE_LEDGER:-$default_ledger}"
windows="${MB_USAGE_WINDOWS:-$default_windows}"
reset="${MB_429_RESET:-}"

# ─────────────────────────────────────────────────────────────────────────────
# CALLER CONTRACT: pass ONLY the transport/API error text — the stderr of the
# FAILING call (the HTTP status line or JSON error body). NEVER pass a model
# completion. A model REVIEW that merely *discusses* "429" or "rate limit" is not
# an exhaustion signal; recording it falsely marked Sol spent and parked the
# OpenAI gate (retro §3.3 / H6). We therefore match only STRONG error signatures a
# real 429/quota response carries — never a bare "429" or a bare "rate limit".
# Grok Build currently reports exhausted subscription capacity as HTTP 402, not
# 429. That exception is deliberately narrower: only the exact, whole transport
# error for the grok-heavy seat is accepted. Generic 402/payment/auth prose, or a
# completion that merely discusses the error, cannot mutate the ledger.
# ─────────────────────────────────────────────────────────────────────────────
sig='HTTP[ /]?429|429 Too Many Requests|status[ :]+429|code[ :]+429|error[^0-9]{0,20}429|rate.?limit.?exceeded|usage.?limit.?reached|quota.?exceeded|insufficient_quota'
grok_402_sig='^[[:space:]]*(Error:[[:space:]]*)?(HTTP[[:space:]]+402:[[:space:]]*|402[[:space:]]+Payment Required:[[:space:]]*)Grok Build usage balance exhausted[[:space:]]*$'
signal_note="429/usage-limit recorded by wrapper"
grok_balance_exhausted=false
if [ "$seat" = "grok-heavy" ] \
  && [[ "$message" != *$'\n'* && "$message" != *$'\r'* ]] \
  && printf '%s' "$message" | grep -Eiq "$grok_402_sig"; then
  signal_note="Grok Build 402 usage-balance-exhausted recorded by wrapper"
  grok_balance_exhausted=true
elif ! printf '%s' "$message" | grep -Eiq "$sig"; then
  exit 0
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "record-429: jq is required" >&2
  exit 1
fi
if [ ! -f "$windows" ]; then
  echo "record-429: usage-window registry not found: $windows" >&2
  exit 1
fi
if ! jq -e --arg seat "$seat" \
  '(.seats | type) == "object" and (.seats | has($seat))' \
  "$windows" >/dev/null 2>&1; then
  echo "record-429: unknown seat $seat (not present in $windows)" >&2
  exit 1
fi

# A reset may be inferred as +5h only when every configured window for this seat
# is actually a five-hour rolling window. Weekly/monthly/mixed/none seats can be
# exhausted much longer; without provider reset evidence they remain spent with
# reset unknown rather than being auto-unparked early.
rolling_only_5h="$(jq -r --arg seat "$seat" '
  (.seats[$seat].windows // []) as $windows
  | (($windows | length) > 0
     and all($windows[]; .kind == "rolling" and (.hours | tonumber?) == 5))
' "$windows")"
if [ -z "$reset" ] && [ "$grok_balance_exhausted" = false ] \
  && [ "$rolling_only_5h" = true ]; then
  reset="$(date -u -v+5H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '+5 hours' +%Y-%m-%dT%H:%M:%SZ)"
fi
if [ -n "$reset" ] && ! jq -ne --arg reset "$reset" \
  '($reset | fromdateiso8601) > now' >/dev/null 2>&1; then
  echo "record-429: MB_429_RESET must be a future UTC ISO instant ending in Z" >&2
  exit 1
fi

umask 077
mkdir -p "$(dirname "$ledger")"
lock="${ledger}.lock"
lock_attempts=0
while ! mkdir "$lock" 2>/dev/null; do
  lock_attempts=$((lock_attempts + 1))
  if [ "$lock_attempts" -ge 250 ]; then
    echo "record-429: timed out waiting for the ledger lock" >&2
    exit 1
  fi
  sleep 0.02
done

tmp="${ledger}.tmp.$$"
trap 'rm -f "$tmp"; rmdir "$lock"' EXIT
if [ -s "$ledger" ]; then
  base="$(cat "$ledger")"
else
  base='{}'
fi
jq --arg seat "$seat" --arg reset "$reset" --arg note "$signal_note" --arg now "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  'if type != "object" then error("ledger root must be an object") else
   . + {($seat): {spent: true, spent_until: (if $reset == "" then null else $reset end), note: $note, updated: $now}} end' \
  <<<"$base" >"$tmp"
mv "$tmp" "$ledger"
