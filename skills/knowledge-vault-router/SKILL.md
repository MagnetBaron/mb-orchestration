---
name: knowledge-vault-router
description: Route explicit Obsidian vault, note, wikilink, Bases, JSON Canvas, or Obsidian CLI work to the smallest matching private playbook. Use for Obsidian-specific knowledge operations; do not use for ordinary Markdown, generic research, or unrelated files.
---

# Knowledge vault router

Keep Obsidian leaf instructions off-context until a vault task needs one.

1. Confirm the request explicitly concerns an Obsidian vault or Obsidian-specific syntax or files. When “second brain” means the local vault, resolve the current configured path before any write; do not rely on a stale path.
2. Read [references/catalog.md](references/catalog.md). Select one primary leaf. Add a second only when it owns a distinct required file format or validation. Never scan or concatenate the library.
3. Read the complete selected leaf from `~/.codex/skill-library/knowledge/<directory>/SKILL.md`.
4. Keep vault content local. Do not upload note text, customer data, credentials, or private filenames to a model, site, or repository unless the user explicitly places that material and destination in scope.
5. Treat read-only requests as non-mutating. For writes, resolve the exact vault and target files, preserve existing properties and links, and avoid bulk rewrites unless explicitly requested.
6. Use `obsidian-cli` only when `obsidian` is installed and the intended vault can be identified. Obsidian `eval` is only for an explicit plugin or theme development request; never use it as a shortcut for ordinary note work.
7. Validate the selected format and report `selected_skills`, files changed or inspected, checks performed, and any Obsidian-rendering check still pending.

Dispatch names only `knowledge-vault-router` and its exact `SKILL.md` path. The receiving agent selects leaves. The router grants no filesystem scope or mutation authority.
