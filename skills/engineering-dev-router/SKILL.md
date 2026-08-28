---
name: engineering-dev-router
description: Route explicit React or Next.js performance and component-architecture work, generic MCP server construction, or evidence-based web performance audits to pinned private playbooks. Do not use for ordinary code edits, non-React UI, or Cloudflare-specific implementation.
---

# Engineering specialty router

Load specialized engineering guidance only when the deliverable matches.

1. Confirm the task is React/Next performance, React component API design, generic MCP server construction, or a measured web-performance audit. Otherwise stop without opening a leaf.
2. Read [references/catalog.md](references/catalog.md). Select one primary leaf and at most one distinct validation leaf. Never scan or concatenate the library.
3. Read the complete selected leaf from the exact path under `~/.codex/skill-library/engineering/` listed in the catalog.
4. For React, inspect package versions and project conventions first. Load only relevant rule files; do not load a compiled all-rules document unless the user requested a broad audit.
5. For MCP work, verify the current official MCP specification and the chosen SDK’s primary documentation. Load only the TypeScript or Python reference actually used. Cloudflare-hosted MCP work routes to `cloudflare-dev-router` unless a generic protocol-design leaf is also materially required.
6. For web performance, require real measurement evidence. Use Chrome DevTools MCP only if present; otherwise use an available browser/CLI fallback and label missing Core Web Vitals or trace evidence honestly.
7. Do not deploy, publish, install dependencies, expose credentials, or broaden scope merely because a leaf contains those steps.
8. Return `selected_skills`, files changed or reviewed, measurements/tests actually run, and remaining validation.

Dispatch names only `engineering-dev-router`; the receiving implementer or reviewer selects the leaf.
