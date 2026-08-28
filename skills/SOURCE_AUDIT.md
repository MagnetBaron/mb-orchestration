# Skill source audit — 2026-08-28

## Need evidence

The Obsidian vault contained 13,444 Markdown notes. Aggregate matches in the
1,726 raw, system, and research notes—not note prose—showed recurring work in
automation/Python (1,645 files), infrastructure/networking (1,329),
Shopify/ecommerce (1,154), testing/QA/review (959), security/credentials (851),
warehouse/inventory (817), Google Workspace/OAuth (756), SEO/analytics (743),
agent orchestration (704), Cloudflare/MCP (323 Cloudflare-specific; 586 MCP
server), React/Next/Vercel (227), and Obsidian/knowledge-vault operations (133).

Existing Magnet Baron, SEO, Google Drive, document, spreadsheet, PDF,
presentation, browser, and mobile skills already cover the highest-frequency
general workflows. Installing lookalikes would increase ambiguity without a
new workflow owner.

## Selected sources

| Source | Pinned revision | Authority/license | Selection and reliability |
|---|---|---|---|
| `dadederk/iOS-Accessibility-Agent-Skill` | `dcc3a36ce1d0099341d545c1af4eb5a8c989bf66` | Specialist upstream | Existing mobile leaf; manual assistive-technology validation remains mandatory. |
| `flutter/agent-plugins` | `864cf8797b190ddb81e4875db6dd6bab89641f62` | Official Flutter | 23 Dart/Flutter leaves; version-sensitive APIs are gated in the router catalog. |
| `cloudflare/skills` | `f96bff754e428838818017f75817f0f9428acd48` | Official Cloudflare, Apache-2.0 | All 13 existing leaves retained, with `web-perf` routed as engineering and 12 platform leaves routed as Cloudflare. Exact local copies matched upstream. |
| `kepano/obsidian-skills` | `a1dc48e68138490d522c04cbf5822214c6eb1202` | Steph Ango, Obsidian CEO; MIT | Four format/CLI leaves selected. No bundled scripts. CLI mutation and `eval` are router-gated. |
| `vercel-labs/agent-skills` | `063bee94c3f4df8453406c830b0a7df0f2860278` | Vercel Labs; per-skill MIT metadata | Static React performance and composition leaves selected. Version and rule-file selection are gated. |
| `anthropics/skills` | `3b3fad96af16a10759d930941b4520ba0c40edae` | Anthropic; MCP leaf Apache-2.0 | Generic MCP builder selected at medium confidence. Upstream labels examples educational, so current official spec/SDK docs override embedded examples and evaluation scripts are opt-in. |

## Rejected or deferred

- `openai/skills`: repository is explicitly deprecated. Current
  `openai/plugins` was inspected instead; its security workflows depend on the
  Codex Security product and were not copied as generic local leaves.
- Anthropic document/PDF/spreadsheet/presentation/web-testing/frontend leaves:
  duplicate stronger installed capabilities or add overlapping triggers.
- Obsidian `defuddle`: executes an on-demand npm package and overlaps existing
  web retrieval.
- Vercel `web-design-guidelines`: fetches unpinned remote instructions on every
  invocation. Vercel deployment/token skills perform external mutations.
- Vercel React view transitions: narrow and rapidly version-sensitive relative
  to demonstrated recurring work.
- Public “awesome skills” indexes: discovery aids, not trusted workflow sources.

## Reliability controls

- Exact commit pins; no branch-at-runtime installation.
- Leaf folders remain outside all discovery roots.
- One router catalog read, one primary leaf, at most one validation leaf.
- Dynamic remote instructions, deployment leaves, and duplicate artifact
  skills excluded.
- Router descriptions include negative triggers.
- Skills cannot grant tools, secrets, filesystem scope, or mutation authority.
- `skills/sync.py --check` fails on missing leaves, global leaf exposure,
  stale generated profiles, router collisions, duplicate names, or bad routes.
