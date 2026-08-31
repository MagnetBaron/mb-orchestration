# Frontier model / role audit

**Date:** 2026-08-28
**Cutoff:** 2026-08-28
**Scope:** Current general-purpose text/vision/agentic/coding models plausibly useful to Magnet Baron orchestration. This is a scoped lab census, not an unbounded claim of every model in existence.
**Excluded from routing (and from this census as candidates):** media-only, embedding, moderation, audio-only, and invitation-only offerings (examples: Gemini image-only / Nano Banana, Gemini Live Translate/TTS, Kimi-Audio).
**Method:** official catalogs for identity/availability; independent measurements for ranking; local CLI/harness smoke or standing operational signal for route state. Vendor benchmarks are labeled self-reported. Harness and effort differences prevent naive score comparison. A single global leaderboard is invalid.

This document is evidence, not an operational contract. Routing is `config/model-registry.json` + `config/providers.json` + `bin/resolve-route.py`. Rank never grants tools, credentials, write access, publish authority, or data access. Unknown, catalog-only, auth-blocked, incubation, and unwired routes fail closed.

**Current-state correction (2026-08-30):** the legacy Grok Bot Review D and Heat Map app routes are
retired. Their replacement named CLI routes are `unwired` and normal execution hard-parks before
prompt/evidence reads until the corresponding code-owned pixel or Clarity input binding exists;
browser/Clarity observation, profile sync, and role tests are additional gates. Cursor Agent's live
model listing established the exact selectable id `cursor-grok-4.6-xhigh`, but the exact inference
attempt returned no terminal receipt or edit. Therefore `grok-4.6-cursor` is now
`catalog_verified`, not `live_verified`, and its local-access smoke is missing. All historical
standing/live language for Cursor and the retired Bots below is superseded by this correction and
does not authorize promotion.

## Limitations

- Local access was sampled on 2026-08-28.
  - **Direct invocation in this audit:** `teamclaude` smokes of `claude-opus-5`, `claude-opus-4-8`, and `claude-fable-5` (restricted mode, strict MCP config, no session persistence, synthetic prompts). Each returned the requested canonical id, first-party, 1M context. See **Local evidence (round 2)** below.
  - **CLI listings, not invocations:** `gpt --models` listed `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.3-codex-spark`. `grok models` listed `grok-4.6` and `grok-4.5` (cached authenticated registry readable; settings refresh produced network warnings). `teamclaude status` listed usable Opus and Fable on at least one account.
  - Direct `claude` without teamclaude was auth-blocked.
- At the 2026-08-28 audit snapshot, pre-existing operational provider routes (Codex Sol/Terra/Luna, Grok Build, Cursor Grok, legacy Grok Bot Review D / Heat Map, Fable architecture seat) were treated as `live_verified` on the independent standing-provider signal in `providers.json`, with evidence wording that distinguished a listing from an invocation. The legacy Grok Bot routes are now retired; use the current-state correction above.
- Independent anchors are Artificial Analysis pages dated in the 2026-08-28 evidence packet. They are not this repo's eval harness. Effort (max / high / xhigh) is not comparable across labs. Descending ranks below are evidence-bounded and role/harness-specific, not a universal ordering.
- Fable's public Intelligence Index 62 includes a documented Opus fallback, so it is not independent family evidence.
- GLM 5.3 Flash (released 2026-08-26) is vendor-heavy; it is cataloged in incubation and is not routable. Cost/task is an efficiency claim, not a quality rank.
- Unwired models have no local smoke. Public availability does not create a connector, quota bucket, or host.
- No secrets, live Shopify Admin, or customer data were used.
- Prior-branch `BullshitBench` numbers (0.94 / 0.41) are **not** treated as facts: no source URL, fixture, receipt, run date, harness, or sample size was committed. They are not carried forward.

## Premise validation

