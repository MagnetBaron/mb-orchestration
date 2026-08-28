# Knowledge vault leaf catalog

Open only selected leaves under `~/.codex/skill-library/knowledge/`.

| Signal | Leaf path | Boundary |
|---|---|---|
| Obsidian Markdown, wikilinks, embeds, callouts, properties, tags | `obsidian-markdown/SKILL.md` | Obsidian syntax only; ordinary Markdown needs no leaf. |
| `.base` files, table/card/list views, filters, formulas, summaries | `obsidian-bases/SKILL.md` | Validate YAML and referenced properties; map views need a separately audited plugin. |
| `.canvas` files, mind maps, flowcharts, node-edge layouts | `json-canvas/SKILL.md` | Validate JSON, unique IDs, and edge targets. |
| Search, read, create, or manage vault notes through installed Obsidian CLI; plugin/theme debugging | `obsidian-cli/SKILL.md` | Prefer direct files for simple local edits. `eval` requires explicit development scope. |

## Pairing

- Use `obsidian-markdown` alone for normal note work.
- Pair `obsidian-cli` with one format leaf only when CLI interaction and format-specific authoring are both required.
- Pair `obsidian-markdown` with Bases or Canvas only when the deliverable includes both formats.
- More than two leaves requires an explicit multi-artifact task.

The upstream `defuddle` leaf is intentionally excluded. It executes an on-demand npm package and overlaps available web retrieval, adding supply-chain and runtime cost without improving vault-format quality.
