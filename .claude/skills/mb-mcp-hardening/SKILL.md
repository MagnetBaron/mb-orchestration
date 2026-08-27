---
name: mb-mcp-hardening
description: Security-review and harden an MCP server (build or change), including the internal MagnetBaron ShopifyMCP. Use when building a new MCP server, adding or changing tools, or reviewing an MCP server's auth, tool design, and secrets handling before it ships. Pairs with the official mcp-builder skill (which covers building).
license: proprietary
allowed-tools: Read, Grep, Glob
---

# MCP server hardening

Use with the official `mcp-builder` skill: `mcp-builder` builds the server;
this skill reviews and hardens it. An MCP change is **standing config**
(self-perpetuating), so it takes the single-frontier review floor, raised to
**cross-family** on OAuth/secrets/prod URL. Never route a server's secrets or
customer PII to a third-party inference host (MB hard ban).

## Hardening checklist

**AuthN / AuthZ**
- OAuth 2.1 with mandatory PKCE for all clients; no implicit grant.
- Validate the token **audience** — accept only tokens minted for this server.
- **Never pass a client token through to an upstream API** (confused-deputy);
  mint or exchange a scoped token instead.

**Tool poisoning / prompt injection** (OWASP Agentic Top 10 ASI01)
- Treat every tool `description` and parameter schema as an attack surface — it is
  read by the model. A tool description must not carry instructions to the agent.
- Pin and review tool metadata; diff it on every change like code.

**Least privilege**
- Scope each credential to exactly what its tool needs (read-only roles unless a
  tool genuinely writes). No personal standing credentials.
- Prefer narrow, workflow-shaped tools over one god-tool with broad scope.

**Input + egress**
- Allow-list and validate every tool input.
- Block SSRF egress to private/link-local IP ranges.

**Irreversible actions**
- Require human confirmation for anything destructive, spending, sending, or
  publishing — maps to MB's owner publish/send/spend/auth gates.

**Runtime**
- Log every tool call (user / client / server / args / downstream / result) so an
  action can be traced to a user, the model, or an injection attempt.

## Applying to the internal ShopifyMCP

- It touches live store data (products, orders, metafields, themes, ShopifyQL) —
  writes are the high-risk surface. Confirm write tools are least-privilege and
  gated; reads may be broader.
- Any change goes through cross-family review (two families) before enabling.

Sources (read for depth, do not duplicate): mcp-builder SKILL.md
(github.com/anthropics/skills), modelcontextprotocol.io "build with Agent Skills",
CSA Agentic MCP Security best practices, Checkmarx MCP security 2026.
