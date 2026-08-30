# Heat Map — Clarity analytics through Grok CLI

Heat Map is the named Grok CLI agent `mb-heat-map`. It is a read-only analytics/input seat, never a
review gate or implementer. The stable provider id is `grok-bot-heat-map`; the executable model is
exactly `grok-4.6`.

The reference route is parked. `grok mcp list` currently exposes no signed-in Clarity/browser source,
so the installed profile alone cannot read heatmaps or replay pixels. Never reuse old Slack/Bot
evidence to mark the CLI route live.
The launcher has no code-owned Clarity/browser input binding yet; registry or inventory attestations
alone cannot promote normal Heat Map execution. A future binding must stage an approved, hash-bound
export or a separately verified least-privilege transport before this seat can become ready.

## Binding

Render the current projects and least-privilege identity from config:

```sh
python3 bin/connectors.py --render clarity
```

`config/connectors.json` owns project ids, hosts, and the login identity. Credentials and session
cookies never enter the repo or a prompt file.

## Launch contract

There is currently no supported normal-execution command. A prompt-declared source, class, path, or
digest cannot authorize a Clarity export or signed-in session, so the launcher parks before reading
the prompt or its declared evidence.

A future code-owned binding must authenticate the least-privilege Clarity source or an approved
export deposit, classify it under `config/handoff-policy.json` before opening the payload, and bind
immutable provenance plus a digest. Only after that binding exists may the provider be wired, its
`grok-cli-heat-map` route become `live_verified`, and signed-in Clarity/browser capability be
role-tested. A transport-only smoke remains safe:

```sh
python3 bin/grok-agent.py --seat grok-bot-heat-map --smoke --execute
```

The smoke byte-validates and privately stages the generated profile. It proves agent/model
selection only and never proves Clarity access or a role result.

## Standing rules

Analyze only approved Clarity heatmaps, session replays, dashboard aggregates, and Clarity
Summarize/Highlights evidence for Magnet Baron or Gadget Duke. Label site, date range, sample size,
device, page/segment, and whether a claim is aggregate, observed replay behavior, or hypothesis.
Report evidence to Dispatch and suggest experiments; do not implement.

If the signed-in source, project match, sample, or provenance is absent, return `unavailable` and do
not invent clicks, scroll depth, conversion, friction, or causality. Do not expose visitor PII or
full form contents.

Never change Clarity settings/members/data, open Shopify Admin, publish, authenticate from a prompt,
export data to third parties, mint storefront URLs, issue `ship`, or treat bulk row dumps as
judgment. Review D remains a separate `mb-review-d` invocation with a separate prompt file.
