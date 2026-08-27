# Magnet Baron orchestration skills

Repo-local Claude Code Skills for `mb-orchestration`. Progressive disclosure: only
`name` + `description` sit in context until a skill triggers. Scanned by the
skill-aware seats — **Claude Code, Cursor (v2.4+), Codex CLI (0.147.0+)** all read
`.claude/skills/`. **Grok Build/Bot does not read skills**; it reads the repo
`.md`, which is why each skill points at the single-source `.md` instead of copying
it.

Evaluation + full backlog: `skills-eval.md`. Integration/handoff: `INTEGRATION.md`.

| Skill | Purpose | Points at / wraps |
|-------|---------|-------------------|
| `mb-mcp-hardening` | Security-review & harden an MCP server (incl. internal ShopifyMCP). | mcp-builder (adopt), CSA/OWASP guidance |
| `doctrine-sync` | Build/refresh the doctrine Map-of-Content (`_index.md`) — second-brain index. | `scripts/build_index.py` (stdlib, validated) |
| `mb-usage-status` | Read live seat/quota state before routing/reviewing. | `usage-status.py`, `usage-metering.md` |
| `mb-review-order` | Apply review depth + cross-family gate order. | `AGENTS.md`, `DOCTRINE.md` §Review depth |

The `orchestrate` dispatch policy stays a **command** (`.claude/commands/orchestrate.md`),
unchanged — it is already shared verbatim across seats.

## Adopt alongside (public, install on the seat — not authored here)

- `mcp-builder` (official) — build/refactor MCP servers —
  https://github.com/anthropics/skills
- `dart-lang/skills` + `flutter/agent-plugins` (when Flutter work starts).
