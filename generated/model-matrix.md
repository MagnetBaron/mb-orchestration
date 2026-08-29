# Model matrix

Generated from `config/model-registry.json` as of 2026-08-28.
Deterministic. Do not hand-edit; run `python3 bin/model-registry.py write-matrix`.

A catalog entry is not a usable route. Only `live_verified` routes resolve.
The public resolver API is fail-closed: every candidate is filtered by `route_is_live` (missing/stale/future/mismatched/unattested evidence never returns).
Last-resort coding requires a concrete live provider with `implement`/`ide` and `code` on both the provider and its bound live route; sharing a plan is not enough.
Quality rank is not selection priority. Rank never grants tools or data.
Descending ranks are evidence-bounded and role/harness-specific, not a universal ordering.
live_verified freshness is compared to the current date (or `--as-of`), not frozen `registry.as_of`.
Promotion attestations (`intake.promote_requires`) live on each live route; `direct_invocation` vs `standing_provider` is explicit.

## Census scope

- as_of: 2026-08-28
- cutoff: 2026-08-28
- scope: Current general-purpose text/vision/agentic/coding models plausibly useful to this orchestration as of 2026-08-28. A scoped lab census, not an unbounded claim of every model in existence.

## Models

| id | family | lab | lifecycle | official ids | excluded |
|---|---|---|---|---|---|
| `claude-fable-5` | anthropic | Anthropic | restricted | claude-fable-5, fable-5 | no |
| `claude-opus-4-8` | anthropic | Anthropic | superseded | claude-opus-4-8, opus-4.8, claude-opus-4.8 | no |
| `claude-opus-5` | anthropic | Anthropic | stable | claude-opus-5, opus-5 | no |
| `deepseek-v4-flash` | deepseek | DeepSeek | stable | deepseek-v4-flash | no |
| `deepseek-v4-pro` | deepseek | DeepSeek | stable | deepseek-v4-pro | no |
| `gemini-3-flash-preview` | google | Google | preview | gemini-3-flash-preview | no |
| `gemini-3.1-flash-lite` | google | Google | stable | gemini-3.1-flash-lite | no |
| `gemini-3.1-pro-preview` | google | Google | preview | gemini-3.1-pro-preview | no |
| `gemini-3.5-flash` | google | Google | stable | gemini-3.5-flash | no |
| `gemini-3.5-flash-lite` | google | Google | stable | gemini-3.5-flash-lite | no |
| `gemini-3.6-flash` | google | Google | stable | gemini-3.6-flash | no |
| `gemini-3.7-flash` | google | Google | preview | gemini-3.7-flash | no |
| `glm-5.2` | zhipu | Z.AI | stable | glm-5.2, glm-5-2 | no |
| `glm-5.3-flash` | zhipu | Z.AI | preview | glm-5.3-flash | no |
| `gpt-5.3-codex-spark` | openai | OpenAI | stable | gpt-5.3-codex-spark | no |
| `gpt-5.4` | openai | OpenAI | stable | gpt-5.4 | no |
| `gpt-5.4-mini` | openai | OpenAI | stable | gpt-5.4-mini | no |
| `gpt-5.5` | openai | OpenAI | stable | gpt-5.5 | no |
| `gpt-5.6-luna` | openai | OpenAI | stable | gpt-5.6-luna | no |
| `gpt-5.6-sol` | openai | OpenAI | stable | gpt-5.6-sol | no |
| `gpt-5.6-terra` | openai | OpenAI | stable | gpt-5.6-terra | no |
| `grok-4.5` | xai | xAI | superseded | grok-4.5 | no |
| `grok-4.6` | xai | xAI | stable | grok-4.6, grok-4.6-build | no |
| `kimi-k2.6` | moonshot | Moonshot | superseded | kimi-k2.6 | no |
| `kimi-k2.7-code` | moonshot | Moonshot | stable | kimi-k2.7-code, kimi-for-coding | no |
| `kimi-k3` | moonshot | Moonshot | stable | kimi-k3, kimi-k3-max | no |
| `muse-code` | meta | Meta | preview | muse-code | no |
| `muse-spark-1.2` | meta | Meta | preview | muse-spark-1.2 | no |
| `open-weight-review-e` | open-weight | unspecified | restricted | review-e | no |
| `qwen-3.8-max` | alibaba | Alibaba | stable | qwen-3.8-max, qwen3-8-max | no |

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

## Per-role rankings (selection vs quality)

### `dispatch`

Classify, stamp review, brief, assign. Authority is entrypoints.json, not model rank. Luna/Terra rank for dispatch work quality.

| kind | n | route | confidence |
|---|---:|---|---|
| quality | 1 | `gpt-5.6-terra-codex` | medium |
| quality | 2 | `opus-5-teamclaude` | medium |
| quality | 3 | `gpt-5.6-luna-codex` | medium |
| selection | 1 | `gpt-5.6-luna-codex` | high |
| selection | 2 | `gpt-5.6-terra-codex` | high |
| selection | 3 | `opus-5-teamclaude` | high |

### `context_scouting`

Cheap first pass to compress or extract facts before expensive seats. Added because it reduces expensive context.

