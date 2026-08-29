---
name: shopify-theme
description: Conventions and safe-change workflow for the Magnet Baron Sense-based Shopify theme (sections, snippets, blocks, assets, templates, locales); use when editing or reviewing that theme.
---

# Magnet Baron Shopify theme

The storefront theme for themagnetbaron.com. Base is **Sense** (Online Store 2.0), schema
`1.1.0`, **heavily customized**. Match the patterns already in the tree; do not import generic
Shopify boilerplate that ignores them. This skill describes how *this* theme is organized so a
change lands correct and style-matched.

> Read the repo's own `README.md` and `docs/WORKFLOW.md` before any deploy-facing work — they are
> the source of truth for live theme IDs and branch mapping, which change and must not be pasted
> from memory.

## Repository layout

Standard OS 2.0 theme directories sit at the repo root (what the Shopify GitHub integration
expects):

```
assets/  blocks/  config/  layout/  locales/  sections/  snippets/  templates/
```

Two directories are **not** theme data and are ignored by Shopify (`.shopifyignore`): `docs/`
(assessments, investigations) and `llms-subtree/` (staged llms.txt content). Editing them never
changes the storefront.

## Custom features (the `mb-` family)

Every bespoke feature is prefixed `mb-` across all its files, so a feature is greppable as one
unit. The real set (see `README.md` "Custom features"):

| Feature | Key files |
| --- | --- |
| Buy card, server-rendered from `[Buy Product=handle,Variant=id]` shortcodes in rich text | `snippets/mb-buy-shortcodes.liquid`, `snippets/mb-buy-card.liquid`, `assets/mb-buy-card.{css,js}` |
| Free shipping bar, country-aware (replaces Hextom) | `sections/mb-free-shipping-bar.liquid`, `assets/mb-free-shipping-bar.js` |
| Shop-by-game menu, single source of truth | `snippets/mb-game-systems.liquid`, `assets/mb-game-systems.css`, `blocks/ai_gen_block_08a79da.liquid` |
| Product tabs (Description / Specifications / Contents / Compatibility) | `snippets/mb-product-tabs.liquid`, `assets/mb-product-tabs.{css,js}` |
| Product upsell, metafield-driven | `snippets/product-upsell.liquid`, `assets/custom.js` (the only remaining jQuery consumer) |
| Magnet spec table, variant-metafield/registry driven | `sections/mb-magnet-spec-table.liquid`, `snippets/mb-magnet-spec-table.liquid`, `snippets/mb-magnet-spec-table-variant.liquid`, `assets/mb-magnet-spec-table.{css,js}`, `templates/product.super-magnets.json` |
| Magnet size finder, mobile-first filtering + cart controls | `sections/magnet-size-table.liquid`, `assets/magnet-size-table.{css,js}`, `snippets/magnet-polarity-placeholder.liquid`, `templates/page.magnet-size-finder.json` |
| Step guide (print-guide pages) | `sections/mb-step-guide.liquid`, `assets/mb-step-guide.{css,js}` |
| Sticky add-to-cart (mobile) | `sections/mb-sticky-atc.liquid` (proxies the main product form), `assets/mb-sticky-atc.{css,js}` |
| Cart terms gate | `snippets/mb-cart-terms.liquid`, `assets/mb-cart-terms.{css,js}` |

When adding a feature, follow the same fan-out: `sections/mb-<name>.liquid` and/or
`snippets/mb-<name>.liquid` + `assets/mb-<name>.css` + `assets/mb-<name>.js`, all sharing the
`mb-<name>` stem.

## Section anatomy

A section is Liquid markup followed by one `{% schema %}...{% endschema %}` JSON block. Copy the
shape from `sections/mb-magnet-spec-table.liquid` or `sections/mb-step-guide.liquid`:

- Schema keys used here: `name`, `tag` (`"section"`), `class` (`"section ..."`), `limit` (e.g. 1
  for once-per-page), `enabled_on` (e.g. `{"templates": ["page"]}`), `settings`, `presets`.
- Setting types in active use: `paragraph`, `header`, `text`, `textarea`, `richtext`, `select`,
  `range` (with `min`/`max`/`step`/`unit`), `checkbox`, `color`, `color_background`, `font_picker`.
- **Color scheme** is a `select` with the theme's standard options and is wired onto the wrapper as
  `class="... color-{{ section.settings.color_scheme }} gradient"`. Reuse the exact option set
  (`background-1`, `background-2`, `inverse`, `accent-1`, `accent-2`); 26 sections already do.
