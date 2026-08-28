# Selective mobile skill tree

`registry.json` pins the upstream iOS accessibility, Dart, and Flutter leaf
playbooks. The 24 leaves live in the non-discovery library
`~/.codex/skill-library/mobile`; they are not linked into a user or repository
skill discovery root.

Only `mobile-dev-router` is linked at `~/.agents/skills/mobile-dev-router`.
Codex, Grok, Claude Code, and compatible clients see one concise description.
When real mobile work matches, the router reads its compact catalog and then
opens only one primary leaf, plus at most one distinct validation leaf.

| Route | Startup exposure | Full instructions loaded |
|---|---|---|
| Dispatch or ordinary agent, unrelated work | one router description | none |
| Dispatch, mobile brief | one router description | no leaf bodies |
| Existing mobile implementation seat | one router description | router, catalog, one or two selected leaves |
| `mb-mobile-accessibility-reviewer` | direct role configuration | `ios-accessibility` only |
| `mb-mobile-tooling` | direct role configuration | router plus role-scoped Dart MCP tools |

The two Codex agent files are role profiles inside existing seats, not new
seats or permissions. Dart MCP is deliberately role-scoped: enabling it for the
repository root would make Dispatch and unrelated agents carry its tool schemas.
Grok can discover and invoke the universal router. A Grok session has Dart MCP
only when its target project or enabled Grok configuration supplies the server;
the router uses CLI fallbacks or reports the live-tool validation gap honestly.

For the one-time conversion from the earlier 24-link layout, run:

```bash
python3 skills/sync.py --migrate-library
```

For normal reconciliation and verification, run:

```bash
python3 skills/sync.py
python3 skills/sync.py --check
```

The migration moves the exact pinned leaf directories from `~/.codex/skills`
into the private library, removes only known leaf symlinks, links the router,
and generates the two machine-local Codex role files. Collisions fail closed.

Briefs use `skills: []` for unrelated work. Mobile implementation briefs use
`skills: [mobile-dev-router]` and include
`~/.agents/skills/mobile-dev-router/SKILL.md` in `must_read`. Native iOS
accessibility review may instead directly name `ios-accessibility` with its
private library path. The skill layer never grants tools, deploys, or broadens
the assigned scope.
