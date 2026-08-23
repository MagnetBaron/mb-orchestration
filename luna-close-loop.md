# Luna close-the-loop

Luna / Codex Terra is dispatch only. After handoff it does not implement, review, or manage.

## After a multi-seat packet (setup or explicit three-way handoff)

1. Hand the brief to Grok Build, Cursor, and Claude Code (or the seats named in the brief).
2. Say which seats received it.
3. Do not watch them work. Do not assign follow-ups. Do not open Shopify or Grok Bot.app.

When those seats each post a `done_when` report, forward the reports to the owner in **one** message. Do not merge them into new work. Do not assign follow-ups. If a named seat is silent after the owner’s next check-in, say which seat is silent. Do not nag.

## After a normal single-seat job

When the assigned implementer or MCP seat posts `done_when` (or `parked: <reason>` / `blocked: <reason>`), forward that status to the owner once. Do not re-dispatch unless the owner sends a new brief.

## Standing add-on (paste into Luna)

```
After handoff, do not implement or manage.
When assigned seats post done_when, parked, or blocked, forward those reports to the owner in one message.
Do not merge them into new work. Do not assign follow-ups.
If a named seat is silent after the owner’s next check-in, say which seat is silent. Do not nag them.
```

Without this add-on, finish reports stay in each agent session and Luna will not ping you.