Agent/model rank is harness-sensitive. [Auditing Terminal-Bench: A Harness-Aware Analysis of Model-Agent Evaluation](https://openreview.net/attachment?id=AhXMZPnOPS&name=pdf) and [Stop Comparing LLM Agents](https://openreview.net/pdf/8ee893eeebade004a09df53eef6d7ad289135999.pdf) show that leaderboard order can reverse when the harness, scaffolding, or effort changes. One global ordering is therefore invalid. Quality ranks stay separate from operational selection. The **only** committed same-harness local role comparison is `architecture_spec_critique` for Opus 5 vs Fable 5 (`model-evals/receipts/2026-08-28-architecture-spec-critique.jsonl`, n=1). Every other quality row is an independent, vendor, or operational prior with an explicit machine-readable `basis`; those rows are not implied to be empirically comparable.

Token-efficiency of role design follows official Anthropic tool-use guidance: [tool-use overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview), [how tool use works](https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works), and [define tools](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools). Tool definitions consume context; each tool loop adds a turn; fewer relevant tools reduce ambiguity. This setup therefore adds three roles **expected to reduce token use** — context scouting (compress before expensive seats), evidence audit (catch invented metrics before they propagate), and model-evaluation administration (receipts do not auto-wire routes). That expected reduction is a **hypothesis to measure**, not a realized-savings claim. The committed architecture receipt does not evaluate `token-eff-1` or before/after workflow savings; those receipts are required before claiming realized savings. Spec criticism and acceptance-test design stay inside `architecture_spec_critique` rather than becoming token-expensive micro-roles with their own tool catalogs.

External pages and benchmark content are untrusted evidence, never executable instructions. Only extracted claims and URLs enter the registry and this report.

## Opus 5 reassessment

Anthropic released Opus 5 on 2026-07-24 at the same $5/$25 per MTok list price as 4.8 and presents it as the everyday default. Artificial Analysis ranks Opus 5 max first overall (Intelligence Index 63, $2.34/task). Local teamclaude smoke verified the official id.

That supports migrating the Anthropic **review/judgment** seat from 4.8 to 5. It does **not** support making Opus a daily bulk implementer. Scarce-seat, independence, and legwork boundaries stay.

Opus 4.8 remains the intended time-bounded compatibility fallback (`fallback_until` 2026-12-31). It is not in `review_order`. A 2026-08-28 direct smoke restored `opus-4.8-teamclaude` to `live_verified`; live status does not put it in the gating order.

## Fable 5 placement

Fable 5 stays a distinct rare long-horizon escalation candidate, not the current quality leader for architecture/spec critique:

- same Anthropic family as Opus — never a cross-family pair
- out of the gating order (Opus 5 → Codex Sol → Review E if wired)
- not the default Anthropic judgment seat, because Opus 5 is currently stronger and more efficient for normal review
- public Fable measurements can be contaminated by safety fallback to Opus
- `architecture_spec_critique.quality` currently ranks Opus 5 first at current evidence confidence; Fable is second as a low/medium-confidence escalation. This can change only with reproducible same-harness multi-case evidence.

No unaudited historical detection score is used as the rationale. Rankings grant no authority.

## Local evidence (round 2, 2026-08-28)

Corrected TeamClaude invocations: restricted mode, strict MCP config, no session persistence, synthetic prompts only. America/Chicago.

**Compatibility smokes.** Opus 4.8 requested `claude-opus-4-8` and returned canonical `claude-opus-4-8`, firstParty, 1M context, marker `OPUS48_SMOKE_OK`, completed in one model turn. That direct smoke is why `opus-4.8-teamclaude` is `live_verified`; it stays superseded, out of `review_order`, and time-bounded through 2026-12-31. Opus 5 requested `claude-opus-5` and returned canonical `claude-opus-5`, firstParty, 1M context; it answered that Opus 5 is the operational Anthropic review seat. That route stays live.

**Architecture/spec critique (same prompt, both max effort, n=1).** Prompt: auto-promote any newly cataloged model from unwired to live routing when its synthetic eval score is ≥0.80; identify the principal architecture/safety defect and the minimum fail-closed correction; ≤120 words; do not discuss latency. Receipts: `model-evals/receipts/2026-08-28-architecture-spec-critique.jsonl`. `bin/model-eval.py` scores:

| Model | total | correctness | token efficiency | tokens_out (incl. thinking) | thinking | latency_ms | cost USD |
|-------|------:|------------:|-----------------:|----------------------------:|---------:|-----------:|---------:|
| claude-fable-5 | 0.7789 | 1.0 | 0.1155 | 1732 | 1487 | 22372 | 0.3858 |
| claude-opus-5 | 0.7752 | 1.0 | 0.1007 | 1986 | 1717 | 26449 | 0.19575 |

Both found the critical fail-open defect (a synthetic score is not an authorization signal; write access to the catalog must not be deployment authority). No clear qualitative Fable win on this sample. The composite scores (0.7789 vs 0.7752) are almost tied and are **not** a quality verdict. `tokens_out` conservatively includes hidden reasoning (1487 / 1717 thinking tokens); the visible response stayed within the 120-word instruction (112 / 118 words). Cost is recorded but does not enter the quality score. Latency weight remains zero. Total reasoning/output token magnitudes were similar. This supports Opus as the normal seat and Fable as an explicit escalation. It does not establish a universal rank. Sample is n=1 per model. Rank can change only with reproducible same-harness multi-case evidence.

## Attestations and freshness clock

Every `live_verified` route carries an `attestations` object covering `intake.promote_requires` (`official_id`, `local_access_smoke`, `role_evals`, `independent_evidence`, `cost_context`, `owner_approval`). Each entry has a typed `state`: `attested`, `missing`, `not_applicable`, or `waived`. Boolean `attested: true` is rejected. `attested` requires a field-specific `evidence_kind` and a dated direct supporting source whose semantics support that requirement; text such as “evaluation suite absent,” “missing,” “unavailable,” or “no evidence” cannot pass. `missing` cannot be `live_verified`. `not_applicable` requires a closed `structural_code` authorized by an exact code-owned `(route_id, model_id, attestation_field)` mapping. Only Opus 4.8 role evals/independent evidence and the exact Grok Bot pixel-walk/heat-map role-eval identities qualify today; mutable compatibility flags, harness fields, capabilities, and rationale cannot create eligibility. Free-form rationale never establishes N/A; absence language cannot turn missing evidence into N/A. `waived` is a time-bounded legacy/standing-provider migration exception (`authority: existing_operational_state`, date, short expiry). It requires both an exact route id on the frozen `intake.legacy_waiver_routes` manifest and a code-owned exact model/provider/host/harness/invocation/family identity tuple. Repointing an allowlisted id invalidates every waiver. It is visible in inventory/matrix/report and does **not** assert that the evidence exists. After expiry the route fails closed. New candidates may never use a legacy waiver. No committed structured owner-approval manifest exists, so owner_approval is waived on existing operational seats rather than claimed as attested; an existing Markdown file cannot attest approval.

`local_access_smoke.signal` / `evidence_kind` is either `direct_invocation` (Opus 5, Opus 4.8, Fable 5 teamclaude smokes) or `standing_provider` (Codex Sol/Terra/Luna listings, Grok Build listing, Cursor pool, Grok Bot identities), and must match live route evidence. Standing seats were not given invented smokes. `official_id` attestations cite direct official vendor https URLs whose host is on the validator's code-owned official-domain map for that model family. The documented `official_sources.allowed_domains_by_family` must mirror that trust root exactly and cannot authorize itself by adding `example.com`; local JSON paths and another family's domain are also insufficient. Review E remains a local placeholder outside the census and is not domain-checked as a promotable vendor source.

Quality ranking rows carry `basis`, `confidence`, and a basis-appropriate `source` pointer. `confidence: high` is allowed only for `basis: local_same_harness` with a committed same-role receipt (`architecture_spec_critique` Opus 5 vs Fable 5). Other bases cap at medium/low and require an independent URL, vendor URL, or, for `operational_prior`, the exact code-approved structured config whose content binds that role/route/model. Arbitrary existing prose files are rejected.

Validation compares evidence and attestation dates to the **actual current date**. `registry.as_of` is a catalog label, not the clock. Tests pass `--as-of` / `validate(..., as_of=)` to freeze it. Future-dated, missing, stale, mismatched, semantically contradictory, or expired-waiver evidence fails closed.

### Directly evaluated vs temporarily grandfathered

This audit states which routes are directly evaluated and which are temporarily grandfathered.

**Directly evaluated** (local_access_smoke attested with `direct_invocation`):

| Route | Direct signal | Other fields |
|-------|---------------|--------------|
| `opus-5-teamclaude` | teamclaude smoke of `claude-opus-5` plus architecture receipt | official_id, role_evals, independent_evidence, cost_context **attested**. owner_approval **waived** (`existing_operational_state`, expires 2026-11-26). |
| `opus-4.8-teamclaude` | teamclaude smoke (`OPUS48_SMOKE_OK`) | official_id **attested**. role_evals and independent_evidence **not_applicable** (`structural_code: compatibility_fallback_not_ranked`). cost_context and owner_approval **waived** (expires 2026-11-26). |
| `fable-5-teamclaude` | architecture-critique invocation of `claude-fable-5` plus receipt | official_id, role_evals, independent_evidence, cost_context **attested**. owner_approval **waived** (`existing_operational_state`, expires 2026-11-26). |

**Temporarily grandfathered** (standing-provider signal plus time-bounded waivers; not described as the missing evidence existing):

| Route | Standing signal | Waived fields (expire 2026-11-26) |
|-------|-----------------|-----------------------------------|
| `gpt-5.6-sol-codex` | `gpt --models` listing; Codex Sol provider | role_evals, owner_approval. independent_evidence and cost_context **attested** (Artificial Analysis). |
| `gpt-5.6-terra-codex` | `gpt --models` listing; Codex Terra provider | role_evals, independent_evidence, cost_context, owner_approval. |
| `gpt-5.6-luna-codex` | `gpt --models` listing; Codex Luna provider | role_evals, independent_evidence, cost_context, owner_approval. |
| `grok-4.6-build` | `grok models` listing; Grok Build provider | role_evals, owner_approval. independent_evidence and cost_context **attested** (Artificial Analysis). |
| `grok-4.6-cursor` | standing Cursor first-party pool | role_evals, owner_approval. independent_evidence and cost_context **attested** on the grok-4.6 model, not the Cursor harness. |
| `grok-bot-visual-qa` | standing Review D provider | owner_approval, cost_context. role_evals **not_applicable** (`app_only_pixel_walk_not_text_suite`). independent_evidence **attested** on grok-4.6. |
| `grok-bot-heat-map` | standing Heat Map provider | owner_approval, cost_context. role_evals **not_applicable** (`app_only_analytics_input_not_text_suite`). independent_evidence **attested** on grok-4.6. |

A `grok models` listing is a standing-provider signal, not a direct invocation.

## Model census (2026-08-28)

Labs in scope: OpenAI, Anthropic, xAI, Google, Moonshot, Z.AI, Alibaba, DeepSeek, Meta. Review E / `open-weight-review-e` is a **local placeholder** independence slot, not a frontier-lab model, and is outside this census. It cannot be promoted or wired until a named candidate model plus an official vendor source replaces it.

Live-verified (may resolve). Evidence kind is exact:

| Route | Model | Host | Evidence | Signal |
|-------|-------|------|----------|--------|
| `opus-5-teamclaude` | claude-opus-5 | teamclaude | **direct live smoke** of `claude-opus-5` (seat-policy + architecture receipt) | `direct_invocation` |
| `opus-4.8-teamclaude` | claude-opus-4-8 | teamclaude | **direct live smoke** (`OPUS48_SMOKE_OK`); superseded compatibility fallback; **not** in `review_order` | `direct_invocation` |
| `fable-5-teamclaude` | claude-fable-5 | teamclaude | **direct live smoke** of `claude-fable-5` (architecture receipt); standing architecture provider | `direct_invocation` |
| `gpt-5.6-sol-codex` | gpt-5.6-sol | gpt wrapper | `gpt --models` **listing**; standing Codex Sol provider | `standing_provider` |
| `gpt-5.6-terra-codex` | gpt-5.6-terra | gpt wrapper | `gpt --models` **listing**; standing Codex Terra provider | `standing_provider` |
| `gpt-5.6-luna-codex` | gpt-5.6-luna | gpt wrapper | `gpt --models` **listing**; standing Codex Luna provider | `standing_provider` |
| `grok-4.6-build` | grok-4.6 | grok CLI | `grok models` **listing**; standing Grok Build implementer | `standing_provider` |
| `grok-4.6-cursor` | grok-4.6 | Cursor | standing first-party Cursor pool provider | `standing_provider` |
| `grok-bot-visual-qa` | grok-4.6 (app) | Grok Bot | standing Review D provider | `standing_provider` |
| `grok-bot-heat-map` | grok-4.6 (app) | Grok Bot | standing Heat Map provider | `standing_provider` |

Catalog-verified (listed or documented; does **not** resolve): gpt-5.5, gpt-5.4, gpt-5.4-mini, gpt-5.3-codex-spark, grok-4.5.

Auth-blocked: `opus-5-direct-claude` (bare `claude` without teamclaude).

Unwired current candidates (cataloged, non-routable unless later wired and verified):

- Google: Gemini 3.7 Flash, 3.6 Flash, 3.5 Flash, 3.5 Flash-Lite, 3.1 Flash-Lite, 3.1 Pro Preview, Gemini 3 Flash Preview
- Moonshot: Kimi K3, K2.7 Code, K2.6
- DeepSeek: V4 Pro and V4 Flash as distinct models (no ambiguous bare `deepseek-v4`)
- Meta: Muse Spark 1.2 (model) and Muse Code (agent product) as distinct candidates
- Z.AI: GLM 5.3 Flash (incubation), GLM 5.2
- Alibaba: Qwen 3.8 Max
- Review E / Fireworks independence slot (local placeholder; not a census lab)

Official catalog URLs used for identity (also machine-readable on each in-scope model and on `official_sources.by_family` with validated coverage):

- OpenAI: https://developers.openai.com/api/docs/models · https://openai.com/index/gpt-5-6/
- Anthropic: https://platform.claude.com/docs/en/about-claude/models/choosing-a-model · https://www.anthropic.com/news/claude-opus-5 · https://www.anthropic.com/news/claude-fable-5-mythos-5
- xAI: https://docs.x.ai/developers/grok-4-6 · https://docs.x.ai/developers/pricing
- Google: https://ai.google.dev/gemini-api/docs/models
- Moonshot: https://platform.kimi.ai/
- Z.AI: https://z.ai/blog/glm-5.3-flash · https://z.ai/blog/glm-5.2
- Meta: https://ai.meta.com/llama/
- Alibaba: https://www.alibabagroup.com/en-US/document-2021044032125272064
- DeepSeek: https://api-docs.deepseek.com/news/news260813/

Independent anchors (not a global leaderboard; harness-specific). Direct pages:

| Model | Harness | Index | USD/task | Label | Pages |
|-------|---------|------:|--------:|-------|-------|
| claude-opus-5 | max | 63 | 2.34 | independent | [model](https://artificialanalysis.ai/models/claude-opus-5) · [release](https://artificialanalysis.ai/models/releases/claude-opus-5) |
| claude-fable-5 | max | 62 | 3.14 | independent, Opus-fallback caveat | [model](https://artificialanalysis.ai/models/claude-fable-5/) |
| grok-4.6 | high | 61 | 0.94 | independent; high beat xhigh in that run | [release](https://artificialanalysis.ai/models/releases/grok-4-6) · [analysis](https://artificialanalysis.ai/articles/grok-4-6-benchmarks-and-analysis) |
| kimi-k3 | max | 60 | 0.84 | independent; verbose; not role-comparable vs Opus 5 | [model](https://artificialanalysis.ai/models/kimi-k3) |
| gpt-5.6-sol | xhigh | 59 | 0.67 | independent; OpenAI also reports Coding Agent Index 80 for Sol / 77.4 for Terra (vendor) | [model](https://artificialanalysis.ai/models/gpt-5-6-sol-xhigh/) |
| qwen-3.8-max | max | 58 | 0.91 | independent; very verbose | [model](https://artificialanalysis.ai/models/qwen3-8-max) |
| glm-5.2 | max | 53 | 0.44 | independent | [model](https://artificialanalysis.ai/models/glm-5-2) |

Vendor self-reported (not independent; efficiency, not quality):

- GLM 5.3 Flash: reported index 57, $0.045/task — [official Z.AI release](https://z.ai/blog/glm-5.3-flash). Incubation; cannot resolve.

## Role recommendations

Quality rank and selection priority are separate. A scarce top model can rank first on quality while a cheaper live route remains the default. Quality is performance evidence for that role, not price. Cost/token efficiency is selection or an explicit `efficiency` field. Descending ranks are evidence-bounded and role-specific. Each quality row has a machine-readable `basis`. Only architecture Opus/Fable cites the local n=1 same-harness receipt; other role rankings are external or operational priors and are not implied to be empirically comparable.

| Role | Selection default (live) | Quality notes | Why |
|------|--------------------------|---------------|-----|
| **dispatch** | Luna (routine) / Terra (high-context). Authority remains `entrypoints.json` (Opus 5 here). | Terra > Opus 5 > Luna (`operational_prior`) | Dispatch is a role and authority boundary, not a prize. |
| **context_scouting** | Luna, then Grok 4.6 | Live extract/compress quality: Luna > Grok (`operational_prior`). GLM 5.3 Flash is an **efficiency** incubation candidate, not quality #1. | Cheap extract/compress before expensive seats. **Added** as a hypothesis expected to reduce expensive-seat token use. |
| **research_synthesis** | Grok 4.6; Terra if the packet is Google MCP | Opus 5 > Sol > Grok. Kimi K3 is a **low-confidence incubation** candidate, not ranked above Opus 5. | Do not invent Google metrics. A lower global index plus long context is not comparable role evidence. |
| **implementation** | Grok 4.6 high | Sol/Opus may rank higher on some coding metrics; too scarce | Preserves independent review lanes. Active implementation default remains Grok 4.6 high. |
| **architecture_spec_critique** | Opus 5; Fable on explicit long-horizon escalation | Opus 5 first at current evidence (`local_same_harness`, n=1); Fable second as a low-confidence long-horizon escalation candidate. Same family. Rank can change only with reproducible same-harness multi-case evidence. | Never a cross-family pair. |
| **code_review** | Opus 5 then Sol (families must differ) | Opus 5 > Sol > Fable (non-gate) | Operational review pair is Opus 5 + GPT-5.6 Sol. |
| **mcp_volume** | Terra | Terra is the only live connector-bearing route. Gemini Flash variants are unwired candidates. GLM Flash is efficiency, not quality. | Connector presence required. |
| **mcp_judgment** | Sol, else Opus 5 | Same two live judgment seats | Code-review risk gate wins Sol the same week. |
| **visual_qa** | Parked pending the `mb-review-d` code-owned pixel binding | Historical Grok Bot route is retired; the named CLI route is unwired and packet rendering is not execution | Never Admin/SimGym. |
| **evidence_audit** | Opus 5 / Sol | Catches invented metrics (`operational_prior`) | **Added** because it catches defects before they propagate. Token-use reduction is a hypothesis to measure. |
| **model_evaluation_admin** | Opus 5 (owner-gated) | Does not auto-promote (`operational_prior`) | Scores never wire routes. Token-use reduction is a hypothesis to measure. |

## Missing roles considered and not added

- Dedicated “SEO writer” or “Shopify publisher” model roles — already covered by implement + owner publish gates; a new model role would look like a permission grant.
- Second Visual QA model — no second live harness.
- Latency-optimized “realtime” role — latency has weight 0 by policy.
- Separate spec-criticism or acceptance-test-design micro-roles — folded into `architecture_spec_critique`. Extra roles would add tool definitions and tool-loop turns without reducing expensive context or catching a distinct defect class.

## Rankings vs authority

- Exactly one user-assigned dispatcher (`entrypoints.dispatcher.provider`).
- Any entry surface may intake and hand over.
- Cross-family selection mechanically rejects two routes from the same family. Operational pair: Opus 5 + GPT-5.6 Sol.
- Fable is same-family, rare architecture/long-horizon escalation only.
- Unknown, catalog-only, auth-blocked, incubation, and unwired availability fails closed.
- A catalog entry is not a usable route.
- `bin/model-registry.py resolve` is fail-closed: it filters every candidate with `route_is_live` and does not depend on CLI `assert_valid`. Missing, stale, future, mismatched, semantically contradictory, expired-waiver, or unattested evidence, undeclared family/independence group, or a route-local identity/family/invocation contradiction, never returns the route.
- Last-resort coding requires a concrete live `implement`/`ide` provider with `code` on both the provider and its bound live route; sharing a plan (Luna/Terra/Sol) is not a coding grant.
- `bin/model-registry.py resolve` returns `authority_grants: false`.
- Rankings grant no authority or connectors.

## Migration (this change-set)

1. Merged the config-driven engine (`config/*.json`, `bin/resolve-route.py`, `bin/doctor.py`, `bin/smoketest.py`) with main's selective skill routers (`skills/`) and idle-mini QA policy.
2. Removed the redundant legacy role-registry directory. Role *loading* remains `config/roles.json` + `bin/generate-roles.py` (not coupled to model releases). Model identity lives only in `config/model-registry.json`.
3. Replaced the Opus 5 hard ban with Opus 5 as the Anthropic gate. Kept Opus 4.8 as a documented, time-bounded compatibility fallback. Round 2 restored it to `live_verified` after a direct smoke; it remains out of `review_order`.
4. Bound each runtime provider to a catalog route. `review_order` is `opus-5 → codex-sol → review-e`, filtered to `live_verified`. Fable is not first and is not in that order. Opus 4.8 is live and still excluded from that order.
5. Added synthetic eval cases and receipt scoring. New-model intake is two-phase.
6. Follow-up: completed the scoped census, split DeepSeek V4 Pro/Flash and Muse Spark/Muse Code, moved cost claims into `efficiency`, and demoted Kimi K3 below Opus 5 for research synthesis.
7. Round 2: committed same-prompt Fable 5 / Opus 5 architecture receipts (`model-evals/receipts/2026-08-28-architecture-spec-critique.jsonl`). n=1 per model; no rank change at that time.
8. Round 3: `architecture_spec_critique.quality` now ranks Opus 5 first at current evidence; Fable is a low-confidence long-horizon escalation candidate. Direct independent-anchor links, premise-validation citations, and receipt-interpretation notes added. Rank can change only with reproducible same-harness multi-case evidence.
9. Evidence/methodology remediation: typed attestation state (`attested`/`missing`/`not_applicable`/`waived`); live routes audited so absence language is never `attested`; standing seats kept live only with time-bounded `existing_operational_state` waivers (expire 2026-11-26); quality rows labeled with `basis`; official vendor https sources on every in-scope model; Review E marked as a local placeholder outside the census; token-efficiency wording reduced to a hypothesis to measure.
10. Typed evidence hardening: field-specific `evidence_kind` on attested fields; exact code-owned route/model/field authorization for structural N/A; frozen legacy waiver identity tuples beyond the documented route-id manifest; code-owned official-domain map mirrored by `official_sources.allowed_domains_by_family`; structured operational-prior source bindings; owner records rejected until a structured manifest exists; ranking `confidence: high` only for `local_same_harness` with a committed receipt, enforced by the validator.

## Future audit instructions

1. Re-run local smokes: `gpt --models`, `grok models`, `teamclaude status`, and direct `teamclaude` invocations for each live Anthropic id. Record the date on each live route. A listing is not an invocation. Opus 4.8 is already live-smoked (2026-08-28); keep it out of `review_order`.
2. Refresh independent anchors from the same harness pages; do not mix effort levels into one table of "winners." Do not rank on price in the quality column.
3. Score `model-evals/cases.json` receipts with `bin/model-eval.py`. Latency may be recorded; it must not decide rank.
4. Catalog new models as `unwired` or `catalog_verified`. Promote to `live_verified` only after official-id, local smoke, role evals, independent evidence, cost/context, and owner approval (`intake.promote_requires`) are **attested** with typed state and a field-specific `evidence_kind`. Each live field is `attested` (dated supporting source whose semantics match), `not_applicable` (closed `structural_code` plus rationale), or, for exact ids on `intake.legacy_waiver_routes` only, `waived` (`existing_operational_state`, date, short expiry). `missing` cannot promote. New candidates may never use a legacy waiver and cannot self-qualify by mutating host/provider/evidence. `official_id` requires a direct official https URL on that family's allowed domain list; local JSON paths, example.com, and cross-family domains are not sufficient. Record `local_access_smoke.signal` as `direct_invocation` or `standing_provider`. Do not invent new smokes; standing operational seats stay labeled standing. Review E remains a local placeholder until a named candidate plus official source exists.
5. Same-harness receipts are the path to promoting an external/operational prior into a measured role ranking. Do not label a quality row `local_same_harness` or `confidence: high` unless a same-role local receipt exists and is pointed at from the row `source`. Other bases need a direct independent URL, vendor URL, or an exact code-approved structured operational config binding the role/route/model, and cap at medium/low. Arbitrary prose files do not qualify. Before claiming realized token-efficiency savings for context scouting, evidence audit, or model-evaluation admin, commit before/after token receipts (`token-eff-1` or equivalent). The architecture receipt is not that evidence.
6. `python3 bin/model-registry.py validate && python3 bin/model-registry.py write-matrix`
7. `python3 bin/doctor.py && python3 bin/smoketest.py`
8. Freshness uses the actual current date, not frozen `registry.as_of`. Pass `--as-of YYYY-MM-DD` to freeze the clock in tests. If evidence or attestations are older than `freshness_days` (90), in the future, missing, mismatched, semantically contradictory, or a waiver is expired, validation fails closed. Do not hand-edit `generated/model-matrix.md`.
9. Never copy vendor blog numbers into `prowess` as if they were this repo's eval.

Machine-readable sibling: `generated/model-matrix.md`.
