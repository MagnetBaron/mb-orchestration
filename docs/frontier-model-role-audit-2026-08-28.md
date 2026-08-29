# Frontier model / role audit

**Date:** 2026-08-28
**Scope:** Magnet Baron orchestration model catalog, per-role rankings, and routing.
**Method:** official catalogs for identity/availability; independent measurements for ranking; local CLI/harness smoke for route state. Vendor benchmarks are labeled self-reported. Harness and effort differences prevent naive score comparison. A single global leaderboard is invalid.

This document is evidence, not an operational contract. Routing is `config/model-registry.json` + `config/providers.json` + `bin/resolve-route.py`. Rank never grants tools, credentials, write access, publish authority, or data access.

## Limitations

- Local access was sampled on 2026-08-28. `gpt --models` and `grok models` were readable; Grok settings refresh produced network warnings but the cached authenticated registry listed `grok-4.6` and `grok-4.5`. `teamclaude` showed usable Opus and Fable on at least one account. A live `teamclaude` invocation of `claude-opus-5` resolved to canonical `claude-opus-5`, first-party, 1M context. Direct `claude` without teamclaude was auth-blocked.
- Independent anchors are Artificial Analysis pages dated in the 2026-08-28 evidence packet. They are not this repo's eval harness. Effort (max / high / xhigh) is not comparable across labs.
- Fable's public Intelligence Index 62 includes a documented Opus fallback, so it is not independent family evidence.
- GLM 5.3 Flash (released 2026-08-26) is vendor-heavy; it is cataloged in incubation and is not routable.
- Unwired models have no local smoke. Public availability does not create a connector, quota bucket, or host.
- No secrets, live Shopify Admin, or customer data were used.
- Prior-branch `BullshitBench` numbers (0.94 / 0.41) are **not** treated as facts: no source URL, fixture, receipt, run date, harness, or sample size was committed. They are not carried forward.

## Opus 5 reassessment

Anthropic released Opus 5 on 2026-07-24 at the same $5/$25 per MTok list price as 4.8 and presents it as the everyday default. Artificial Analysis ranks Opus 5 max first overall (Intelligence Index 63, $2.34/task). Local teamclaude smoke verified the official id.

That supports migrating the Anthropic **review/judgment** seat from 4.8 to 5. It does **not** support making Opus a daily bulk implementer. Scarce-seat, independence, and legwork boundaries stay.

Opus 4.8 remains a time-bounded compatibility fallback (`fallback_until` 2026-12-31) while the id is genuinely available. It is not in `review_order`.

## Fable 5 placement

Fable 5 stays a distinct rare highest-capability / long-horizon escalation:

- same Anthropic family as Opus — never a cross-family pair
- out of the gating order
- not the default Anthropic judgment seat, because Opus 5 is currently stronger and more efficient for normal review
- public Fable measurements can be contaminated by safety fallback to Opus

No unaudited historical detection score is used as the rationale.

## Model census (2026-08-28)

Live-verified (may resolve):

| Route | Model | Host | Evidence |
|-------|-------|------|----------|
| `opus-5-teamclaude` | claude-opus-5 | teamclaude | local smoke, 1M context |
| `opus-4.8-teamclaude` | claude-opus-4-8 | teamclaude | fallback, still served |
| `fable-5-teamclaude` | claude-fable-5 | teamclaude | teamclaude status |
| `gpt-5.6-sol-codex` | gpt-5.6-sol | gpt wrapper | `gpt --models` |
| `gpt-5.6-terra-codex` | gpt-5.6-terra | gpt wrapper | `gpt --models` |
| `gpt-5.6-luna-codex` | gpt-5.6-luna | gpt wrapper | `gpt --models` |
| `grok-4.6-build` | grok-4.6 | grok CLI | `grok models` |
| `grok-4.6-cursor` | grok-4.6 | Cursor | first-party pool |
| `grok-bot-visual-qa` | grok-4.6 (app) | Grok Bot | standing Review D |
| `grok-bot-heat-map` | grok-4.6 (app) | Grok Bot | standing Heat Map |

Catalog-verified (listed locally, not a seat): gpt-5.5, gpt-5.4, gpt-5.4-mini, gpt-5.3-codex-spark, grok-4.5.

