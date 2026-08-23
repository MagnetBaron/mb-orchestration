# Cursor Ultra usage (bundled with SuperGrok Heavy)

This is the allocation map for **Cursor Ultra** as it sits next to SuperGrok Heavy. Two different companies’ meters. Do not treat “Grok in Cursor” as the same bucket as `grok` CLI / Grok Bot.

Check live numbers in Cursor Settings → Spending / usage dashboard. Cursor Models size is “generous,” not a published dollar figure. Other Models on Ultra is **$400 / billing month**.

## Two Cursor pools (reset with Cursor billing month)

| Pool | What it is | Ultra include |
|------|------------|---------------|
| **Cursor Models** | First-party: Cursor **Grok 4.6**, **Grok 4.5**, **Composer 2.5** (and their Fast variants) | Generous included usage. **Not** the $400. |
| **Other Models** | Third-party at API list rates | **$400 / mo**, then on-demand if you enable it |

Unlimited **Tab** completions are outside both pools.

## What spends the $400 (Other Models)

Use these only when Codex/Claude review or owner asked. This is the **Last $** seat in `AGENTS.md`.

- Claude: Fable 5, Opus 5, Sonnet 5, …
- OpenAI in the Cursor picker: **GPT-5.6 Sol, Terra, Luna** (and Fast / long-context multipliers)
- Gemini and other third-party picker models
- Cursor Router **Balance / Intelligence** when it routes to a third-party model

Cursor Sol here does **not** spend Codex $200 plan Sol. See `sol-usage.md`.

## What does *not* spend the $400

| Surface | Meter |
|---------|--------|
| Cursor picker: Grok 4.6 / 4.5 / Composer 2.5 | **Cursor Models** pool |
| Cursor Router **Auto Cost** (when it stays on first-party) | Cursor Models |
| Tab completion | Unlimited on paid Ultra |
| **Grok Build CLI** (`grok`) | SuperGrok **Heavy** usage, not Cursor |
| grok.com chat / Imagine / Voice | SuperGrok Heavy |
| **Grok Bot** (Website Visual QA, standing work) | Grok Bot / Heavy-or-Ultra Bot weekly meter — not the $400 |
| Codex CLI Sol / Terra / Luna | ChatGPT Pro $200 plan |
| Claude Code / teamclaude | Claude plan seats |

## How this sits with SuperGrok Heavy

Heavy is the abundant **Grok** pool (Build + grok.com + Bot compute). Ultra is the **IDE**: big Cursor Models pool + $400 Other Models + Bot access.

Linking Heavy may zero the Ultra *subscription fee*; it does **not** merge Heavy tokens into the $400, and it does not enlarge Cursor Models by a published dollar amount. Do not buy both expecting stacked Ultra quotas.

## Orchestration allocation

1. Implement in **Grok Build** (Heavy), not Cursor Sol/Claude.
2. Everyday Cursor IDE work: stay on **Grok 4.6 / Composer** (Cursor Models).
3. Cursor **Other Models** ($400) last — after Grok + Claude + Codex review spend, or owner override.
4. Do not park the picker on Sol/Fable/Opus for daily typing.
5. When $400 is gone: stop Other Models unless owner enables on-demand. Fall back to Cursor Grok / Grok Build / teamclaude.

## Hard bans

- Using Cursor Sol or Claude in Cursor as the default implementer
- Assuming Cursor Grok 4.6 burns the $400 (it does not)
- Assuming Cursor Sol burns Codex weekly Sol (it does not)
- Leaving Grok Bot.app open on the 16 GB Mini to “use Ultra”
