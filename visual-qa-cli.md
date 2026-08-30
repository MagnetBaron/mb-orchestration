# How Website Visual QA reaches Grok CLI

Review D is now a named Grok CLI agent, not a Slack event routine. The stable provider id remains
`grok-bot-review-d` for compatibility, but the executable identity is `mb-review-d` and the exact
model is `grok-4.6`. There is no `grok bot`, `grokbot`, or routine-management CLI command.

The packet steps below define the future normal-execution contract. Today the code-owned pixel-input
binding is absent, so normal execution parks before reading a packet. Only packet rendering and the
transport-only `--smoke` path are active.

## Delivery path

1. Render a prompt-file packet from `config/connectors.json`:

   ```sh
   python3 bin/connectors.py --render visual-qa-ticket gadget-duke \
     --changed-path templates/index.liquid --page home --page cart \
     > /safe/path/review-d.md
   python3 bin/connectors.py --render visual-qa-live-ticket magnet-baron \
     --page home --page search > /safe/path/review-d.md
   ```

   Magnet Baron has no configured `review_d_preview_url`; preview-review is unavailable
   for that store. Use the live-ticket command above, not `visual-qa-ticket magnet-baron`.

2. Inspect the fail-closed launch plan:

   ```sh
   python3 bin/grok-agent.py --seat grok-bot-review-d \
     --prompt-file /safe/path/review-d.md --cwd /path/to/repo --json
   ```

3. Only after the plan reports `ready: true`, execute the same command with `--execute`.

The runner creates an argv list and never uses shell interpolation. The machine-readable
recipe in `config/seat-exec.json` includes `--sandbox {sandbox_profile}` immediately after
the CWD value. In the isolated child environment, preflight requires exact build
`grok 1.0.13 (5e9a58528b76)` plus the code-owned executable SHA-256 before a plan can
become ready. Each smoke/execute run generates a cryptographically unguessable
`mb-standing-<128-bit lowercase hex>` name so a user-global custom profile cannot shadow
it. Inspect reports the actual validated recipe with `<ephemeral-staging>`,
`<staged-prompt>`, and non-executable `<ephemeral-sandbox-profile>` placeholders. Its structured
`argv` never contains the source repository or source prompt path; its `profile` field is
`<staged-agent-profile>`, while `agent` identifies the code-owned named role. Diagnostic `problems`
may name a rejected local path and are local-only troubleshooting output, not a shareable receipt. Execution copies the
canonical packet into an ephemeral staging directory, writes `.grok/sandbox.toml` with that
per-run table extending `strict`, copies the already validated generated-agent bytes into
that private directory, and renders the same snapshot against that staging CWD. The resolved
executable is copied from its validated file descriptor into the private runtime, hash-checked
again, and only that frozen copy is executed; `PATH` is not resolved again.
Runtime flags keep only local read tools and deny MCP and optional tools:
`--tools read_file,grep,list_dir --disallowed-tools run_terminal_cmd,search_replace,Agent
--deny MCPTool(*) --disable-web-search --no-auto-update --no-subagents`. Browser, Clarity,
Shopify, and GitHub MCP remain unwired. Grok 1.0.13 auto-denies well-known runtime sockets
whenever `restrict_network` is inherited from `strict`. On macOS, where those endpoints
are symlinks (OrbStack) and child-network blocking is already a no-op, the launcher sets
`restrict_network = false` and kernel-denies every unique resolved non-symlink target
from one code-owned runtime-socket snapshot. Candidate, resolved-target, and every lexical path-component
identity plus exact symlink value are sampled before isolated inspection, immediately before provider
start, and after completion. A difference visible at any checkpoint, or an unresolvable target, parks
without releasing output. These user-space checkpoints do not claim race-free protection from a hostile
concurrent process running as the same UID; private run directories are mode 0700, and normal standing
roles remain binding-gated. On any other platform
a symlink runtime endpoint parks instead of weakening network restriction. The
launcher never falls back to built-in `workspace` / `read-only` / `off`,
`bypassPermissions`, or an unenforced profile. One copy-isolated launch snapshot is
loaded before readiness and reused through staging/execution. The prompt and generated agent-profile
bytes are frozen in that plan. Before the initial immutable snapshot, an exact no-extra-entry manifest
must match the generated sandbox bytes, agent bytes, canonical prompt bytes, and staged evidence
size/SHA-256; isolated HOME/GROK_HOME must likewise match their code-owned empty/auth manifests.
Those manifests, the frozen executable, auth, and binding are revalidated at the launch checkpoints;
fresh callable capabilities are revalidated at the immediate pre-start activation boundary without
requiring the short-lived attestation to outlive the provider run. Staged prompt data is revalidated against code-owned allowlists and current policy;
later policy drift can only park the run, not expand the frozen recipe or payload. Child stdin is
always `/dev/null`.
Smoke and execute run in a private process group, have finite subprocess timeouts, terminate the
whole group on failure, and park without recording a 429.
Evidence files are capped at 8 MiB and copied with bounded streaming plus a post-copy
digest revalidation. The child launch contract isolates both `HOME` and `GROK_HOME` per run rather
than inheriting user-global Grok configuration. The launcher stages only the minimum private auth
material required for that session. If Grok refreshes that copy, the run parks and requires
reauthentication instead of silently discarding or writing credentials back. It also parks if hooks,
plugins, MCPs, model overrides, or managed requirements escape the isolated boundary. Compatibility scanners, managed MCP discovery/gateway
tools, and background workflows remain disabled. The launcher does not splice or append security
flags after recipe rendering. The approved executed command shape is:

