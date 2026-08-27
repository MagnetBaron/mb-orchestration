---
name: mb-usage-status
description: Read live seat/quota state for the Magnet Baron orchestration before routing or reviewing. Use whenever a decision depends on which seats are available, spent, or soft-capped, or when the user asks for the seat map. Runs usage-status.py and interprets it; never estimate quota from the model.
license: proprietary
allowed-tools: Bash(python3 usage-status.py*), Bash(python3 ./usage-status.py*), Read
---

# Usage status (seat/quota state)

Seat state and reset instants come from the ledger + computed windows, **never**
from LLM token estimation and never hardcoded. Run the tool, read its output,
route from that.

## Run it

```
python3 usage-status.py
```

Prints each seat: `available` / spent / soft-capped, next reset, and window type
(weekly / rolling 5h / monthly / metered). "limits come from recorded 429/ledger
signals + computed windows" — a seat with "no signal recorded" is available by
window, not probed.

## Use it well

- **Route reviews by this, not guesswork** (`AGENTS.md` risk gate). Order when a
  frontier review is needed: Fable → Codex Sol → Opus 4.8 → Review E (if wired).
- **Exhaustion opens the next seat only on quota evidence** (a recorded 429 or
  ledger %), never on a probe failure/timeout — those fail closed and park
  (`EDGE-CASES.md`).
- A whole-pipe outage is one outage (Fable+Opus 4.8 = one Anthropic pipe;
  Sol+Terra+Luna = one Codex pipe). Diagnose, do not cascade.
- To record a 429 signal: `roles/record-429.sh` (see `usage-metering.md`).

Single source: `usage-metering.md`, `sol-usage.md`, `fireworks-usage.md`. Read
those for the metering rules; do not re-summarize them here.
