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
| **Hard review / architecture / land-gate** | **Anthropic — Fable 5** (then Opus 4.8) | Strongest judgment; the reliability pass before you ship |
| **Second review opinion (diff)** | **OpenAI — Codex Sol** | Independent family from Anthropic — the pair a cross-family gate needs |
| **Google-MCP volume** (Search Console, Drive, DataForSEO) | **OpenAI — GPT Terra** | Has the Google connectors; cheap tool loops |
| **Interpreting MCP/analytics numbers** | **Anthropic Opus / OpenAI Sol** | Scarce judgment on already-fetched data (never bulk-fetch here) |
| **Storefront pixel QA** | **xAI — Grok Bot (Visual QA)** | Credential-free preview walks; app-only cloud teammate |
| **Analytics heatmaps/replays** | **xAI — Grok Bot (Heat Map)** | Browser-only Clarity layer the API can't return |
| **Independent third-family review** | **open-weight — Review E** | The only review family that is *not* Anthropic/OpenAI/xAI (see §3) |
| **IDE / inline edits** | **Cursor (Grok pool)** | First-party pool; drain before paid buckets |
| **Dispatch** | **OpenAI — Codex Luna** (or any provider you choose) | One coordinator; never implements |

**The cross-family rule is the load-bearing one:** for money/auth/PII/secrets work, two *different*
families must each review. Anthropic's Fable and Opus are ONE family — two Claude passes do not count.
So you need at least a second family in the building (OpenAI via Codex, or open-weight via Review E).

---

## 2. Fable — why it matters, and why it matters *more* without Codex

**Fable 5 is a premium grant.** It is included on higher Claude tiers (Max, Team Premium) and is
**not** guaranteed on Pro or Team Standard — those default to Sonnet. Confirm what your accounts
actually grant with `bin/detect-fable.py`; the system treats Fable as available only when a live
Claude seat truly carries it.

Fable is the strongest reviewer. It matters **more** when you don't have Codex, because:

- Without Codex you have **no OpenAI review family** (no Sol). Your only high-end review family is
  Anthropic (Fable + Opus). Fable's extra quality carries more weight when it's your best pass.
- A **cross-family** gate then can't use OpenAI. Your independent second family must be **open-weight
  (Review E / Fireworks or a local model)**. Budget for wiring Review E, or accept that money/auth/PII
  work parks until you add a second family.

**Rule of thumb:** *Have Codex?* Fable is a luxury upgrade over Opus for review. *No Codex?* Fable +
a wired Review E is close to mandatory for any risk-class work.

---

## 3. Keep Fable (and your model) from silently downgrading

Claude will, under load or by plan change, quietly serve a smaller model — which can silently remove
Fable or drop Opus to Sonnet mid-task. Verified levers (from `code.claude.com/docs/en/model-config`):

- **`availableModels` allowlist — the practical control.** List the models you actually want
  (`opus-4.8`, and `fable-5` if granted). Leave `opus-5` OUT (it's forbidden here) and, if you want a
  hard **refusal instead of a silent drop to Sonnet** under an Opus cap, leave `sonnet-5` out too. A
  request for a missing model then fails loudly instead of downgrading.
- **`fallbackModel`** is opt-IN and fires only on overload/unavailable server errors for one turn —
  **not** on rate-limit or billing. Leave it unset for no automatic switch.
- **`switchModelsOnFlag: false`** (or `/config` → "Switch models when a message is flagged") stops the
  safety classifier from swapping Fable/Opus mid-task.
- The silent **Opus→Sonnet quota downgrade has no first-class opt-out** (Anthropic issue
  claude-code#3434, closed). The `availableModels` allowlist is the workaround.
- **teamclaude** (§5) handles this across accounts: it blocks `*fable*` automatically when no seat can
  serve it and unblocks when one can, so you don't hand-edit routes. `bin/detect-fable.py` records a
  downgrade so the router re-routes immediately.

**Recommendation:** pin `opus-4.8` via `availableModels`, never `opus-5`; if Fable is central to your
review, disable model-switching-on-flag and check `bin/detect-fable.py` weekly.

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
| needed any frontier review | 1× Claude Max | the Fable + Opus anchor |
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

**Where you type a request is your choice; who assigns seats is one config-bound dispatcher.** Set both
in `config/entrypoints.json`:

- Any surface (Codex CLI, Claude Code, Cursor, phone) can be where you *start*. Non-dispatcher surfaces
  classify + draft a brief and hand it to the dispatcher.
- The **dispatcher** (default Codex Luna) is the only seat that assigns other seats. Exactly one at a time.
- **No Codex?** Point `dispatcher.provider` at a provider you own (e.g. a Claude seat) and flip that
  surface's `can_dispatch` to true. The single-dispatcher invariant holds; only the holder moves.

This is how the same system serves a shop owner at a Mac console, a teammate in Cursor, and you on a
phone — without four people all trying to dispatch.

---

## 7. Porting the system to a different user

Everything user-specific is in `config/`. To hand this to someone with different plans, MCPs, entry
points, and habits:

1. Rewrite `config/subscriptions.json` with their plans (this drives Fable grants and capacity).
2. Set `config/entrypoints.json` — their dispatcher and entry surfaces.
3. Set `config/connectors.json` — their MCP connectors, stores, analytics login, Slack channel.
4. Fill the anchors they know in `config/usage-windows.json`.
5. Run `python3 bin/doctor.py` (must be error-free) and `python3 bin/smoketest.py` (must be 13/13).
6. `python3 bin/detect-agents.py` to see which agents are live; register any new CLI with
   `bin/detect-agents.py --register-template <cmd>` and paste the entry into `config/providers.json`.

No policy prose changes. The routing re-derives from their config. That is the durability guarantee:
the system flexes with technology and subscription changes because those live in data, not in words.

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
