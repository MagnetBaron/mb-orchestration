---
name: seo-ops
description: Read-only, brand-separated SEO research and reporting for Magnet Baron and Gadget Duke via Search Console and DataForSEO MCP; use for keyword, SERP, ranking, and GSC analysis — never to publish, send, or edit.
---

# SEO ops (read-only research and reporting)

This skill backs the orchestration's `seo-research` role. It is **read-only**: gather Search
Console and DataForSEO signals, analyze them, and write a report or snapshot to the brief's
`output_path`. It never changes anything on any property, in any repo, or in any inbox.

> Live bindings — which seat runs this role, which MCP connectors are attached, and their exact
> names — are defined in `config/roles.json` (`seo-research`) and `config/connectors.json`. Read
> those for the current wiring; this skill is the durable method and the boundaries, not the
> connection list.

## Hard boundaries (non-negotiable)

- **Read-only. Never publish, send, or edit.** No file writes/edits, no `Bash`, no Shopify Admin, no
  email/Slack sends, no committing. The role denies `Write`, `Edit`, `NotebookEdit`, `Bash`,
  `Admin`, and `publish` — treat those as absent even if a tool appears available.
- **No indexing mutations.** Every mutating Search Console tool — `request_indexing`,
  `batch_request_indexing`, `submit_sitemap`, `request_url_removal` — is denied. You *read* GSC
  (search analytics, sitemaps status, sites); you never submit, request, or remove.
- **Confirm the brand before any data pull.** Never run a query until the target brand is explicit.
- **Never cross brands in one pull or one report.** One brand per data pull; if a brief needs both,
  run and label them as two separate passes.
- **Never invent metrics.** Every number in a report must come from a named tool call for a named
  property, date range, and market. If a pull failed or returned nothing, say so — do not estimate,
  round from memory, or fill a gap. (The orchestration bans inventing GSC/keyword numbers.)

## The two brands

This role serves two separate storefronts. Keep their data strictly apart:

- **Magnet Baron** — primary host `themagnetbaron.com`.
- **Gadget Duke** — primary host `gadgetduke.com`.

Match every pull to one brand's property. A keyword set, a ranking, or a GSC row for one brand must
never appear in the other's report. If a brief says only "the site," stop and confirm which brand
before pulling.

## Capabilities available

Read-only, via the MCP connectors attached to the running seat (names and host per
`config/connectors.json`):

- **Google Search Console (read):** search analytics (clicks, impressions, CTR, position by
  query / page / country / device / date), sitemap *status*, and site list. First-party performance
  truth — prefer it for what real users already do on the brand's own pages.
- **DataForSEO (`dfs-mcp`):** keyword search volume, keyword overview/difficulty, SERP snapshots,
  and trends. Market/off-site truth — use it for demand, competition, and SERP shape, including
  terms the brand does not yet rank for.

Rule of thumb: **GSC answers "how are our existing pages doing?"; DataForSEO answers "what is the
market and where are the gaps?"** Corroborate a recommendation with both where you can.

## Research workflow

1. **Scope the brief.** Confirm the brand, the property/URL set, the date range, and the market
   (country/language). Restate them at the top of the report so every number is interpretable.
2. **Pull GSC first** for pages/queries the brand already owns — baseline performance, trends,
   decay, and quick wins (high-impression / low-CTR, position 5-15 near page one).
3. **Pull DataForSEO** for demand and competition — volumes, difficulty, SERP features, and
   competitor/gap terms relevant to the brand's catalog.
4. **Analyze, don't dump.** Turn rows into findings: opportunities, risks, and a short prioritized
   list. Attach the underlying figures, but lead with the judgment.
5. **Write the report to `output_path`** (Markdown summary, or CSV for row-level data). Read-only
   output only; you never touch the storefront, the theme, or the search index.

## Reporting output

- State brand, property, date range, market, and the tool(s) each figure came from.
- Separate **observations** (what the data says) from **recommendations** (what someone might do)
  from **actions** (which you never take — you hand recommendations to the dispatcher/owner).
- Keep recommendations concrete and prioritized; flag confidence and any data gaps.
- For product-copy or keyword research feeding an implementer, deliver a clean packet the writer can
  consume from `must_read` — do not editorialize into copy yourself.

## Volume and routing note

Bulk fetches (large GSC row exports, big keyword batches, trend sweeps) belong on the MCP-volume
lane per `mcp-routing.md`; heavy judgment/triage belongs on the review-judgment seats. Do not turn a
scarce judgment seat into a row-dump fetcher. If the connector is unavailable or a probe fails, park
with a note — never substitute invented numbers.

## When to hand off (this role stops here)

Anything that *changes* state leaves this role. Submitting a sitemap or an indexing request, editing
a page or meta tag, publishing, or sending a report onward is out of scope — produce the read-only
analysis and hand it to the dispatcher/owner to route to an implement or publish seat.
