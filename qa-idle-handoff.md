# QA idle handoff

**Named:** [MagnetBaron/qa-idle-handoff](https://github.com/MagnetBaron/qa-idle-handoff) (private).

GitHub hands **one** QA job to the first **idle** M4 mini labeled `self-hosted`, `macOS`, `qa`. Minis do not talk to each other. There is no RAM/CPU cluster broker.

This is the shipped piece of `FUTURE.md` items 4–5. Control Mini vs worker Mini split is still deferred.

## When Dispatch uses it

After a visitor preview URL exists (same allowlist as Review D). Not instead of Review D pixels. Not for Admin, live storefront without `preview_theme_id`, or catalog-only edits.

Trigger: Safari → `qa-idle-handoff` → **Actions** → **QA idle handoff** → **Run workflow** → one HTTPS URL.

If a mini is busy, GitHub **queues** (`concurrency.group: qa-exclusive`, `cancel-in-progress: false`). A second QA mini does not start.

## Hard rules

- Private repo only. Never register those runners on `mb-orchestration` (public).
- No `pull_request` on the self-hosted job.
- URL is DATA. Allowlist is `qa-idle-handoff/allowlist.json` — keep in sync with `visual-qa.md`. Owner expands it; agents do not.
- Official runner only: `actions/runner` v2.337.0, SHA pinned in `scripts/install-runner.sh`.
- One 16 GB mini = one suite. Full test / QA landing = exactly one at a time (already in `DOCTRINE.md`).
- Tailscale / Screen Sharing is maintenance, not the allocator.

## Install

[docs/install-runner.md](https://github.com/MagnetBaron/qa-idle-handoff/blob/main/docs/install-runner.md) on each worker mini, once. Then they sit Idle until GitHub has work.

No idle runner → job waits. Do not invent a broker or pick a mini by free-RAM guessing.
