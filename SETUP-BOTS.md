# Finish this setup on the worker machine

Codex is the entry point. Codex does not implement. Hand this file to Grok Build, Cursor, and Claude Code. They complete the machine setup. Luna/Terra only confirm the three receivers have the packet, then stop.

## Codex (Terra/Luna) — you

1. Open `MagnetBaron/mb-orchestration`.
2. Copy the packet at the bottom to Grok Build, Cursor, and Claude Code.
3. Reply: handed to Grok Build, Cursor, Claude Code. Exit.
4. Do not clone extra copies, do not run teamclaude, do not open Grok Bot.app, do not touch Shopify.

## Grok Build — implement install

Read `install.md`, `AGENTS.md`, `visual-qa.md`.

- Confirm clones: `mb-orchestration`, `teamclaude` (MagnetBaron org).
- Confirm `AGENTS.md` / `CLAUDE.md` at orchestration root so Codex/Cursor/Claude see them.
- Do **not** leave Grok Bot.app running. If it is open, note it and quit after the human signs the Bot in (owner step).
- Do **not** create Shopify staff/collaborator accounts.
- Smoke: files present; document paths.

## Cursor — desktop discovery

- Open folder `mb-orchestration` so the project is in Recents.
- Confirm GitHub Desktop can see MagnetBaron/mb-orchestration and MagnetBaron/teamclaude.
- Do not install extra Claude GUI apps.

## Claude Code — review only

- Read `DOCTRINE.md` + `visual-qa.md` against what Grok/Cursor did.
- Output `ship` | `fix-list` | `blocked` for the *setup*, not a product change.
- Pin opus-4.8. teamclaude if seats exist. No Fable as installer.

## Owner-only (not a coding bot)

Once per account, not on every Mini boot:

1. Open Grok Bot.app on a non-worker machine if possible; else one short session on the Mini.
2. Create or rename Bot **Website Visual QA**.
3. Paste standing rules from `visual-qa.md`.
4. Connect Slack. Routine: mention in `#visual-qa` → walk preview URL on allowlist → reply in thread.
5. Quit Grok Bot.app. Login item off.
6. Create Slack channel `#visual-qa` if missing.

## Packet for Codex to paste

objective: Finish mb-orchestration + teamclaude desktop discovery and Review D wiring on THIS machine per SETUP-BOTS.md. Codex stays dispatcher.

must_read:
- install.md
- AGENTS.md
- visual-qa.md
- SETUP-BOTS.md

must_not_touch: Shopify Admin, theme publish, Grok Bot.app left running, four Claude desktop apps, Cursor $400, Luna implementing

output_path: a short report in the session (clone paths, clients that see the folders, owner-only leftover)

done_when: both repos openable; AGENTS.md loaded; Visual QA documented as Slack Review D; Grok Bot.app not required on the Mini for daily dispatch

effort: setup
