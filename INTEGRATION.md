# Skills integration handoff

For the session that wires these skills into the orchestration system. Authored on
branch `claude/shopify-skills-local-tools-wvwnjh` in both repos. Nothing here is
enabled for production use yet — enabling is gated (see §4). Rationale and the full
adopt/build/skip evaluation: `skills-eval.md`.

## 1. What was built (8 skills, ready to call)

Format is `.claude/skills/<name>/SKILL.md` — the portable location scanned by
**Claude Code, Cursor (v2.4+), and Codex CLI (0.147.0+)**. **Grok Build/Bot does
not read skills**; every skill is a thin wrapper that points at the single-source
`.md` so Grok reads the same source directly. One source, all seats converge.

**`mb-shopify-theme/.claude/skills/`**
- `mb-theme-safety` — platform-limits / silently-wedged-file guard (wraps `scripts/mb-check-theme-limits.mjs`; `references/limits.md`).
- `mb-shopify-release` — owner-gated live-release ritual (wraps `mb-backport.sh` + `mb-release.sh --live`).
- `mb-theme-conventions` — house Liquid conventions + custom-feature file map.
- `theme-preflight` — pre-push validation gate (Dev MCP validate + limits + Review D).

**`mb-orchestration/.claude/skills/`**
- `mb-mcp-hardening` — security-review/harden an MCP server (incl. internal ShopifyMCP).
- `doctrine-sync` — second-brain Map-of-Content indexer (`scripts/build_index.py`, stdlib, validated: indexes 21 md files).
- `mb-usage-status` — live seat/quota read (wraps `usage-status.py`).
- `mb-review-order` — review depth + cross-family gate order (points at `AGENTS.md` / `DOCTRINE.md`).

## 2. How the seats call them

- **Model-invoked:** the description triggers the skill when a matching task appears
  (that is the "as needed" path). Descriptions are written what+when, third person.
- **User-invoked:** `/mb-theme-safety` etc. If later packaged as a plugin, they
  namespace as `/mb-tools:<skill>`.
- **Grok:** unchanged — reads `AGENTS.md` + repo `.md`. Do not move routing rules
  out of `AGENTS.md` into a skill, or Grok (the default implementer) loses them.

## 3. Adopt these public skills too (install on the seat; not authored here)

- `liquid-skills` (3 official Shopify Liquid skills) + `liquid-lsp` — `Shopify/liquid-skills`.
- Shopify **Dev MCP**, scoped to `validate_theme` + schema introspection — `Shopify/dev-mcp`. (An MCP, so it carries a standing tool-schema cost; `theme-preflight` gates *when* to call it.)
- `mcp-builder` (official) — `anthropics/skills` — pairs with `mb-mcp-hardening`.
- `dart-lang/skills` + `flutter/agent-plugins` — only when Flutter work starts.
- Selective: `evanca/flutter-ai-rules` (state-mgmt), `obra/superpowers` (TDD/debug/worktrees), `trailofbits/skills` (audit passes) — each behind the §4 third-party gate.

## 4. Review gates BEFORE enabling for real use (do not skip)

Building the files on a branch is done; **enabling/landing** carries the risk gate
(`DOCTRINE.md` §Review depth — skills are *standing config*, self-perpetuating):
- Skill library merge to `main` → **single-frontier** floor (standing config).
- `mb-shopify-release` → **cross-family + owner** (it can open a live-deploy PR; prod).
- `mb-mcp-hardening` and any MCP change → **cross-family** (OAuth/secrets/prod URL).
- **Any third-party/public skill enable** → **cross-family + `/security-review`** of
  its `SKILL.md` and every bundled script (skills execute code; `allowed-tools` can
  self-grant; `!`command`` runs shell before the model sees the body). Pin versions.
- Never route a skill/script carrying secrets or customer PII to a third-party
  inference host (existing hard ban).

## 5. Packaging path

- **Now (Tier 1):** repo-local `.claude/skills/` — works immediately for
  Claude/Codex/Cursor once merged, zero install. Reaches cloud sessions/routines
  (repo `.claude/` is cloned); personal `~/.claude/skills/` would not.
- **Later (Tier 2):** if you want one installable, versioned bundle across repos,
  create a private `magnetbaron/mb-claude-plugins` marketplace (a plugin per group).
  Note the two-repo split — theme skills wrap theme scripts and belong with the
  theme; a marketplace would reference them, not relocate them.

## 6. Portability rules baked in

- Cross-surface skills use only the 6 portable frontmatter fields
  (`name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`).
- No Claude-only frontmatter (`context`, `paths`, `hooks`, `disable-model-invocation`)
  is used, so all 8 load on Codex/Cursor too. `mb-shopify-release` relies on its
  description + the script's own guards + the owner merge gate instead of
  `disable-model-invocation`; on the Claude seat you may add that flag for an extra
  guard (it will make that one skill Claude-only).
- Skill count is a budget (~20 full descriptions before Claude Code truncates
  least-used ones). This set is 8; add the §7.2 backlog pull-based, not in bulk.

## 7. Pull-based backlog (build when the task recurs — see `skills-eval.md` §7.2)

`mb-theme-codemod`, `mb-css-bundle`, `mb-perf-audit`, `mb-seo-structured-data`,
`mb-i18n`, `mb-integrations` (Judge.me/Omnisend/Stoq), `mb-teamclaude`,
`mb-visual-qa-handoff`, and the second-brain line (`vault-search`, `capture-note`
with review-class auto-stamp, `decision-log`). Skip: a Flow-authoring skill
(Sidekick owns it), and anything duplicating a built-in (`/code-review`,
`/security-review`, `/init`) or the live GitHub/Shopify Admin MCPs.

## 8. Validation done in this session

- `doctrine-sync/scripts/build_index.py` runs clean (stdlib only; indexed 21 md
  files; correctly skips `.claude/`, `.git/`; deterministic, no timestamps).
- All skill names are valid (lowercase-hyphen, no reserved words); frontmatter is
  portable; bodies are short and point at single sources rather than copying them.
- Not done (intentionally, gated): enabling any skill, editing `AGENTS.md`/`CLAUDE.md`
  to reference the library, creating a plugin/marketplace, installing public skills.
  Those are this integration's calls, under §4.
