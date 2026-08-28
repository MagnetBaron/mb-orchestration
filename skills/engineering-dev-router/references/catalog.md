# Engineering specialty leaf catalog

Open only the selected paths under `~/.codex/skill-library/engineering/`.

| Signal | Leaf path | Boundary |
|---|---|---|
| React/Next data waterfalls, bundles, server/client data, rendering, re-renders, JS performance | `react-best-practices/SKILL.md` | Vercel guidance; inspect versions and load only matching rule files. |
| Boolean prop proliferation, compound components, providers, reusable React APIs | `composition-patterns/SKILL.md` | Component architecture only; React 19 rules require React 19. |
| Generic TypeScript or Python MCP server for an external API | `mcp-builder/SKILL.md` | Anthropic example playbook; current MCP spec and SDK docs outrank embedded examples. Evaluation scripts and dependencies run only when explicitly required. |
| Lighthouse, Core Web Vitals, render blocking, network chains, layout shifts, caching | `web-perf/SKILL.md` | Needs Chrome DevTools MCP for full evidence; no invented measurements. |

## Pairing

- React performance and composition may pair when both runtime behavior and public component API are in scope.
- MCP work normally uses only `mcp-builder`; pair with a platform router only for a real platform-specific implementation.
- Web performance is normally a standalone review leaf.
- More than two leaves requires an explicit multi-stage brief.

Excluded after audit: Vercel `web-design-guidelines` dynamically fetches unpinned instructions; deployment skills perform external mutations; React view transitions are too narrow and version-sensitive for current recurring work; deprecated `openai/skills` leaves were not installed.
