---
name: naming
description: Request-driven generation and read-only screening of strong, brandable names for a business, brand, or product — it applies only the hard limits intrinsic to the specific thing being named and flexes everything else to the brief; use when naming a company, brand, product, app, package, domain, or the like.
---

# Naming (dynamic, read-only generation + verification)

This skill backs the orchestration's `naming` role. It is **read-only and request-driven**: it
generates candidate names, screens them for brandability, verifies them against read-only signals,
and writes a shortlist with rationale to the brief's `output_path`. It never registers a domain or
handle, files or clears a trademark, publishes, sends, or edits a repo or storefront.

> Live bindings — the seat, the MCP connectors (DataForSEO), and the Slack visual-QA channel — are in
> `config/roles.json` (`naming`), `config/skills.json` (`magnet-baron-skills:naming`), and
> `config/connectors.json` (`dataforseo` / alias `dfs-mcp`, `slack.visual_qa`). Read those for the
> current wiring; this skill is the durable method and the boundaries, not the connection list.

## The one rule: hard limits come from the item, not the skill

This is the core of the skill. **Do not apply a fixed checklist.**

1. Identify **what** is being named, derive **that item's intrinsic hard requirements**, and treat
   **only those** as pass/fail gates.
2. **Everything else flexes** — length, tone, name type, technique mix, syllable count, how many
   candidates, how deep to verify — is an adaptive default you tune to the brief, never a rule.
3. Adaptive defaults, not rules: **business/brand names lean shorter and more evocative; product
   names may be longer and more descriptive.** Override freely when the brief asks.
4. If the item type isn't in the table below, **derive its hard limits from first principles** — what
   registry, marketplace, exchange, jurisdiction, or legal constraint is intrinsic to *that* thing.
   The table is a starting set, not a closed list.

### Naming-target profiles (extensible)

| Item being named | Intrinsic hard limits (the ONLY gates) | Adaptive defaults (flex to brief) |
|---|---|---|
| Company / legal entity | Name available in the registration jurisdiction; not identical/confusingly close to a live mark in the relevant class | Short, broad, extensible |
| Brand / trade name (online commerce) | An acceptable-form domain is acquirable; a usable social handle exists; no collision with a strong in-category brand | Short, evocative, memorable, radio-test clean |
| Product within an existing line | Fits the parent naming architecture; unique within the catalog; consistent with line conventions | May be longer, descriptive, feature-led; alphanumeric OK |
| App | Unique/acceptable in the target app store(s); within the store's title-length limit | Benefit-suggestive; keyword-aware |
| Software package / library / OSS | Name free on the target registry (npm/PyPI/crates/Maven…); CLI-safe (lowercase, no spaces) | Short, typable, memorable |
| Domain-first / URL-first | The exact chosen domain is acquirable at an acceptable TLD | Brandable, short |
| Stock ticker / symbol | Within the exchange's character limit; not already assigned | Pronounceable, mnemonic |
| Feature / internal codename | Internal uniqueness only (no external gate) | Free, playful, themeable |
| Collection / campaign / event | Unique within its own catalog/calendar; nothing beyond that | Descriptive OK; can be long |

Match the request to one profile (or infer one), apply that row's hard limits as gates, adapt the rest.

## Hard boundaries (safety rails — inherited from the harness, always on)

These are **not** naming requirements and they do **not** flex — they are the read-only guardrails
every seat inherits:

- **Read-only. Generate and verify only.** Never register a domain/handle, file or clear a trademark,
  publish, send, or edit a repo/storefront. The role denies `Write`, `Edit`, `Bash`, `Admin`, and
  `publish` — treat them as absent even if a tool appears available.
- **Trademark clearance is a legal task.** A preliminary knockout (searching the public register or
  the web) is *informational only* — it is not legal clearance, does not judge likelihood of
  confusion or trademark class, and covers only what it searched. Full clearance is a trademark
  attorney at the shortlist stage. **Never attest that a name is "cleared" or "safe to use."**
