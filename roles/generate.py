#!/usr/bin/env python3
"""Validate and generate Phase 1 role definitions for three existing hosts."""
from __future__ import annotations
import argparse, json, os, shutil, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULTS = {"claude": Path.home()/".claude/agents", "grok": Path.home()/".grok/agents", "codex": ROOT/"generated/codex-config.toml"}
def load(path):
    data = json.loads(path.read_text())
    required = {"review-d", "heat-map", "grok-build"}
    if data.get("schema_version") != 1 or not isinstance(data.get("roles"), dict) or not required.issubset(data["roles"]):
        raise ValueError("roles.json must contain schema_version 1 and the three Phase 1 seed roles")
    for name, role in data["roles"].items():
        if not name or not role.get("description") or not role.get("seat") or not role.get("prompt"):
            raise ValueError(f"{name}: missing description, seat, or prompt")
        denied = set(role.get("deny_tools", []))
        hosts = role.get("hosts", ["claude", "grok", "codex"])
        if not isinstance(hosts, list) or not hosts or len(hosts) != len(set(hosts)) or not set(hosts).issubset({"claude", "grok", "codex"}):
            raise ValueError(f"{name}: hosts must be a unique subset of claude, grok, codex")
        for host in hosts:
            host_config = role.get(host, {}) if host in role else {"tools": role.get("tools", {}).get(host)}
            tools = host_config.get("tools")
            if not isinstance(tools, list) or not tools or len(tools) != len(set(tools)):
                raise ValueError(f"{name}: {host} tools must be a non-empty unique list")
            if denied.intersection(tools):
                raise ValueError(f"{name}: {host} allowlist overlaps deny_tools")
            mcp = host_config.get("mcpServers", [])
            if not isinstance(mcp, list) or any(not isinstance(x, str) or not x for x in mcp):
                raise ValueError(f"{name}: {host} mcpServers must be a list of names")
        for host in set(role) & {"claude", "grok", "codex"}:
            if host not in hosts:
                raise ValueError(f"{name}: config supplied for host {host}, but host is not enabled")
    return data["roles"]

def host_config(role, host):
    return role.get(host, {"tools": role.get("tools", {}).get(host)})

def claude(role, name):
    config = host_config(role, "claude")
    lines = ["---", f"name: mb-{name}", f"description: {role['description']}", "tools: " + ", ".join(config["tools"]), f"model: {config.get('model', 'inherit')}" ]
    for field in ("effort", "memory"):
        if field in config: lines.append(f"{field}: {config[field]}")
    if config.get("skills"): lines.append("skills: " + ", ".join(config["skills"]))
    if config.get("mcpServers"): lines.append("mcpServers: [" + ", ".join(json.dumps(x) for x in config["mcpServers"]) + "]")
    return "\n".join(lines) + f"\n---\n\n{role['prompt']}\n\nMechanically denied: {', '.join(role['deny_tools'])}.\n"

def grok(role, name):
    tools = ", ".join(host_config(role, "grok")["tools"])
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
        hosts = role.get("hosts", ["claude", "grok", "codex"])
        if "claude" in hosts: outputs[args.claude_dir/f"mb-{name}.md"] = claude(role, name)
        if "grok" in hosts: outputs[args.grok_dir/f"mb-{name}.md"] = grok(role, name)
    codex_roles = {name: role for name, role in roles.items() if "codex" in role.get("hosts", ["claude", "grok", "codex"])}
    outputs[args.codex_output] = codex(codex_roles)
    if not args.check:
        for path, text in outputs.items(): write_atomic(path, text)
    print(f"validated {len(roles)} roles; {'checked' if args.check else f'wrote {len(outputs)} artifacts'}")

if __name__ == "__main__": main()
