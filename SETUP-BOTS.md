# Finish this setup on the worker machine

Codex is the entry point. Codex does not implement. Hand this file to Grok Build, Cursor, and Claude Code. They complete the machine setup. Luna/Terra only confirm the three receivers have the packet, then stop.

## Codex (Terra/Luna) — you

1. Open `MagnetBaron/mb-orchestration`.
2. Copy the packet at the bottom to Grok Build, Cursor, and Claude Code.
3. Reply: handed to Grok Build, Cursor, Claude Code. Exit.
4. Do not clone extra copies, do not run teamclaude, do not open Grok Bot.app, do not touch Shopify.

## Grok Build — implement install

Read `install.md`, `AGENTS.md`, `visual-qa.md`, `visual-qa-slack.md`.

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

- Read `DOCTRINE.md` + `visual-qa.md` + `visual-qa-slack.md` against what Grok/Cursor did.
- Output `ship` | `fix-list` | `blocked` for the *setup*, not a product change.
- Pin opus-4.8. teamclaude if seats exist. No Fable as installer.

## Owner-only (not a coding bot)

Once per account. Full Slack wake-up steps: [visual-qa-slack.md](./visual-qa-slack.md).

1. Open Grok Bot on a non-worker machine if possible; else one short session on the Mini.
2. Create or rename Bot **Website Visual QA**. Paste `visual-qa.md`.
3. Slack **plugin** + Slack **event** integration (two different connections).
4. Invite the Slack app into `#visual-qa`. Create the channel if missing.
5. Routine: new `#visual-qa` message containing `shopifypreview.com` → walk allowlist → reply in thread.
6. Test run, then quit Grok Bot.app. Login item off.

## Packet for Codex to paste

objective: Finish mb-orchestration + teamclaude desktop discovery and Review D wiring on THIS machine per SETUP-BOTS.md. Codex stays dispatcher.

must_read:
- install.md
- AGENTS.md
- visual-qa.md
- visual-qa-slack.md
- SETUP-BOTS.md

must_not_touch: Shopify Admin, theme publish, Grok Bot.app left running, four Claude desktop apps, Cursor $400, Luna implementing

output_path: a short report in the session (clone paths, clients that see the folders, owner-only leftover)

done_when: both repos openable; AGENTS.md loaded; Visual QA Slack wake-up documented; Grok Bot.app not required on the Mini for daily dispatch

effort: setup
