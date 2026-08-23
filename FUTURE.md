# Deferred — not in v1

This repo is **policy only**. v1 assumes one worker machine. Do not load this file into agent context.

## Expansion: multi-Mini seats (same AI accounts)

Hardware: several baseline M4 16 GB Minis; same quota pool, not 3×.

Intended later, **not implemented**:

1. **Control Mini** — Codex/CLI + phone pairing only.
2. **Worker / QA Mini** — implement + exactly one test suite.
3. **Active host** — Codex Remote connected host or console user. Not free-RAM guessing.
4. **Exclusive QA** — two QA Minis never simultaneous.
5. **No RAM/CPU cluster broker**.
6. **Official Grok Bot HTTP API** — when xAI ships one, replace Slack drop if it is cleaner. Do not adopt `:1340` or require Grok Bot.app on the worker.
7. **Product-edit factory** — batch Shopify MCP catalog jobs under Codex; still no Review D per SKU.

Until this ships: pick one worker Mini by hand. Copy `AGENTS.md` onto that box.