- **Never invent availability data.** Every availability or collision claim must come from a named
  tool call (a DataForSEO tool, a web fetch, or a grokbot ticket reply). If a check did not run or
  returned nothing, say so — never estimate, guess, or fill from memory.
- **Be honest about the grokbot lane** (Step 4C): it is optional and owner-gated. Never claim a
  name-search routine exists when it does not.

## Step 1 — Scope the brief (establish what flexes)

Confirm or derive, and restate at the top of the output so every later judgment is interpretable:

- The **item** and its profile (table above) → its **hard limits** (which dimensions must be verified).
- Positioning/offer, audience, and personality/tone.
- Length and name-type preferences — or leave open.
- **Must-include** and **must-avoid** words, letters, sounds, or themes.
- Target **languages/markets** to screen.
- How many candidates to deliver, and how deep to verify.

Ambiguous item or hard limits → ask the dispatcher/owner before generating; do not guess a gate.

## Step 2 — Generate wide (adaptive technique mix)

Work in **territories** (strategy-derived directions: benefit, origin, metaphor, feeling, category)
and run techniques inside each to produce volume before any filtering. Generate more than you will
deliver.

Technique menu (pick per brief): word-association / mind-map · morpheme & root combination ·
Latin/Greek roots · metaphor & analogy · thesaurus laddering · portmanteau / blend · productive
affixes (`-ly -ify -io -o -a -able`) · compounding · truncation / clipping · rhyme & alliteration ·
onomatopoeia / sound-symbolic coinage · real-word repurposing (arbitrary) · careful respelling
(only if it still passes the radio test) · foreign or coined borrowing.

**Name type ↔ trademark strength** (steer with this; do not gate on it): the distinctiveness spectrum
runs **Generic → Descriptive → Suggestive → Arbitrary → Fanciful**, weak → strong for legal
protectability. Descriptive is easy to grasp but weak and hard to register/defend; **Suggestive is
the practitioner sweet spot** (inherently distinctive *and* it does marketing work); Arbitrary and
Fanciful are strongest legally but need investment to build meaning. Adaptive default: bias
suggestive/arbitrary for a brand or company; descriptive-leaning is often fine for a product or
feature.

## Step 3 — Screen for brandability (guidance, not gates)

Score and rank candidates. Only the item's hard limits are pass/fail; the following shape the ranking:

- **Neumeier's 7:** distinctive · brief · appropriate (*reasonable* fit, not literal) · easy to spell
  & pronounce (the "radio test": heard once, spelled right) · likable · extendable ("legs") ·
  protectable.
- **Watkins keep vs kill:** **SMILE** (Suggestive · Memorable · Imagery · Legs · Emotional) against
  **SCRATCH** to avoid (Spelling-challenged · Copycat · Restrictive · Annoying · Tame ·
  Curse-of-knowledge · Hard-to-pronounce).
- **Linguistic brandability:** sound symbolism (rounded *b/m/l/o/u* read soft; plosives *k/t/p/x/z*
  read sharp — match to positioning); an initial plosive tends to aid recall; favor fluent,
  pronounceable forms (~1–3 syllables, often 2) unless deliberate "premium/innovative" friction is
  intended; alliteration/reduplication aid memory; keep spelling unambiguous (radio test again).
- **Cross-language/cultural screen:** check the target-market languages for unintended meaning,
  slang, or offense — pronunciation, slang, and look-alikes, not just dictionary meaning. Flag risks;
  a real screen needs native speakers, so the skill surfaces concerns, it does not certify safety.

**Reliability, stated honestly:** the trademark distinctiveness spectrum is settled US legal
doctrine; the bouba/kiki sound-symbolism and processing-fluency/pronounceability effects are
peer-reviewed; the agency frameworks (Neumeier's 7, Watkins' SMILE/SCRATCH, the "~2 syllables"
heuristic) are practitioner consensus, not empirically proven. Apply the frameworks as judgment, not
law.

## Step 4 — Verify availability (the research-agent pass, scoped to the hard limits)

