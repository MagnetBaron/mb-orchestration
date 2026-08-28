#!/usr/bin/env python3
"""Validate and generate host-native role definitions from the capability-level registry."""
from __future__ import annotations
import argparse, json, os, re, shutil, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULTS = {
    "claude": Path.home() / ".claude/agents",
    "grok": Path.home() / ".grok/agents",
    "codex": ROOT / "generated/codex-config.toml",
}
LEVELS = ("frontier", "sole", "terra", "luna")
HOSTS = ("claude", "grok", "codex")
REQUIRED_ROLES = {"review-d", "heat-map", "grok-build", "seo-research"}
READ_ONLY_TOOLS = {
    "claude": frozenset({"Read", "Glob", "Grep", "WebSearch", "WebFetch"}),
    "grok": frozenset({"Read", "Glob", "Grep", "WebSearch", "WebFetch"}),
    "codex": frozenset({"read_file", "list_dir", "search"}),
}
MCP_MUTATIONS = {
    "gsc-indexing": frozenset({"request_indexing", "batch_request_indexing", "submit_sitemap", "request_url_removal"}),
}
MCP_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
WRITE_TOOLS = frozenset({
    "Bash", "Write", "Edit", "NotebookEdit", "Admin", "publish",
    "write_file", "search_replace", "apply_patch",
})
PROTECTED_CONFIGS = (
    Path.home() / ".codex/config.toml",
    Path.home() / ".claude/settings.json",
    Path.home() / ".grok/config.toml",
)


def provider_levels(levels: dict) -> dict[str, str]:
    mapping = {}
    for level in LEVELS:
        for provider in levels[level]["providers"]:
            if provider in mapping:
                raise ValueError(f"{provider}: provider listed at more than one capability level")
            mapping[provider] = level
    return mapping


def host_config(role: dict, host: str) -> dict:
    if host in role:
        return role[host]
    return {"tools": role.get("tools", {}).get(host)}


