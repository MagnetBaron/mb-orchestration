# Finish this setup on the worker machine

Codex is the entry point. Codex does not implement. Hand this file to Grok Build, Cursor, and Claude Code. They complete the machine setup. Luna/Terra only confirm the three receivers have the packet, then stop.

## Codex (Terra/Luna) — you

1. Open `MagnetBaron/mb-orchestration`.
2. Copy the packet at the bottom to Grok Build, Cursor, and Claude Code.
3. Reply: handed to Grok Build, Cursor, Claude Code. Exit.
4. Do not clone extra copies, do not run teamclaude, do not open Grok Bot.app, do not touch Shopify.

## Grok Build — implement install

Read `install.md`, `AGENTS.md`, `mcp-routing.md`, `visual-qa.md`, `visual-qa-slack.md`, `EDGE-CASES.md`, `usage-metering.md`.

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

- Read `DOCTRINE.md`, `mcp-routing.md`, `visual-qa.md`, `visual-qa-slack.md`, `EDGE-CASES.md` against what Grok/Cursor did.
- Output `ship` | `fix-list` | `blocked` for the *setup*, not a product change.
- Pin opus-4.8. teamclaude if seats exist. No Fable as installer.

## Owner-only (not a coding bot)

Once per account.

1. **Website Visual QA + Slack** — full steps in [visual-qa-slack.md](./visual-qa-slack.md). Quit Bot.app on the worker Mini.
2. **Google MCP on Codex/Claude** — ensure Search Console, Drive, DataForSEO (or equivalent) are connected on the seats that run GPT Terra / Opus so `mcp-routing.md` is real, not aspirational.
3. **Luna close-loop** — paste standing add-on from [luna-close-loop.md](./luna-close-loop.md) if you want finish reports forwarded.
4. **Usage metering** — set the `config/usage-windows.json` anchors you know (Grok weekly weekday/time, Cursor billing day) so `bin/usage-status.py` computes resets; wrappers/owner write `config/usage-ledger.json`. See `usage-metering.md`.

## Packet for Codex to paste

objective: Finish mb-orchestration + teamclaude desktop discovery and policy wiring on THIS machine per SETUP-BOTS.md. Codex stays dispatcher.

must_read:
- install.md
- AGENTS.md
- mcp-routing.md
- visual-qa.md
- visual-qa-slack.md
- EDGE-CASES.md
- SETUP-BOTS.md

must_not_touch: Shopify Admin, theme publish, Grok Bot.app left running, four Claude desktop apps, Cursor $400, Luna implementing

output_path: a short report in the session (clone paths, clients that see the folders, owner-only leftover including MCP connector check)

done_when: both repos openable; AGENTS.md loaded; `python3 bin/doctor.py` and `python3 bin/smoketest.py` green; Visual QA Slack path documented; MCP routing docs present; Grok Bot.app not required on the Mini for daily dispatch; `bin/usage-status.py` runs and reports seat resets

effort: setup
