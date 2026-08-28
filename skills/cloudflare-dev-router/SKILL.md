---
name: cloudflare-dev-router
description: Route explicit Cloudflare Workers, storage, Agents SDK, Durable Objects, Wrangler, Zero Trust, Sandbox, Turnstile, or email work to the smallest private playbook. Do not use for generic web, server, network, or AI tasks with no Cloudflare scope.
---

# Cloudflare development router

Use one precise Cloudflare leaf instead of advertising the full platform pack.

1. Confirm the task names Cloudflare or a uniquely Cloudflare resource. Do not trigger on generic workers, tunnels, storage, email, agents, or sandboxes.
2. Read [references/catalog.md](references/catalog.md). Select one primary leaf. Add one validation leaf only when it owns a separate required check. Never read the entire private library.
3. Read the complete selected leaf from `~/.codex/skill-library/cloudflare/<name>/SKILL.md`.
4. Prefer a specialized leaf over the broad `cloudflare` leaf. Use the broad leaf only for platform selection or work spanning services with no narrower owner.
5. Verify current Cloudflare documentation and the project’s installed package, compatibility date, and configuration before version-sensitive advice.
6. Skills do not supply credentials or authorize account changes, secret writes, resource creation, deployment, DNS changes, email sending, or policy changes. Preserve the user’s approval boundary and resolve exact account, zone, Worker, environment, and config targets first.
7. For `turnstile-spin`, require an explicit Turnstile setup/fix request and follow every embedded confirmation gate. Never expose a secret. For Wrangler, confirm the executable and auth state before commands; deployment still requires explicit scope.
8. Return `selected_skills`, files or resources affected, validation actually run, and any live Cloudflare or production check still pending.

Dispatch names only `cloudflare-dev-router` and its exact path. The receiver selects leaves. The router grants no tools, credentials, deployment, or broader scope.