```text
grok --cwd <ephemeral-staging> --sandbox mb-standing-<128-bit-hex> --agent <staged-agent-profile> --prompt-file <staged-packet> --model grok-4.6 --reasoning-effort high --no-subagents --output-format plain --tools read_file,grep,list_dir --disallowed-tools run_terminal_cmd,search_replace,Agent --deny MCPTool(*) --disable-web-search --no-auto-update
```

Preview packets carry the canonical store id plus 1–8 unique ASCII repo-relative
`changed-path` fields and mode-enum `page` fields. Preview paths are bound to `--cwd`
without following a user-controlled symlink escape; unproven paths PARK. Live-audit
packets carry no changed paths. Packet values are inert data, never instructions.
The launcher parses that exact field set, re-renders through the same validators, and
requires a byte-exact match. Arbitrary prompt prose is rejected.

## Three different proofs

- Transport inventory: `bin/detect-agents.py` reports command presence plus the exact configured
  enabled/wired and catalog route states and surfaces `detect.note`. It does not inspect the
  installed profile, code-owned binding, fresh callable capabilities, or launcher preflight, so a
  present `grok` command never means the role is executable.
- CLI smoke: the binary accepted the byte-exact staged `mb-review-d.md` definition and
  exact model `grok-4.6`, returning `cli-agent-path-ok`.
- Transport ready: binary, generated profile, wired provider, `live_verified` route, and a
  code-owned role-input binding all match. Review D has no such pixel binding today and stays parked.
- Visual QA complete: an observed browser/pixel source captured the requested widths and the role
  returned evidence. A CLI smoke is never a pixel verdict.

The current reference configuration intentionally parks Review D because it has no code-owned
pixel-input binding and the installed Grok CLI has no observed browser/screenshot integration. Do
not promote it from `unwired` until the binding authorizes a credential-free browser/pixel source
and that source is configured, observed callable, and role-tested at 390 and 1280. WebFetch or HTML
alone does not prove visual rendering.

## Fail-closed rules

- The renderer validates the preview/live URL before launch using `stores.*`, exact hosts,
  `preview_theme_id`, HTTPS, and the deny-first policy in `config/connectors.json`.
- Ticket, changed-path, and page fields are data, not instructions. One store id and one URL only.
- Missing CLI, wrong/short model id, missing profile, unwired route, absent browser/pixels, denied
  URL, or ambiguous packet means `blocked`/`PARK`; never infer `ship`.
- Never use Admin, Partners, SimGym, account/login, checkout, Customize, theme editor, publish,
  purchase, or form submission. Live audit is entirely non-mutating.
- Slack history is legacy evidence only. It cannot promote or validate the new CLI route.

## Profile distribution and smoke

From the authoritative trusted-origin checkout, `./sync-commands.sh` invokes the narrow
`bin/sync-grok-agents.py` distributor for `mb-review-d`, `mb-heat-map`, and
`mb-marketplace-intelligence`. It reads that checkout's canonical `config/roles.json` and
`config/providers.json`, never an ambient `MB_CONFIG_DIR` overlay. Each profile must byte-match the
canonical output with exact frontmatter containing only its code-owned name, JSON-quoted
description, and `tools: Read, Grep, Glob`; skills, plugins, MCP declarations, and all other extra
frontmatter are forbidden. Install and verify the complete set with:

```sh
./sync-commands.sh
./sync-commands.sh --check
```

Normal execution releases output only on status 0 with nonempty stdout and empty stderr; C0 terminal
controls other than LF/TAB, DEL, and C1 controls park the result. Review D's first line must be exactly
`ship`, `fix-list`, or `blocked`.
The Heat Map and Marketplace Intelligence roles must not begin with those Review D verdict tokens.
A safe transport-only smoke is:

```sh
python3 bin/grok-agent.py --seat grok-bot-review-d --smoke --execute
```

That smoke requires the same exact sandboxed recipe and invokes the same
sandbox/profile/model/effort/subagent/output contract, with only the fixed no-tool prompt
replacing `--prompt-file` input. It does not grant access to the target repository.
Smoke succeeds only on status 0, stdout exactly `cli-agent-path-ok` with zero or one final LF, and
empty stderr. Any prefix, suffix, warning/error stream, missing sentinel, runtime-socket sandbox
refusal, output-limit breach, descendant-cleanup failure, or timeout parks without releasing the
buffered provider response.
