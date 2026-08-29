# Magnet Baron orchestration — user guide (best practices)

> **This file is for humans deciding how to set up and pay for the system.**
> It is **NOT operational policy and must never be loaded into an agent's context.**
> Agents run on `AGENTS.md` + `config/` + `bin/` only. Nothing here changes routing;
> it helps *you* pick plans, understand why the families matter, and port the system
> to your own subscriptions, MCPs, entry points, and habits.

The system orchestrates several AI CLIs so that cheap/abundant seats do the volume, scarce
high-end seats do the judgment, and the engine keeps running when any one seat hits its
limit. You do not need every plan below — the whole point is that it flexes to what you have.

---

## 1. Which AI family matters for which task

Route by **family**, not by brand loyalty. The families are Anthropic (Claude: Fable, Opus),
OpenAI (GPT/Codex: Sol, Terra, Luna), xAI (Grok: Build + the two Grok Bots), open-weight
(DeepSeek/Kimi/Qwen/GLM via Fireworks or a local runtime), and Cursor (a harness over mixed models).

| Task | Best family | Why |
|------|-------------|-----|
| **Bulk implementation** (code, listings, catalog volume) | **xAI — Grok Build** | Abundant volume; worktree isolation; cheap per token |
| **Land-gate / hard review (first gate)** | **Anthropic — Opus 5** | Operational Anthropic gate (released 2026-07-24); independent Intelligence Index 63 at max. Not a bulk implementer |
| **Second review opinion (diff)** | **OpenAI — Codex Sol** | Independent family from Anthropic — the pair a cross-family gate needs |
| **Architecture / long-horizon (rare)** | **Anthropic — Fable 5** | Same family as Opus; out of the gating order. Opus 5 is stronger/more efficient for normal judgment |
| **Google-MCP volume** (Search Console, Drive, DataForSEO) | **OpenAI — GPT Terra** | Has the Google connectors; cheap tool loops |
| **Interpreting MCP/analytics numbers** | **Anthropic Opus / OpenAI Sol** | Scarce judgment on already-fetched data (never bulk-fetch here) |
| **Storefront pixel QA** | **xAI — Grok Bot (Visual QA)** | Credential-free preview walks; app-only cloud teammate |
| **Analytics heatmaps/replays** | **xAI — Grok Bot (Heat Map)** | Browser-only Clarity layer the API can't return |
| **Independent third-family review** | **open-weight — Review E** | The only review family that is *not* Anthropic/OpenAI/xAI (see §3) |
| **IDE / inline edits** | **Cursor (Grok pool)** | First-party pool; drain before paid buckets |
| **Dispatch** | Requested/profile intake provider, with recorded-availability fallback | Exactly one effective coordinator per run; reviewer chain flexes around dispatcher and authors. Rankings never grant authority |

**The cross-family rule is the load-bearing one:** for money/auth/PII/secrets work, two *different*
families must each review. Anthropic's Fable and Opus are ONE family — two Claude passes do not count.
So you need at least a second family in the building (OpenAI via Codex, or open-weight via Review E).

---

## 2. Fable — a premium grant that is NOT your gate

**Fable 5 is a premium grant** (included on higher Claude tiers — Max, Team Premium — not guaranteed
on Pro/Team-Standard, which default to Sonnet). Confirm what your accounts grant with
`bin/detect-capability.py`.

**Fable is OUT of the gating order.** It is a rare architecture/long-horizon escalation in the same
family as Opus. **Opus 5 is the first (Anthropic) gate** because it is currently stronger and more
efficient for normal Anthropic judgment; some public Fable measurements are also contaminated by a
safety fallback to Opus, so they are not independent family evidence. Do not pay for Fable expecting
it to be your reviewer. Do not treat Fable + Opus as two families.

**What actually matters without Codex** is not Fable — it's a *second family*. Without Codex you have no
OpenAI gate (no Sol); your only gating family is Anthropic (Opus). A cross-family gate then needs an
**independent open-weight family — Review E (Fireworks or a local model)**. So:

- *Have Codex?* You already have two gating families (Anthropic Opus + OpenAI Sol). Fable is optional.
- *No Codex?* Wire **Review E** for the second family, or money/auth/PII work parks. Fable does **not**
  fill that gap — it is the same family as Opus.

---

## 3. Keep your model (Opus 5) from silently downgrading

Claude will, under load or by plan change, quietly serve a smaller model — dropping your **Opus 5
gate to Sonnet** mid-task (the costly one), or removing the optional Fable pass. Verified levers (from
`code.claude.com/docs/en/model-config`):

