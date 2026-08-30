# How Website Visual QA reaches Grok CLI

Review D is now a named Grok CLI agent, not a Slack event routine. The stable provider id remains
`grok-bot-review-d` for compatibility, but the executable identity is `mb-review-d` and the exact
model is `grok-4.6`. There is no `grok bot`, `grokbot`, or routine-management CLI command.

## Delivery path

1. Render a prompt-file packet from `config/connectors.json`:

   ```sh
   python3 bin/connectors.py --render visual-qa-ticket gadget-duke \
     --changed-path templates/index.liquid --page home --page cart \
     > /safe/path/review-d.md
   python3 bin/connectors.py --render visual-qa-live-ticket magnet-baron \
     --page home --page search > /safe/path/review-d.md

   Magnet Baron has no configured `review_d_preview_url`; preview-review is unavailable
   for that store. Use the live-ticket command above, not `visual-qa-ticket magnet-baron`.
   ```

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
`<staged-prompt>`, and non-executable `<ephemeral-sandbox-profile>` placeholders, never
the source repository, source prompt path, or live profile name. Execution copies the
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
from its code-owned runtime-socket candidate list. On any other platform a symlink runtime endpoint parks instead of weakening
network restriction. Unresolvable socket targets park before provider invocation. The
launcher never falls back to built-in `workspace` / `read-only` / `off`,
`bypassPermissions`, or an unenforced profile. One copy-isolated launch snapshot is
loaded before readiness and reused through staging/execution. The prompt and generated agent-profile
bytes are frozen in that plan. Staged prompt data is revalidated against code-owned allowlists and
current policy; later policy drift can only park the run, not expand the frozen recipe or payload.
Smoke and execute have finite subprocess timeouts and park without recording a 429.
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

- CLI smoke: the binary accepted the byte-exact staged `mb-review-d.md` definition and
  exact model `grok-4.6`, returning `cli-agent-path-ok`.
- Transport ready: binary, generated profile, wired provider, `live_verified` route, and a
  code-owned role-input binding all match. Review D has no such pixel binding today and stays parked.
- Visual QA complete: an observed browser/pixel source captured the requested widths and the role
  returned evidence. A CLI smoke is never a pixel verdict.

The current reference configuration intentionally parks Review D because the installed Grok CLI
has no observed browser/screenshot integration. Do not promote it from `unwired` until a
credential-free browser/pixel source is configured, observed callable, and role-tested at 390 and
1280. WebFetch or HTML alone does not prove visual rendering.

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

`python3 bin/generate-roles.py` generates `mb-review-d`, `mb-heat-map`, and
`mb-marketplace-intelligence`. Installed profiles must byte-match generated output. A safe
transport-only smoke is:

```sh
python3 bin/grok-agent.py --seat grok-bot-review-d --smoke --execute
```

That smoke requires the same exact sandboxed recipe and invokes the same
sandbox/profile/model/effort/subagent/output contract, with only the fixed no-tool prompt
replacing `--prompt-file` input. It does not grant access to the target repository.
A missing `cli-agent-path-ok` sentinel, a runtime-socket sandbox refusal, or a timeout
parks the smoke.
