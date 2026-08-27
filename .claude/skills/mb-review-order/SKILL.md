---
name: mb-review-order
description: Apply the Magnet Baron review routing order and cross-family gate when a change needs review. Use when stamping review depth on a change-set or choosing which reviewer seat to spend. Points at the single-source class map and risk gate rather than restating them, so the routing stays correct as doctrine changes.
license: proprietary
allowed-tools: Read, Grep
---

# Review order and cross-family gate

This skill is a pointer, not a copy. The class map is single-source in
`DOCTRINE.md` §Review depth; the risk gate is in `AGENTS.md`. Read those to stamp
`review:` — do not classify against any list restated here (a lossy copy
over-spends frontiers and drops Review D).

## The routing that does not change

- **Depth floor by task class** → read `DOCTRINE.md` §Review depth table rows.
  Class is derived from the diff's touched paths/resources, not the brief's claim;
  ambiguity rounds up one level. The risk gate only ever **raises** the floor.
- **Levels:** none · self-check (implementer's own tests bound to `done_when`) ·
  single-frontier (first live seat) · cross-family (one pass each from two
  families).
- **Order** (route by `mb-usage-status`, not guesswork):
  **Fable (if present) → Codex Sol → Opus 4.8 → Review E (Fireworks, if wired) → stop.**
- **Families:** Fable + Opus 4.8 are **one** family (Anthropic); Codex Sol is
  OpenAI; Review E is independent open-weight. Cross-family needs two *different*
  families — never two Anthropic passes.
- **Review E** engages only at confirmed quota exhaustion of native seats, or as
  the second family when one native family is quota-spent and only one remains;
  never on a mere outage, never as sole gate on a risk class, never with
  secrets/PII.
- **`blocked` wins** if reviews disagree. Max two fix loops, then park unless a
  novel defect.
- **Review D** (Website Visual QA) when storefront pixels change — separate from
  code review; `visual-qa.md`.

## Gate raises (from `AGENTS.md`)

Raise to cross-family on: auth / money / PII / prod / irreversible · multi-service
· Grok conflict or flaky tests · standing config touching OAuth/secrets/prod URL.
`user said ship` = land, not spend a frontier.

Single source: `AGENTS.md` (risk gate) + `DOCTRINE.md` §Review depth. Use
`mb-usage-status` for live seat state.
