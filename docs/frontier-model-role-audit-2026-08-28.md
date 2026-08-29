# Frontier model / role audit

**Date:** 2026-08-28
**Cutoff:** 2026-08-28
**Scope:** Current general-purpose text/vision/agentic/coding models plausibly useful to Magnet Baron orchestration. This is a scoped lab census, not an unbounded claim of every model in existence.
**Excluded from routing (and from this census as candidates):** media-only, embedding, moderation, audio-only, and invitation-only offerings (examples: Gemini image-only / Nano Banana, Gemini Live Translate/TTS, Kimi-Audio).
**Method:** official catalogs for identity/availability; independent measurements for ranking; local CLI/harness smoke or standing operational signal for route state. Vendor benchmarks are labeled self-reported. Harness and effort differences prevent naive score comparison. A single global leaderboard is invalid.

This document is evidence, not an operational contract. Routing is `config/model-registry.json` + `config/providers.json` + `bin/resolve-route.py`. Rank never grants tools, credentials, write access, publish authority, or data access. Unknown, catalog-only, auth-blocked, incubation, and unwired routes fail closed.

## Limitations

- Local access was sampled on 2026-08-28.
  - **Direct invocation in this audit:** a live `teamclaude run -- --model claude-opus-5` call resolved to canonical `claude-opus-5`, first-party, 1M context.
  - **CLI listings, not invocations:** `gpt --models` listed `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.3-codex-spark`. `grok models` listed `grok-4.6` and `grok-4.5` (cached authenticated registry readable; settings refresh produced network warnings). `teamclaude status` listed usable Opus and Fable on at least one account.
  - **Not directly invoked in this audit:** Opus 4.8. It is cataloged as the intended time-bounded compatibility fallback and is `catalog_verified` (non-resolvable) until a direct smoke receipt exists.
  - Direct `claude` without teamclaude was auth-blocked.
- Pre-existing operational provider routes (Codex Sol/Terra/Luna, Grok Build, Cursor Grok, Grok Bot Review D / Heat Map, Fable architecture seat) stay `live_verified` on the independent standing-provider signal in `providers.json`, with evidence wording that distinguishes a listing from an invocation.
- Independent anchors are Artificial Analysis pages dated in the 2026-08-28 evidence packet. They are not this repo's eval harness. Effort (max / high / xhigh) is not comparable across labs. Descending ranks below are evidence-bounded and role/harness-specific, not a universal ordering.
- Fable's public Intelligence Index 62 includes a documented Opus fallback, so it is not independent family evidence.
- GLM 5.3 Flash (released 2026-08-26) is vendor-heavy; it is cataloged in incubation and is not routable. Cost/task is an efficiency claim, not a quality rank.
- Unwired models have no local smoke. Public availability does not create a connector, quota bucket, or host.
- No secrets, live Shopify Admin, or customer data were used.
- Prior-branch `BullshitBench` numbers (0.94 / 0.41) are **not** treated as facts: no source URL, fixture, receipt, run date, harness, or sample size was committed. They are not carried forward.

## Opus 5 reassessment

Anthropic released Opus 5 on 2026-07-24 at the same $5/$25 per MTok list price as 4.8 and presents it as the everyday default. Artificial Analysis ranks Opus 5 max first overall (Intelligence Index 63, $2.34/task). Local teamclaude smoke verified the official id.

That supports migrating the Anthropic **review/judgment** seat from 4.8 to 5. It does **not** support making Opus a daily bulk implementer. Scarce-seat, independence, and legwork boundaries stay.

Opus 4.8 remains the intended time-bounded compatibility fallback (`fallback_until` 2026-12-31). It is not in `review_order`. In this audit it was not directly invoked, so its route is `catalog_verified` and fails closed until a smoke receipt exists.

## Fable 5 placement

Fable 5 stays a distinct rare highest-capability / long-horizon escalation:

- same Anthropic family as Opus — never a cross-family pair
- out of the gating order (Opus 5 → Codex Sol → Review E if wired)
- not the default Anthropic judgment seat, because Opus 5 is currently stronger and more efficient for normal review
- public Fable measurements can be contaminated by safety fallback to Opus

No unaudited historical detection score is used as the rationale. Rankings grant no authority.

## Model census (2026-08-28)

Labs in scope: OpenAI, Anthropic, xAI, Google, Moonshot, Z.AI, Alibaba, DeepSeek, Meta, Review E / open-weight.

Live-verified (may resolve). Evidence kind is exact:

