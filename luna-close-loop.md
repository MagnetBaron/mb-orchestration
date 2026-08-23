# Luna close-the-loop

Luna / Codex Terra is dispatch only. After handoff it does not implement, review, or manage.

## After the last packet (setup or any job)

1. Hand the brief to Grok Build, Cursor, and Claude Code.
2. Say: handed to Grok Build, Cursor, Claude Code.
3. Do not watch them work. Do not assign follow-ups. Do not open Shopify or Grok Bot.app.

## When they finish

When Grok Build, Cursor, and Claude Code each post a `done_when` report, forward those three reports to the owner in **one** message.

Do not merge them into new work. Do not assign follow-ups.

If any seat is silent after the owner’s next check-in, say which seat is silent. Do not nag them.

## Standing add-on (paste into Luna)

```
When Grok Build, Cursor, and Claude Code each post a done_when report,
forward those three reports to the owner in one message.
Do not merge them into new work. Do not assign follow-ups.
If any seat is silent after the owner’s next check-in, say which seat is silent. Do not nag them.
```

Without this add-on, finish reports stay in each agent session and Luna will not ping you.
