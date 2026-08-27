# Skills evaluation — Shopify / Flutter / GitHub / second-brain

Research packet for adopting **Claude Code Skills** at Magnet Baron on the "load on demand, no token burn locally" model. Current as of 2026-08-27. Verdicts are `adopt` (install existing) · `build` (private, MB-proprietary) · `skip` (immature, redundant, or already owned). This file is the `must_read` for the skill-library build lane; it does not enable anything by itself.

**Authority note:** this is a design-time doc like `DOCTRINE.md`. Keep it out of every agent context; load it only when building or routing skill work.

---

## 0. The mechanic — why "skills" *are* the no-token-burn answer

A skill is a filesystem folder (`SKILL.md` + optional scripts/refs) that Claude reads on demand. Loading is **progressive disclosure**, three levels:

| Level | Loads | Token cost | Content |
|-------|-------|-----------|---------|
| L1 metadata | always, at startup | **~100 tok/skill** | `name` + `description` only |
| L2 body | when the skill triggers | **< 5k tok** | `SKILL.md` body |
| L3 resources | only when opened | **zero until accessed** | bundled refs (read on open); scripts run via bash, only *output* enters context |

This is exactly MB's existing discipline, automated. `DOCTRINE.md` already says "keep this out of every agent context; load only when designing/debugging"; the specialty maps are "load by domain." A skill *is* a specialty `.md` that loads itself by domain, plus runnable scripts. The `/orchestrate` command already does manual progressive disclosure (points at files to read rather than inlining them).

**Three honest caveats — bake into doctrine:**

1. **Metadata is cheap, not free.** Every installed skill's name+description sits in the system prompt every turn (~100 tok). Skill *count* is a budget.
2. **There is a listing budget with silent truncation.** Claude Code caps the combined skill listing at ~1% of the context window (`skillListingBudgetFraction`); past it, it **drops the descriptions of least-used skills** and they stop triggering. On a 200k model that is roughly **~20 full-description skills** before pressure. Watch with `/doctor` and `/context`. Lever: `disable-model-invocation: true` removes a skill's description from context entirely (loads only when *you* type `/name`) — correct for side-effecting skills (`/deploy`, `/release`).
3. **An invoked body persists for the session** (re-attached within a 25k budget after compaction). Keep bodies < 500 lines; push detail into `references/` that load only when needed.

**The bigger token tax is MCP, not skills.** MCP tool definitions are always-in-context per connected server (10+ schemas for a full Obsidian or Shopify Dev MCP). Skills reuse tools Claude already has (Read/Grep/Write/Bash). For a quota-disciplined shop, *filesystem + skills* beats *MCP + skills* wherever a job doesn't need live API access. Install MCPs deliberately and scope them.