- **Padding** is two `range` settings (`padding_top`/`padding_bottom`), applied either inline or via
  a scoped `{%- style -%}.section-{{ section.id }}-padding{ ... }{%- endstyle -%}` block.
- Wrap content in the `page-width` class for the standard content column (36 sections do).
- Give every generated DOM id a `-{{ section.id }}` suffix (`MbStepGuideNav-{{ section.id }}`) so
  two instances never collide. Custom snippets build a `card_uid` from handle + variant + index for
  the same reason.
- End with a `presets` entry so the section is insertable in the theme editor.

## Snippets and rendering

Call snippets with named params: `{% render 'mb-buy-card', handle: h, variant: 'ALL', index: 3 %}`.
`render` isolates scope (no parent-variable leakage, and `increment` counters reset per call — see
the comment in `mb-buy-shortcodes.liquid`).

Hard-won lessons baked into the code, keep them:

- **`all_products[handle]` is capped** (~20 unique handle lookups per page) and product pages
  already spend part of that budget expanding shortcodes. Prefer the **object form**
  (`product_object:`/`variant_object:`) whenever you hold a drop. Resolve with `if/elsif`, never
  `product_object | default: all_products[handle]` — Liquid evaluates the default's argument either
  way and still burns a lookup.
- The buy-card transform is invoked as
  `{% render 'mb-buy-shortcodes', content: <rich text>, strip_only: <bool> %}`. Pass
  `strip_only: true` anywhere the text feeds a meta description, an `og:` tag, or JSON-LD, so a
  shortcode never leaks into search results. `layout/theme.liquid` already does this for
  `page_description`.

## Theme blocks

`blocks/*.liquid` are OS 2.0 theme blocks: markup + a `{% schema %}` block, and the root element
must carry `{{ block.shopify_attributes }}` (see `blocks/ai_gen_block_08a79da.liquid`, which just
renders the `mb-game-systems` snippet). Block schema limits are strict — see Theme limits below.

## Assets, CSS and JS

- Load CSS from a section with `{{ 'file.css' | asset_url | stylesheet_tag }}`; load JS with
  `<script src="{{ 'file.js' | asset_url }}" defer></script>`. Emit assets **conditionally** — the
  spec-table section only emits its CSS when the rendered component is non-blank and only emits its
  JS when `product.variants.size > 1`. Do not unconditionally add render-blocking assets.
- CSS file naming mirrors Sense: component styles are `component-<name>.css`, section styles
  `section-<name>.css`, custom feature styles `mb-<name>.css`.
- **Critical CSS bundle:** `assets/component-critical.css` is generated from
  `component-price.css` + `component-rte.css` + `component-rating.css` by
  `scripts/rebuild-css-bundle.sh` (Shopify has no build step). If you edit any of those sources, run
  the script and commit the regenerated bundle; reviewers check staleness with
  `scripts/rebuild-css-bundle.sh --check`.

### JavaScript conventions

Vanilla ES5-style JS, no framework. jQuery is still loaded but its **only** remaining consumer is
the product upsell in `assets/custom.js`; do not add new jQuery dependencies.

- Wrap each asset in an IIFE with `'use strict';`.
- **Guard against double-load.** Each feature sets a one-time window flag, e.g.
  `if (window.MBBuyCardLoaded) return; window.MBBuyCardLoaded = true;` (buy card), or the
  re-entrant `if (window.MBStickyATC && window.MBStickyATC.init) { window.MBStickyATC.init(document); return; }` pattern for section-scoped init. Duplicate `<script>`
  tags are expected on some pages; the guard is what makes them safe. Never remove it.
- Bind behavior to `data-mb-*` attributes (`data-mb-buy-form`, `data-mb-sticky-atc`,
  `data-mb-content`), not to style classes. Classes are for CSS; `data-mb-*` hooks are for JS.

## Liquid conventions

- Use whitespace-controlled tags (`{%- ... -%}`) and the `{%- liquid -%}` multiline form for logic,
  as the existing snippets do.
- Escape and format at output: `| escape` on any product/user text, `| money` for prices,
  `| image_url: width: N` with `srcset`/`sizes` + explicit `width`/`height` + `loading="lazy"`
  `decoding="async"` for images (see `mb-buy-card.liquid`).
