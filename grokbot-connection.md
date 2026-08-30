# Grok standing roles — CLI transport

The active orchestration path no longer communicates with Grok Bot through Slack. The durable
provider ids keep their `grok-bot-*` names for compatibility, but their executable transport is the
installed Grok CLI and named profiles:

| Provider id | CLI agent | Input | Current state |
|---|---|---|---|
| `grok-bot-review-d` | `mb-review-d` | validated preview/live packet | parked: browser/pixels absent |
| `grok-bot-heat-map` | `mb-heat-map` | approved Clarity evidence | parked: signed-in Clarity/browser absent |
| `grok-bot-marketplace-intelligence` | `mb-marketplace-intelligence` | approved deposited evidence | parked pending profile sync + role smoke |

`grok` 1.0.13 exposes `--agent`, `--prompt-file`, `--model`, and related top-level flags. It does not
expose a `grok bot`, `grokbot`, Slack, or routine-management subcommand. The separate cloud Grok Bot
app and its historical Slack routines are a different product and are not controlled by this CLI.

## Exact command contract

`config/seat-exec.json` is authoritative. Every standing role pins `grok-4.6`, the validated full
path to a generated `mb-*.md` agent definition, a prompt file, no subagents, and plain output. `bin/doctor.py` rejects shortened model ids,
wrong agents, reordered/extra flags, permission bypasses, or a non-CLI route. `bin/grok-agent.py`
checks the executable, installed profile, provider/route state, and exact argv before execution.

## Evidence boundary

The definition-file-path command smoke for `mb-review-d` passed on 2026-08-30 and returned
`cli-agent-path-ok`. This proves agent-definition and exact-model
selection only. It does not prove screenshot capture, 390/1280 rendering, authenticated Clarity,
marketplace permission, or a completed role outcome. Slack-era live evidence remains historical and
must never be reused to promote a new CLI route.

The correct failure mode is a visible park:

- Review D: no observed browser/pixel source.
- Heat Map: no observed signed-in Clarity/browser source.
- Marketplace Intelligence: no installed generated profile or one-time role receipt.

Once a missing capability is installed by user action, refresh integration inventory, regenerate
and sync roles, run the role-specific smoke, record evidence, and only then promote its new
`grok-cli-*` route to `live_verified` and set `wired:true`.

Legacy Slack history remains useful only as historical behavior evidence for the old app route. It
is not an active delivery path, fallback, or current capability attestation.
