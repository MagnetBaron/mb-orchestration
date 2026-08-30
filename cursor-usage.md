# Cursor Ultra usage (bundled with SuperGrok Heavy)

This is the allocation map for **Cursor Ultra** as it sits next to SuperGrok Heavy. Two different companies’ meters. Do not treat “Grok in Cursor” as the same bucket as `grok` CLI / Grok Bot.

Cursor Models size is “generous,” not a published dollar figure. Other Models on Ultra is **$400 / billing month** (reset date in `config/usage-windows.json`, `cursor-other-400`). A `$` seat has no `%` cap, so when the $400 is spent the owner marks it in `usage-ledger.json` with `spent_until` = next billing reset (copied from the Cursor dashboard). Agents route off `usage-status`, not a live dashboard glance.

## Same model family, not the same seat

**Cursor Grok 4.6** and **Grok Build** both serve Grok 4.6. They are not the exact same product.

- Same model family (Grok 4.6), available in both Cursor and Grok Build.
- Different harness, tools, default effort, and billing label. The selectable Grok CLI model is exactly `grok-4.6`; `grok-4.6-build` is only this repository's internal route key. Same weights in spirit; different wrapper. Benchmarks move with the harness, not just the name.
- **Different meters:** Cursor Grok → Cursor Models pool. `grok` CLI → SuperGrok Heavy.

So: use Cursor Grok to empty the IDE pool first. Keep Heavy for the orchestration implementer (`grok` CLI), not because the brain is a different species.

## Drain order (Cursor Models before Heavy)

1. **Cursor IDE agent / inline** → **Cursor Grok 4.6** (Cursor Models). Drain this pool first.
2. **Orchestration implementer** → **Grok Build CLI** (Heavy). Do not move repo volume into Cursor just to “save Heavy” if the job is already a Build worktree.
3. Cursor **Other Models $400** last (`AGENTS.md` Last $).
4. Codex Sol / teamclaude stay review seats (`sol-usage.md`).

If Cursor Models is healthy, do not start a second Grok Build process on the Mini for an IDE-shaped edit. If the job is a dispatched brief with a worktree, stay on Build.

## Composer 2.5 — do not hoard a reserve

Composer shares the **same Cursor Models pool** as Grok 4.6. There is no separate Composer bank to “maintain.” Unused Composer quota does not convert into extra Grok 4.6 later.

Keep Composer as a **picker choice**, not a savings account:

- Use Composer (or Composer Fast) for tight, interactive IDE loops: rename, small patch, follow-the-cursor edit, cheap iteration.
- Use Cursor Grok 4.6 for harder / longer IDE agents.
- Do not leave Composer unused “in case.” Prefer Grok 4.6 when the task is real work; flip to Composer when latency and short hops matter.
- Do not use Composer as the orchestration implementer.

## Two Cursor pools (reset with Cursor billing month)

| Pool | What it is | Ultra include |
|------|------------|---------------|
| **Cursor Models** | First-party: Cursor **Grok 4.6**, **Grok 4.5**, **Composer 2.5** (and Fast) | Generous. **Not** the $400. Drain Grok 4.6 here first. |
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
| Grok Bot | Bot / Heavy weekly meter |
| Codex CLI | ChatGPT Pro $200 |
| teamclaude | Claude seats |

## Hard bans

- Cursor Sol/Claude as default implementer
- Treating Cursor Grok as the $400
- Treating Cursor Sol as Codex Sol
- Hoarding Composer while idling Grok 4.6 in the same pool
- Grok Bot.app open on the worker Mini