| Route | Model | Host | Evidence |
|-------|-------|------|----------|
| `opus-5-teamclaude` | claude-opus-5 | teamclaude | **direct live smoke** of `claude-opus-5` |
| `fable-5-teamclaude` | claude-fable-5 | teamclaude | teamclaude **status listing** of a usable Fable route; standing architecture provider |
| `gpt-5.6-sol-codex` | gpt-5.6-sol | gpt wrapper | `gpt --models` **listing**; standing Codex Sol provider |
| `gpt-5.6-terra-codex` | gpt-5.6-terra | gpt wrapper | `gpt --models` **listing**; standing Codex Terra provider |
| `gpt-5.6-luna-codex` | gpt-5.6-luna | gpt wrapper | `gpt --models` **listing**; standing Codex Luna provider |
| `grok-4.6-build` | grok-4.6 | grok CLI | `grok models` **listing**; standing Grok Build implementer |
| `grok-4.6-cursor` | grok-4.6 | Cursor | standing first-party Cursor pool provider |
| `grok-bot-visual-qa` | grok-4.6 (app) | Grok Bot | standing Review D provider |
| `grok-bot-heat-map` | grok-4.6 (app) | Grok Bot | standing Heat Map provider |

Catalog-verified (listed or documented; does **not** resolve): gpt-5.5, gpt-5.4, gpt-5.4-mini, gpt-5.3-codex-spark, grok-4.5, **Opus 4.8** (intended fallback; no direct smoke in this audit).

Auth-blocked: `opus-5-direct-claude` (bare `claude` without teamclaude).

Unwired current candidates (cataloged, non-routable unless later wired and verified):

- Google: Gemini 3.7 Flash, 3.6 Flash, 3.5 Flash, 3.5 Flash-Lite, 3.1 Flash-Lite, 3.1 Pro Preview, Gemini 3 Flash Preview
- Moonshot: Kimi K3, K2.7 Code, K2.6
- DeepSeek: V4 Pro and V4 Flash as distinct models (no ambiguous bare `deepseek-v4`)
- Meta: Muse Spark 1.2 (model) and Muse Code (agent product) as distinct candidates
- Z.AI: GLM 5.3 Flash (incubation), GLM 5.2
- Alibaba: Qwen 3.8 Max
- Review E / Fireworks independence slot

Official catalog URLs used for identity:

- OpenAI: https://developers.openai.com/api/docs/models · https://openai.com/index/gpt-5-6/
- Anthropic: https://platform.claude.com/docs/en/about-claude/models/choosing-a-model · https://www.anthropic.com/news/claude-opus-5 · https://www.anthropic.com/news/claude-fable-5-mythos-5
- xAI: https://docs.x.ai/developers/grok-4-6 · https://docs.x.ai/developers/pricing
- Google: https://ai.google.dev/gemini-api/docs/models
- Moonshot: https://platform.kimi.ai/
- Z.AI: https://z.ai/blog/glm-5.3-flash · https://z.ai/blog/glm-5.2
- Meta: https://ai.meta.com/llama/
- Alibaba: https://www.alibabagroup.com/en-US/document-2021044032125272064
- DeepSeek: https://api-docs.deepseek.com/news/news260813/

Independent anchors (not a global leaderboard; harness-specific):

| Model | Harness | Index | USD/task | Label |
|-------|---------|------:|--------:|-------|
| claude-opus-5 | max | 63 | 2.34 | independent |
| claude-fable-5 | max | 62 | 3.14 | independent, Opus-fallback caveat |
| grok-4.6 | high | 61 | 0.94 | independent; high beat xhigh in that run |
| kimi-k3 | max | 60 | 0.84 | independent; verbose; not role-comparable vs Opus 5 |
| gpt-5.6-sol | xhigh | 59 | 0.67 | independent; OpenAI also reports Coding Agent Index 80 for Sol / 77.4 for Terra (vendor) |
| qwen-3.8-max | max | 58 | 0.91 | independent; very verbose |
| glm-5.3-flash | reported | 57 | 0.045 | vendor_self_reported; efficiency, not quality |
| glm-5.2 | max | 53 | 0.44 | independent |

## Role recommendations

Quality rank and selection priority are separate. A scarce top model can rank first on quality while a cheaper live route remains the default. Quality is performance evidence for that role, not price. Cost/token efficiency is selection or an explicit `efficiency` field. Descending ranks are evidence-bounded and role/harness-specific.