Auth-blocked: `opus-5-direct-claude` (bare `claude` without teamclaude).

Unwired candidates: Gemini 3.7 Flash, Kimi K3, GLM 5.3 Flash (incubation), GLM 5.2, Qwen 3.8 Max, DeepSeek V4, Muse Spark 1.2, Review E / Fireworks.

Excluded from routing: media-only, embedding, moderation, audio-only, invitation-only models.

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
| kimi-k3 | max | 60 | 0.84 | independent; verbose |
| gpt-5.6-sol | xhigh | 59 | 0.67 | independent; OpenAI also reports Coding Agent Index 80 for Sol / 77.4 for Terra (vendor) |
| qwen-3.8-max | max | 58 | 0.91 | independent; very verbose |
| glm-5.3-flash | reported | 57 | 0.045 | vendor_self_reported |
| glm-5.2 | max | 53 | 0.44 | independent |

## Role recommendations

Quality rank and selection priority are separate. A scarce top model can rank first on quality while a cheaper live route remains the default.

| Role | Selection default (live) | Quality notes | Why |
|------|--------------------------|---------------|-----|
| **dispatch** | Luna (routine) / Terra (high-context). Authority remains `entrypoints.json` (Opus 5 here). | Terra > Opus 5 > Luna | Dispatch is a role and authority boundary, not a prize. |
| **context_scouting** | Luna, then Grok 4.6 | GLM 5.3 Flash ranks high on cost but is unwired/incubating | Cheap extract/compress before expensive seats. **Added** because it reduces expensive context. |
| **research_synthesis** | Grok 4.6; Terra if the packet is Google MCP | Kimi K3 quality candidate (verbose, unwired) | Do not invent Google metrics. |
| **implementation** | Grok 4.6 | Sol/Opus may rank higher on some coding metrics; too scarce | Preserves independent review lanes. |
| **architecture_spec_critique** | Opus 5; Fable on explicit long-horizon escalation | Fable first on quality for breadth | Same family; never a cross-family pair. |
| **code_review** | Opus 5 then Sol (families must differ) | Opus 5 > Sol > Fable (non-gate) | Operational review pair. |
| **mcp_volume** | Terra | Gemini Flash / GLM Flash are candidates without connectors | Connector presence required. |
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
- Cross-family selection mechanically rejects two routes from the same family.
- Unknown availability fails closed.
- A catalog entry is not a usable route.
- `bin/model-registry.py resolve` returns `authority_grants: false`.

## Migration (this change-set)

1. Merged the config-driven engine (`config/*.json`, `bin/resolve-route.py`, `bin/doctor.py`, `bin/smoketest.py`) with main's selective skill routers (`skills/`) and idle-mini QA policy.
2. Removed the redundant legacy role-registry directory. Role *loading* remains `config/roles.json` + `bin/generate-roles.py` (not coupled to model releases). Model identity lives only in `config/model-registry.json`.
3. Replaced the Opus 5 hard ban with Opus 5 as the Anthropic gate. Kept Opus 4.8 as a compatibility fallback.
4. Bound each runtime provider to a catalog route. `review_order` is `opus-5 → codex-sol → review-e`, filtered to `live_verified`.
5. Added synthetic eval cases and receipt scoring. New-model intake is two-phase.

## Future audit instructions

1. Re-run local smokes: `gpt --models`, `grok models`, `teamclaude status`, one `teamclaude run -- --model claude-opus-5`. Record the date on each live route.
2. Refresh independent anchors from the same harness pages; do not mix effort levels into one table of "winners."
3. Score `model-evals/cases.json` receipts with `bin/model-eval.py`. Latency may be recorded; it must not decide rank.
4. Catalog new models as `unwired` or `catalog_verified`. Promote to `live_verified` only after official-id, local smoke, role evals, independent evidence, cost/context, and owner approval (`intake.promote_requires`).
5. `python3 bin/model-registry.py validate && python3 bin/model-registry.py write-matrix`
6. `python3 bin/doctor.py && python3 bin/smoketest.py`
7. If evidence is older than `freshness_days` (90) on a live_verified route, validation fails. Do not hand-edit `generated/model-matrix.md`.
8. Never copy vendor blog numbers into `prowess` as if they were this repo's eval.

Machine-readable sibling: `generated/model-matrix.md`.
