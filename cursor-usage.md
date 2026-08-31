# Cursor Ultra usage (bundled with SuperGrok Heavy)

This is the allocation map for **Cursor Ultra** as it sits next to SuperGrok Heavy. Two different companies’ meters. Do not treat “Grok in Cursor” as the same bucket as `grok` CLI; the legacy Grok Bot app routes are retired.

Cursor Models size is “generous,” not a published dollar figure. Other Models on Ultra is **$400 / billing month** (reset date in `config/usage-windows.json`, `cursor-other-400`). A `$` seat has no `%` cap, so when the $400 is spent the owner marks it in `usage-ledger.json` with `spent_until` = next billing reset (copied from the Cursor dashboard). Agents route off `usage-status`, not a live dashboard glance.

## Same model family, not the same seat

**Cursor Grok 4.6** and **Grok Build** both serve Grok 4.6. They are not the exact same product.

- Same model family (Grok 4.6), available in both Cursor and Grok Build.
- Different harness, tools, default effort, and billing label. The selectable Grok CLI model is exactly `grok-4.6`; `grok-4.6-build` is only this repository's internal route key. Same weights in spirit; different wrapper. Benchmarks move with the harness, not just the name.
- **Different meters:** Cursor Grok → Cursor Models pool. `grok` CLI → SuperGrok Heavy.

So: use Grok Build for the orchestration implementation lane while Heavy is healthy. Cursor Grok is the included implementation-only overflow after a provider-confirmed Heavy exhaustion signal, not an independent reviewer or dispatcher.

## Implementation order (Heavy, then included Cursor overflow)

1. **Orchestration implementer** → **Grok Build CLI** (Heavy) while the seat is usable.
2. When the real Build call returns the exact, case-sensitive provider transport error `402 Payment Required: Grok Build usage balance exhausted` (or exact `HTTP 402: Grok Build usage balance exhausted`), record the source provider's configured `usage_seat` and resolve again. `config/providers.json` binds the Cursor provider through `overflow_after_provider`; the router derives both dependency IDs from config and fails closed on a missing or malformed reference. The configured overflow recipe is **Cursor Agent** with the same scoped brief in the same isolated worktree: `--trust --print --workspace <worktree> --model cursor-grok-4.6-xhigh` plus one positional instruction to read that brief. The route is currently catalog-only because its exact inference attempt hung without a terminal receipt, so resolution parks until a successful exact-model smoke promotes it to `live_verified`.
3. Cursor **Other Models $400** last (`AGENTS.md` Last $).
4. Codex Sol / teamclaude stay review seats (`sol-usage.md`).

The current `cursor-agent --list-models` output proves the exact selectable Cursor model id, not inference availability. The exact invocation was attempted but returned no stdout, edit, or terminal receipt before it was stopped; that negative result keeps the route catalog-only. A later promotion must change the route to `live_verified`/`local_smoke`, attest `local_access_smoke` as `direct_invocation`, make the latest evidence a `terminal_inference_receipt`, and record the exact receipt `{harness:"cursor-agent", invocation_id:"cursor-grok-4.6-xhigh", exit_code:0, completed:true}`. It must also pass the generic model-registry promotion predicate; the corrected invocation cannot inherit the frozen waiver for the old `grok-4.6` identity. If promoted, the seat remains implementation-only and cannot supply a review verdict or dispatch authority. Review D, Heat Map, and Marketplace Intelligence remain separately permissioned standing Grokbots and stay parked while their code-owned bindings are absent; Cursor overflow never impersonates them.

Grok outage is not quota exhaustion: probe once and park. Generic 402/payment/auth text or a completion quoting the error does not open the Cursor overflow. When Cursor Models is also exhausted, park rather than touching Cursor Other Models automatically.

## Composer 2.5 — do not hoard a reserve

Composer shares the **same Cursor Models pool** as Grok 4.6. There is no separate Composer bank to “maintain.” Unused Composer quota does not convert into extra Grok 4.6 later.

Keep Composer as a **picker choice**, not a savings account:

- Use Composer (or Composer Fast) for tight, interactive IDE loops: rename, small patch, follow-the-cursor edit, cheap iteration.
- Use Cursor Grok 4.6 for harder / longer IDE agents, including the bounded Build-overflow path above.
- Do not leave Composer unused “in case.” Prefer Grok 4.6 when the task is real work; flip to Composer when latency and short hops matter.
- Do not use Composer as the orchestration implementer.

## Two Cursor pools (reset with Cursor billing month)

| Pool | What it is | Ultra include |
|------|------------|---------------|
| **Cursor Models** | First-party: Cursor **Grok 4.6**, **Grok 4.5**, **Composer 2.5** (and Fast) | Generous. **Not** the $400. For orchestration, use only as included overflow after confirmed Grok Build exhaustion and a live-verified Cursor route. |
| **Other Models** | Third-party at API list rates | **$400 / mo**, then on-demand if enabled |

Unlimited **Tab** completions are outside both pools.

## What spends the $400 (Other Models)

Claude Fable/Opus/Sonnet, GPT-5.6 Sol/Terra/Luna in the Cursor picker, Gemini, Router Balance/Intelligence when it leaves first-party. Cursor Sol does **not** spend Codex plan Sol.

## What does *not* spend the $400

| Surface | Meter |
|---------|--------|
| Cursor Grok 4.6 / 4.5 / Composer 2.5 | Cursor Models |
| Tab | Unlimited on Ultra |
| Grok Build CLI | SuperGrok Heavy |
| grok.com | SuperGrok Heavy |
| Legacy Grok Bot.app (retired; do not use) | Historical Bot / Heavy weekly meter |
| Codex CLI | ChatGPT Pro $200 |
| teamclaude | Claude seats |

## Hard bans

- Cursor Sol/Claude as default implementer
- Treating Cursor Grok as the $400
- Treating Cursor Sol as Codex Sol
- Hoarding Composer while idling Grok 4.6 in the same pool
- Opening or signing into the retired Grok Bot.app on the worker Mini
