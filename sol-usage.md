# GPT-5.6 Sol on the $200 Codex plan

Sol is **Review B**, not the implementer and not the dispatcher. Terra/Luna stay the Codex entry. teamclaude is Claude seats and does not spend this pool.

**Reset & %:** read from `usage-status` — the weekly window and `soft_cap_pct` live in `usage-windows.json` (seat `codex-sol`); do not hardcode the day/time here. A wrapper records a real 429 into `usage-ledger.json`; the owner may note the plan-UI % there as a fallback. See `usage-metering.md`.

## Cursor Sol is a different meter

| Surface | What Sol spends |
|---------|-----------------|
| **Codex CLI / ChatGPT Work** (this file) | ChatGPT Pro / Codex **plan limits** (5h + weekly) |
| **Cursor** model picker `gpt-5.6-sol` | Cursor **Other Models** pool at API rates ($4 / $0.4 / $20 per 1M). Ultra includes $400/mo of that pool. Does **not** draw Codex plan Sol. |

Do not treat Cursor Sol usage as “free Codex Sol,” and do not treat Codex Sol as spending Cursor’s $400. They are separate. Orchestration Review B is **Codex Sol** unless the brief explicitly says Cursor.

## Roles on the Codex account

| Model | Job |
|-------|-----|
| Luna or Terra | Dispatch only (queue, assign, status) |
| Sol | Git-diff review when Fable is empty or risk gate says review |
| Grok Build | All implementation |
| Opus 4.8 via teamclaude | Extra frontier pass if needed; not a Sol substitute for every ticket |

## Cap: 90% all week

Allow new **Codex Sol** reviews while weekly Sol used is **under 90%**. The 90% is `soft_cap_pct` in `usage-windows.json`; check it with `usage-status`, do not judge it by feel.

- Same threshold Sun through Sat. No early-week soft cap.
- At or over 90%: still dispatch **Grok** for volume. Code review → **Opus 4.8**, then **Review E (Fireworks) if wired**, otherwise park. Do not fake a “review” on Terra/Luna.
- Catalog-only product edits (no risk gate): skip Sol.
- Owner “use Sol on this one” beats the 90% line for that ticket only.
- After the weekly reset (`usage-status`, seat `codex-sol`): treat weekly Sol as 0% and start again.

Saturday is not special for throttling. Drain real parked reviews toward 90% if the queue needs it; still no makework.

## Review quality (do not throttle)

The $200 plan has enough Sol for full-quality reviews. When Sol is assigned:

- Use the effort the review needs (including high). Do not force medium to “save” quota.
- One thorough Sol pass per change-set is the default. A second Sol pass only for a **novel** defect after a fix loop — not to re-read the same diff.
- Do not use Sol as the implementer, for phone chatter, or for Ultra/fast modes as a habit. Fast mode multiplies cost; skip it unless the owner asked for speed on that review.

## Dispatch check (Codex Luna/Terra before starting Sol)

1. Review brief with `attack_angle` and a git diff path?
2. Fable unavailable (or owner said Sol)?
3. Risk gate or owner requires review?
4. Weekly Sol under the soft cap per `usage-status`?
5. This change-set already had a Sol pass? If yes → stop or Opus, not a duplicate Sol.

Any no → do not start Sol.
