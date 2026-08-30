# Model matrix

Generated from `config/model-registry.json` as of 2026-08-28.
Deterministic. Do not hand-edit; run `python3 bin/model-registry.py write-matrix`.

A catalog entry is not a usable route. Only `live_verified` routes resolve.
The public resolver API is fail-closed: every candidate is filtered by `route_is_live` (missing/stale/future/mismatched/unattested evidence, undeclared family/independence group, or a route-local identity/family/invocation contradiction never returns).
Last-resort coding requires a concrete live provider with `implement`/`ide` and `code` on both the provider and its bound live route; sharing a plan is not enough.
Quality rank is not selection priority. Rank never grants tools or data.
Descending ranks are evidence-bounded and role/harness-specific, not a universal ordering.
live_verified freshness is compared to the current date (or `--as-of`), not frozen `registry.as_of`.
Promotion attestations (`intake.promote_requires`) use typed state: attested, missing, not_applicable, waived.
`attested` requires a field-specific `evidence_kind` and a dated source whose semantics support the requirement; absence language cannot pass.
`not_applicable` requires a closed `structural_code` validated per field and route; free-form rationale cannot establish N/A.
`waived` is a time-bounded legacy/standing-provider migration exception and does not assert the evidence exists.
Legacy waivers are exact route ids on `intake.legacy_waiver_routes` only.
Official vendor URLs are checked against `official_sources.allowed_domains_by_family`.
Quality rows carry an explicit `basis` plus a basis-appropriate evidence pointer. `confidence: high` is only `local_same_harness` with a committed receipt. The only local same-harness role comparison is architecture_spec_critique Opus 5 vs Fable 5.
Token-efficiency of added roles is a hypothesis to measure, not a realized-savings claim.

## Census scope

- as_of: 2026-08-28
- cutoff: 2026-08-28
- scope: Current general-purpose text/vision/agentic/coding models plausibly useful to this orchestration as of 2026-08-28. A scoped lab census, not an unbounded claim of every model in existence.

## Models