def validate(data: dict) -> None:
    if data.get("schema_version") != 2:
        raise ValueError("roles.json must use schema_version 2")
    levels = data.get("capability_levels")
    if not isinstance(levels, dict) or tuple(levels) != LEVELS:
        raise ValueError("capability_levels must declare frontier, sole, terra, and luna in that order")
    for level in LEVELS:
        spec = levels[level]
        providers = spec.get("providers") if isinstance(spec, dict) else None
        if not isinstance(spec, dict) or not spec.get("job"):
            raise ValueError(f"{level}: missing job")
        if not isinstance(providers, list) or not providers or len(providers) != len(set(providers)):
            raise ValueError(f"{level}: providers must be a non-empty unique list")
        if any(not isinstance(p, str) or not p for p in providers):
            raise ValueError(f"{level}: providers must be non-empty names, not model-family requirements")
    mapping = provider_levels(levels)

    aliases = data.get("compatibility_aliases")
    if not isinstance(aliases, dict):
        raise ValueError("compatibility_aliases is required")
    seats = aliases.get("seats")
    review_order = aliases.get("review_order")
    if not isinstance(seats, dict) or not seats:
        raise ValueError("compatibility_aliases.seats must map current seat names to providers")
    if any(v not in mapping for v in seats.values()):
        raise ValueError("compatibility_aliases.seats values must be providers at a capability level")
    if not isinstance(review_order, list) or not review_order or len(review_order) != len(set(review_order)):
        raise ValueError("compatibility_aliases.review_order must be a unique provider list")
    if any(name not in mapping for name in review_order):
        raise ValueError("review_order entries must be replaceable providers, not model families")

    roles = data.get("roles")
    if not isinstance(roles, dict) or not REQUIRED_ROLES.issubset(roles):
        raise ValueError("roles.json must contain the Phase 1 seed roles")
    for name, role in roles.items():
        if not name or not isinstance(role, dict):
            raise ValueError(f"{name}: invalid role")
        if role.get("family") or role.get("model_family"):
            raise ValueError(f"{name}: model-family requirements are not allowed; use capability levels")
        for field in ("description", "prompt"):
            if not role.get(field):
                raise ValueError(f"{name}: missing {field}")
        if role.get("level") not in LEVELS:
            raise ValueError(f"{name}: level must be one of {', '.join(LEVELS)}")
        if role.get("seat") not in mapping:
            raise ValueError(f"{name}: seat must be a provider at a capability level")
        if mapping[role["seat"]] != role["level"]:
            raise ValueError(f"{name}: seat {role['seat']} is a {mapping[role['seat']]} provider, not {role['level']}")
        if not isinstance(role.get("read_only"), bool):
            raise ValueError(f"{name}: read_only must be a boolean role/tool restriction")
        denied = role.get("deny_tools")
        if not isinstance(denied, list) or any(not isinstance(x, str) or not x for x in denied):
            raise ValueError(f"{name}: deny_tools must be a list of names")
        denied_set = set(denied)
        hosts = role.get("hosts", list(HOSTS))
        if not isinstance(hosts, list) or not hosts or len(hosts) != len(set(hosts)) or not set(hosts).issubset(HOSTS):
            raise ValueError(f"{name}: hosts must be a unique subset of claude, grok, codex")
        for host in hosts:
            config = host_config(role, host)
            tools = config.get("tools")
            if not isinstance(tools, list) or not tools or len(tools) != len(set(tools)):
                raise ValueError(f"{name}: {host} tools must be a non-empty unique list")
            if denied_set.intersection(tools):
                raise ValueError(f"{name}: {host} allowlist overlaps deny_tools")
            if role["read_only"] and WRITE_TOOLS.intersection(tools):
                raise ValueError(
                    f"{name}: read_only forbids write tools on any host, including writing agents ({host})"
                )
            if role["read_only"] and not set(tools).issubset(READ_ONLY_TOOLS[host]):
                unknown = sorted(set(tools) - READ_ONLY_TOOLS[host])
                raise ValueError(f"{name}: read_only unknown or non-read-safe tools on {host}: {unknown}")
            if "model" in config and config["model"] != "inherit":
                raise ValueError(f"{name}: host model pins are not allowed; use capability-level provider bindings")
            mcp = config.get("mcpServers", [])
            if not isinstance(mcp, list) or any(not isinstance(x, str) or not x for x in mcp):
                raise ValueError(f"{name}: {host} mcpServers must be a list of names")
            if any(not MCP_NAME.fullmatch(x) for x in mcp):
                raise ValueError(f"{name}: {host} mcpServers must be connector names, not URLs or credentials")
            if host == "grok" and mcp:
                raise ValueError(f"{name}: Grok mcpServers are unsupported until a host adapter emits them")
            mcp_denials = role.get("mcp_deny_tools", {}).get(host, {})
            for server in mcp:
                required = MCP_MUTATIONS.get(server, frozenset())
                denied_server = set(mcp_denials.get(server, []))
                if role["read_only"] and required and not required.issubset(denied_server):
                    raise ValueError(f"{name}: read_only MCP server {server} lacks mutation denials")
        for host in set(role) & set(HOSTS):
            if host not in hosts:
                raise ValueError(f"{name}: config supplied for host {host}, but host is not enabled")


def load(path: Path) -> dict:
    data = json.loads(path.read_text())
    validate(data)
    return data


def restriction_lines(role: dict) -> str:
    if role["read_only"]:
        ro = "yes. Write tools stay denied for every host, including writing agents."
    else:
        ro = "no. Write tools follow this role's host allowlists."
    return (
        f"Capability level: {role['level']}. Providers at a level are replaceable.\n"
        f"Read-only: {ro}\n"
        f"Mechanically denied: {', '.join(role['deny_tools'])}.\n"
    )


def claude(role: dict, name: str) -> str:
    config = host_config(role, "claude")
    lines = [
        "---",
        f"name: mb-{name}",
        f"description: {json.dumps(role['description'])}",
        "tools: " + ", ".join(config["tools"]),
        f"model: {config.get('model', 'inherit')}",
    ]
    for field in ("effort", "memory"):
        if field in config:
            lines.append(f"{field}: {config[field]}")
    if config.get("skills"):
        lines.append("skills: [" + ", ".join(json.dumps(x) for x in config["skills"]) + "]")
    if config.get("mcpServers"):
        lines.append("mcpServers: [" + ", ".join(json.dumps(x) for x in config["mcpServers"]) + "]")
    denied_mcp = role.get("mcp_deny_tools", {}).get("claude", {})
    denied_tools = [tool for server in config.get("mcpServers", []) for tool in denied_mcp.get(server, [])]
    if denied_tools:
        lines.append("disallowedTools: " + ", ".join(denied_tools))
    return "\n".join(lines) + f"\n---\n\n{role['prompt']}\n\n" + restriction_lines(role)


