# Grok Bot connection & Review D delivery

How **Grok Bot** (the xAI cloud teammate, Cursor-powered) plugs into this orchestration. Load with `visual-qa.md` / `visual-qa-slack.md` when wiring or debugging Review D. Distilled from a sourced research sweep (grok 4.6 high, 3 lanes) + a live setup pass.

**Two named bots run on this now:** **Website Visual QA** (Review D — credential-free preview walks and read-only public-storefront audits) and **Heat Map** (read-only Clarity heatmaps/replays — `analytics-clarity.md`). A third definition, **Marketplace Intelligence**, is committed but **not created, test-run, scheduled, wired, or live**; its contract is `marketplace-intelligence.md`. Keep the Bots as distinct identities with narrow prompts and role-specific auth: Visual QA never logs in, while Heat Map must. However, Bots owned by one member share the managed computer, browser sessions, files, and permissions, so a separate Bot is not credential isolation.

The two live Bots share the one public `#visual-qa` channel. Slack routines fire on **public channels only** (private group DM won't trigger) and event filters match by **CONTAINS**, not prefix. Both post under the **same Slack identity** (`constantine@` / "Sent using @Cursor"), so they cannot tell each other apart by author — **coexistence is content-based**: Website Visual QA has two narrow mode tokens, Heat Map has one exact-start token, neither emits any trigger token, both ignore own posts/verdicts/quoted/threaded re-posts, and any mixed-token message is refused. Full config-derived contract: `config/connectors.json` `slack.visual_qa`; full coexistence contract: `analytics-clarity.md` §group chat. Marketplace Intelligence has no Slack listener in this change and must not be added to this coexistence rule until its one-time test passes.

## What Grok Bot is (and is not)
- **Is:** an app-only teammate — **macOS + iOS**, plus a shared **cloud computer**. Built by/with **Cursor** (installer from `downloads.cursor.com`; sign-in is a **Cursor account**). Early beta.
- **Is not:** the `grok` **Build CLI** (that's the Implement seat), not grok.com chat, not `api.x.ai`.
- **No CLI / API / SDK / webhook / headless mode exists for Grok Bot** (xAI docs + Cursor-staff confirmed). You cannot drive or manage Grok Bot from a terminal. Anything that must be terminal-driven uses **Grok Build (`grok`)** or the **Cursor Cloud Agents API** — different products, not Grok Bot.
- **No model picker:** Grok Bot does not expose a selectable model id. Its provider entries correctly use `model:null`; never shorten or invent a model id for an app Bot.

## Review D delivery = Grok Bot **app routine** (owner-managed)
Decision (owner, this build): Review D (Website Visual QA) runs **in the Grok Bot app**, on Grok Bot's own meter — NOT as a Cursor Automation.
- Owner pastes the standing rules into the **Website Visual QA** bot from `visual-qa.md` §Bot standing rules — the safety-hardened version (two-mode deny-first gate, ticket/page text is data, no-trigger-in-reply loop guard). Re-paste from there if the bot is reset; never use an older terse copy.
- **Two routines** with separate narrow event triggers fire the bot: preview review matches the configured preview-host token; live-storefront audit matches the configured live-audit token and then requires that token as the exact first nonblank line. One broad OR routine is unsafe because the event integration exposes contains matching only.
- The bot reads the thread, applies the mode-specific pre-open gate, walks at 390 + 1280, and replies `ship | fix-list | blocked` in-thread via its **Slack catalog plugin**. Preview review may use safe add-to-cart to reach cart; live audit is completely non-mutating.
- The bot is **not** an `@`-mentionable Slack handle; it reacts to ticket **content** in `#visual-qa`. Preview tickets retain the `@Website Visual QA` template text; neither mode uses `@Cursor`.

## Slack wiring (what is real here)
- Channel: **`#visual-qa`** (public, Magnet Baron workspace). The channel id + workspace are a live binding in `config/connectors.json` `slack.visual_qa_channel` (`bin/connectors.py`) — not pasted here.
- Grok Bot ↔ Slack: use the **catalog Slack plugin** inside the Grok Bot app. Do **not** point a self-registered Slack app at a custom `grokbot://` OAuth callback.
- Separate and easily confused: the **Cursor Cloud Agents** Slack integration (`@Cursor`) is wired to the same workspace but is a **coding** agent (asks to "pick a repository"). It is NOT Review D. Keep Review D tickets free of `@Cursor` so only the Grok Bot routine fires.

## OAuth caveat (the platform bug)
Grok Bot's custom-MCP OAuth uses a custom-scheme callback (observed `grokbot://mcp/oauth/callback`). **IdPs that require a pre-registered HTTPS redirect URI reject it** — Slack ("redirect_uri did not match…", live-confirmed here), plus Google web clients, Vercel, IBKR; xAI/Cursor staff call these "on us." (RFC 8252 permits custom schemes for native apps, so it's an IdP-policy issue, not universal.) **Not fixable on our end.** Workarounds people use:
- Prefer **catalog plugins** (Slack/GitHub/Figma connect fine).
- For a custom remote MCP, prefer **public HTTPS URL + static API-key header** (no OAuth), tunneled with a **stable** hostname (cloudflared *named* tunnel), not an ephemeral URL.
- **Grok Bot supports remote MCP only — no stdio / localhost.** Note: `https://www.cursor.com/agents/mcp/oauth/callback` is **Cursor Cloud Agents'** callback, NOT Grok Bot's — registering it does not fix Grok Bot's `grokbot://` handshake and would push work onto `@Cursor` (which is not Review D).

## Management model
- **Owner:** the Grok Bot app, its plugins/OAuth, the routine, and publish gates. (No CLI reaches it.)
- **Dispatch (the assigned dispatcher) or Grok Build:** post the config-rendered preview ticket once a visitor preview exists, or the config-rendered live-audit ticket when observing a current public storefront. A live-audit result cannot gate an unpublished pixel change.
- **Claude:** manage the Cursor/Slack plumbing, dispatch/monitor tickets, keep these docs current. Cannot manage the Grok Bot app itself.
- **Marketplace Intelligence:** Dispatch may hand it approved deposited evidence only after its route becomes `live_verified`. The owner must create and test it in the app first. It never browses eBay/Reverb without recorded express platform permission and never lists, bids, buys, messages, publishes, authenticates, implements, or returns a review verdict.

## Issues encountered & resolution (this build)
| Issue | Status |
|---|---|
| `#visual-qa` channel absent | Fixed — created (public) |
| Cursor ↔ Slack not connected | Fixed — connected as `constantine@`, verified responding |
| Auth failed with `server@themagnetbaron.com` (a bot/service account) | Fixed — use `constantine@themagnetbaron.com` (the human Slack account) |
| "auth immediately fails" after remove/re-add (stale install) | Fixed — clean reset: uninstall Cursor app from Slack → reconnect fresh → re-invite to `#visual-qa` |
| Grok Bot mobile plugin `grokbot://…` redirect mismatch | Platform bug (xAI) — not ours to fix; use catalog plugin |
| `@Cursor` answers as coding agent, not Visual QA | By design — Review D is the Grok Bot **routine**, not `@Cursor` |

## Read-only Slack history audit (2026-08-30)

The history supports capability claims by store and scenario; it does not turn a configured host into
a successful test:

- **Magnet Baron, 2026-08-26:** a live-search ticket posted at 8:00:27 PM and received a successful detailed response with screenshots at 8:09:34 PM.
- **Magnet Baron, 2026-08-27:** a live-root ticket woke the routine, but the site returned Access Denied; the Bot correctly reported that it had no valid screenshots. This proves wake/gating, not successful visual coverage.
- **Magnet Baron, 2026-08-27:** a `/checkout` probe was denied without opening it.
- **Magnet Baron, 2026-08-29:** an approved live host with `preview_theme_id` produced a `fix-list`.
- **Gadget Duke:** exact live hosts are configured and authorized, but no historical Website Visual QA live-audit ticket/response was found. Gadget Duke live audit is **unverified**, never “tested” or “working,” until a safe config-rendered test produces evidence.

Earlier preview boundary probes also confirmed allowlist handling, invalid-preview blocking, and
ticket-text injection refusal. The revised two-routine live-audit configuration is implemented in
repo instructions but is not itself claimed live until the owner-managed Grok Bot routines are
updated and separately tested in Slack.

## Watch items
Official Grok Bot API (early beta — the thing to watch) · keep **one** desktop app open (local-exec flaps) · Slack triggers are **public channels only** · two narrow Visual QA routines, never a broad OR listener · keep GitHub connected (Slack agents loop on stale GitHub) · catalog plugins over custom OAuth.