Run a **read-only** verification pass **only on the dimensions the matched profile actually
requires** — do not check a package registry for a legal-entity name, or a stock exchange for a
campaign title. Three lanes:

**A) DataForSEO** — always-on where the connector is active (claude host; `dataforseo` / `dfs-mcp`):
- **SERP collision** — does the term already surface a dominant existing brand (`serp_organic_live_advanced`).
- **Business-name collision** — existing businesses/listings (`business_data_business_listings_search`).
- **Marketplace/product collision** — existing products under the name (`merchant_amazon_products_live_advanced`, `dataforseo_labs_amazon_*`).
- **Demand/footprint** — is the term already a heavily-branded keyword (`dataforseo_labs_google_keyword_overview`, `..._keyword_ideas`).
- **Domain registration signal** — WHOIS status (`domain_analytics_whois_overview`). WHOIS shows
  registration, not a purchase quote — confirm true availability at a registrar via lane B.

**B) Web research** — WebSearch/WebFetch, any host: registrar domain-availability confirmation ·
social-handle availability · app-store / package-registry name checks · USPTO or other public-register
trademark **knockout** (preliminary only) · quick cross-language slang check. Cite the fetch for every
claim.

**C) grokbot visual lane** — OPTIONAL, owner-gated (Website Visual QA in Slack `#visual-qa`): a
read-only visual/web look (logo or design collision, "see it rendered"). **Honest constraints:**
grokbot is app-only — no CLI/API/webhook — and reacts only to content posted in the public
`#visual-qa` channel through owner-configured **narrow routines**. Today only two routines exist
(a `shopifypreview.com` preview token and a `visual-qa: live-audit` token); **there is no generic
name-search routine.** So use this lane only if the owner has first created a narrow name-search
routine/token — otherwise post nothing, and record the lane as unavailable. Never reuse the
storefront tokens for name search, and never claim an unwired routine exists.

**Legal lane** — always out of scope: full trademark clearance, likelihood-of-confusion analysis,
class selection, and comprehensive common-law + native-speaker linguistic screening go to the
owner/attorney. The skill never clears.

## Step 5 — Shortlist and deliver

Write to the brief's `output_path` (Markdown). Lead with judgment, attach the raw signals:

- The **restated brief**, the **matched profile**, and its **hard limits**.
- A **shortlist** of a few strong candidates (default ~3–7; adapt to the brief).
- **Per candidate:** name type; brandability notes (Neumeier / SMILE-SCRATCH / linguistic); and the
  **availability finding for each hard-limit dimension checked**, each tied to the tool that produced
  it, with any gaps stated explicitly.
- A **risks/flags** section: spelling, cross-language, weak-trademark, and any dimension left
  unverified — plus the standing note that **legal clearance by an attorney is still required before
  use.**

## Product vs company/brand, and naming architecture (reference)

- **Product names** live inside a system and may be longer, descriptive, and feature-oriented
  (*iPhone 15 Pro Max*, *Microsoft 365*). **Company/brand names** should be shorter, broader,
  evocative, and **extensible** so they stretch across future offerings (*Apple*, *Amazon*, *Virgin*).
- **Architecture** (fit it when naming a product — it is part of that profile's hard limit): branded
  house (one master name + descriptors — *Google Drive*) · house of brands (standalone brands —
  P&G → *Tide*, *Pampers*) · endorsed / sub-brand (*Courtyard by Marriott*) · descriptor + name
  (*Adobe Photoshop*) · alphanumeric (*Audi A4*). When naming a product, first establish which
  architecture the parent uses and conform to it.

## When the skill stops (handoff)

Produce the shortlist and the read-only findings, then hand to the dispatcher/owner. Registering a
domain or handle, filing or clearing a trademark, and publishing are out of scope and never done
here; legal clearance goes to an attorney. If a required verification lane is unavailable (connector
down, or the grokbot name-search routine not wired), deliver what you have, mark the gap, and park the
rest — never fill it with a guess.
