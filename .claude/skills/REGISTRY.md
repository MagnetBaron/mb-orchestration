# Skills registry (single source)

The durable catalogue of every skill the orchestration can call. `AGENTS.md`
§Skills points here; do not duplicate this list into `AGENTS.md`. Skills are
committed to the repo (never `~/.claude`) so they are durable and reach cloud
sessions/routines.

## How each seat calls a skill

- **Claude Code · Codex CLI (0.147+) · Cursor (2.4+)** — auto-load when the task
  matches a skill's `description`. All three scan `.claude/skills/`.
- **Grok Build / Grok Bot (bulk coder, does NOT auto-load skills)** — a skill
  reaches Grok as a **`must_read` path in the brief**. Dispatch looks up the
  trigger below, puts the `SKILL.md` path in `must_read`, and Grok reads it before
  implementing. Grok can also self-serve: scan this table, read the matching
  `SKILL.md` by path. A skill is just another `must_read` path.

## Layer 1 — MB brand skills (proprietary / private)

| Skill | Path | Use when (trigger for Grok `must_read`) | Land gate |
|-------|------|------------------------------------------|-----------|
| `mb-theme-safety` | `mb-shopify-theme/.claude/skills/mb-theme-safety/` | before any theme push; a file won't update despite a merged push | single-frontier |
| `mb-shopify-release` | `mb-shopify-theme/.claude/skills/mb-shopify-release/` | owner asks to promote/deploy to live | cross-family + owner |
| `mb-theme-conventions` | `mb-shopify-theme/.claude/skills/mb-theme-conventions/` | editing sections/snippets/blocks/templates/assets or customer copy | single-frontier |
| `theme-preflight` | `mb-shopify-theme/.claude/skills/theme-preflight/` | after theme edits, before push/PR | single-frontier |
| `mb-usage-status` | `.claude/skills/mb-usage-status/` | before routing/reviewing; user asks for the seat map | none (read-only) |
| `mb-review-order` | `.claude/skills/mb-review-order/` | stamping review depth / choosing a reviewer seat | none (read-only) |

## Layer 2 — MB public-distributable candidates (generic; MIT-able; publishable)

| Skill | Path | Use when | Notes |
|-------|------|----------|-------|
| `mb-mcp-hardening` | `.claude/skills/mb-mcp-hardening/` | building/changing an MCP server; security review before ship | generic MCP security; strip MB names → publish as `mcp-hardening` |
| `doctrine-sync` | `.claude/skills/doctrine-sync/` | refresh the doctrine Map-of-Content index | generic markdown indexer (`build_index.py`); publishable as `vault-index` |

## Layer 3 — adopt (third-party / built-in; install on the seat, do not fork)

Enable behind the gate: **cross-family + `/security-review`** for any third-party
skill (skills execute code; `allowed-tools` can self-grant; `!command` runs shell).

| Skill / bundle | Source | Use for | MB verdict |
|----------------|--------|---------|-----------|
| `liquid-skills` (+ `liquid-lsp`) | `Shopify/liquid-skills` | OS 2.0 Liquid authoring, a11y, standards | adopt |
| Shopify **Dev MCP** (scoped) | `Shopify/dev-mcp` | `validate_theme` + schema introspection (MCP, not a skill) | adopt scoped |
| `mcp-builder` | `anthropics/skills` (on box: `/mnt/skills/examples/mcp-builder`) | build MCP servers (pairs with `mb-mcp-hardening`) | adopt |
| `skill-creator` | `anthropics/skills` (on box: `/mnt/skills/examples/skill-creator`) | author/measure new MB skills | adopt (authoring tool) |
| `brand-guidelines` | `anthropics/skills` (on box: `/mnt/skills/examples/brand-guidelines`) | template for an MB brand skill (Anthropic's own brand) | reference → build `mb-brand-guidelines` |
| `dart-lang/skills`, `flutter/agent-plugins` | official | Dart/Flutter | adopt when Flutter starts |
| `obra/superpowers` (subset) | marketplace | TDD, systematic-debugging, git-worktrees | adopt selective |

## On-box inventory (the "gather" — catalogue only; licences forbid forking)

Present on this machine now. Paths are this container's mount (`/mnt/skills`,
`/root/.claude/skills`); on the Mini they live in the CLI install / `~/.claude`.
Source of truth for the Anthropic ones is the `anthropics/skills` repo + claude.ai
sync — **reference/install, do not copy** (public set is source-available; examples
carry their own LICENSE.txt).

- **Anthropic public (source-available):** `docx`, `pdf`, `pptx`, `xlsx`,
  `file-reading`, `pdf-reading`, `frontend-design`, `product-self-knowledge`
  (`/mnt/skills/public`). Docs skills already synced to MB via claude.ai.
- **Anthropic examples (see LICENSE.txt) — MB-dev-relevant:** `mcp-builder`⭐,
  `skill-creator`⭐, `brand-guidelines`⭐, `web-artifacts-builder`, `canvas-design`,
  `theme-factory`, `internal-comms`, `deep-research`, `doc-coauthoring`,
  `setup-writing-style`, `algorithmic-art`, `paint`, `slack-gif-creator`, `learn`
  (`/mnt/skills/examples`).
- **Anthropic examples — consumer/agentic, not MB-dev:** `benepass-reimbursement`,
  `call-to-book`, `cancel-unsubscribe`, `event-planning`, `file-expenses`,
  `file-form`, `financial-calculator`, `grocery-shopping`, `hire-help`,
  `meal-delivery`, `prescription-refill`, `return-refund`. Ignore for orchestration.
- **User synced (claude.ai):** `docx`, `pdf`, `pptx`, `xlsx`, `morning`,
  `import-memory`, `session-start-hook` (`/root/.claude/skills`). Personal/synced —
  not durable for the fleet; the durable copies are the repo ones above.

Full evaluation and the pull-based build backlog: `../../skills-eval.md`.
Integration status + gates: `../../INTEGRATION.md`. Work request for wiring the
distributable layers: `../../requests/skills-integration.md`.
