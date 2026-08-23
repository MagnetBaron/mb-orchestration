# Deferred — not in v1

This repo is **policy only**. v1 assumes one worker machine. Do not load this file into agent context.

## Expansion: multi-Mini seats (same AI accounts)

Hardware: several baseline M4 16 GB Minis at different desks; same Grok / Claude / Codex / Cursor logins (one quota pool, not 3×).

Intended later, **not implemented**:

1. **Control Mini** — Codex/CLI + phone pairing only. No full QA, no Grok volume.
2. **Worker / QA Mini** — implement + exactly one test suite.
3. **Active host** — which desk is in use (Codex Remote connected host, or console user on `/dev/console`). Not free-RAM guessing.
4. **Exclusive QA** — two QA Minis are never used at the same time; suite runs only on the active seat; the other is idle even if powered on.
5. **No RAM/CPU cluster broker** — do not auto-hop jobs between Minis to “use spare cores.” Busy worker → queue (refill law).

Until this ships: pick one worker Mini by hand (or Codex Remote target). Copy `AGENTS.md` onto that box.
