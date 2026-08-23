# mb-orchestration

Tight multi-CLI coding policy for Magnet Baron.

**Grok implements. A non-Grok frontier reviews. Codex dispatches. Cursor $400 is last.**

## Why this exists

Public orchestration prompts and plugins (Fable-as-commander, 28-agent catalogs, full skill trees) work, but they **blow context**. This repo keeps one canonical `AGENTS.md` (~120 lines) shared by Codex/Cursor-family tools, plus a one-screen `CLAUDE.md` import for Claude Code.

## Roles

1. **Codex ($200)** — phone task manager only (Terra/Luna)
2. **Grok Super Heavy / Build / Bot** — primary implementer
3. **Fable 5** (while Max/Premium include it) — frontier reviewer / architect
4. **GPT-5.6 Sol** — frontier reviewer when Fable is empty or post-downgrade
5. **Opus 4.8** — Claude reliability reviewer (not Opus 5)
6. **Cursor Ultra** — IDE on Cursor Models; Other Models $400 last resort

## Files

| File | Purpose |
|------|---------|
| [AGENTS.md](./AGENTS.md) | Canonical routing (all agents) |
| [CLAUDE.md](./CLAUDE.md) | `@AGENTS.md` + Claude pins |
| [teamclaude.routes.example.json](./teamclaude.routes.example.json) | Fable/Opus seat routes |
| [install.md](./install.md) | Copy paths + optional heavier harnesses |

## Research basis (short)

- Fable leads long-horizon patch quality; Sol leads terminal/agent loops; Grok leads $/task speed — so **implement with Grok, review with Fable/Sol**.
- Published patterns agree on **architect ≠ implementer** and **blind review on git diff** ([fable-foreman](https://github.com/olsenbrands/fable-foreman), [master-workflow](https://github.com/luckeyfaraday/master-workflow), [fable-orchestrator](https://github.com/mar3co/fable-orchestrator)).
- `AGENTS.md` is the cross-tool standard; Claude uses `CLAUDE.md` with `@AGENTS.md` import.

## Setup

See [install.md](./install.md).

## Note on the missing external prompt

The chat that created this asked to trim an external orchestration prompt, but the prompt body was not attached. This policy is the refined version of that intent plus the current quota map. Open an issue with any longer prompt to compress it further into `AGENTS.md`.
