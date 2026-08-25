# Cross-CLI role registry proposal, Phase 1

## Scope

This is a loader for three existing seats, not a seat allocator. The seed
roles are Review D, Heat Map, and Grok Build. The registry maps each role to
the existing seat name and emits host-native definitions for Claude Code and
Grok, plus an owner-applied Codex TOML fragment. It does not change the review
order, create credentials, add an MCP server, or edit any protected config.

`roles/generate.py` validates the schema and writes atomically. Running it
twice with the same inputs produces byte-identical content. `--check` performs
schema validation without writing.

## Mechanical restrictions

Each role has a per-host allowlist and an explicit deny list. The generator
fails if a host tool list is missing/duplicated or if `mcpServers` is not
explicitly denied. Claude and Grok receive frontmatter `tools` allowlists;
Codex receives `tools` and `deny_tools` in the generated fragment. Phase 1
declares no `mcpServers`. Grok Build is the only seed role with write tools,
and its prompt retains isolated-worktree and no-publish boundaries.

The generated roles resolve to these existing seats only:

| Role | Existing seat |
|---|---|
| Review D | Grok Bot Website Visual QA |
| Heat Map | Grok Bot Heat Map |
| Grok Build | Grok Build |

No seat is added to any review order. The order remains Fable → Codex Sol →
Opus 4.8 → Review E, exactly as currently documented.

## 429 metering

`roles/record-429.sh` updates only on text matching a provider 429/rate-limit/
usage-limit signal. It writes an atomic `spent_until` entry to the existing
gitignored `usage-ledger.json`, using the existing rolling five-hour reset
contract unless `MB_429_RESET` is supplied for a test. Timeouts, auth failures,
and arbitrary non-zero exits do nothing. The three existing wrappers call it
after preserving their normal output and exit code.

## Owner-applied configuration

The generator emits `generated/codex-config.toml`; the owner must review and
apply its `[subagents.roles.*]` and `[profiles.*]` blocks to `~/.codex/config.toml`.
This proposal does not edit that file. The Claude/Grok generated files likewise
write only to the requested user agent directories when the owner runs the
generator with its default destinations.

## Doctrine edits requiring owner approval

No doctrine file was changed. If the owner adopts this registry as policy, the
following edits need explicit approval:

* `AGENTS.md:25-29` could add one sentence that roles load inside the named
  seats and cannot alter seat ownership, Google MCP routing, or the entry-point
  rule.
* `AGENTS.md:50-58` could state that role loading does not change the review
  order and that a role granting write tools keeps the existing review floor.
* `DOCTRINE.md:22-36` could add the registry as a definition-loading layer
  beneath the existing authority chain, while retaining “Roles (not models)”
  and “Codex remains the only entry point.”
* `DOCTRINE.md:111-120` could explicitly classify role-file changes with write
  tools as the existing repo/app or standing-config risk class and therefore
  require the already stated cross-family gate where applicable.

These are proposed line ranges, not edits. The registry does not weaken any
existing ban or authorize a new seat.

## Verification record

The implementation verification should run:

```sh
python3 roles/generate.py --check
tmp=$(mktemp -d)
python3 roles/generate.py --claude-dir "$tmp/claude" --grok-dir "$tmp/grok" --codex-output "$tmp/codex.toml"
cp -R "$tmp" "$tmp.before"
python3 roles/generate.py --claude-dir "$tmp/claude" --grok-dir "$tmp/grok" --codex-output "$tmp/codex.toml"
diff -ru "$tmp.before" "$tmp"
MB_USAGE_LEDGER="$tmp/usage-ledger.json" MB_429_RESET="2099-01-01T00:00:00Z" \
  bash roles/record-429.sh grok-heavy 'HTTP 429 rate limit exceeded'
python3 usage-status.py --ledger "$tmp/usage-ledger.json"
```

The write-tool seed requires the requested cross-family review before an
owner lands the wrapper/config integration.