Sources: [Agent Skills overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) · [best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) · [Skills in Claude Code](https://code.claude.com/docs/en/skills).

---

## 1. Skill vs the adjacent mechanisms (division of labor)

| Mechanism | Token model | Use for | MB mapping |
|-----------|-------------|---------|-----------|
| **CLAUDE.md / AGENTS.md** | always-on, every turn | stable facts, routing rules that must *always* apply | `AGENTS.md`, `CLAUDE.md` — keep lean; migrate long *procedures* out into skills |
| **Skill** | on-demand (L1 only always-on) | a repeated *procedure*, checklist, domain playbook | the specialty `*.md` + the runnable `scripts/mb-*.mjs\|sh` |
| **MCP server** | tool schemas always-on + live data | live actions against external systems | ShopifyMCP, GitHub, Google/GSC, DataForSEO, Slack — the real always-on tax |
| **Slash command** | loads on invoke | legacy prompt template | `/orchestrate` — commands are now merged into skills; if both exist the skill wins |
| **Plugin** | packaging unit | *distributing* skills+commands+agents+hooks+MCP config to the team, versioned | the vehicle for a private MB skill library |
| **Subagent** | isolated context window | delegating big/parallel work | already in use (this packet was built by four) |

One-liner: **CLAUDE.md = always-on facts · Skills = on-demand procedures · MCP = live tools · Plugins = how you ship skills · Subagents = isolated execution.**

**Multi-CLI caveat (MB-critical).** `SKILL.md` is now a cross-tool open standard: **Claude Code, Cursor (v2.4+, Jan 2026), and Codex CLI (0.147.0+, Aug 2026) all consume it** — Codex and Cursor scan `.claude/skills/` too — so one repo-committed library serves three of your seats, dispatch included. The exception is **Grok Build / Grok Bot**, your default implementer and cloud seat, which reads `AGENTS.md` + repo `.md`, not skills. Author skills as thin wrappers over the single-source `.md` so every seat converges. Full matrix + design rule in §7.3.

---

## 2. Shopify coding skills (the primary ask)

**Bottom line:** there is now a first-party answer. Adopt the official Liquid skills, add the Dev MCP scoped to validation, and build the MB-proprietary layer no public skill can provide. **Flow needs no skill.**

| # | Candidate | Source | Verdict | Why |
|---|-----------|--------|---------|-----|
| 1 | **liquid-skills** (3 skills: `shopify-liquid-themes`, `liquid-theme-standards`, `liquid-theme-a11y`) | [Shopify/liquid-skills](https://github.com/Shopify/liquid-skills) · [benjaminsehl/liquid-skills](https://github.com/benjaminsehl/liquid-skills) (118★, Apr 2026) | **adopt** | Exact fit: OS 2.0 sections/blocks/snippets, schema JSON, LiquidDoc, BEM+design tokens, WCAG 2.2. True progressive disclosure. Pick #1. |
| 2 | **Shopify Dev MCP** (`@shopify/dev-mcp`) — scoped to `validate_theme`, `validate_graphql_codeblocks`, `introspect_admin_schema`, `search_docs_chunks` | [Shopify/dev-mcp](https://github.com/Shopify/dev-mcp) · npm `@shopify/dev-mcp` | **adopt (scoped)** | The pre-push correctness gate the internal Admin MCP lacks; docs/schema only, no store creds. It is an MCP (token cost) — gate its use behind a skill (see `theme-preflight`). |
| 3 | **liquid-lsp** | in [Shopify/liquid-skills](https://github.com/Shopify/liquid-skills) | **adopt (optional)** | In-editor Liquid LSP; needs Shopify CLI (already installed via `scripts/mb-theme.sh`). |
| 4 | Shopify AI Toolkit (umbrella) | [Shopify/Shopify-AI-Toolkit](https://github.com/Shopify/Shopify-AI-Toolkit) (519★, MIT) | **skip the umbrella, take its parts** | Bundles Dev MCP + liquid-skills + wrapper; blanket-install front-loads the MCP everywhere. Take #1 and #2 deliberately instead. (Note: a get-ryze.ai blog cites "1,439★" — wrong; real is 519.) |
| 5 | Shopify Flow authoring skill | — (none exists) | **skip / defer** | Sidekick authors Flows natively from natural language and better; `.flow` files are sha256-digest-prefixed JSON with an undocumented digest → programmatic generation is a wall. At most a low-priority *reference* skill of your standard trigger/condition/action patterns. |
| 6 | Community Shopify kits (sarojpunde, domocarroll, Jeffallan `shopify-expert`, henkisdabro, florinel-chis MCP) | various GitHub | **skip** | All 3–4★, few commits, heavy on Hydrogen/Functions/app-dev you don't run. Mine for ideas, don't depend on them. |
| 7 | Hydrogen/Oxygen, Functions, checkout-UI extensions | — | **skip (overkill)** | You are a Liquid theme, not headless. Out of scope. |

### Shopify skills to **build** (MB-proprietary — nothing public covers these)

| Skill | What it encodes | Source material |
|-------|-----------------|-----------------|
| **`mb-theme-safety`** ⭐ | The platform-limits gotcha: a file breaking a [theme limit](https://shopify.dev/docs/storefronts/themes/architecture/limits) is **silently refused** by Shopify (push succeeds, PR merges, theme-check passes, no error) and the last accepted copy keeps serving. The 25-char block-name limit wedged `sections/main-product.liquid` for **days**. Skill runs `mb-check-theme-limits.mjs` and blocks the "answer a wedged file with a no-op resync" anti-pattern. | `scripts/mb-check-theme-limits.mjs`, `docs/WORKFLOW.md` |
| **`mb-shopify-release`** ⭐ | The `production` = live-deploy ritual: `scripts/mb-backport.sh` → `scripts/mb-release.sh --live`; `settings_data.json` invariants (free-shipping-bar section, `type_body_font: poppins_n4`); pre-push hook; branch-protection unavailable (GH Free). `disable-model-invocation: true` — owner-fired only. | `docs/WORKFLOW.md`, `scripts/mb-release.sh`, `scripts/mb-backport.sh` |
| **`mb-theme-conventions`** | House rules on top of generic `liquid-skills`: the custom features + their files (buy-card shortcodes, free-shipping bar, product tabs, magnet spec table, size finder, upsell); `{% render 'mb-buy-shortcodes', strip_only: true %}` in meta/og/JSON-LD; drafts-only for new products/articles; no em/en dashes in customer prose; unpublished-theme preview needs a Share link (bare `?preview_theme_id=` 302s to live). | `README.md`, `snippets/mb-*.liquid` |
| **`theme-preflight`** | Orchestrates the Dev MCP: run `validate_theme` + `validate_graphql_codeblocks`, then `mb-theme-safety`, then open a Review D pixel ticket, before `theme push`. Keeps the MCP's value without front-loading its tool defs everywhere. | Dev MCP + `visual-qa.md` |
| **`agents-md-llms-txt`** (small) | Author/maintain `templates/agents.md.liquid` / `llms.txt.liquid` for agent-commerce discoverability of the catalog. No public skill wraps these. | `llms-subtree/`, Shopify changelog |

---

## 3. Flutter, general coding, GitHub

**Bottom line:** first-party Dart/Flutter skills now exist (adopt), Claude Code already ships the review/init skills (skip duplicates), live GitHub ops are the MCP's job, and the only builds are thin MB-specific ones.

| Candidate | Source | Verdict | Why |
|-----------|--------|---------|-----|
| **dart-lang/skills** (13 skills) | [dart-lang/skills](https://github.com/dart-lang/skills) (official, updated 2026-08-27) | **adopt** | Testing, coverage, static analysis, FFI, CLI — the Dart substrate under any Flutter work. |
| **flutter/agent-plugins** (10 skills) | [flutter/agent-plugins](https://github.com/flutter/agent-plugins) (official, 2,882★, BSD-3) | **adopt** | Canonical Flutter: widgets, tests, routing (go_router), architecture, responsive layout. Bundles its own MCP config. |
| **evanca/flutter-ai-rules** (36 skills) | [evanca/flutter-ai-rules](https://github.com/evanca/flutter-ai-rules) (619★, MIT) | **adopt (selective)** | Patch the official gap: **state management (Riverpod/Bloc/Provider)** + golden tests. Don't enable all 36. |
| **obra/superpowers** | [obra/superpowers](https://github.com/obra/superpowers) via its marketplace | **adopt (selective)** | Take `test-driven-development`, `systematic-debugging`, `using-git-worktrees`, `finishing-a-development-branch`. **Skip** its review/orchestration skills — they collide with `/code-review` and `orchestrate`. (Install via marketplace; the standalone skills repo is archived.) |
| **trailofbits/skills** | [trailofbits/skills](https://github.com/trailofbits/skills) | **adopt (conditional)** | Audit-grade security only for auth/money/PII changes. Respect the hard ban: never route secrets/PII to a third-party host. |
| `/code-review`, `/simplify`, `/security-review`, `/init`, `session-start-hook` | Claude Code built-ins (present in this env) | **skip — already owned** | Maps onto the Review C lane. Don't adopt external equivalents. |
| Live GitHub ops (issues/PRs/checks/logs/merge/releases) | GitHub MCP (present) | **skip — that's the MCP** | Build skills only for the *judgment/format* layer, not to duplicate the API. |
| Generic community Flutter/commit skills | various (1–7★) | **skip** | Vaporware/immature; official + evanca dominate. |

### Coding/GitHub skills to **build** (thin, MB-specific)

| Skill | What it encodes |
|-------|-----------------|
| **`mb-github-triage`** | Your label taxonomy + severity rubric, mapped to `DOCTRINE.md` §Review depth classes. Pairs with the GitHub MCP (MCP does; skill decides). |
| **`mb-commit`** (tiny) | Deterministic conventional-commits + your mandated commit trailers. ~30 lines beats an unvetted third-party skill. |
| **`mb-release-notes`** | Your repo's actual changelog/SemVer ritual (theme + any app). Or adopt `semver-changelog` and tune. |
| **`mb-review-order`** | The cross-family gate order (Fable → Sol → 4.8 → Review E) as a skill, so the Claude seat honors it without re-reading `AGENTS.md` each turn. |
| Flutter release/flavor/melos (conditional) | Only once the app's architecture is chosen; the one real gap nothing public fills. Defer. |

---

## 4. Obsidian second brain

**Integration verdict: no MCP server — use Claude Code's native filesystem tools on a git-backed markdown vault.** It is the leanest option (no standing tool-schema tax, no HTTP server, no self-signed cert, no CVE surface) and matches how MB already works. `mb-orchestration` *is already a vault*; Claude reads/writes it on demand today.

- Add an MCP server only for a concrete need: the running app's graph/Dataview (→ Local REST API plugin, **patched** — [GHSA-62gx-5q78-wrvx](https://advisories.gitlab.com/npm/obsidian-local-rest-api/GHSA-62gx-5q78-wrvx/), July 2026, arbitrary host file R/W/delete; localhost-only) + [MarkusPfundstein/mcp-obsidian](https://github.com/MarkusPfundstein/mcp-obsidian); or a hardened filesystem server [StevenStavrakis/obsidian-mcp](https://github.com/StevenStavrakis/obsidian-mcp) if you must have MCP without the plugin.
- **Reference implementation to fork:** [AgriciDaniel/claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian) (filesystem + local BM25 + consent-gated egress — closest match to MB's cost discipline and no-secrets ban). **Structural template to mine:** [eugeniughelbur/obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain) (multi-CLI packaging, tiered context budgets) — but **leave its paid-API research commands off**; they collide with the cost gates and the secrets/PII ban.

**The insight that makes this cheap for MB:** `DOCTRINE.md` §Review depth already uses **"(vault category)"** task classes (internal notes · content prose · catalog data · money data · SEO structural · storefront/Liquid · repo code · standing config · outbound irreversible · legal/HR). The vault taxonomy already exists — a capture skill can auto-stamp the review floor on capture.

### Second-brain skills to **build** (ranked)

| # | Skill | What it does | Token story |
|---|-------|--------------|-------------|
| 1 | **`doctrine-sync` / `vault-index`** ⭐ | Ingest the orchestration `.md` + `llms-subtree/*` and generate a top-level **Map of Content** (`_index.md`) with `[[links]]` + one-line summaries. Turns the scattered pile into a navigable brain. Directly answers the ask. | script globs/reads off-disk, writes the index; Claude sees only the diff |
| 2 | **`vault-search` / `retrieve`** | Grounded retrieval that returns only *paths + snippets*, then reads 1–3 notes. "retrieve-before-answer; cite paths." Foundation for the rest. | bounded by top-k, never the whole vault |
| 3 | **`capture-note`** | Capture to `inbox/` with frontmatter, PARA destination, link candidates, **and the auto-stamped review class** from the §Review depth table. | one note in/out |
| 4 | **`decision-log`** (ADR) | Record routing/quota/architecture calls (context, options, choice, reversibility), cross-linked to the doctrine MOC. Uniquely MB-shaped — feeds the risk gate's "why we routed here." | append-only |
| 5 | **`daily-note` / `worklog`** | Append dispatch outcomes + a `usage-status` snapshot; extends the existing "on completion, refill or state idle" discipline. | append-only |
| 6 | **`weekly-review` / `link-suggester`** | Scheduled hygiene: orphans, stale usage files, un-MOC'd notes; a linter script feeds Claude a short findings list. | scan is a script; Claude sees a summary |

Embeddings are optional — grep/BM25 is token-free and deterministic; add local Ollama embeddings only if keyword recall proves insufficient.

---

## 5. Packaging, security, and how this fits the risk gate

**Packaging (three tiers):**
1. **Repo-local project skills** — commit theme skills to `mb-shopify-theme/.claude/skills/<name>/SKILL.md`. These load for that repo **and** carry into cloud sessions/routines (repo `.claude/` is cloned) — the path that reaches the Grok Bot / scheduled lanes.
2. **Private plugin + marketplace** — a new private repo `magnetbaron/mb-claude-plugins` (`.claude-plugin/marketplace.json` + `mb-tools/skills/*`). `​/plugin marketplace add magnetbaron/mb-claude-plugins` → install. Namespaces as `/mb-tools:<skill>`; versioned by `plugin.json`.
3. **Managed settings** — for org-wide force-enable/disable and `disableSkillShellExecution` (relayed as a *finding*, not applied here).

Personal `~/.claude/skills/` is experiments only — it does **not** reach cloud sessions, routines, or teammates.

**Security gate — folds into the existing risk gate / `DOCTRINE.md` §Safety gates.** Third-party skills execute code:
- A skill's `allowed-tools` can **self-grant** broad access, and applies even in untrusted `-p`/cloned-repo runs → review it before running Claude Code in any cloned repo.
- `!​`command`` injections run shell **before** Claude sees the body → a supply-chain surface.
- **Enabling any third-party skill = the Lane 3 gate: cross-family review + `/security-review` of `SKILL.md` and every bundled script, versions pinned, updates diffed like a dependency.** The Obsidian GHSA and the get-ryze star inflation both show why. Never route a skill/script that could carry secrets/PII to a third-party inference host (existing hard ban).

**Skill-count is a quota.** Past ~20 full-description skills, Claude Code silently truncates least-used descriptions. Curate deliberately — on brand with "unspent quota at reset is waste," but here the waste is context, not tokens-at-reset. Use `skill-creator` ([anthropics/skills](https://github.com/anthropics/skills)) to A/B descriptions and prove a skill helps before committing it.

---

## 6. Recommended roadmap

**Phase 1 — adopt now (existing, low risk, high fit):**
1. `liquid-skills` (3 official Liquid skills) + `liquid-lsp`.
2. Shopify Dev MCP, scoped to `validate_theme` + schema introspection.
3. `dart-lang/skills` + `flutter/agent-plugins` (only when Flutter work starts).
4. `mcp-builder` (official) — for building/refactoring MCP servers, incl. the internal ShopifyMCP.

**Phase 2 — build MB-proprietary (the real leverage; author on Grok Build, consumed by Claude/Codex/Cursor):**
1. `mb-theme-safety` ⭐ (highest ROI — prevents multi-day wedge losses).
2. `mb-shopify-release` ⭐ (owner-fired; prod = live).
3. `mb-theme-conventions` (layered on `liquid-skills`).
4. `doctrine-sync` / `vault-index` ⭐ (turns the doctrine pile into a navigable brain).
5. `theme-preflight`, then `vault-search`, `capture-note`, `decision-log`.
6. `mb-mcp-hardening` (secure the internal ShopifyMCP; cross-family review). Rest of the coding-task surface (§7.2) is pull-based.

**Phase 3 — selective / conditional:**
- `evanca/flutter-ai-rules` (state-mgmt slice) · `obra/superpowers` (TDD/debugging/worktrees slice) · `trailofbits/skills` (audit passes) — each behind the Lane 3 security gate.
- `mb-github-triage`, `mb-commit`, `mb-release-notes`, `mb-review-order` (thin).

**Skip:** the AI Toolkit umbrella (take its parts) · a Flow-authoring skill (Sidekick owns it) · Hydrogen/Functions/checkout · all 3–4★ community Shopify kits · external code-review/security/init skills (built-ins own them) · skills that duplicate the GitHub/Shopify Admin MCPs.

**Packaging decision:** start Phase 2 as repo-local `.claude/skills/` in `mb-shopify-theme` (cloud-safe); promote cross-repo skills into a private `mb-claude-plugins` marketplace once more than one repo needs them.

---

## 7. Follow-ups — MCP servers, full coding-task map, cross-agent portability

### 7.1 Building and securing MCP servers (this was under-covered in the first pass)

**Build → adopt `mcp-builder`** (official, `anthropics/skills`). Full lifecycle: tool-design planning, TypeScript (MCP SDK) or Python (FastMCP) implementation, MCP Inspector testing, and evals. Install `/plugin install mcp-server-dev@claude-plugins-official` or `npx skills add https://github.com/anthropics/skills --skill mcp-builder`. Directly relevant — you run an internal `MagnetBaron-Internal-ShopifyMCP`; this is the skill for extending or refactoring it.

**Secure → build `mb-mcp-hardening`** (no single public skill covers this; the guidance is canonical 2026 material). Checklist the skill encodes, applied to the internal ShopifyMCP:
- **AuthN/Z:** OAuth 2.1 + mandatory PKCE; validate token *audience* (accept only tokens minted for you); never pass a client token through to upstream APIs (confused-deputy).
- **Tool poisoning / prompt injection:** treat tool descriptions + parameter schemas as an attack surface (OWASP Agentic Top 10 ASI01 / tool-poisoning); pin and review tool metadata; a tool description must not carry instructions.
- **Least privilege:** scope every credential to exactly what a tool needs (read-only roles unless a write tool needs it); no personal standing creds.
- **Input + egress:** allow-list and validate every tool input; block SSRF egress to private IP ranges.
- **Irreversible actions:** require human confirmation (maps to your owner publish/send/spend gates).
- **Runtime:** log every tool call (user / client / server / args / downstream / result) for traceability.

This maps onto your existing hard bans (no secrets/PII to third-party inference) and the risk gate: an MCP change is *standing config* → single-frontier floor, raised to **cross-family** on OAuth/secrets/prod URL. Sources: [mcp-builder SKILL.md](https://github.com/anthropics/skills/blob/main/skills/mcp-builder/SKILL.md) · [MCP: build with Agent Skills](https://modelcontextprotocol.io/docs/2026-07-28/develop/build-with-agent-skills) · [CSA Agentic MCP Security](https://labs.cloudsecurityalliance.org/agentic/agentic-mcp-security-best-practices-v1/) · [Checkmarx MCP security 2026](https://checkmarx.com/learn/mcp-security-risks-real-world-incidents-and-security-controls/).

### 7.2 Your full coding-task surface → skill map

Derived from both repos. "in packet" = already in §2–§3. Do **not** build all at once — skill count is a budget (§0); build pull-based when a task recurs.

| Coding task (evidence in repo) | Skill | Verdict |
|---|---|---|
| Build / extend MCP servers (internal ShopifyMCP) | `mcp-builder` | **adopt** |
| Secure / harden MCP servers | `mb-mcp-hardening` | **build** |
| Theme codemods — programmatic section/block insert + relocate (`scripts/mb-add-*.mjs`, `mb-relocate-upsell.mjs`, `mb-row-above-reviews.mjs`) | `mb-theme-codemod` (idempotent, limit-safe transforms) | **build** |
| CSS bundle rebuild (`rebuild-css-bundle.sh`, `CSS_BUNDLE_NOTES.md`) | `mb-css-bundle` | **build (small)** |
| Performance audits (`PERF_NOTES.md`; DataForSEO `on_page_lighthouse`) | `mb-perf-audit` (Lighthouse via MCP → prioritized fixes) | **build** |
| Technical SEO / structured data (soft-404 noindex fix, `strip_only`, JSON-LD) | `mb-seo-structured-data` | **build** |
| i18n / locale files (`locales/`) | `mb-i18n` | **build (small)** |
| Third-party app integration (Judge.me, Omnisend, Stoq — `JUDGEME_NOTES.md`) | `mb-integrations` | **build** |
| Theme limits / wedge diagnosis | `mb-theme-safety` ⭐ | **build (in packet)** |
| Release / backport / settings reconcile | `mb-shopify-release` ⭐ | **build (in packet)** |
| Theme conventions | `mb-theme-conventions` | **build (in packet)** |
| Pre-push validation | `theme-preflight` | **build (in packet)** |
| Usage metering (`usage-status.py`, `record-429.sh`) | `mb-usage-status` (run + interpret; never LLM-estimate) | **build (small)** |
| teamclaude routing (`sync-commands.sh`, routes JSON, `mb/sync-plan`) | `mb-teamclaude` | **build (small)** |
| Roles registry (Python + tests: `roles/generate.py`) | general Python + `superpowers` TDD | **adopt (covered)** |
| Visual QA handoff (`visual-qa*.md`, Slack) | `mb-visual-qa-handoff` | **build (small)** |
| Analytics interpretation (Clarity / GSC / DataForSEO) | retrieval skill over `analytics-clarity.md` (judgment, not automation) | **build (small)** |
| Code review / security review / simplify / init | Claude Code built-ins | **skip — owned** |

### 7.3 Are skills portable between agents? (mostly yes now — one exception, and it's your implementer)

`SKILL.md` became a genuine cross-tool open standard in 2026. Portability by seat:

| Seat (`AGENTS.md`) | Tool | Consumes skills? | How |
|---|---|---|---|
| Review C / MCP judgment | **Claude Code** | ✅ | `.claude/skills/`, plugins |
| IDE | **Cursor** | ✅ | Skills since **v2.4** (Jan 2026); scans `.claude/skills/` |
| Dispatch / Review B / MCP volume | **Codex CLI** | ✅ (new) | Skills since **0.147.0** (Aug 7 2026); scans `.codex/skills/` **and** `.claude/skills/`; can import Cursor skills |
| **Implement (default)** | **Grok Build** | ❌ (none surfaced) | reads `AGENTS.md` + repo `.md` |
| Cloud standing / Review D | **Grok Bot** | ❌ | Slack + repo `.md` |

One repo-committed library (`.claude/skills/`) now serves **Claude, Cursor, and Codex** — three seats, dispatch included. The exception is **Grok**, your default implementer and cloud seat.

**Design rule (the important part):** author each skill as a **thin wrapper over the single-source repo `.md`**, not a fork of that knowledge. Then skill-aware seats (Claude/Cursor/Codex) load it progressively; Grok reads the same `.md` directly; one source, all seats converge — your single-source discipline, intact. Corollaries:
- **Instruction files stay per-tool.** Codex→`AGENTS.md`, Claude→`CLAUDE.md`, Cursor→`.cursor/rules`. Keep always-on *routing rules* in `AGENTS.md` (the all-seats contract), not in a skill.
- **Cross-surface skills use only the 6 portable frontmatter fields** (`name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`). Reserve Claude-Code-only frontmatter (`context`, `paths`, `hooks`, `disable-model-invocation`) for Claude-only skills — it errors on other surfaces.
- **Grok authors, skill-aware seats consume.** Routing a skill *build* to Grok is fine (writing `SKILL.md` + scripts is implement work); Grok just won't *use* the result at runtime — Claude/Codex/Cursor will.
- **Cloud/routine reach:** repo `.claude/skills/` clones into cloud sessions; personal `~/.claude/skills/` does not. Commit skills to the repo.

Sources: [Cursor 2.4 / Codex skill portability](https://www.digitalapplied.com/blog/codex-cli-cross-harness-skill-portability-lock-in) · [cross-agent skills 2026](https://mcp.directory/blog/cross-agent-skills-cursor-codex-cline-antigravity-gemini-mastra-portability) · [agent instruction files](https://codex.danielvaughan.com/2026/05/27/agent-instruction-files-agents-md-claude-md-cross-tool-portability-codex-cli/).

---

## Appendix — starter `SKILL.md` drafts for the top private builds

Drafts for the build lane to finalize (not enabled by this file). Bodies kept short; detail belongs in `references/`.

### A. `mb-theme-safety/SKILL.md`
```markdown
---
name: mb-theme-safety
description: Diagnose and prevent silently-wedged Shopify theme files at Magnet Baron. Use before pushing theme changes, and whenever a file "won't update" on a connected theme despite a successful push/merge. Runs the platform-limits check and blocks no-op resync commits.
allowed-tools: Bash(node scripts/mb-check-theme-limits.mjs *), Read, Grep
---
When a theme file appears not to update on `mb-shopify-theme/main` or `Live` even though the push succeeded and the PR merged: Shopify silently refused to write a file that breaks a platform limit and keeps serving the last accepted copy. Theme-check passes; the integration reports no error. This is NOT a stalled sync.

Do this, in order:
1. Run `node scripts/mb-check-theme-limits.mjs` (the pre-push hook runs it too). Read the failing file + limit.
2. Common wedge: section/block `name` > 25 chars. Also asset size, file count, nesting. See references/limits.md.
3. Fix the offending file to satisfy the limit, then push. The write unwedges on the next accepted copy.
4. NEVER answer a wedged file with an empty/no-op "resync" commit — touching it again cannot clear it.
Reference: docs/WORKFLOW.md "Things that would quietly break this".
```

### B. `mb-shopify-release/SKILL.md`
```markdown
---
name: mb-shopify-release
description: Cut a Magnet Baron storefront release. Use ONLY when the owner asks to promote main to the live storefront. Merges to production are live deploys to customers.
disable-model-invocation: true
allowed-tools: Bash(scripts/mb-backport.sh), Bash(scripts/mb-release.sh *), Read
---
Merges to `production` deploy to customers (theme `Live`, 189928177954). Owner-gated. Never auto-fire.

Sequence:
1. `scripts/mb-backport.sh` — takes production's own config first so promotion can't discard theme-editor work on Live.
2. Reconcile `config/settings_data.json`: preserve the mb-free-shipping-bar section and `type_body_font: poppins_n4` (release invariants).
3. `scripts/mb-release.sh --live` — opens the release PR (it refuses if production holds anything main lacks; it never merges).
4. Owner reviews the settings diff and merges. That merge is the deploy.
Pre-push hook must be enabled per clone: `git config core.hooksPath .githooks`. GitHub branch protection is unavailable (GH Free). Reference: docs/WORKFLOW.md.
```

### C. `doctrine-sync/SKILL.md`
```markdown
---
name: doctrine-sync
description: Build or refresh the Magnet Baron doctrine Map of Content (second brain index) from the orchestration markdown. Use to turn the scattered .md files into a navigable, linked index, or after doctrine changes.
allowed-tools: Bash(python3 scripts/build_index.py *), Read, Write, Grep
---
Generate _index.md (top-level MOC) and per-domain MOCs from the repo's markdown, so the doctrine is navigable without loading every file into context.

1. Run `python3 scripts/build_index.py` — globs *.md + llms-subtree/*, reads H1/frontmatter, emits _index.md with [[links]] + one-line summaries, and domain MOCs (routing, review, usage, per-game).
2. Preserve git as source of truth; the index is derived, never authoritative.
3. Review the diff, commit. Do not inline file bodies into the index — links only.
Design intent: this is the retrieval layer for capture-note / vault-search. Keep it path-based and token-cheap.
```

---

## Sources
Shopify: [liquid-skills](https://github.com/Shopify/liquid-skills) · [dev-mcp](https://github.com/Shopify/dev-mcp) · [Shopify-AI-Toolkit](https://github.com/Shopify/Shopify-AI-Toolkit). Coding: [dart-lang/skills](https://github.com/dart-lang/skills) · [flutter/agent-plugins](https://github.com/flutter/agent-plugins) · [evanca/flutter-ai-rules](https://github.com/evanca/flutter-ai-rules) · [obra/superpowers](https://github.com/obra/superpowers) · [trailofbits/skills](https://github.com/trailofbits/skills). Second brain: [AgriciDaniel/claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian) · [eugeniughelbur/obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain) · [GHSA-62gx-5q78-wrvx](https://advisories.gitlab.com/npm/obsidian-local-rest-api/GHSA-62gx-5q78-wrvx/). Mechanics/sourcing: [Agent Skills overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) · [Skills in Claude Code](https://code.claude.com/docs/en/skills) · [Create plugins](https://code.claude.com/docs/en/plugins) · [anthropics/skills](https://github.com/anthropics/skills) · [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official).

*Egress caveats: shopify.dev, claude.com/docs narrative pages, and several registry sites were proxy-blocked during research; facts were corroborated across GitHub repos (fetched directly), npm, and advisories. Star counts are rough maturity signals, not audited figures.*
