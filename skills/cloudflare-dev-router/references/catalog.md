# Cloudflare leaf catalog

Open selected leaves under `~/.codex/skill-library/cloudflare/`.

| Signal | Leaf | Boundary |
|---|---|---|
| Platform choice spanning Workers, Pages, KV, D1, R2, AI, networking, security, or IaC | `cloudflare` | Broad fallback; prefer a specialized leaf. |
| Stateful AI agent, scheduled workflow, RPC, WebSocket chat, queues, voice, or agent email on Workers | `agents-sdk` | Cloudflare Agents SDK only. |
| Durable Object RPC, SQLite, alarms, or WebSockets | `durable-objects` | Stateful coordination implementation. |
| Worker authoring or review, bindings, streaming, global state, observability | `workers-best-practices` | Pair with `wrangler` only if CLI/config work is required. |
| Wrangler commands, config, bindings, deploy, KV/R2/D1/Queues/Workflows | `wrangler` | Commands need verified CLI/auth; mutations remain scoped. |
| Transactional email sending, Email Routing, SPF/DKIM/DMARC, deliverability | `cloudflare-email-service` | Sending and routing only; sending is consequential. |
| Cloudflare One Access, Gateway, WARP, Tunnel, WAN, DLP, CASB, posture | `cloudflare-one` | Retrieval-first; distinguish design, review, and live config. |
| Migration from Zscaler, Palo Alto, VPN, SWG, or SASE | `cloudflare-one-migrations` | Explicit migration assessment or plan only. |
| Current stable `@cloudflare/sandbox` | `sandbox-stable` | Do not apply to `@next`. |
| New work on `@cloudflare/sandbox@next` 1.0 preview | `sandbox-next` | Version-sensitive preview. |
| Port stable Sandbox to `@next` | `sandbox-migrate-to-next` | Explicit migration only. |
| Add or repair Cloudflare Turnstile | `turnstile-spin` | Resource/secret workflow; explicit request and all confirmation gates required. |

Generic page-performance work routes through `engineering-dev-router`, which owns the separately stored `web-perf` leaf.