- Customer-facing strings come from locales via the `t` filter
  (`{{ 'products.product.add_to_cart' | t }}`). Add new keys to `locales/en.default.json` (and its
  `.schema.json`); do not hardcode English in markup.

## Localization

`locales/` holds ~30 languages. `en.default.json` is the storefront copy; `*.schema.json` files are
theme-editor labels. A new user-visible string means a new key in `en.default.json`; other locales
can fall back until translated.

## Theme limits (silent-failure risk)

`scripts/mb-check-theme-limits.mjs` enforces Shopify's documented limits and runs first in the
pre-push hook. **Breaking a limit does not error the push — Shopify silently refuses to write that
one file and keeps serving stale code.** The real caps:

- Liquid file ≤ **256 KB**; `settings_schema.json` / JSON template / section group ≤ **512 KB**.
- A single Liquid setting value ≤ **50 KB**.
- ≤ **1000** JSON templates, ≤ **20** section groups, ≤ **1250** blocks per JSON resource, ≤ **50**
  blocks per section (default).
- Section/block `name` ≤ **25** chars; a custom (preset/block) name ≤ **100**.
- ≤ 100000 files/theme; ≤ 250 MB total non-asset code.

Keep section and preset `name` values short for this reason.

## Testing

Tests live in `tests/*.test.js` and are **plain Node scripts** (no framework): they
`require('node:assert/strict')`, run `staticChecks()` then `behaviorChecks()`, and finish by writing
`"<feature>: all checks passed"` to stdout. Run one with `node tests/<name>.test.js`.

Static checks worth mirroring for a new `mb-` feature (pattern in
`tests/mb-magnet-spec-table.test.js`):
- Liquid block balance (`if/endif`, `unless/endunless`, `for/endfor`, `capture/endcapture`,
  `case/endcase`, `schema/endschema`).
- The `{% schema %}` payload is valid JSON.
- The component JS parses (`new Function(script)`).
- Behavioral invariants (e.g. assets emitted only after a non-blank component; single-variant
  products omit JS) asserted against the section source, plus a DOM harness for the JS.

Add or extend a test alongside any `mb-` change and run it before you push.

## Branch and deploy safety

**Confirm the current mapping in `README.md` / `docs/WORKFLOW.md`; IDs move.** The invariant rules:

- **Merges to `production` are live deploys** — that branch drives the published `Live` theme and
  reaches customers. `main` drives an *unpublished* prototype theme; merging there reaches no
  customer.
- Work on a feature branch (`feature/*`, `agent/*`, `claude/*`, `grok/*` — none touch Shopify), open
  a PR, review the diff, merge to `main`. Cut a release only via `scripts/mb-backport.sh` then
  `scripts/mb-release.sh --live` (backport first so a live theme-editor change is not overwritten).
- The pre-push hook (`.githooks/pre-push`) refuses direct pushes to `main`/`production` and runs the
  theme-limits check. Enable it once per clone: `git config core.hooksPath .githooks`. Overrides
  (`ALLOW_MAIN_PUSH=1`, `ALLOW_PRODUCTION_PUSH=1`, `SKIP_THEME_LIMITS=1`) exist but are last resorts.
- CLI theme commands go through `scripts/mb-theme.sh` (non-expiring Theme Access token from the
  Keychain). Do not run raw `shopify theme` with an interactive login.
- `config/settings_data.json` is a two-way sync artifact (theme-editor edits commit back). Treat the
  `mb-free-shipping-bar` section and `type_body_font: poppins_n4` as release invariants; reconcile
  the file every release, never blind-overwrite it.

## House rules

- **Never publish a theme from the repo.** The owner proofs and publishes.
- New products and articles are created as **drafts**.
- **No em dashes or en dashes in customer-facing prose.** (Decorative storefront glyphs/SVG — stars,
  flags, arrows — are intentional design and fine; the rule is about copy.)
- Style-match the surrounding files; no drive-by refactors outside your named scope.

## Change checklist

1. Grep the `mb-<feature>` stem to find every file in the unit.
2. Edit section/snippet + matching `assets/mb-<feature>.{css,js}`; keep the window guard and
   `data-mb-*` hooks; escape/localize output.
3. If you touched a critical-CSS source, run `scripts/rebuild-css-bundle.sh` and commit the bundle.
4. Keep schema `name`s short; verify block/section counts against the limits.
5. Add/extend `tests/mb-<feature>.test.js`; run `node tests/mb-<feature>.test.js`.
6. Feature branch → PR → review → merge to `main`; never push straight to `production`.
