# Cross-CLI role registry (Phase 1)

Roles are a loading mechanism inside existing seats. They do not create seats,
change review order, or grant credentials. The canonical definitions are the
JSON files in this directory. Run `./generate.py --help` for destinations and
use `--check` to validate without writing.

The generator writes Claude and Grok agent markdown plus a Codex TOML fragment.
The Codex fragment is intentionally emitted as an owner-applied proposal; this
phase never edits `~/.codex/config.toml`.