def grok(role: dict, name: str) -> str:
    tools = ", ".join(host_config(role, "grok")["tools"])
    return (
        f"---\nname: mb-{name}\ndescription: {json.dumps(role['description'])}\ntools: {tools}\n"
        f"---\n\n{role['prompt']}\n\n" + restriction_lines(role)
    )


def toml_quote(s: str) -> str:
    return json.dumps(s)


def toml_list(values) -> str:
    return "[" + ", ".join(toml_quote(x) for x in values) + "]"


def codex(data: dict, roles: dict) -> str:
    out = [
        "# Generated role registry fragment. Owner applies this to ~/.codex/config.toml.",
        "# No new seats, credentials, or live MCP connections.",
        "# Capability levels are durable; model and seat names are replaceable providers.",
        "# Existing seats and review order are compatibility aliases only.",
        "",
    ]
    for level in LEVELS:
        spec = data["capability_levels"][level]
        out += [
            f"[capability_levels.{level}]",
            f"job = {toml_quote(spec['job'])}",
            f"providers = {toml_list(spec['providers'])}",
            "",
        ]
    aliases = data["compatibility_aliases"]
    out += [
        "[compatibility_aliases]",
        f"review_order = {toml_list(aliases['review_order'])}",
        "",
        "[compatibility_aliases.seats]",
    ]
    for seat, provider in aliases["seats"].items():
        out.append(f"{toml_quote(seat)} = {toml_quote(provider)}")
    out.append("")
    for name, role in roles.items():
        tools = host_config(role, "codex")["tools"]
        out += [
            f"[subagents.roles.{name}]",
            f"description = {toml_quote(role['description'])}",
            f"level = {toml_quote(role['level'])}",
            f"seat = {toml_quote(role['seat'])}",
            f"read_only = {'true' if role['read_only'] else 'false'}",
            f"prompt = {toml_quote(role['prompt'])}",
            f"tools = {toml_list(tools)}",
            f"deny_tools = {toml_list(role['deny_tools'])}",
            "",
        ]
    for name, role in roles.items():
        out += [
            f"[profiles.mb-{name}]",
            f"role = {toml_quote(name)}",
            f"level = {toml_quote(role['level'])}",
            f"seat = {toml_quote(role['seat'])}",
            "",
        ]
    return "\n".join(out)


def artifacts(data: dict, claude_dir: Path, grok_dir: Path, codex_output: Path) -> dict[Path, str]:
    outputs = {}
    roles = data["roles"]
    for name, role in roles.items():
        hosts = role.get("hosts", list(HOSTS))
        if "claude" in hosts:
            outputs[claude_dir / f"mb-{name}.md"] = claude(role, name)
        if "grok" in hosts:
            outputs[grok_dir / f"mb-{name}.md"] = grok(role, name)
    codex_roles = {
        name: role for name, role in roles.items()
        if "codex" in role.get("hosts", list(HOSTS))
    }
    outputs[codex_output] = codex(data, codex_roles)
    return outputs


def write_atomic(path: Path, text: str) -> None:
    resolved = path.resolve()
    if resolved in {p.resolve() for p in PROTECTED_CONFIGS}:
        raise ValueError(f"refusing to write protected config {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    shutil.move(tmp, path)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--claude-dir", type=Path, default=DEFAULTS["claude"])
    ap.add_argument("--grok-dir", type=Path, default=DEFAULTS["grok"])
    ap.add_argument("--codex-output", type=Path, default=DEFAULTS["codex"])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    data = load(args.root / "roles.json")
    outputs = artifacts(data, args.claude_dir, args.grok_dir, args.codex_output)
    if not args.check:
        for path, text in outputs.items():
            write_atomic(path, text)
    print(f"validated {len(data['roles'])} roles; {'checked' if args.check else f'wrote {len(outputs)} artifacts'}")


if __name__ == "__main__":
    main()
