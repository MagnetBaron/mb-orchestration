# Request: integrate the skills set into orchestration (distributable + brand layers)

Work request for the next session. Written as an MB brief. The skills exist and are
wired into `AGENTS.md` §Skills; this request covers the distribution structure,
the review/land gates, and the public-vs-brand split.

## Brief

- **objective:** land the skill set into the orchestration so every seat (incl.
  Grok, the bulk coder) can call it durably, and stand up a public-distributable
  skill set that coexists with the brand-specific one.
- **must_read:** `skills-eval.md` · `INTEGRATION.md` · `.claude/skills/REGISTRY.md`
  · `AGENTS.md` §Skills · `DOCTRINE.md` §Review depth (gate).
- **must_not_touch:** `config/settings_data.json`, any `production`/`main` deploy,
  live theme, secrets. Do not enable `mb-shopify-release` or any MCP change without
  the cross-family + owner gate.
- **output_path:** the marketplace repo(s) below + PRs merging the two branches
  `claude/shopify-skills-local-tools-wvwnjh`.
- **done_when:** (1) both skill branches reviewed at their gate and merged; (2)
  the public + brand marketplaces resolve and install; (3) a Grok test brief loads
  a skill via `must_read` and implements from it; (4) the adopt-list is installed
  on the Mini seats.
- **effort:** medium. **review:** single-frontier (standing config); cross-family
  for `mb-shopify-release`, MCP changes, and every third-party enable.

## Already done (this branch, both repos)

- 8 skills authored as `.claude/skills/<name>/SKILL.md` (portable 6-field
  frontmatter; scanned by Claude/Codex/Cursor). See `INTEGRATION.md` §1.
- `AGENTS.md` §Skills added: seat reachability + the **Grok `must_read` protocol**
  (a skill reaches Grok as a `must_read` path; `REGISTRY.md` maps trigger → path).
  Two hard bans added (personal `~/.claude/skills` as durable store; third-party
  enable without cross-family + `/security-review`).
- `REGISTRY.md` = the single-source catalogue, incl. the on-box skill inventory.
- `doctrine-sync/scripts/build_index.py` validated (21 md files).

## How to make the public and brand sets coexist

Three layers load side by side, kept distinct by **namespacing** (`mb-brand:*`,
`mb-common:*`, and each third-party plugin's own prefix). Repo-local `.claude/skills/`
is Tier 1 (works now, no install); the marketplaces below are Tier 2 (distributable,
versioned).

1. **Brand set — private.** New private repo `magnetbaron/mb-claude-plugins` with a
   `mb-brand` plugin (`.claude-plugin/plugin.json`, license proprietary) that
   references the brand skills (theme + release + orchestration-specific). Private
   marketplace: `/plugin marketplace add magnetbaron/mb-claude-plugins`.
2. **Public set — publishable.** A `mb-common` plugin (license MIT) for the generic
   skills (`mcp-hardening`, `vault-index`/`doctrine-sync`) — strip MB-internal
   references first. Ship it in the same private marketplace initially; when ready,
   publish `magnetbaron/mb-skills-public` (or submit to `anthropics/claude-plugins-community`).
3. **Third-party + built-in.** Install from their own marketplaces (see
   `REGISTRY.md` Layer 3). `mcp-builder` + `skill-creator` + `brand-guidelines` are
   already on the box under `/mnt/skills/examples` — install from `anthropics/skills`.

Coexistence rules: keep brand names `mb-*` prefixed so they never clobber a public
skill; project `.claude/skills/` wins over plugin skills on a name clash; the
`mb-common` (public) set must contain nothing brand-specific or secret so it stays
publishable.

## Durability for Grok (verify before closing)

Grok does not read skills. The durable path is the `must_read` protocol in
`AGENTS.md` §Skills + `REGISTRY.md`. **Test:** dispatch a small theme brief with
`must_read: mb-shopify-theme/.claude/skills/mb-theme-safety/SKILL.md`; confirm Grok
reads it and runs the limits check before pushing. If the marketplace route is used
on the Mini, add the installed plugin's skill path (e.g.
`~/.claude/plugins/.../skills/<name>/SKILL.md`) to `REGISTRY.md` so Grok can read
those too.

## Next-session task list

1. Run the gates: single-frontier review of the two skill branches; cross-family +
   owner for `mb-shopify-release`; cross-family for `mb-mcp-hardening`/MCP; merge.
2. Install the adopt-list on the Mini seats: `liquid-skills` (+`liquid-lsp`),
   Shopify Dev MCP (scoped), `mcp-builder`, `skill-creator`. Flutter set when needed.
3. Create `magnetbaron/mb-claude-plugins` with `mb-brand` + `mb-common` plugins;
   verify `/plugin install` on a Claude seat and a Codex seat.
4. Build `mb-brand-guidelines` from the `brand-guidelines` template (MB colours,
   type, voice; the no-em-dash-in-copy rule).
5. Decide open-sourcing `mb-common`; if yes, publish the public marketplace.
6. Then pull from the backlog (`skills-eval.md` §7.2) as tasks recur.

## Do not

- Enable `mb-shopify-release` or land an MCP change without the gate + owner.
- Put anything brand-specific or secret in the public (`mb-common`) plugin.
- Move routing rules out of `AGENTS.md` into a skill (Grok would lose them).
- Fork the Anthropic on-box skills into MB repos (licences) — install/reference.
