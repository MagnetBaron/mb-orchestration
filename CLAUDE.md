# Claude Code

@AGENTS.md

## Claude-only

- **Model: pin `opus-4.8`. Opus 5 is forbidden** (default or reviewer). Enforce it at the harness, not just in prose: put `opus-4.8` in `availableModels` and leave `opus-5`/`claude-opus-5` OUT, so a stray request refuses instead of running the banned model. `bin/doctor.py` fails on any config that selects a forbidden model.
- **Fable 5: architecture only, OUT of the gating order** (owner ruling 2026-08-25, Orchestration Retro — it measured worst on nonsense detection, BullshitBench 0.41 vs Opus 0.94). Never a gating reviewer, never a sole gate, never the default implementer. It is a per-account grant available only while a live Claude seat includes it; confirm with `bin/detect-capability.py`. **Opus 4.8 is the first (Anthropic) gate.**
- **Five Claude seats via teamclaude:** Max + 2 Team-premium (Fable-capable) + 2 Pro (Opus overflow, no Fable). Route through **teamclaude** so it rotates across 5h windows and tracks per-model caps (an account out of Opus quota still serves others). Do not stack all work on one account; do not hand-edit routes.
- **Entry-surface mode.** On this machine Claude Code is a *non-dispatcher* surface (`config/entrypoints.json`): show status (`bin/usage-status.py`), classify + stamp + draft a brief, then hand it to the dispatcher. Do not assign other seats or implement outside the Claude review/judgment seat. `/orchestrate` runs in this mode.
- **Keep the model from silently downgrading** (verified, `code.claude.com/docs/en/model-config`): the Opus→Sonnet quota downgrade has no first-class opt-out — the `availableModels` allowlist is the lever (exclude `sonnet-5` too if you want a hard refusal over a downgrade). `fallbackModel` is opt-in and fires only on overload, not rate-limits. `switchModelsOnFlag:false` stops safety-flag model swaps. Full guidance for humans: `USER-GUIDE.md`.
- After downgrade to Pro / Team-Standard: losing Fable removes only the optional architecture pass — the **gating order is unchanged: Opus 4.8 → Codex Sol → Review E (if wired) → stop**. teamclaude `mb/sync-plan` blocks `*fable*` automatically when no seat can serve it; do not hand-edit routes.
