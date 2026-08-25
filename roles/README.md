# Cross-CLI role registry (Phase 1)

Roles are a loading mechanism inside existing seats. They do not create seats,
change review order, or grant credentials. Routing uses durable capability
levels (`frontier`, `sole`, `terra`, `luna`). Model and seat names are
replaceable providers at a level; the current seats and review order are
compatibility aliases.

`read_only` is a role/tool restriction for any writing agent, not a host-specific
ban. The canonical definitions are `roles.json` in this directory, currently
covering four roles. Run `./generate.py --help` for destinations and use
`--check` to validate without writing.

The generator writes Claude and Grok agent markdown plus a Codex TOML fragment.
The Codex fragment is intentionally emitted as an owner-applied proposal; this
phase never edits `~/.codex/config.toml`.
