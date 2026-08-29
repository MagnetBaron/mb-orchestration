# MCP routing

**Not previously spelled out.** Default implementer remains Grok Build. Google MCP (Search Console, Drive, DataForSEO / Trends / Ads volume, and similar) is available on **Opus** and **appropriate GPT models** (Codex Terra / Sol; not the Luna coordination helper). Grok does not assume Google MCP for these jobs.

The **assigned dispatcher** dispatches — in this setup the Claude orchestration surface (Codex is a worker/review seat here: dispatch-capable, but not the assigned dispatcher). The seat that *runs* the MCP calls is assigned below.

## Connector map — lives in `config/connectors.json`

**Which seat has which connector is dynamic and must not be hardcoded here** (it goes stale the
moment a connector moves). The single source is `config/connectors.json` `mcp_connectors.*.available_on`;
print the current map with `bin/connectors.py`. Today that is roughly: Google Search Console / Drive /
DataForSEO on Opus + GPT (Codex); Shopify (MB Internal) preferred on Grok for volume catalog; GitHub
on all coding seats — but **read the config, do not trust this sentence** when routing.

If a connector is missing on the assigned seat (per `available_on`), park and report — do not invent data.

## MCP strap-in (distribution): primed → ready → active

A distributed clone carries its own MCP servers plug-and-play, admin-managed, via a required
`status` on each `config/connectors.json` `mcp_connectors` entry:

- **active** — live-eligible. Existing live connectors are backfilled with `status: active`.
- **primed** — bundled/declared for distribution but NOT wired (some MCPs aren't ready yet).
- **ready** — validated + wireable, awaiting owner activation.
- **missing or unknown** — inert, never active. The schema requires `status`; doctor errors if it is absent.

Only **active** is live-eligible. A primed/ready entry may carry an optional **`server`** block
(`transport`/`command`/`args`/`url`/`env_keys`/`note`) — the launch DESCRIPTOR, carried **as data
only**. The lifecycle is admin-driven and out of band: the owner/admin validates a primed server,
lifts it to `ready`, then flips it to `active` (setting the env vars named in `env_keys`) — only
then is it routable.

**Hard inert guarantee.** Priming NEVER connects, launches, probes, or activates anything:

- The router refuses to grant a non-active connector to any seat — `bin/routing.py`'s
  `connector_is_active` is the single lifecycle predicate (routing, role/MCP generation, doctor,
  and skill gates). Connector-derived labels (IDs, aliases, **and classes** such as `google-mcp`)
  are recognized before coarse provider capability labels; a primed name or class copied into
  `providers.json` `capabilities` does not grant access. Missing/unknown/primed/ready never route and `available_on` is only a
  *declaration* of the seat it would ride on once active. A primed Shopify connector does not
  satisfy a write-capable Shopify skill gate. Existing `status: active` connectors still route.
  `--needs-mcp` resolves through id, alias, or class and PARKS unless a matching connector is
  `status=active` and lists the MCP volume seat (Terra) in `available_on`.
- `bin/doctor.py` (`check_connector_lifecycle`) validates the SHAPE only — status enum, a well-formed
  server block — and *proves* the inertness (a non-active connector is granted to no provider, not
  only `available_on` seats). It rejects provider capability collisions with connector IDs, aliases,
  and classes. It reads
  strings; it never runs `command`, opens `url`, spawns a process, or hits the network.
- `bin/smoketest.py` asserts a primed connector validates and is inert while active connectors still route.
- **No credentials in-repo.** A `server` block holds NO secrets: `env_keys` names the env vars the
  admin sets out of band; values never appear in the repo.

Activation (primed/ready → active, wiring a role/seat to it) is a **standing-config** change — run
`bin/doctor.py` before it lands.

## Assignment matrix

| Job | Primary seat | Why | Not |
|-----|--------------|-----|-----|
| **Coding / repo implement** | **Grok Build** | Abundant volume; worktrees; doctrine implementer | Opus or Sol as daily coder |
| **Code review** | Opus 5 → Codex Sol → Review E | Judgment on git diff (Fable out of gating) | MCP not required |
| **General Google MCP work** (one-off Drive pull, sitemap check, small GSC query) | **Codex GPT Terra** first | Has Google MCP; cheaper than Sol/Opus for tool loops | Luna (coordination helper, not the MCP-volume seat); Grok without connector |
| **Bulk analytics** (GSC rows, keyword batches, trends sweeps, multi-page Drive extract) | **Codex GPT Terra** (Luna coordination helper may assist) | Volume MCP loops; write CSV/summary to `output_path` | Opus for row dumps; Sol unless analysis judgment is the product |
| **Analytics judgment** (what the numbers mean, priority, strategy) | **Codex Sol** under 90% (`sol-usage.md`), else **Opus 5** | Scarce judgment on already-fetched data | Re-fetching bulk on Sol/Opus |
| **Product description research** (keywords, SERP intent, GSC queries for a SKU family) | **Codex GPT Terra** (MCP) | Google MCP required | |
| **Product description draft / bulk listing copy** | **Grok Build** (Shopify path) after research packet exists | Volume writing; catalog edits | Opus writing every SKU |
| **Product description brand / claim risk** | **Opus 5** or Sol review | Claims, compliance, voice | |
| **Mixed job** (research + code or research + listings) | Split briefs: MCP research seat → artifact path → Grok implement | One connector domain per brief | One agent inventing both without paths |

## Durable patterns

### 1. Product description pipeline

```
The assigned dispatcher
  1) Research brief → GPT Terra + Google MCP (keywords, GSC, Drive brief if any)
     output_path: research note / CSV
  2) Write brief → Grok Build + Shopify (titles, bodies, metafields)
     must_read: that research path
  3) Optional Review → Sol or Opus if claims/risk gate
```

Many SKUs, same template: one research packet for the family, then Grok bulk write. No Review D unless storefront chrome changes.

### 2. Bulk analytics pipeline

```
The assigned dispatcher
  1) Fetch brief → GPT Terra + GSC / DataForSEO / Drive
     done_when: tables at output_path, row counts, date range
  2) Optional interpret brief → Sol or Opus
     must_read: the tables only (no re-query unless gaps)
```

Never assign Opus to pull 10k GSC rows. Fetch on GPT; judge on Sol/Opus.

### 3. Coding with MCP context

```
The assigned dispatcher
  1) If code needs live Google numbers: GPT Terra MCP → snapshot file in repo or artifacts
  2) Grok Build implements against that snapshot (must_read)
  3) Code review as usual (diff only)
```

Grok does not need Google MCP mid-compile if the brief points at a frozen snapshot.

## Dispatch rules (the assigned dispatcher)

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
- Luna as the MCP-volume workhorse or repo implementer (it is a lightweight coordination helper; Terra runs MCP volume)
- Mixing research + production write in one brief with no intermediate path
