#!/usr/bin/env python3
"""Atomically install/check the three standing Grok CLI profiles.

This narrow distributor intentionally does not require unrelated live MCP inventory. The full
role generator still validates every role; this path validates only the standing profiles it owns.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
spec = importlib.util.spec_from_file_location("generate_roles_for_sync", HERE / "generate-roles.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

ROLE_NAMES = ("review-d", "heat-map", "marketplace-intelligence")


def expected() -> dict[str, str]:
    roles = json.loads((ROOT / "config" / "roles.json").read_text())["roles"]
    providers = json.loads((ROOT / "config" / "providers.json").read_text())["providers"]
    out = {}
    for name in ROLE_NAMES:
        role = roles.get(name)
        if not isinstance(role, dict) or not role.get("read_only"):
            raise ValueError(f"{name}: missing read-only role definition")
        seat = providers.get(role.get("seat")) or {}
        if seat.get("kind") != "cli" or seat.get("model") != "grok-4.6":
            raise ValueError(f"{name}: seat must be a Grok CLI provider pinned to grok-4.6")
        tools = set((role.get("tools") or {}).get("grok") or [])
        if tools & gen.WRITE_TOOLS:
            raise ValueError(f"{name}: standing Grok profile contains write tools")
        out[f"mb-{name}.md"] = gen.grok(role, name)
    return out


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-home", type=Path, default=Path.home())
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    target = args.target_home / ".grok" / "agents"
    rc = 0
    for filename, body in expected().items():
        path = target / filename
        if args.check:
            if path.is_file() and not path.is_symlink() and path.read_text() == body:
                print(f"OK      {path} (copy)")
            else:
                print(f"BROKEN  {path}")
                rc = 1
        else:
            write_atomic(path, body)
            print(f"SYNCED  {path}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