| Role | Selection default (live) | Quality notes | Why |
|------|--------------------------|---------------|-----|
| **dispatch** | Luna (routine) / Terra (high-context). Authority remains `entrypoints.json` (Opus 5 here). | Terra > Opus 5 > Luna | Dispatch is a role and authority boundary, not a prize. |
| **context_scouting** | Luna, then Grok 4.6 | Live extract/compress quality: Luna > Grok. GLM 5.3 Flash is an **efficiency** incubation candidate, not quality #1. | Cheap extract/compress before expensive seats. **Added** because it reduces expensive context. |
| **research_synthesis** | Grok 4.6; Terra if the packet is Google MCP | Opus 5 > Sol > Grok. Kimi K3 is a **low-confidence incubation** candidate, not ranked above Opus 5. | Do not invent Google metrics. A lower global index plus long context is not comparable role evidence. |
| **implementation** | Grok 4.6 high | Sol/Opus may rank higher on some coding metrics; too scarce | Preserves independent review lanes. Active implementation default remains Grok 4.6 high. |
| **architecture_spec_critique** | Opus 5; Fable on explicit long-horizon escalation | Fable first on long-horizon breadth quality; same family | Never a cross-family pair. |
| **code_review** | Opus 5 then Sol (families must differ) | Opus 5 > Sol > Fable (non-gate) | Operational review pair is Opus 5 + GPT-5.6 Sol. |
| **mcp_volume** | Terra | Terra is the only live connector-bearing route. Gemini Flash variants are unwired candidates. GLM Flash is efficiency, not quality. | Connector presence required. |
| **mcp_judgment** | Sol, else Opus 5 | Same two live judgment seats | Code-review risk gate wins Sol the same week. |
| **visual_qa** | Grok Bot Review D | Only live preview walker | Never Admin/SimGym. |
| **evidence_audit** | Opus 5 / Sol | Catches invented metrics | **Added** because it catches defects before they propagate. |
| **model_evaluation_admin** | Opus 5 (owner-gated) | Does not auto-promote | Scores never wire routes. |

## Missing roles considered and not added

- Dedicated “SEO writer” or “Shopify publisher” model roles — already covered by implement + owner publish gates; a new model role would look like a permission grant.
- Second Visual QA model — no second live harness.
- Latency-optimized “realtime” role — latency has weight 0 by policy.

## Rankings vs authority

- Exactly one user-assigned dispatcher (`entrypoints.dispatcher.provider`).
- Any entry surface may intake and hand over.
- Cross-family selection mechanically rejects two routes from the same family. Operational pair: Opus 5 + GPT-5.6 Sol.
- Fable is same-family, rare architecture/long-horizon escalation only.
- Unknown, catalog-only, auth-blocked, incubation, and unwired availability fails closed.
- A catalog entry is not a usable route.
- `bin/model-registry.py resolve` returns `authority_grants: false`.
- Rankings grant no authority or connectors.

## Migration (this change-set)

1. Merged the config-driven engine (`config/*.json`, `bin/resolve-route.py`, `bin/doctor.py`, `bin/smoketest.py`) with main's selective skill routers (`skills/`) and idle-mini QA policy.
2. Removed the redundant legacy role-registry directory. Role *loading* remains `config/roles.json` + `bin/generate-roles.py` (not coupled to model releases). Model identity lives only in `config/model-registry.json`.
3. Replaced the Opus 5 hard ban with Opus 5 as the Anthropic gate. Kept Opus 4.8 as a documented compatibility fallback; this audit did not smoke it, so it is `catalog_verified` and fails closed.
4. Bound each runtime provider to a catalog route. `review_order` is `opus-5 → codex-sol → review-e`, filtered to `live_verified`. Fable is not first and is not in that order.
5. Added synthetic eval cases and receipt scoring. New-model intake is two-phase.
6. Follow-up: completed the scoped census, split DeepSeek V4 Pro/Flash and Muse Spark/Muse Code, moved cost claims into `efficiency`, and demoted Kimi K3 below Opus 5 for research synthesis.

## Future audit instructions

1. Re-run local smokes: `gpt --models`, `grok models`, `teamclaude status`, one `teamclaude run -- --model claude-opus-5`. Record the date on each live route. A listing is not an invocation; promote Opus 4.8 only after a direct smoke.
2. Refresh independent anchors from the same harness pages; do not mix effort levels into one table of "winners." Do not rank on price in the quality column.
3. Score `model-evals/cases.json` receipts with `bin/model-eval.py`. Latency may be recorded; it must not decide rank.
4. Catalog new models as `unwired` or `catalog_verified`. Promote to `live_verified` only after official-id, local smoke, role evals, independent evidence, cost/context, and owner approval (`intake.promote_requires`).
5. `python3 bin/model-registry.py validate && python3 bin/model-registry.py write-matrix`
6. `python3 bin/doctor.py && python3 bin/smoketest.py`
7. If evidence is older than `freshness_days` (90) on a live_verified route, validation fails. Do not hand-edit `generated/model-matrix.md`.
8. Never copy vendor blog numbers into `prowess` as if they were this repo's eval.

Machine-readable sibling: `generated/model-matrix.md`.