| id | family | lab | lifecycle | official ids | official source | placeholder | excluded |
|---|---|---|---|---|---|---|---|
| `claude-fable-5` | anthropic | Anthropic | restricted | claude-fable-5, fable-5 | https://www.anthropic.com/news/claude-fable-5-mythos-5 | no | no |
| `claude-opus-4-8` | anthropic | Anthropic | superseded | claude-opus-4-8, opus-4.8, claude-opus-4.8 | https://platform.claude.com/docs/en/about-claude/models/choosing-a-model | no | no |
| `claude-opus-5` | anthropic | Anthropic | stable | claude-opus-5, opus-5 | https://www.anthropic.com/news/claude-opus-5 | no | no |
| `deepseek-v4-flash` | deepseek | DeepSeek | stable | deepseek-v4-flash | https://api-docs.deepseek.com/news/news260813/ | no | no |
| `deepseek-v4-pro` | deepseek | DeepSeek | stable | deepseek-v4-pro | https://api-docs.deepseek.com/news/news260813/ | no | no |
| `gemini-3-flash-preview` | google | Google | preview | gemini-3-flash-preview | https://ai.google.dev/gemini-api/docs/models | no | no |
| `gemini-3.1-flash-lite` | google | Google | stable | gemini-3.1-flash-lite | https://ai.google.dev/gemini-api/docs/models | no | no |
| `gemini-3.1-pro-preview` | google | Google | preview | gemini-3.1-pro-preview | https://ai.google.dev/gemini-api/docs/models | no | no |
| `gemini-3.5-flash` | google | Google | stable | gemini-3.5-flash | https://ai.google.dev/gemini-api/docs/models | no | no |
| `gemini-3.5-flash-lite` | google | Google | stable | gemini-3.5-flash-lite | https://ai.google.dev/gemini-api/docs/models | no | no |
| `gemini-3.6-flash` | google | Google | stable | gemini-3.6-flash | https://ai.google.dev/gemini-api/docs/models | no | no |
| `gemini-3.7-flash` | google | Google | preview | gemini-3.7-flash | https://ai.google.dev/gemini-api/docs/models | no | no |
| `glm-5.2` | zhipu | Z.AI | stable | glm-5.2, glm-5-2 | https://z.ai/blog/glm-5.2 | no | no |
| `glm-5.3-flash` | zhipu | Z.AI | preview | glm-5.3-flash | https://z.ai/blog/glm-5.3-flash | no | no |
| `gpt-5.3-codex-spark` | openai | OpenAI | stable | gpt-5.3-codex-spark | https://developers.openai.com/api/docs/models | no | no |
| `gpt-5.4` | openai | OpenAI | stable | gpt-5.4 | https://developers.openai.com/api/docs/models | no | no |
| `gpt-5.4-mini` | openai | OpenAI | stable | gpt-5.4-mini | https://developers.openai.com/api/docs/models | no | no |
| `gpt-5.5` | openai | OpenAI | stable | gpt-5.5 | https://developers.openai.com/api/docs/models | no | no |
| `gpt-5.6-luna` | openai | OpenAI | stable | gpt-5.6-luna | https://openai.com/index/gpt-5-6/ | no | no |
| `gpt-5.6-sol` | openai | OpenAI | stable | gpt-5.6-sol | https://openai.com/index/gpt-5-6/ | no | no |
| `gpt-5.6-terra` | openai | OpenAI | stable | gpt-5.6-terra | https://openai.com/index/gpt-5-6/ | no | no |
| `grok-4.5` | xai | xAI | superseded | grok-4.5 | https://docs.x.ai/developers/pricing | no | no |
| `grok-4.6` | xai | xAI | stable | grok-4.6 | https://docs.x.ai/developers/grok-4-6 | no | no |
| `kimi-k2.6` | moonshot | Moonshot | superseded | kimi-k2.6 | https://platform.kimi.ai/ | no | no |
| `kimi-k2.7-code` | moonshot | Moonshot | stable | kimi-k2.7-code, kimi-for-coding | https://platform.kimi.ai/ | no | no |
| `kimi-k3` | moonshot | Moonshot | stable | kimi-k3, kimi-k3-max | https://platform.kimi.ai/ | no | no |
| `muse-code` | meta | Meta | preview | muse-code | https://ai.meta.com/llama/ | no | no |
| `muse-spark-1.2` | meta | Meta | preview | muse-spark-1.2 | https://ai.meta.com/llama/ | no | no |
| `open-weight-review-e` | open-weight | local-placeholder | restricted | review-e | — | yes | no |
| `qwen-3.8-max` | alibaba | Alibaba | stable | qwen-3.8-max, qwen3-8-max | https://www.alibabagroup.com/en-US/document-2021044032125272064 | no | no |

## Routes

