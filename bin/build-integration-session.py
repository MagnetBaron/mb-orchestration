#!/usr/bin/env python3
"""Bind a trusted runtime tool inventory to exactly one resolver invocation.

Input on stdin is a bounded JSON object whose keys are runtime tool names and
whose values are booleans. The bridge retains no tool arguments or metadata,
creates a fresh one-use in-memory attestation, and calls resolve-route once:

  printf '%s' '{"mcp__github__get_me":true,"mcp__github__get_file_contents":true}' | \
    bin/build-integration-session.py --runtime codex -- \
      --class repo-code --scale routine --json --no-record

The envelope, challenge, raw names, and aliases are never written to disk.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import integrations  # noqa: E402


def _load_resolver():
    spec = importlib.util.spec_from_file_location("resolve_route_session_bridge", HERE / "resolve-route.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _split_argv(argv: list[str]) -> tuple[list[str], list[str]]:
    try:
        separator = argv.index("--")
    except ValueError:
        raise ValueError("a '--' separator followed by resolve-route arguments is required") from None
    bridge_args, resolver_args = argv[:separator], argv[separator + 1:]
    if not resolver_args:
        raise ValueError("resolve-route arguments are required after '--'")
    if any(arg == "--integration-session" or arg.startswith("--integration-session=")
           for arg in resolver_args):
        raise ValueError("a second integration session is forbidden")
    return bridge_args, resolver_args


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        bridge_argv, resolver_argv = _split_argv(argv)
    except ValueError as exc:
        print(f"build-integration-session: {exc}", file=sys.stderr)
        return 2
    ap = argparse.ArgumentParser(
        description="Bind a bounded runtime tool inventory to one resolver invocation."
    )
    ap.add_argument("--runtime", required=True, choices=["codex"])
    args = ap.parse_args(bridge_argv)
    try:
        raw = sys.stdin.buffer.read(integrations.RUNTIME_TOOLS_MAX_BYTES + 1)
        overlay = integrations.build_runtime_tool_overlay(args.runtime, raw)
    except (integrations.InventoryError, OSError) as exc:
        print(f"build-integration-session: invalid runtime tool inventory (fail closed): {exc}",
              file=sys.stderr)
        return 2
    resolver = _load_resolver()
    try:
        return resolver.main(resolver_argv, integration_overlay=overlay)
    finally:
        integrations.clear_process_session()


if __name__ == "__main__":
    raise SystemExit(main())