- **`availableModels` allowlist — the practical control.** List the models you actually want
  (`claude-opus-5`, and `fable-5` if granted). If you want a
  hard **refusal instead of a silent drop to Sonnet** under an Opus cap, leave `sonnet-5` out too. A
  request for a missing model then fails loudly instead of downgrading. Opus 4.8 may remain listed as a compatibility fallback while available.
- **`fallbackModel`** is opt-IN and fires only on overload/unavailable server errors for one turn —
  **not** on rate-limit or billing. Leave it unset for no automatic switch.
- **`switchModelsOnFlag: false`** (or `/config` → "Switch models when a message is flagged") stops the
  safety classifier from swapping Fable/Opus mid-task.
- The silent **Opus→Sonnet quota downgrade has no first-class opt-out** (Anthropic issue
  claude-code#3434, closed). The `availableModels` allowlist is the workaround.
- **teamclaude** (§5) handles this across accounts: it blocks `*fable*` automatically when no seat can
  serve it and unblocks when one can, so you don't hand-edit routes. `bin/detect-capability.py` records a
  downgrade so the router re-routes immediately.

**Recommendation:** pin `claude-opus-5` via `availableModels`; if Fable is central to your
architecture pass, disable model-switching-on-flag and check `bin/detect-capability.py` weekly.

---

## 4. What plan should you buy? (calculation from last month's habits)

Use `bin/subscription-calculator.py` — give it what you actually did **last month** and it recommends a
stack with reasons and an indicative monthly cost. It is deterministic: same inputs, same answer.

```bash
python3 bin/subscription-calculator.py \
  --implement-hours-per-day 4 --reviews-per-week 25 --mcp-bulk-per-week 5 \
  --cross-family --storefront-pixels --analytics --ide-hours-per-day 2 --team-size 2
```

**How it reasons (so you can sanity-check it):**

| If last month you… | It recommends | Because |
|--------------------|---------------|---------|
| coded/listed ≥1 h/day, or did storefront/analytics | SuperGrok Heavy | abundant volume + both Grok Bots ride one plan |
| needed any frontier review | 1× Claude Max | the Opus 5 gate (Fable optional, architecture only) |
| did >10 reviews/week | +1–3 Claude Team-premium seats | teamclaude rotates review load so no seat caps mid-week |
| coded heavily but reviewed lightly | +2 Claude Pro | cheap Opus overflow + rotation headroom (no Fable) |
| did Google-MCP bulk, or any cross-family work | Codex $200 | GPT Terra for MCP volume; Sol supplies the OpenAI review family |
| need cross-family but have **no** Codex | Fireworks Review E (~$20/mo) | an open-weight family to satisfy the gate |
| spent real time in an IDE | Cursor Ultra | first-party Grok pool + $400 last-resort bucket |

**Worked examples**

- *Heavy shop owner* (4 h/day implement, 25 reviews/wk, MCP, pixels, analytics, IDE, team of 2):
  Grok Heavy + Claude Max + 1 Claude Team-premium + Codex $200 + Cursor Ultra ≈ **$1,025/mo**.
  This is close to the reference setup (which adds a second Team seat + 2 Pro seats for extra rotation).
- *Solo Pro user, no Codex, some money work* (1 h/day, 3 reviews/wk, cross-family):
  Grok Heavy + Claude Max + Codex $200 ≈ **$700/mo** — the calculator pushes you toward Codex precisely
  because cross-family needs a second family. If you refuse Codex, it recommends Fireworks Review E instead.
- *Light solo* (little review, no risk work): a single Claude Pro ($25) covers it.

Prices are indicative for **sizing**; verify current pricing/tiers before buying.

---

## 5. Trustworthy building blocks (real, open-source)

The system leans on a few verified projects rather than reinventing them:

- **teamclaude** — https://github.com/KarpelesLab/teamclaude (MIT). Multi-account Claude proxy with
  automatic quota-based rotation for Claude Code; tracks **per-model** weekly caps, so an account out
  of one model still serves others. This is what turns "5 Claude accounts" into one resilient pool.
  Install: `npm install -g @karpeleslab/teamclaude`.
- **ccusage** — https://github.com/ryoppippi/ccusage (MIT). Token-usage/cost analysis for coding CLIs,
  including a 5-hour-block report matching Claude's billing windows. Good for calibrating the anchors
  in `config/usage-windows.json` from real usage.
- **claude-squad** — https://github.com/smtg-ai/claude-squad. Terminal manager that runs multiple
  agents in isolated git **worktrees** — the same isolation model this system mandates for implement lanes.
- **awslabs/cli-agent-orchestrator** — https://github.com/awslabs/cli-agent-orchestrator (Apache-2.0).
  A reference for coordinating multiple coding-agent CLIs; useful reading if you outgrow the thin scripts here.

(Verify each repo's current state before adopting; open-source moves.)

---

## 6. Entry points — work from wherever you like

**Where you type and which tested intake model you select are your choices.** `config/entrypoints.json`
defines profiles and fallback order; the router selects one effective dispatcher per run:

- `--intake-provider codex-sol|opus-5|opus-4.8|fable-5|codex-terra|codex-luna|grok-build` honors that provider while usable.
- `--profile <name>` supplies a per-user default without changing another user's preference.
- Recorded usage exhaustion moves to the evidence-ranked fallback automatically. Known non-dispatch surfaces relay without gaining authority; unknown providers park.
- Reviewer choice changes with dispatcher and implementer. Authors are excluded; dispatcher self-attestation cannot satisfy the independent intent/risk check.
- Ordinary repo artifacts transfer without another permission prompt. Restricted data parks instead of asking you to weaken the boundary.

This is how the same system serves a shop owner at a Mac console, a teammate in Cursor, and you on a
phone — without four people all trying to dispatch.

---

## 7. Porting the system to a different user

Everything user-specific is in `config/`. To hand this to someone with different plans, MCPs, entry
points, and habits:

1. Rewrite `config/subscriptions.json` with their plans (this drives Fable grants and capacity).
2. Set `config/entrypoints.json` — their entry surfaces, profiles, and fallback order.
3. Set `config/connectors.json` — their MCP connectors, stores, analytics login, Slack channel.
4. Fill the anchors they know in `config/usage-windows.json`.
5. Run `python3 bin/doctor.py` (must be error-free) and `python3 bin/smoketest.py` (must be 13/13).
6. `python3 bin/detect-agents.py` to see which agents are live; register any new CLI with
   `bin/detect-agents.py --register-template <cmd>` and paste the entry into `config/providers.json`.

Keep your own config outside the repo if you like: point **`MB_CONFIG_DIR`** at a folder holding your
`subscriptions.json` / `entrypoints.json` / `usage-windows.json` / `monitoring.json`; the shared
registry (providers, review-depth, roles, connectors) is inherited from the repo. Worked layers for a
solo Pro user, a two-subscription setup, and a larger agency are in `config/examples/` — copy the one
closest to you. **The reference `config/` is just one example of a complicated setup, not the target.**

No policy prose changes. The routing re-derives from their config. That is the durability guarantee:
the system flexes with technology and subscription changes because those live in data, not in words.

---

## 9. Controlling how hard each account drains

Each seat in `usage-windows.json` carries a drain policy — this is how you set "drain some accounts
hard, protect the intake account":

- **`"drain": "full"`** — drain freely (your worker/admin/server accounts, Grok Build). Most seats.
- **`"drain": "reserve"` + `"reserve_pct": N`** — hold headroom. Put this on your **intake/dispatch**
  account (or Cursor, if that's your intake) so it always has room to do its job.
- **`"intake": true`** — labels the dispatch seat so `bin/drain-plan.py --reserve` sizes its reserve
  from what dispatch actually consumed × a margin (`monitoring.json` → `reserve_defaults`).
- **`"billing": "metered"`** — marks a $-API pool (Cursor Other Models, Review E) so it drains LAST.

**The reserve never blocks coding.** It only *lowers priority*. If every other account is spent, the
reserved dispatch account codes anyway — there is no state where quota is available and the system
stalls on a self-imposed cap. With one or two subscriptions the dispatch account is expected to code.
Run `bin/drain-plan.py` to see the live "use this before it's lost" order (soon-to-reset weekly/monthly
quota first, included before metered, reserves last-but-usable).

## 10. The usage dashboard, history, and retention

- **Dashboard:** `python3 bin/dashboard.py` writes a self-contained `data/dashboard.html` — open it on
  this computer to see per-account usage, reset windows, the live drain order, your subscription stack
  and cost, and a health score (never-strand guarantee, waste-at-reset, metered-$ discipline, Fable
  availability). `--demo` seeds sample data for a preview.
- **History:** `python3 bin/usage-record.py --snapshot` captures the current state into
  `data/usage-history.jsonl`. Schedule it (e.g. hourly via cron/LaunchAgent) so the dashboard and the
  plan-change advice have real data. Sources beyond your own notes (teamclaude, ccusage) wire in
  `monitoring.json`; `--owner codex-sol=88` records a % you read off a provider dashboard.
- **Learned windows:** `usage-record.py --learn-windows` infers reset anchors from observed resets, so
  your refresh windows stay current automatically (it never overrides an anchor you set by hand).
- **Retention (your control):** `monitoring.json` → `retention_days` (default **365**) bounds how long
  history is kept; `usage-record.py --prune` (and every `--snapshot`) drops older records so the log
  never grows without limit. Set it to your comfort; `0` keeps everything (not recommended).
- **Plan-change advice from real use:** `bin/subscription-calculator.py --from-history` compares what
  you *pay for* against what you *used* — flagging under-used plans to drop and frequently-capped ones
  to grow.

## 10b. Routing-quality observability (decision log, not task contents)

Admins can evaluate routing quality over time without storing briefs, diffs, or identity.

- **What is collected:** requested vs effective intake and profile, fallback reason, task class /
  risk / review depth, selected implementer and reviewers (plus independence groups and author
  exclusion), handoff decision and artifact *classes*, recorded usage tier evidence, timing,
  terminal status, test/review verdicts, fix-loop and retraction counts, and provider-reported
  token/cost figures **only when a provider actually reported them**.
- **What is never collected:** raw prompts, task bodies, diffs, credentials, tokens/secrets,
  customer data, production exports, email addresses, or absolute user paths. Multi-user
  tracking uses an explicit pseudonym (`--actor-id team-a`) or `profile:<name>` — the tools
  never read `$USER`, `$HOME`, or git identity.
- **Where it lives:** `data/orchestration-events.jsonl` under `$MB_DATA_DIR` (gitignored).
  Retention is `monitoring.json` → `observability.retention_days` (default 365). Unlike
  usage history, emit does **not** auto-prune: run `python3 bin/observe.py prune` (or a
  cron/LaunchAgent that calls it) at a bounded admin point. `usage-record.py --snapshot`
  still prunes usage history automatically; the two logs are not equivalent.
  `--record` / `--record-observability` always emit even if `MB_OBSERVABILITY=0`;
  `--no-record` always suppresses. Synthetic fixtures used in tests are committed under
  `model-evals/fixtures/observability/`.
- **How to read it:** `python3 bin/observe.py report` (add `--json` for machine output).
  Coverage/missingness, success/park/fallback rates, token-per-success *where measured*,
  usage starvation, handoff parks, reviewer disagreement, and per-role/provider/actor
  outcomes are all labeled **observational, not causal**. Missing token/cost fields stay
  empty; they are never filled with zeros or estimates.
- **Failure policy:** a malformed observability config fails `bin/doctor.py`. A disk/write
  failure never converts a parked routing decision into success. Observability does not
  grant tools, credentials, or review authority.
- **Adding a metric for a future model:** bump or extend the event schema
  (`config/observability-event.schema.json`; `additionalProperties` is already true so
  unknown fields are readable), record the new field only when it is actually available,
  add a synthetic fixture line, teach `bin/observe.py` analyze to *display* it without
  treating it as a cause, and add a unit test that a missing value stays `null`. Do not
  backfill invented token or quality numbers.

## 11. Keeping model choice current as models change

Capabilities and model strength are data, so newer/older models slot in cleanly:

- Assignment is by **capability + prowess** (`providers.json`), not habit — the router sends browser
  work to a browser-capable seat, review to the highest-prowess reviewer live, etc.
- **A new model is one edit.** To adopt Opus 5.1, Fable 5.1, or a successor to Fable/Sol, add a provider
  entry bound to its capability *level* (see `providers.json` → `model_slot_in`), optionally
  `supersedes` the incumbent, catalog the model in `config/model-registry.json` as non-routable first,
  promote only after local smoke + evals + owner approval, then run `bin/doctor.py`. Pin
  `claude-opus-5` via `availableModels` and consider disabling auto-downgrade (§3). A catalog entry
  is not a live route.
- **Upgrades are detected too, not just downgrades.** `bin/detect-capability.py` surfaces a seat that
  *regained* Fable (adopt it: `--record-upgrade <seat>`) and a `supersedes` model waiting to replace an
  incumbent — the mirror of downgrade detection.

---

## 8. Habits that keep the engine running longest

- **Let the cheap seats do volume.** Never move bulk work onto scarce judgment seats because a probe
  failed — park it instead (the system enforces this, but know why).
- **Spend abundant quota before reset; conserve scarce quota.** Unused weekly Grok/Sol quota at reset is
  wasted; but don't burn Fable/Sol on things Grok can do.
- **Record real limits, never guess.** A real 429 marks a seat spent (`bin/record-429.sh`); a timeout
  does not. This keeps the router honest.
- **Add Claude seats, not just bigger plans.** Five rotating accounts (via teamclaude) survive one
  capping far better than one large account.
- **Wire an independent family** (Review E) if you do any money/auth/PII work — otherwise those jobs
  park whenever your one non-Anthropic family is spent.
- **Run `bin/doctor.py` before changing config**, and `bin/smoketest.py` after — a broken registry
  mis-routes every later job.