| route | model | state | lifecycle | host | harness | invocation | evidence | signal | provider |
|---|---|---|---|---|---|---|---|---|---|
| `deepseek-v4-flash-unwired` | `deepseek-v4-flash` | unwired | stable | none | none | `deepseek-v4-flash` | 2026-08-28 vendor_self_reported | — | — |
| `deepseek-v4-pro-unwired` | `deepseek-v4-pro` | unwired | stable | none | none | `deepseek-v4-pro` | 2026-08-28 vendor_self_reported | — | — |
| `fable-5-teamclaude` | `claude-fable-5` | live_verified | restricted | teamclaude | claude-cli | `claude-fable-5` | 2026-08-28 local_smoke | direct_invocation | fable-5 |
| `gemini-3-flash-preview-unwired` | `gemini-3-flash-preview` | unwired | preview | none | none | `gemini-3-flash-preview` | 2026-08-28 vendor_self_reported | — | — |
| `gemini-3.1-flash-lite-unwired` | `gemini-3.1-flash-lite` | unwired | stable | none | none | `gemini-3.1-flash-lite` | 2026-08-28 vendor_self_reported | — | — |
| `gemini-3.1-pro-preview-unwired` | `gemini-3.1-pro-preview` | unwired | preview | none | none | `gemini-3.1-pro-preview` | 2026-08-28 vendor_self_reported | — | — |
| `gemini-3.5-flash-lite-unwired` | `gemini-3.5-flash-lite` | unwired | stable | none | none | `gemini-3.5-flash-lite` | 2026-08-28 vendor_self_reported | — | — |
| `gemini-3.5-flash-unwired` | `gemini-3.5-flash` | unwired | stable | none | none | `gemini-3.5-flash` | 2026-08-28 vendor_self_reported | — | — |
| `gemini-3.6-flash-unwired` | `gemini-3.6-flash` | unwired | stable | none | none | `gemini-3.6-flash` | 2026-08-28 vendor_self_reported | — | — |
| `gemini-3.7-flash-unwired` | `gemini-3.7-flash` | unwired | preview | none | none | `gemini-3.7-flash` | 2026-08-28 vendor_self_reported | — | — |
| `glm-5.2-unwired` | `glm-5.2` | unwired | stable | none | none | `glm-5.2` | 2026-08-28 independent_benchmark | — | — |
| `glm-5.3-flash-unwired` | `glm-5.3-flash` | unwired | preview | none | none | `glm-5.3-flash` | 2026-08-28 vendor_self_reported | — | — |
| `gpt-5.3-codex-spark-codex` | `gpt-5.3-codex-spark` | catalog_verified | stable | codex | gpt-wrapper | `gpt-5.3-codex-spark` | 2026-08-28 cli_listing | standing_provider | — |
| `gpt-5.4-codex` | `gpt-5.4` | catalog_verified | stable | codex | gpt-wrapper | `gpt-5.4` | 2026-08-28 cli_listing | standing_provider | — |
| `gpt-5.4-mini-codex` | `gpt-5.4-mini` | catalog_verified | stable | codex | gpt-wrapper | `gpt-5.4-mini` | 2026-08-28 cli_listing | standing_provider | — |
| `gpt-5.5-codex` | `gpt-5.5` | catalog_verified | stable | codex | gpt-wrapper | `gpt-5.5` | 2026-08-28 cli_listing | standing_provider | — |
| `gpt-5.6-luna-codex` | `gpt-5.6-luna` | live_verified | stable | codex | gpt-wrapper | `gpt-5.6-luna` | 2026-08-28 cli_listing | standing_provider | codex-luna |
| `gpt-5.6-sol-codex` | `gpt-5.6-sol` | live_verified | stable | codex | gpt-wrapper | `gpt-5.6-sol` | 2026-08-28 cli_listing | standing_provider | codex-sol |
| `gpt-5.6-terra-codex` | `gpt-5.6-terra` | live_verified | stable | codex | gpt-wrapper | `gpt-5.6-terra` | 2026-08-28 cli_listing | standing_provider | codex-terra |
| `grok-4.5-cli` | `grok-4.5` | catalog_verified | superseded | grok-cli | grok | `grok-4.5` | 2026-08-28 cli_listing | standing_provider | — |
| `grok-4.6-build` | `grok-4.6` | live_verified | stable | grok-cli | grok | `grok-4.6` | 2026-08-28 cli_listing | standing_provider | grok-build |
| `grok-4.6-cursor` | `grok-4.6` | live_verified | stable | cursor | cursor-agent | `grok-4.6` | 2026-08-28 owner_eval | standing_provider | cursor-grok |
| `grok-bot-heat-map` | `grok-4.6` | live_verified | stable | grok-bot | grok-bot-app | `heat-map` | 2026-08-28 owner_eval | standing_provider | grok-bot-heat-map |
| `grok-bot-visual-qa` | `grok-4.6` | live_verified | stable | grok-bot | grok-bot-app | `website-visual-qa` | 2026-08-28 owner_eval | standing_provider | grok-bot-review-d |
| `kimi-k2.6-unwired` | `kimi-k2.6` | unwired | superseded | none | none | `kimi-k2.6` | 2026-08-28 vendor_self_reported | — | — |
| `kimi-k2.7-code-unwired` | `kimi-k2.7-code` | unwired | stable | none | none | `kimi-k2.7-code` | 2026-08-28 vendor_self_reported | — | — |
| `kimi-k3-unwired` | `kimi-k3` | unwired | stable | none | none | `kimi-k3` | 2026-08-28 independent_benchmark | — | — |
| `muse-code-unwired` | `muse-code` | unwired | preview | none | none | `muse-code` | 2026-08-28 vendor_self_reported | — | — |
| `muse-spark-1.2-unwired` | `muse-spark-1.2` | unwired | preview | none | none | `muse-spark-1.2` | 2026-08-28 vendor_self_reported | — | — |
| `opus-4.8-teamclaude` | `claude-opus-4-8` | live_verified | superseded | teamclaude | claude-cli | `claude-opus-4-8` | 2026-08-28 local_smoke | direct_invocation | opus-4.8 |
| `opus-5-direct-claude` | `claude-opus-5` | auth_blocked | stable | claude-cli-direct | claude-cli | `claude-opus-5` | 2026-08-28 local_smoke | direct_invocation | — |
| `opus-5-teamclaude` | `claude-opus-5` | live_verified | stable | teamclaude | claude-cli | `claude-opus-5` | 2026-08-28 local_smoke | direct_invocation | opus-5 |
| `qwen-3.8-max-unwired` | `qwen-3.8-max` | unwired | stable | none | none | `qwen-3.8-max` | 2026-08-28 independent_benchmark | — | — |
| `review-e-fireworks` | `open-weight-review-e` | unwired | restricted | fireworks | http | `review-e` | 2026-08-28 none | — | review-e |

