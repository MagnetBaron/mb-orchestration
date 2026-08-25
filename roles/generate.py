#!/usr/bin/env python3
"""Validate and generate Phase 1 role definitions for three existing hosts."""
from __future__ import annotations
import argparse, json, os, shutil, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULTS = {"claude": Path.home()/".claude/agents", "grok": Path.home()/".grok/agents", "codex": ROOT/"generated/codex-config.toml"}
def load(path):
    data = json.loads(path.read_text())
    if data.get("schema_version") != 1 or not isinstance(data.get("roles"), dict) or set(data["roles"]) != {"review-d", "heat-map", "grok-build"}:
        raise ValueError("roles.json must contain schema_version 1 and exactly the three Phase 1 seed roles")
    for name, role in data["roles"].items():
        if not name or not role.get("description") or not role.get("seat") or not role.get("prompt"):
            raise ValueError(f"{name}: missing description, seat, or prompt")
        denied = set(role.get("deny_tools", []))
        if "mcpServers" not in denied:
            raise ValueError(f"{name}: mcpServers must be explicitly denied")
        for host in ("claude", "grok", "codex"):
            tools = role.get("tools", {}).get(host)
            if not isinstance(tools, list) or not tools or len(tools) != len(set(tools)):
                raise ValueError(f"{name}: {host} tools must be a non-empty unique list")
            if denied.intersection(tools):
                raise ValueError(f"{name}: {host} allowlist overlaps deny_tools")
    return data["roles"]

def claude(role, name):
    tools = ", ".join(role["tools"]["claude"])
    return f"---\nname: mb-{name}\ndescription: {role['description']}\ntools: {tools}\nmodel: inherit\n---\n\n{role['prompt']}\n\nMechanically denied: {', '.join(role['deny_tools'])}.\n"

def grok(role, name):
    tools = ", ".join(role["tools"]["grok"])
    return f"---\nname: mb-{name}\ndescription: {role['description']}\ntools: {tools}\n---\n\n{role['prompt']}\n\nMechanically denied: {', '.join(role['deny_tools'])}.\n"

def toml_quote(s): return json.dumps(s)
def codex(roles):
    out = ["# Generated role registry fragment. Owner applies this to ~/.codex/config.toml.", "# No new seats; these names resolve inside existing seats.", ""]
    for name, role in roles.items():
        out += [f"[subagents.roles.{name}]", f"description = {toml_quote(role['description'])}", f"seat = {toml_quote(role['seat'])}", f"prompt = {toml_quote(role['prompt'])}", "tools = [" + ", ".join(toml_quote(x) for x in role["tools"]["codex"]) + "]", "deny_tools = [" + ", ".join(toml_quote(x) for x in role["deny_tools"]) + "]", ""]
    for name, role in roles.items():
        out += [f"[profiles.mb-{name}]", f"role = {toml_quote(name)}", f"seat = {toml_quote(role['seat'])}", ""]
    return "\n".join(out)

def write_atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    with os.fdopen(fd, "w") as f: f.write(text)
    shutil.move(tmp, path)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--claude-dir", type=Path, default=DEFAULTS["claude"])
    ap.add_argument("--grok-dir", type=Path, default=DEFAULTS["grok"])
    ap.add_argument("--codex-output", type=Path, default=DEFAULTS["codex"])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    roles = load(args.root / "roles.json")
    outputs = {}
    for name, role in roles.items():
        outputs[args.claude_dir/f"mb-{name}.md"] = claude(role, name)
        outputs[args.grok_dir/f"mb-{name}.md"] = grok(role, name)
    outputs[args.codex_output] = codex(roles)
    if not args.check:
        for path, text in outputs.items(): write_atomic(path, text)
    print(f"validated {len(roles)} roles; {'checked' if args.check else f'wrote {len(outputs)} artifacts'}")

if __name__ == "__main__": main()
