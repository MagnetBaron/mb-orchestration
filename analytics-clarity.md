# Heat Map — Clarity analytics through Grok CLI

Heat Map is the named Grok CLI agent `mb-heat-map`. It is a read-only analytics/input seat, never a
review gate or implementer. The stable provider id is `grok-bot-heat-map`; the executable model is
exactly `grok-4.6`.

The reference route is parked. `grok mcp list` currently exposes no signed-in Clarity/browser source,
so the installed profile alone cannot read heatmaps or replay pixels. Never reuse old Slack/Bot
evidence to mark the CLI route live.

## Binding

Render the current projects and least-privilege identity from config:

```sh
python3 bin/connectors.py --render clarity
```

`config/connectors.json` owns project ids, hosts, and the login identity. Credentials and session
cookies never enter the repo or a prompt file.

## Launch contract

Create a prompt naming a regular non-symlink export with `role: heat-map`, `source:
approved-clarity-export`, `evidence-path`, and its exact `evidence-sha256`. The launcher recomputes
the digest before it runs. Then use the fail-closed inspection:

```sh
python3 bin/grok-agent.py --seat grok-bot-heat-map \
  --prompt-file /safe/path/heat-map.md --cwd /path/to/repo --json
```

Execution is allowed only after the provider is wired, its `grok-cli-heat-map` route is
`live_verified`, `mb-heat-map` is installed, and signed-in Clarity/browser capability has been
observed and role-tested. The resulting command uses the byte-validated
`grok --agent ~/.grok/agents/mb-heat-map.md` definition file, never Slack.

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
