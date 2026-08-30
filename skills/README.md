# Selective skill tree

`registry.json` pins 44 leaf playbooks in four non-discovery libraries under
`~/.codex/skill-library/`. Only four concise routers are linked into
`~/.agents/skills/`:

| Router | Private leaves | Use |
|---|---:|---|
| `mobile-dev-router` | 24 | Dart, Flutter, native iOS accessibility |
| `cloudflare-dev-router` | 12 | Cloudflare platform and operations |
| `knowledge-vault-router` | 4 | Obsidian Markdown, Bases, Canvas, CLI |
| `engineering-dev-router` | 4 | React specialties, generic MCP design, web performance |

Codex, Grok, Claude Code, and compatible clients see only router metadata.
When a real task matches, the router reads its compact catalog and opens one
primary leaf plus at most one distinct validation leaf. Dispatch never reads
leaf bodies. Unrelated briefs use `skills: []`.

This follows Codex progressive disclosure: startup sees skill names,
descriptions, and paths, while full `SKILL.md` bodies load only after selection.
Keeping leaves outside user and repository discovery roots avoids description
truncation and accidental broad activation as the library grows.

`orca` is the orchestration entry skill, not a role-loaded specialty router. Its
tracked source is `skills/orca/SKILL.md`; `sync-commands.sh` copies it to
`~/.agents/skills/orca/SKILL.md`. It intentionally remains outside
`skills/registry.json`, whose allowlist governs skills that may be bound inside
implementation and review roles.

## Installation and reconciliation

Upstream sources and exact revisions are in `registry.json`; evaluation and
exclusions are in `SOURCE_AUDIT.md`. Install new upstream leaves directly into
their bundle’s private `library_root`. Never install them into
`~/.codex/skills` or `~/.agents/skills`.

For the migration of known legacy user-level leaves, then normal verification:

```bash
python3 skills/sync.py --migrate-library
python3 skills/sync.py --check
```

Normal reconciliation:

```bash
python3 skills/sync.py
python3 skills/sync.py --check
```

The migration moves only registry-owned leaf directories, removes only known
leaf symlinks, creates router links, and regenerates the two mobile Codex role
profiles. Collisions fail closed. Other role profiles are deliberately not
created: Cloudflare, vault, React, MCP, and performance tasks need no permanent
tool schema, so briefs load their router dynamically.

## Brief routing

Every brief carries `skills`. Unrelated work uses `skills: []`. A matching
brief names one router and includes its exact
`~/.agents/skills/<router>/SKILL.md` path in `must_read`. The receiver selects
the private leaf. A dedicated native iOS accessibility review may directly
name only `ios-accessibility` and its private path.

Skills never create seats, grant credentials or tools, expand filesystem
scope, deploy, publish, or authorize an external mutation.
