# GPT-5.6 Sol on the $200 Codex plan

Sol is **Review B**, not the implementer and not the dispatcher. Terra/Luna stay the Codex entry. teamclaude is Claude seats and does not spend this pool.

$200 Pro 20x has a large Luna/Terra slice and a much smaller Sol slice. Sol also burns faster per turn (long tool loops, high effort). Do not treat “a lot of usage” as permission to make Sol the primary 5.6 model.

Read `codex` / plan usage UI for the weekly %. There is no reliable public weekly number. Manual ledger in the backlog header only.

## Roles on this account

| Model | Job |
|-------|-----|
| Luna or Terra | Dispatch only (queue, assign, status) |
| Sol | One git-diff review when Fable is empty or risk gate says review |
| Grok Build | All implementation |
| Opus 4.8 via teamclaude | Second frontier review if Sol already used on this change-set or Sol is gated off |

## Do not use Sol until 75% as the primary model

Wrong: “Sol is primary 5.6 until 75%, then fall back.” That is how you empty the week by Wednesday.

Right: Sol is scarce judgment. Default implementer is Grok. Default Codex talk is Luna/Terra. Sol only on a review brief.

Hard bans for Sol: implement, phone chatter, Ultra/fast mode, xhigh/max effort as default, second Sol pass on the same change-set, dual Sol+Opus on one branch unless the first review found a novel defect.

Effort: **medium** default, **high** only for auth/money/PII/prod. Never Ultra. Never fast (multiplier).

## Weekday remaining-Sol gate

Use **weekly Sol % used** from the plan UI (or a note in the backlog header). If unknown, treat as conservative (assume mid-week).

| Local weekday (America/Chicago) | New Sol reviews allowed while weekly Sol used is below |
|--------------------------------|--------------------------------------------------------|
| Sun – Tue | 40% |
| Wed – Thu | 60% |
| Fri | 75% |
| Sat (pre-reset drain) | 90% |

If over that day’s cap:

- Still dispatch **Grok** for volume.
- Code review → **Opus 4.8** (teamclaude) if the risk gate still requires a frontier pass.
- If neither Sol nor Opus should spend: park the review. Do not dump it on Terra as a fake “review.”

If under the cap and the change is catalog-only (no risk gate): skip Sol. Grok summary is enough.

Owner override: “use Sol on this one” beats the table for that ticket only.

## Reset-aware

- Early week: protect Sol so Friday ship reviews still exist.
- Saturday: drain leftover Sol on **real** parked reviews only. No makework.
- After a published Codex reset: start the table again from 0%.

## Dispatch check (Codex Luna/Terra asks before assigning Sol)

1. Is this a review brief with `attack_angle` and a git diff path?
2. Is Fable unavailable?
3. Does risk gate or owner say review?
4. Is weekly Sol % under today’s cap?
5. Has this change-set already had a Sol pass? If yes → stop or Opus, not second Sol.

Any no → do not start Sol.
