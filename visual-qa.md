# Review D — Website Visual QA

Grok Bot named **Website Visual QA**. Cloud computer only. Dispatch via Slack, not the Mini app, not `grok` CLI.

**How the ticket reaches the Bot:** [visual-qa-slack.md](./visual-qa-slack.md).

## Allowlist (edit this block only to add a site)

### 1) Magnet Baron
- Live: themagnetbaron.com, www.themagnetbaron.com, the-magnet-baron.myshopify.com
- Preview: `*.shopifypreview.com` when the brief names Magnet Baron / the-magnet-baron
- Extra: `preview_theme_id=*` on an approved Magnet Baron live host
- Never: admin.shopify.com, `/admin`, partners.shopify.com, SimGym

### 2) Gadget Duke
- Live: gadgetduke.com, www.gadgetduke.com, gadget-duke.myshopify.com
- Preview: `*.shopifypreview.com` when the brief names Gadget Duke / gadget-duke
- Extra: `preview_theme_id=*` on an approved Gadget Duke live host
- Never: admin.shopify.com, `/admin`, partners.shopify.com, SimGym

## Slack ticket (Codex or Grok Build posts this; Bot does not mint the URL)

Channel: `#visual-qa`

```
@Website Visual QA
site: Magnet Baron | Gadget Duke
url: https://<token>-<shop_id>.shopifypreview.com
changed: <one line>
pages: Home, collection, PDP, cart
```

Host must match the allowlist. Expired or live-theme preview → stop and ask for a new Share Preview.

## When to fire Review D

| Change | Review D |
|--------|----------|
| Theme / section / layout / CSS / PDP template | Yes |
| New collection page template | Yes |
| Product title, body, metafield, price, SKU, tags only | No — catalog path |
| Many products, same template | No extra Visual QA per SKU |
| User said ship a visible storefront change | Yes |

## Bot standing rules (source of truth for the named Bot)

You are Website Visual QA. Allowlist above. No Admin, no collaborator, no SimGym, no publish, no checkout submit. Walk 390 and 1280. Screenshot. Verdict ship | fix-list | blocked in the Slack thread.