## Live-route attestations

Typed promotion state. `attested` means a field-specific `evidence_kind` plus a dated supporting source whose semantics match the requirement. `waived` is a time-bounded legacy/standing-provider migration exception (exact route id on `intake.legacy_waiver_routes`) and does **not** assert that the evidence exists. `not_applicable` requires a closed `structural_code` for the field and route; it is never a synonym for missing. `missing` cannot be `live_verified`.

Evaluation: `direct` = `local_access_smoke` attested with `direct_invocation`; `standing` = standing-provider signal. `+grandfathered` means at least one field is `waived`. Cell extras are `evidence_kind` or `structural_code`.

| route | evaluation | official_id | local_access_smoke | role_evals | independent_evidence | cost_context | owner_approval | waivers expire |
|---|---|---|---|---|---|---|---|---|
| `fable-5-teamclaude` | direct+grandfathered | attested/official_vendor_release | attested/direct_invocation | attested/normalized_receipt | attested/independent_benchmark | attested/independent_pricing | waived | 2026-11-26 |
| `gpt-5.6-luna-codex` | standing+grandfathered | attested/official_vendor_release | attested/standing_provider | waived | waived | waived | waived | 2026-11-26 |
| `gpt-5.6-sol-codex` | standing+grandfathered | attested/official_vendor_release | attested/standing_provider | waived | attested/independent_benchmark | attested/independent_pricing | waived | 2026-11-26 |
| `gpt-5.6-terra-codex` | standing+grandfathered | attested/official_vendor_release | attested/standing_provider | waived | waived | waived | waived | 2026-11-26 |
| `grok-4.6-build` | standing+grandfathered | attested/official_vendor_catalog | attested/standing_provider | waived | attested/independent_benchmark | attested/independent_pricing | waived | 2026-11-26 |
| `grok-4.6-cursor` | standing+grandfathered | attested/official_vendor_catalog | attested/standing_provider | waived | attested/independent_benchmark | attested/independent_pricing | waived | 2026-11-26 |
| `grok-bot-heat-map` | standing+grandfathered | attested/official_vendor_catalog | attested/standing_provider | not_applicable/app_only_analytics_input_not_text_suite | attested/independent_benchmark | waived | waived | 2026-11-26 |
| `grok-bot-visual-qa` | standing+grandfathered | attested/official_vendor_catalog | attested/standing_provider | not_applicable/app_only_pixel_walk_not_text_suite | attested/independent_benchmark | waived | waived | 2026-11-26 |
| `opus-4.8-teamclaude` | direct+grandfathered | attested/official_vendor_catalog | attested/direct_invocation | not_applicable/compatibility_fallback_not_ranked | not_applicable/compatibility_fallback_not_ranked | waived | waived | 2026-11-26 |
| `opus-5-teamclaude` | direct+grandfathered | attested/official_vendor_release | attested/direct_invocation | attested/normalized_receipt | attested/independent_benchmark | attested/official_pricing | waived | 2026-11-26 |

