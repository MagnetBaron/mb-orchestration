#!/bin/bash
# Record ONLY a provider-confirmed 429/usage-limit signal into config/usage-ledger.json.
# Never call this for auth failures, timeouts, or generic non-zero exits (those are
# OUTAGE, not exhaustion — EDGE-CASES.md QUOTA-vs-OUTAGE). The 5h default reset matches
# the rolling window; pass MB_429_RESET for a different reset instant.
set -euo pipefail

seat="${1:?seat name required (a seat in config/usage-windows.json)}"
message="${2:-}"
default_ledger="$(cd "$(dirname "${BASH_SOURCE[0]}")/../config" && pwd)/usage-ledger.json"
ledger="${MB_USAGE_LEDGER:-$default_ledger}"
reset="${MB_429_RESET:-$(date -u -v+5H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '+5 hours' +%Y-%m-%dT%H:%M:%SZ)}"

if ! printf '%s' "$message" | grep -Eiq '(^|[^0-9])(429|rate.?limit|usage.?limit|quota.?exceed|too many requests)([^0-9]|$)'; then
  exit 0
fi

mkdir -p "$(dirname "$ledger")"
lock="${ledger}.lock"
while ! mkdir "$lock" 2>/dev/null; do sleep 0.02; done
trap 'rmdir "$lock"' EXIT

tmp="${ledger}.tmp.$$"
if [ -s "$ledger" ]; then
  base="$(cat "$ledger")"
else
  base='{}'
fi
if command -v jq >/dev/null 2>&1; then
  jq --arg seat "$seat" --arg reset "$reset" --arg note "429/usage-limit recorded by wrapper" --arg now "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '. + {($seat): {spent_until: $reset, note: $note, updated: $now}}' \
    <<<"$base" >"$tmp"
else
  echo "record-429: jq is required to update $ledger" >&2
  exit 1
fi
mv "$tmp" "$ledger"
