# Grok standing roles — CLI transport

The active orchestration path no longer communicates with Grok Bot through Slack. The durable
provider ids keep their `grok-bot-*` names for compatibility, but their executable transport is the
installed Grok CLI and named profiles:

| Provider id | CLI agent | Input | Current state |
|---|---|---|---|
| `grok-bot-review-d` | `mb-review-d` | validated preview/live packet | parked: no code-owned pixel-input deposit |
| `grok-bot-heat-map` | `mb-heat-map` | approved Clarity evidence | parked: no code-owned signed-in Clarity deposit |
| `grok-bot-marketplace-intelligence` | `mb-marketplace-intelligence` | approved deposited evidence | parked: no code-owned authorized deposit manifest |

`grok` 1.0.13 exposes `--agent`, `--prompt-file`, `--model`, and related top-level flags. It does not
expose a `grok bot`, `grokbot`, Slack, or routine-management subcommand. The separate cloud Grok Bot
app and its historical Slack routines are a different product and are not controlled by this CLI.

## Exact command contract

`config/seat-exec.json` is authoritative. Every standing role pins `grok-4.6`, the validated full
path to a generated `mb-*.md` agent definition, a prompt file, no subagents, and plain output. `bin/doctor.py` rejects shortened model ids,
wrong agents, reordered/extra flags, permission bypasses, or a non-CLI route. For normal execution,
`bin/grok-agent.py` checks the executable, installed profile, exact enabled/wired provider state,
live route, binding, fresh capabilities, and exact argv. The fixed transport-only smoke intentionally
does not claim or require normal provider/route/capability readiness.

## Evidence boundary

The definition-file-path command smoke for `mb-review-d` passed on 2026-08-30 and returned
`cli-agent-path-ok`. This proves agent-definition and exact-model
selection only. It does not prove screenshot capture, 390/1280 rendering, authenticated Clarity,
marketplace permission, or a completed role outcome. Slack-era live evidence remains historical and
must never be reused to promote a new CLI route.

The correct failure mode is a visible park:

- Review D: no code-owned browser/pixel input binding.
- Heat Map: no code-owned signed-in Clarity input binding.
- Marketplace Intelligence: prompt-declared paths, sources, classes, and hashes are not transfer
  authorization; no code-owned approved-deposit manifest exists.

Before any normal role can be promoted, implement its code-owned input boundary. That boundary must
authorize and classify the source before reading or staging its payload; a prompt cannot classify
itself. Then refresh integration inventory, regenerate and sync roles, run the role-specific test,
record evidence, and only then promote its new `grok-cli-*` route to `live_verified` and set
`wired:true`. A transport-only smoke can run while normal execution remains parked.

Legacy Slack history remains useful only as historical behavior evidence for the old app route. It
is not an active delivery path, fallback, or current capability attestation.
