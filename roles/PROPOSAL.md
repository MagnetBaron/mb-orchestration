# Cross-CLI role registry proposal, Phase 1

## Scope

This is a loader inside existing seats, not a seat allocator. The seed roles
are Review D, Heat Map, Grok Build, and the read-only SEO Research role. The
registry maps each role to a durable capability level and emits host-native
definitions for Claude Code and Grok, plus an owner-applied Codex TOML
fragment. It does not change the review order, create credentials, add an MCP
server, or edit any protected config.

`roles/generate.py` validates the schema and writes atomically. Running it
twice with the same inputs produces byte-identical content. `--check` performs
schema validation without writing.

## Capability levels

Routing requirements are capability levels, not models or model families.
Providers bound to a level are replaceable. The four levels are:

| Level | Job | Current providers (replaceable) |
|---|---|---|
| frontier | Hard review, architecture, land-gate judgment | fable-5, opus-4.8, review-e |
| sole | Scarce judgment: diff review and MCP interpretation | codex-sol |
| terra | Volume: MCP bulk, implementation, standing bot work | gpt-terra, grok-build, grok-bot-review-d, grok-bot-heat-map |
| luna | Dispatch only: queue, assign, status, risk gate | codex-luna |

The compatibility review gate remains governed by the unchanged doctrine and
`AGENTS.md`; this registry does not redefine cross-family independence. Replacing
a provider does not change the level or invent a seat. Owner-approved doctrine
edits may later express independence as a qualified binding property.

## Compatibility aliases

Existing seat names and the current review order are aliases of the provider
bindings above. They are preserved so today's dispatch docs keep working; they
are not model-family requirements.

| Alias | Provider | Level |
|---|---|---|
| Review A | fable-5 | frontier |
| Review B | codex-sol | sole |
| Review C | opus-4.8 | frontier |
| Review E | review-e | frontier |
| Review D | grok-bot-review-d | terra |
| Heat Map | grok-bot-heat-map | terra |
| Grok Build | grok-build | terra |
| MCP volume | gpt-terra | terra |
| Dispatch | codex-luna | luna |

Review-order alias (unchanged): fable-5 → codex-sol → opus-4.8 → review-e.
No seat is added to that order.

The generated roles still resolve only to existing seats:

| Role | Level | Existing seat | Read-only |
|---|---|---|---|
| Review D | terra | Grok Bot Website Visual QA | yes |
| Heat Map | terra | Grok Bot Heat Map | yes |
| Grok Build | terra | Grok Build | no |
| SEO Research | terra | Grok Build (existing seat), with Claude host configuration | yes |

## Mechanical restrictions

Each role has a per-host allowlist and an explicit deny list. `read_only` is a
role/tool capability restriction: when true, write tools are forbidden on every
host, including writing agents. It is not a Grok-only ban. The generator fails
if a host tool list is missing/duplicated, a disabled host has config, a
read-only role allows write tools, a seat/level pair does not match a provider,
or an MCP declaration is malformed.

Claude and Grok receive frontmatter allowlists; Codex receives `tools` and
`deny_tools` in the generated fragment. MCP entries are connector names only.
This commit does not add credentials or open a live MCP connection. Hosts
without a declared connector simply omit `mcpServers`; no host is forbidden by
identity.

Grok Build remains the only seed role that is not read-only. Its prompt retains
isolated-worktree and no-publish boundaries. SEO Research keeps the requested
`seo-ops` skill and `gsc-indexing`/`dfs-mcp` name declarations on Claude.

## 429 metering

`roles/record-429.sh` updates only on text matching a provider 429/rate-limit/
usage-limit signal. It writes an atomic `spent_until` entry to the existing
gitignored `usage-ledger.json`, using the existing rolling five-hour reset
contract unless `MB_429_RESET` is supplied for a test. Timeouts, auth failures,
and arbitrary non-zero exits do nothing. The three existing wrappers call it
after preserving their normal output and exit code.

## Owner-applied configuration

The generator emits `generated/codex-config.toml`; the owner must review and
apply its `[capability_levels.*]`, `[subagents.roles.*]`, and `[profiles.*]`
blocks to `~/.codex/config.toml`. This proposal does not edit that file, nor
`~/.claude/settings.json`, nor `~/.grok/config.toml`. The Claude/Grok generated
files write only to the requested user agent directories when the owner runs
the generator with its default destinations.

## Doctrine edits requiring owner approval

No doctrine file was changed. If the owner adopts this registry as policy, the
following edits need explicit approval:

* `AGENTS.md:25-29` could add one sentence that roles load inside the named
  seats, route by capability level, and cannot alter seat ownership, Google MCP
  routing, or the entry-point rule.
* `AGENTS.md:50-58` could state that role loading does not change the review
  order alias and that a role granting write tools keeps the existing review
  floor.
* `DOCTRINE.md:22-36` could add the registry as a definition-loading layer
  beneath the existing authority chain, while retaining “Roles (not models)”
  and “Codex remains the only entry point,” with frontier/sole/terra/luna as
  the durable classes and current seat names as aliases.
* `DOCTRINE.md:111-120` could explicitly classify role-file changes with write
  tools as the existing repo/app or standing-config risk class and therefore
  retain the already stated cross-family gate where applicable.

These are proposed line ranges, not edits. The registry does not weaken any
existing ban or authorize a new seat.

## Verification record

The implementation verification should run:

```sh
python3 roles/generate.py --check
python3 roles/test_generate.py
tmp=$(mktemp -d)
python3 roles/generate.py --claude-dir "$tmp/claude" --grok-dir "$tmp/grok" --codex-output "$tmp/codex.toml"
cp -R "$tmp" "$tmp.before"
python3 roles/generate.py --claude-dir "$tmp/claude" --grok-dir "$tmp/grok" --codex-output "$tmp/codex.toml"
diff -ru "$tmp.before" "$tmp"
python3 -c 'import tomllib, pathlib, sys; tomllib.loads(pathlib.Path(sys.argv[1]).read_text())' "$tmp/codex.toml"
MB_USAGE_LEDGER="$tmp/usage-ledger.json" MB_429_RESET="2099-01-01T00:00:00Z" \
  bash roles/record-429.sh grok-heavy 'HTTP 429 rate limit exceeded'
python3 usage-status.py --ledger "$tmp/usage-ledger.json"
git diff --check
```

A write-capable seed role and named MCP declarations still require the
requested cross-family review before an owner lands the wrapper/config
integration. The MCP servers remain owner-applied config; this commit does not
connect or test them live.
