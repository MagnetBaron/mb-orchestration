#!/usr/bin/env python3
"""Atomically install/check the three standing Grok CLI profiles.

This narrow distributor intentionally does not require unrelated live MCP inventory. The full
role generator still validates every role; this path validates only the standing profiles it owns.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import tempfile
from pathlib import Path

import mborch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
spec = importlib.util.spec_from_file_location("generate_roles_for_sync", HERE / "generate-roles.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

ROLE_NAMES = ("review-d", "heat-map", "marketplace-intelligence")
STANDING_GROK_TOOLS = {
    "review-d": ("Read", "Grep", "Glob"),
    "heat-map": ("Read", "Grep", "Glob"),
    "marketplace-intelligence": ("Read", "Grep", "Glob"),
}


def grok_tools_from_profile(text: str) -> tuple[str, ...] | None:
    if not isinstance(text, str) or not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    tools = None
    for line in text[4:end].splitlines():
        if line.startswith("tools:"):
            if tools is not None:
                return None
            names = tuple(part.strip() for part in line[6:].split(",") if part.strip())
            if not names:
                return None
            tools = names
    return tools


def standing_tools_problem(role_name: str, tools) -> str | None:
    allowed = STANDING_GROK_TOOLS.get(role_name)
    if allowed is None:
        return f"{role_name}: unknown standing Grok role"
    if tools is None:
        return f"{role_name}: standing Grok profile is missing an exact tools allowlist"
    if tuple(tools) != allowed:
        return f"{role_name}: standing Grok tools must be exact {list(allowed)!r}"
    return None


def expected() -> dict[str, str]:
    roles = mborch.load_config("roles.json", required=True)["roles"]
    providers = mborch.load_config("providers.json", required=True)["providers"]
    out = {}
    for name in ROLE_NAMES:
        role = roles.get(name)
        if not isinstance(role, dict) or not role.get("read_only"):
            raise ValueError(f"{name}: missing read-only role definition")
        seat = providers.get(role.get("seat")) or {}
        if seat.get("kind") != "cli" or seat.get("model") != "grok-4.6":
            raise ValueError(f"{name}: seat must be a Grok CLI provider pinned to grok-4.6")
        declared = (role.get("tools") or {}).get("grok")
        problem = standing_tools_problem(name, declared)
        if problem:
            raise ValueError(problem)
        body = gen.grok(role, name)
        rendered = grok_tools_from_profile(body)
        problem = standing_tools_problem(name, rendered)
        if problem:
            raise ValueError(problem)
        out[f"mb-{name}.md"] = body
    return out


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-home", type=Path, default=Path.home())
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    target = args.target_home / ".grok" / "agents"
    try:
        profiles = expected()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ERROR   cannot generate Grok profiles: {exc}")
        return 2
    rc = 0
    for filename, body in profiles.items():
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
