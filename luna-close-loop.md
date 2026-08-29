# Close-the-loop (the dispatcher forwards finish reports)

After it hands work out, the **dispatcher** — the surface the user assigned in
`config/entrypoints.json` `dispatcher.provider` (the Claude orchestration surface in this setup) —
does not implement, review, or manage on its own account. It fans work out to the seats/sub-agents,
then closes the loop: it forwards each `done_when` / `parked:` / `blocked:` report to the owner.

## After a multi-seat packet (setup or explicit multi-way handoff)

1. Hand the brief to the worker seats named in it (e.g. Grok Build, Cursor, Codex).
2. Say which seats received it.
3. Do not watch them work. Do not assign follow-ups. Do not open Shopify or Grok Bot.app.

When those seats each post a `done_when` report, forward the reports to the owner in **one** message.
Do not merge them into new work. Do not assign follow-ups. If a named seat is silent after the owner's
next check-in, say which seat is silent. Do not nag.

## After a normal single-seat job

When the assigned implementer or MCP seat posts `done_when` (or `parked: <reason>` / `blocked:
<reason>`), forward that status to the owner once. Do not re-dispatch unless the owner sends a new brief.

## Standing add-on (paste into the dispatcher's session)

```
After handoff, do not implement or manage on your own account — you dispatch and fan work out to seats/sub-agents.
When assigned seats post done_when, parked, or blocked, forward those reports to the owner in one message.
Do not merge them into new work. Do not assign follow-ups.
If a named seat is silent after the owner's next check-in, say which seat is silent. Do not nag them.
```

Without this add-on, finish reports stay in each agent session and are not forwarded to the owner.