## Official vendor sources

Direct official https URLs. Family coverage and `allowed_domains_by_family` are mechanically validated. Local JSON paths are not official sources. Review E / `open-weight-review-e` is a local placeholder outside the census.

| family | allowed domains | covers | urls |
|---|---|---|---|
| `alibaba` | `alibabagroup.com`, `alibabacloud.com` | `qwen-3.8-max` | https://www.alibabagroup.com/en-US/document-2021044032125272064 |
| `anthropic` | `anthropic.com`, `claude.com` | `claude-fable-5`, `claude-opus-4-8`, `claude-opus-5` | https://platform.claude.com/docs/en/about-claude/models/choosing-a-model · https://www.anthropic.com/news/claude-opus-5 · https://www.anthropic.com/news/claude-fable-5-mythos-5 |
| `deepseek` | `deepseek.com` | `deepseek-v4-flash`, `deepseek-v4-pro` | https://api-docs.deepseek.com/news/news260813/ |
| `google` | `ai.google.dev` | `gemini-3-flash-preview`, `gemini-3.1-flash-lite`, `gemini-3.1-pro-preview`, `gemini-3.5-flash`, `gemini-3.5-flash-lite`, `gemini-3.6-flash`, `gemini-3.7-flash` | https://ai.google.dev/gemini-api/docs/models |
| `meta` | `ai.meta.com`, `meta.com`, `llama.com` | `muse-code`, `muse-spark-1.2` | https://ai.meta.com/llama/ |
| `moonshot` | `kimi.ai`, `moonshot.ai` | `kimi-k2.6`, `kimi-k2.7-code`, `kimi-k3` | https://platform.kimi.ai/ |
| `openai` | `openai.com`, `developers.openai.com` | `gpt-5.3-codex-spark`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.5`, `gpt-5.6-luna`, `gpt-5.6-sol`, `gpt-5.6-terra` | https://developers.openai.com/api/docs/models · https://openai.com/index/gpt-5-6/ |
| `xai` | `x.ai` | `grok-4.5`, `grok-4.6` | https://docs.x.ai/developers/grok-4-6 · https://docs.x.ai/developers/pricing |
| `zhipu` | `z.ai` | `glm-5.2`, `glm-5.3-flash` | https://z.ai/blog/glm-5.3-flash · https://z.ai/blog/glm-5.2 |

Local placeholders (not labs in scope; cannot be promoted or wired until a named candidate plus official source replaces them): `open-weight-review-e`.

## Per-role rankings (selection vs quality)

Quality `basis` is machine-readable. `local_same_harness` is only the committed architecture_spec_critique Opus 5 vs Fable 5 receipt (n=1). `confidence: high` requires that basis plus a committed receipt pointer. Other quality rows are external or operational priors with a basis-appropriate source, not same-role local comparisons.

### `dispatch`

Classify, stamp review, brief, assign. Authority is entrypoints.json, not model rank. Luna/Terra rank for dispatch work quality.

| kind | n | route | confidence | basis | evidence |
|---|---:|---|---|---|---|
| quality | 1 | `gpt-5.6-terra-codex` | medium | operational_prior | config/providers.json |
| quality | 2 | `opus-5-teamclaude` | medium | operational_prior | config/entrypoints.json |
| quality | 3 | `gpt-5.6-luna-codex` | medium | operational_prior | config/providers.json |
| selection | 1 | `gpt-5.6-luna-codex` | high |  |  |
| selection | 2 | `gpt-5.6-terra-codex` | high |  |  |
| selection | 3 | `opus-5-teamclaude` | high |  |  |

### `context_scouting`

Cheap first pass to compress or extract facts before expensive seats. Expected to reduce expensive-seat token use; that is a hypothesis to measure, not a realized-savings claim.

| kind | n | route | confidence | basis | evidence |
|---|---:|---|---|---|---|
| quality | 1 | `gpt-5.6-luna-codex` | medium | operational_prior | config/providers.json |
| quality | 2 | `grok-4.6-build` | medium | operational_prior | config/providers.json |
| selection | 1 | `gpt-5.6-luna-codex` | medium |  |  |
| selection | 2 | `grok-4.6-build` | medium |  |  |
| efficiency | 1 | `glm-5.3-flash-unwired` | low |  |  |
| efficiency | 2 | `gemini-3.5-flash-lite-unwired` | low |  |  |
| efficiency | 3 | `gpt-5.6-luna-codex` | medium |  |  |

### `research_synthesis`

Long-context synthesis from already-fetched packets. Does not invent Google metrics.

| kind | n | route | confidence | basis | evidence |
|---|---:|---|---|---|---|
| quality | 1 | `opus-5-teamclaude` | medium | independent_external_prior | https://artificialanalysis.ai/models/claude-opus-5 |
| quality | 2 | `gpt-5.6-sol-codex` | medium | independent_external_prior | https://artificialanalysis.ai/models/gpt-5-6-sol-xhigh/ |
| quality | 3 | `grok-4.6-build` | medium | operational_prior | config/providers.json |
| quality | 4 | `kimi-k3-unwired` | low | independent_external_prior | https://artificialanalysis.ai/models/kimi-k3 |
| selection | 1 | `grok-4.6-build` | high |  |  |
| selection | 2 | `gpt-5.6-terra-codex` | high |  |  |
| selection | 3 | `opus-5-teamclaude` | medium |  |  |

### `implementation`

Repo/app code in an isolated worktree.

| kind | n | route | confidence | basis | evidence |
|---|---:|---|---|---|---|
| quality | 1 | `gpt-5.6-sol-codex` | medium | vendor_external_prior | https://openai.com/index/gpt-5-6/ |
| quality | 2 | `opus-5-teamclaude` | medium | independent_external_prior | https://artificialanalysis.ai/models/claude-opus-5 |
| quality | 3 | `grok-4.6-build` | medium | operational_prior | config/providers.json |
| quality | 4 | `qwen-3.8-max-unwired` | low | independent_external_prior | https://artificialanalysis.ai/models/qwen3-8-max |
| quality | 5 | `deepseek-v4-pro-unwired` | low | vendor_external_prior | https://api-docs.deepseek.com/news/news260813/ |
| quality | 6 | `kimi-k2.7-code-unwired` | low | vendor_external_prior | https://platform.kimi.ai/ |
| quality | 7 | `muse-spark-1.2-unwired` | low | vendor_external_prior | https://ai.meta.com/llama/ |
| selection | 1 | `grok-4.6-build` | high |  |  |
| selection | 2 | `grok-4.6-cursor` | high |  |  |
| efficiency | 1 | `deepseek-v4-flash-unwired` | low |  |  |
| efficiency | 2 | `grok-4.6-build` | high |  |  |

### `architecture_spec_critique`

Rare long-horizon / spec critique. Opus 5 first at current evidence; Fable is a low-confidence long-horizon escalation candidate. Same family.

| kind | n | route | confidence | basis | evidence |
|---|---:|---|---|---|---|
| quality | 1 | `opus-5-teamclaude` | high | local_same_harness | model-evals/receipts/2026-08-28-architecture-spec-critique.jsonl |
| quality | 2 | `fable-5-teamclaude` | low | local_same_harness | model-evals/receipts/2026-08-28-architecture-spec-critique.jsonl |
| selection | 1 | `opus-5-teamclaude` | high |  |  |
| selection | 2 | `fable-5-teamclaude` | medium |  |  |

### `code_review`

Diff review. Cross-family pair is Opus 5 + Sol. Fable is not a second family.

| kind | n | route | confidence | basis | evidence |
|---|---:|---|---|---|---|
| quality | 1 | `opus-5-teamclaude` | medium | independent_external_prior | https://artificialanalysis.ai/models/claude-opus-5 |
| quality | 2 | `gpt-5.6-sol-codex` | medium | independent_external_prior | https://artificialanalysis.ai/models/gpt-5-6-sol-xhigh/ |
| quality | 3 | `fable-5-teamclaude` | low | independent_external_prior | https://artificialanalysis.ai/models/claude-fable-5/ |
| quality | 4 | `review-e-fireworks` | low | operational_prior | config/providers.json |
| selection | 1 | `opus-5-teamclaude` | high |  |  |
| selection | 2 | `gpt-5.6-sol-codex` | high |  |  |
| selection | 3 | `opus-4.8-teamclaude` | low |  |  |

### `mcp_volume`

High-volume connector fetches. Connector presence is required; public models do not create connectors.

| kind | n | route | confidence | basis | evidence |
|---|---:|---|---|---|---|
| quality | 1 | `gpt-5.6-terra-codex` | medium | operational_prior | config/connectors.json |
| quality | 2 | `gemini-3.7-flash-unwired` | low | vendor_external_prior | https://ai.google.dev/gemini-api/docs/models |
| selection | 1 | `gpt-5.6-terra-codex` | high |  |  |
| selection | 2 | `gpt-5.6-luna-codex` | medium |  |  |
| efficiency | 1 | `glm-5.3-flash-unwired` | low |  |  |
| efficiency | 2 | `gemini-3.5-flash-lite-unwired` | low |  |  |
| efficiency | 3 | `gemini-3.7-flash-unwired` | low |  |  |

### `mcp_judgment`

Interpret already-fetched MCP output. Never row-dump fetch loops.

| kind | n | route | confidence | basis | evidence |
|---|---:|---|---|---|---|
| quality | 1 | `opus-5-teamclaude` | medium | operational_prior | config/providers.json |
| quality | 2 | `gpt-5.6-sol-codex` | medium | operational_prior | config/providers.json |
| selection | 1 | `gpt-5.6-sol-codex` | high |  |  |
| selection | 2 | `opus-5-teamclaude` | high |  |  |

### `visual_qa`

Storefront pixel review of a visitor preview URL.

| kind | n | route | confidence | basis | evidence |
|---|---:|---|---|---|---|
| quality | 1 | `grok-bot-visual-qa` | medium | operational_prior | config/providers.json |
| selection | 1 | `grok-bot-visual-qa` | high |  |  |

### `evidence_audit`

Check claims against snapshots and sources. Catches invented metrics before they propagate.

| kind | n | route | confidence | basis | evidence |
|---|---:|---|---|---|---|
| quality | 1 | `opus-5-teamclaude` | medium | operational_prior | config/providers.json |
| quality | 2 | `gpt-5.6-sol-codex` | medium | operational_prior | config/providers.json |
| selection | 1 | `opus-5-teamclaude` | medium |  |  |
| selection | 2 | `gpt-5.6-sol-codex` | medium |  |  |
| efficiency | 1 | `glm-5.3-flash-unwired` | low |  |  |

### `model_evaluation_admin`

Administer candidate evals and receipts. Owner/admin gated; scores do not auto-wire routes.

| kind | n | route | confidence | basis | evidence |
|---|---:|---|---|---|---|
| quality | 1 | `opus-5-teamclaude` | medium | operational_prior | config/providers.json |
| quality | 2 | `gpt-5.6-sol-codex` | medium | operational_prior | config/providers.json |
| selection | 1 | `opus-5-teamclaude` | low |  |  |
| selection | 2 | `gpt-5.6-sol-codex` | low |  |  |

## Invariants

- `catalog_is_not_a_route`: true
- `cross_family_requires_distinct_families`: true
- `cross_family_uses_independence_groups`: true
- `duplicate_physical_invocations_fail_closed`: true
- `fable_is_same_family_as_opus`: true
- `freshness_uses_current_date`: true
- `last_resort_coding_requires_concrete_coder`: true
- `only_live_verified_resolves`: true
- `quality_is_not_price`: true
- `quality_rank_is_not_selection_priority`: true
- `rankings_are_role_and_harness_specific`: true
- `required_tools_are_not_capabilities`: true
- `resolver_api_fails_closed`: true
- `single_dispatcher_per_run`: exactly one effective dispatcher is selected per run from the requested intake/provider profile and live usage; rankings never grant dispatch
- `tools_never_follow_rank`: true
- `unknown_availability_fails_closed`: true
