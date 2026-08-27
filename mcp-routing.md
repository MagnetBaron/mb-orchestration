# MCP routing

**Not previously spelled out.** Default implementer remains Grok Build. Google MCP (Search Console, Drive, DataForSEO / Trends / Ads volume, and similar) is available on **Opus** and **appropriate GPT models** (Codex Terra / Sol; not Luna-as-dispatch). Grok does not assume Google MCP for these jobs.

Codex (Terra/Luna) still dispatches. The seat that *runs* the MCP calls is assigned below.

## Connector map — lives in `config/connectors.json`

**Which seat has which connector is dynamic and must not be hardcoded here** (it goes stale the
moment a connector moves). The single source is `config/connectors.json` `mcp_connectors.*.available_on`;
print the current map with `bin/connectors.py`. Today that is roughly: Google Search Console / Drive /
DataForSEO on Opus + GPT (Codex); Shopify (MB Internal) preferred on Grok for volume catalog; GitHub
on all coding seats — but **read the config, do not trust this sentence** when routing.

If a connector is missing on the assigned seat (per `available_on`), park and report — do not invent data.

## Assignment matrix

| Job | Primary seat | Why | Not |
|-----|--------------|-----|-----|
| **Coding / repo implement** | **Grok Build** | Abundant volume; worktrees; doctrine implementer | Opus or Sol as daily coder |
| **Code review** | Opus 4.8 → Codex Sol → Review E | Judgment on git diff (Fable out of gating) | MCP not required |
| **General Google MCP work** (one-off Drive pull, sitemap check, small GSC query) | **Codex GPT Terra** first | Has Google MCP; cheaper than Sol/Opus for tool loops | Luna (dispatch only); Grok without connector |
| **Bulk analytics** (GSC rows, keyword batches, trends sweeps, multi-page Drive extract) | **Codex GPT Terra** (or Luna only if owner promotes it off dispatch for that brief) | Volume MCP loops; write CSV/summary to `output_path` | Opus for row dumps; Sol unless analysis judgment is the product |
| **Analytics judgment** (what the numbers mean, priority, strategy) | **Codex Sol** under 90% (`sol-usage.md`), else **Opus 4.8** | Scarce judgment on already-fetched data | Re-fetching bulk on Sol/Opus |
| **Product description research** (keywords, SERP intent, GSC queries for a SKU family) | **Codex GPT Terra** (MCP) | Google MCP required | |
| **Product description draft / bulk listing copy** | **Grok Build** (Shopify path) after research packet exists | Volume writing; catalog edits | Opus writing every SKU |
| **Product description brand / claim risk** | **Opus 4.8** or Sol review | Claims, compliance, voice | |
| **Mixed job** (research + code or research + listings) | Split briefs: MCP research seat → artifact path → Grok implement | One connector domain per brief | One agent inventing both without paths |

## Durable patterns

### 1. Product description pipeline

```
Codex dispatches
  1) Research brief → GPT Terra + Google MCP (keywords, GSC, Drive brief if any)
     output_path: research note / CSV
  2) Write brief → Grok Build + Shopify (titles, bodies, metafields)
     must_read: that research path
  3) Optional Review → Sol or Opus if claims/risk gate
```

Many SKUs, same template: one research packet for the family, then Grok bulk write. No Review D unless storefront chrome changes.

### 2. Bulk analytics pipeline

```
Codex dispatches
  1) Fetch brief → GPT Terra + GSC / DataForSEO / Drive
     done_when: tables at output_path, row counts, date range
  2) Optional interpret brief → Sol or Opus
     must_read: the tables only (no re-query unless gaps)
```

Never assign Opus to pull 10k GSC rows. Fetch on GPT; judge on Sol/Opus.

### 3. Coding with MCP context

```
Codex dispatches
  1) If code needs live Google numbers: GPT Terra MCP → snapshot file in repo or artifacts
  2) Grok Build implements against that snapshot (must_read)
  3) Code review as usual (diff only)
```

Grok does not need Google MCP mid-compile if the brief points at a frozen snapshot.

## Dispatch rules (Codex)

1. Does this brief **require Google MCP** (GSC, Drive, DataForSEO, Trends)?
   - No → default **Grok Build** for implement; reviews unchanged.
   - Yes → primary **GPT Terra** (bulk/general) or **Sol/Opus** (judgment only).
2. Is the deliverable **code or Shopify catalog volume**?
   - Yes → Grok still implements; MCP seat only supplies `must_read` artifacts first.
3. Is the deliverable **the analytics table itself**?
   - Yes → GPT Terra; stop when files land. No auto Sol.
4. Opus: tool-capable judgment and Review C — not the default MCP roomba.
5. Cursor Other Models with Google MCP: Last $ only (`cursor-usage.md`).

## Hard bans

- Opus or Sol as default implementer because “they have MCP”
- Grok inventing search volumes or GSC numbers without a connector or a provided snapshot
- Re-running bulk MCP on Sol/Opus after Terra already fetched
- Luna implementing MCP jobs (dispatch only)
- Mixing research + production write in one brief with no intermediate path
