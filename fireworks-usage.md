# Review E — independent-family review fallback (Fireworks today)

Review E is the **frontier independent-family review slot** (`config/providers.json` provider
`review-e`) and the **next independent family after Codex Sol** in `review_order`. It is a
**replaceable backing**: Fireworks open-weight API today, a local open-weight
LLM (or another off-family CLI) later — the slot and its rules don't change when the backing does.
It is **metered, review-only**, and **not wired** (no key on the Mini). Until the owner wires it,
any brief that would route here **parks** with `blocked: Review E unwired`. Opus 4.8 is an Anthropic
compatibility fallback, not this independent post-Sol family. Fable is same-family architecture input
and never fills this slot. Never an implementer, dispatcher, MCP seat, or architecture reviewer.

Its value is **independence**, not capacity: Fable + Opus 5 are one family (Anthropic), Sol is OpenAI. A Fireworks open-weight model (DeepSeek / Moonshot / Alibaba / Zhipu labs) is the first review family that is none of Anthropic / OpenAI / xAI. See `DOCTRINE.md` §Correlated failure.

## One role (review-only)

**Cross-family second slot.** A safety-gate-5 item needs one pass from each of two families, but one native family is **quota-spent** so only one remains (e.g. post-downgrade Sol spent, or teamclaude spent). Review E fills the **second** family slot so the gate is satisfiable instead of parking. A family merely *down* (outage) is not spent — that parks, it does not open Review E. If all native gating seats are spent, park to the earliest reset: Review E alone never satisfies the gate. `user said ship` grants landing authority, not permission to spend on Review E.

Independent second-family review is the reason to wire this slot.

## No reset — it is dollars

There is no weekly window to drain. Every engagement is metered spend, so the drain law never applies here (`DOCTRINE.md` Economics). Owner sets a monthly cap at wiring time (`monthly_cap_usd` in `config/usage-windows.json`, e.g. **$20/mo**); over cap → park, do not silently overspend.

## Engage trigger — QUOTA opens it, OUTAGE never does

Only **positive quota evidence** opens Review E. Record the state in `usage-ledger.json` (read by `usage-status`) **before** engaging.

| Signal | Class | Effect |
|--------|-------|--------|
| `usage-status` shows the seat spent / soft-capped (recorded **429** or ledger %) | **QUOTA** | counts toward exhaustion |
| Fable absent by plan (downgrade) | **N/A** | Fable is NOT a gating seat — its absence never opens Review E; the gate seats are Opus 5 + Sol |
| Probe failure, timeout, 5xx, DNS, auth-expired, "command not found" | **OUTAGE** | **park** — says nothing about quota |

- A probe result can **park** work but can **never** route it to Review E (`EDGE-CASES.md` probe rule).
- **Correlated pipes:** teamclaude down = one Claude outage that also takes the assigned dispatcher when it is a Claude seat (direct Claude CLI is auth_blocked in this setup — do not treat it as a working route). Codex down = Sol *and* Terra MCP — not "reviewers exhausted."
- **All three reviewers erroring at once = local Mini fault.** Diagnose the box; do not engage Review E — it would mask the fault or fail identically.

## Dispatch check (all five, mirrors Sol)

1. Stamped `review: cross-family`? (never `none`, `self-check`, or `single-frontier`)
2. Exactly one native family remains usable and another native family is QUOTA-spent per `usage-status` — not merely probed down?
3. Is Review E the independent second family, never the only reviewer?
4. Diff within the fallback cap and **secret/PII scan clean**?
5. Not already reviewed by an open-weight family on this change-set?

Any **no** → do not engage. Park.

## API + model pin

- OpenAI-compatible. Base URL `https://api.fireworks.ai/inference/v1`, header `Authorization: Bearer $FIREWORKS_API_KEY`.
- Model id is account-scoped: `accounts/fireworks/models/<model>`. The serverless catalogue **rotates** — a 404 means retired; **re-pin**, do not hardcode one id forever.
- Class: **open-frontier reasoning, 128K+ context, structured-output support, serverless tier.** Pin one exact id + one named alternate below.
- **Ban** ≤70B instruct tiers, "Scout"-class, and "fast"/distilled variants — that is the quality cliff arriving through a default parameter.
- Candidates seen in third-party code (NOT confirmed live — the catalogue rotates, **verify each at wiring**): `accounts/fireworks/models/deepseek-r1-0528`, `…/deepseek-v3p1`, `…/kimi-k2-instruct-0905`, `…/qwen3-coder-480b-a35b-instruct`. Families to confirm: DeepSeek R1/V3(+later), Kimi K2(-thinking), Qwen3-235B-thinking / Qwen3-Coder-480B, GLM-4.x. A 404 = retired → re-pin.

```
PINNED  : accounts/fireworks/models/<owner fills at wiring>
ALTERNATE: accounts/fireworks/models/<owner fills at wiring>
```

## Wrapper contract

A thin one-shot API call invoked by whoever holds the review lane — **not** a daemon, not a second CLI on the Mini (no ban conflict). The wrapper script lives in the tooling repo, not this policy repo; only its contract is documented here.

1. Input: a **git diff** (merge-base..tip), the brief paths, and `attack_angle`. Never the worker story.
2. **Secret/PII scan first.** Any key, token, password, Admin URL, or customer PII in the diff → **park for a native seat**; secrets/PII never leave for a third-party host (`EDGE-CASES.md`).
3. Cap the diff (~3k lines / ~100k tokens). Over cap → `blocked: diff exceeds fallback seat limits`, park.
4. `temperature 0`, JSON-schema-forced output `{ verdict: ship|fix-list|blocked, findings:[{file,line,severity,note}] }`. Invalid JSON → one retry → else `blocked` (fail closed).
5. Write the verdict to `output_path`; append one ledger line (below). `blocked` wins on disagreement, unchanged.

## Verdict semantics

- On any **risk-gate class**, a Fireworks `ship` is recorded as **`advisory-ship — owner lands`**. It is never the sole gate for auth / money / PII / prod / irreversible.
- A bare `ship` with zero findings on a >200-line diff from this seat is low-confidence → park for a native seat or owner call.

## Ledger + tripwire

One line per engagement in the backlog: `date · role(1|2) · model id · tokens · $ · change-set`.

**> 2 role-1 engagements in a month is a capacity signal** — tell the owner to buy native quota. It is never a routing precedent; the fallback must not become the routine reviewer (that converges the system on its weakest judge).

## Hard bans

- Review E as implementer, dispatcher, MCP fetch/judge, or architecture/design reviewer.
- Engaging on an **outage/probe** signal, or before ledger-confirmed exhaustion.
- Sole land-gate on a risk class; both slots of a cross-family pair.
- Any pre-exhaustion "cheap review" use — inverts the scarce-judgment doctrine.
- Sending secrets / API keys / tokens / customer PII to the API.
- A health-check cron or makework probe against Fireworks.
