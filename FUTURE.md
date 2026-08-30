# Deferred — not all of this is v1

This is a **policy + tooling** repo; this file lists only deferred work. Do not load it into agent context.

## Multi-Mini seats (same AI accounts)

Hardware: several baseline M4 16 GB Minis; same quota pool, not 3×.

### Shipped

- **Exclusive QA idle handoff** — GitHub Actions in private [`MagnetBaron/qa-idle-handoff`](https://github.com/MagnetBaron/qa-idle-handoff). First idle mini labeled `qa` takes the job. Two QA minis never simultaneous (`qa-exclusive`). No RAM/CPU cluster broker. Policy: `qa-idle-handoff.md`.

### Still deferred

1. **Control Mini** — Codex/CLI + phone pairing only.
2. **Worker Mini as implementer** — implement + exactly one test suite on a dedicated box (QA smoke is what shipped; Grok Build still runs on the active host).
3. **Active host** — Codex Remote connected host or console user. Not free-RAM guessing.
4. **Code-owned browser/pixel and Clarity input bindings for Grok CLI** — implement the separate fail-closed bindings first; then adopt only official or tightly scoped observed integrations, sync profiles, and role-test them before promoting Review D/Heat Map. Do not invent localhost Bot APIs or let observed capability substitute for the binding.
5. **Product-edit factory** — batch Shopify MCP catalog jobs under Codex; still no Review D per SKU.

Implement work: still pick one worker Mini by hand and copy `AGENTS.md` onto that box. QA smoke is the exception — Dispatch clicks **Run workflow** on `qa-idle-handoff`.