| kind | n | route | confidence |
|---|---:|---|---|
| quality | 1 | `gpt-5.6-luna-codex` | medium |
| quality | 2 | `grok-4.6-build` | medium |
| selection | 1 | `gpt-5.6-luna-codex` | medium |
| selection | 2 | `grok-4.6-build` | medium |
| efficiency | 1 | `glm-5.3-flash-unwired` | low |
| efficiency | 2 | `gemini-3.5-flash-lite-unwired` | low |
| efficiency | 3 | `gpt-5.6-luna-codex` | medium |

### `research_synthesis`

Long-context synthesis from already-fetched packets. Does not invent Google metrics.

| kind | n | route | confidence |
|---|---:|---|---|
| quality | 1 | `opus-5-teamclaude` | high |
| quality | 2 | `gpt-5.6-sol-codex` | high |
| quality | 3 | `grok-4.6-build` | medium |
| quality | 4 | `kimi-k3-unwired` | low |
| selection | 1 | `grok-4.6-build` | high |
| selection | 2 | `gpt-5.6-terra-codex` | high |
| selection | 3 | `opus-5-teamclaude` | medium |

### `implementation`

Repo/app code in an isolated worktree.

| kind | n | route | confidence |
|---|---:|---|---|
| quality | 1 | `gpt-5.6-sol-codex` | medium |
| quality | 2 | `opus-5-teamclaude` | medium |
| quality | 3 | `grok-4.6-build` | high |
| quality | 4 | `qwen-3.8-max-unwired` | low |
| quality | 5 | `deepseek-v4-pro-unwired` | low |
| quality | 6 | `kimi-k2.7-code-unwired` | low |
| quality | 7 | `muse-spark-1.2-unwired` | low |
| selection | 1 | `grok-4.6-build` | high |
| selection | 2 | `grok-4.6-cursor` | high |
| efficiency | 1 | `deepseek-v4-flash-unwired` | low |
| efficiency | 2 | `grok-4.6-build` | high |

### `architecture_spec_critique`

Rare long-horizon / spec critique. Opus 5 first at current evidence; Fable is a low-confidence long-horizon escalation candidate. Same family.

| kind | n | route | confidence |
|---|---:|---|---|
| quality | 1 | `opus-5-teamclaude` | high |
| quality | 2 | `fable-5-teamclaude` | low |
| selection | 1 | `opus-5-teamclaude` | high |
| selection | 2 | `fable-5-teamclaude` | medium |

### `code_review`

Diff review. Cross-family pair is Opus 5 + Sol. Fable is not a second family.

| kind | n | route | confidence |
|---|---:|---|---|
| quality | 1 | `opus-5-teamclaude` | high |
| quality | 2 | `gpt-5.6-sol-codex` | high |
| quality | 3 | `fable-5-teamclaude` | low |
| quality | 4 | `review-e-fireworks` | low |
| selection | 1 | `opus-5-teamclaude` | high |
| selection | 2 | `gpt-5.6-sol-codex` | high |
| selection | 3 | `opus-4.8-teamclaude` | low |

### `mcp_volume`

High-volume connector fetches. Connector presence is required; public models do not create connectors.

| kind | n | route | confidence |
|---|---:|---|---|
| quality | 1 | `gpt-5.6-terra-codex` | high |
| quality | 2 | `gemini-3.7-flash-unwired` | low |
| selection | 1 | `gpt-5.6-terra-codex` | high |
| selection | 2 | `gpt-5.6-luna-codex` | medium |
| efficiency | 1 | `glm-5.3-flash-unwired` | low |
| efficiency | 2 | `gemini-3.5-flash-lite-unwired` | low |
| efficiency | 3 | `gemini-3.7-flash-unwired` | low |

### `mcp_judgment`

Interpret already-fetched MCP output. Never row-dump fetch loops.

| kind | n | route | confidence |
|---|---:|---|---|
| quality | 1 | `opus-5-teamclaude` | high |
| quality | 2 | `gpt-5.6-sol-codex` | high |
| selection | 1 | `gpt-5.6-sol-codex` | high |
| selection | 2 | `opus-5-teamclaude` | high |

### `visual_qa`

Storefront pixel review of a visitor preview URL.

| kind | n | route | confidence |
|---|---:|---|---|
| quality | 1 | `grok-bot-visual-qa` | high |
| selection | 1 | `grok-bot-visual-qa` | high |

### `evidence_audit`

Check claims against snapshots and sources. Catches invented metrics before they propagate.

| kind | n | route | confidence |
|---|---:|---|---|
| quality | 1 | `opus-5-teamclaude` | high |
| quality | 2 | `gpt-5.6-sol-codex` | high |
| selection | 1 | `opus-5-teamclaude` | medium |
| selection | 2 | `gpt-5.6-sol-codex` | medium |
| efficiency | 1 | `glm-5.3-flash-unwired` | low |

### `model_evaluation_admin`

Administer candidate evals and receipts. Owner/admin gated; scores do not auto-wire routes.

| kind | n | route | confidence |
|---|---:|---|---|
| quality | 1 | `opus-5-teamclaude` | medium |
| quality | 2 | `gpt-5.6-sol-codex` | medium |
| selection | 1 | `opus-5-teamclaude` | low |
| selection | 2 | `gpt-5.6-sol-codex` | low |

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
- `single_dispatcher`: entrypoints.json dispatcher.provider is the only authority assignment; rankings never grant dispatch
- `tools_never_follow_rank`: true
- `unknown_availability_fails_closed`: true
