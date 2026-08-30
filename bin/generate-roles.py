#!/usr/bin/env python3
"""Validate and generate host-native role definitions from the capability-level registry.

Reads TWO config files:
  * config/providers.json — capability levels, families, provider→level bindings, review_order
                            (the single source; roles must resolve onto these providers).
  * config/roles.json     — role definitions (a loading mechanism inside existing seats).

Emits Claude and Grok agent markdown plus an owner-applied Codex TOML fragment.
Running twice with identical inputs produces byte-identical output. `--check`
validates without writing. It never edits a protected host config.
"""
from __future__ import annotations
import argparse, json, os, re, shutil, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mborch  # noqa: E402
import routing  # noqa: E402
import integrations  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULTS = {
    "roles": mborch.find_config("roles.json"),
    "providers": mborch.find_config("providers.json"),
    "claude": Path.home() / ".claude/agents",
    "grok": Path.home() / ".grok/agents",
    "codex": HERE.parent / "generated/codex-config.toml",
}
LEVELS = ("frontier", "sole", "terra", "luna")
HOSTS = ("claude", "grok", "codex")
REQUIRED_ROLES = {"review-d", "heat-map", "grok-build", "seo-research"}
READ_ONLY_TOOLS = {
    "claude": frozenset({"Read", "Glob", "Grep", "WebSearch", "WebFetch"}),
    "grok": frozenset({"Read", "Glob", "Grep", "WebSearch", "WebFetch"}),
    "codex": frozenset({"read_file", "list_dir", "search"}),
}
MCP_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


def mcp_mutation_map(runtime: str, inventory=None):
    """Observed-effective MCP connectors → mutating tools from the vetted connector ceiling.
    A connector ABSENT from this map is UNVETTED: a read_only role may not declare it (fail-closed,
    H1). A connector present with an empty set is explicitly known read-safe. Both the connector name
    and its declared `alias` (e.g. dataforseo / dfs-mcp) are registered. Static active state
    alone never enters this map."""
    c = mborch.load_config("connectors.json", required=False)
    out = {}
    adapters = integrations.load_adapters()
    for name, meta in (c.get("mcp_connectors") or {}).items():
        if not routing.connector_is_active(meta):
            continue  # primed/ready/missing/unknown are inert — not a vetted live MCP
        authorized = any(
            integrations.provider_runtime(pid, adapters) == runtime
            for pid in (meta.get("available_on") or [])
        )
        observed, _reason = integrations.effective(
            runtime, "mcp", name, require_callable=True, inv=inventory
        )
        if not authorized or not observed:
            continue
        muts = set(meta.get("mutating_tools", []))
        out[name] = muts
        alias = meta.get("alias")
        if alias:
            out[alias] = muts
    return out
WRITE_TOOLS = frozenset({
    "Bash", "Write", "Edit", "NotebookEdit", "Admin", "publish",
    "write_file", "search_replace", "apply_patch",
})
PROTECTED_CONFIGS = (
    Path.home() / ".codex/config.toml",
    Path.home() / ".claude/settings.json",
    Path.home() / ".grok/config.toml",
)


def skills_registry() -> dict:
    """Vetted skills registry from skills.json (single source), keyed by `plugin:skill` id.
    A skill ABSENT from this map is UNVETTED: a role may not bind it (fail-closed — the same H1
    rule connectors.json enforces for MCP). Returns the raw per-skill metadata map."""
    s = mborch.load_config("skills.json", required=False)
    reg = s.get("skills") if isinstance(s, dict) else None
    return reg if isinstance(reg, dict) else {}


def plugin_source_dir(plugin: str) -> Path:
    """Resolve a plugin name to its on-disk source dir via the repo marketplace
    (.claude-plugin/marketplace.json), falling back to plugins/<plugin>. This is what makes an
    in-repo `plugin:skill` id HOST-DISCOVERABLE rather than a dangling reference."""
    mkt = mborch.REPO / ".claude-plugin" / "marketplace.json"
    if mkt.exists():
        try:
            data = json.loads(mkt.read_text())
        except Exception:
            data = {}
        for entry in data.get("plugins", []):
            if isinstance(entry, dict) and entry.get("name") == plugin:
                src = str(entry.get("source") or "").lstrip("./").rstrip("/")
                if src:
                    return mborch.REPO / src
    return mborch.REPO / "plugins" / plugin


def skill_md_path(skill_id: str) -> Path:
    """The in-repo SKILL.md a `plugin:skill` id resolves to (plugins/<plugin>/skills/<skill>/SKILL.md)."""
    plugin, _, name = skill_id.partition(":")
    return plugin_source_dir(plugin) / "skills" / name / "SKILL.md"


def seat_has_capability(seat: str, cap, providers_data: dict, connectors: dict, inventory=None) -> bool:
    """A seat satisfies `cap` only through `routing.capabilities_of`.

    Connector IDs and aliases are always derived (even if they equal a coarse word) and
    are granted only by an explicitly active matching connector whose lifecycle predicate
    passes and whose `available_on` includes the seat. A class label follows the catalog
    coarse exception. Coarse provider capability labels never grant a derived label
    (primed/ready/missing/unknown stay inert even if the name was copied into capabilities).
    None = no capability gate.
    """
    if cap is None:
        return True
    prov = (providers_data.get("providers") or {}).get(seat, {})
    return cap in routing.capabilities_of(seat, prov, connectors, inventory=inventory)


def provider_levels(providers_data: dict) -> dict[str, str]:
    """Build provider→level from providers.json, validating the level blocks."""
    levels = providers_data.get("capability_levels")
    if not isinstance(levels, dict) or tuple(levels) != LEVELS:
        raise ValueError("providers.json capability_levels must declare frontier, sole, terra, luna in that order")
    provs = providers_data.get("providers")
    if not isinstance(provs, dict) or not provs:
        raise ValueError("providers.json must define a non-empty providers map")
    mapping: dict[str, str] = {}
    for pid, p in provs.items():
        if not isinstance(p, dict):
            raise ValueError(f"{pid}: provider entry must be an object")
        if p.get("family") in (None, "") or not isinstance(p.get("functions"), list) or not p["functions"]:
            raise ValueError(f"{pid}: provider needs a family and a non-empty functions list")
        lvl = p.get("level")
        if lvl not in LEVELS:
            raise ValueError(f"{pid}: level must be one of {', '.join(LEVELS)}")
        mapping[pid] = lvl
    order = providers_data.get("review_order")
    if not isinstance(order, list) or not order or len(order) != len(set(order)):
        raise ValueError("providers.json review_order must be a unique non-empty list")
    if any(pid not in mapping for pid in order):
        raise ValueError("providers.json review_order entries must be defined providers")
    # Forbidden models are the explicit providers.json map only (Opus 5 is not auto-banned).
    for pid, p in provs.items():
        if mborch.model_is_forbidden(p.get("model"), providers_data.get("forbidden_models")):
            raise ValueError(f"{pid}: selects forbidden model {p.get('model')!r}")
    return mapping


def host_config(role: dict, host: str) -> dict:
    if host in role:
        return role[host]
    return {"tools": role.get("tools", {}).get(host)}


def validate_roles(roles_data: dict, mapping: dict[str, str], providers_data: dict, inventory=None) -> None:
    if roles_data.get("schema_version") != 3:
        raise ValueError("roles.json must use schema_version 3")
    roles = roles_data.get("roles")
    if not isinstance(roles, dict) or not REQUIRED_ROLES.issubset(roles):
        raise ValueError("roles.json must contain the seed roles")
    skills_reg = skills_registry()
    connectors = mborch.load_config("connectors.json", required=False) or {}
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
            raise ValueError(f"{name}: seat must be a provider defined in providers.json")
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
            mut = mcp_mutation_map(host, inventory=inventory)
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
            mcp_all = connectors.get("mcp_connectors") or {}
            alias_to_name = {n: n for n in mcp_all}
            for n, m in mcp_all.items():
                if m.get("alias"):
                    alias_to_name[m["alias"]] = n
            for server in mcp:
                real = alias_to_name.get(server)
                if real and not routing.connector_is_active(mcp_all.get(real) or {}):
                    raise ValueError(
                        f"{name}: {host} MCP connector {server!r} is not active "
                        f"(status={(mcp_all.get(real) or {}).get('status')!r}; "
                        "missing/unknown/primed/ready are inert)"
                    )
                denied_server = set(mcp_denials.get(server, []))
                if role["read_only"]:
                    if server not in mut:
                        raise ValueError(
                            f"{name}: read_only MCP connector {server!r} is UNVETTED — declare it in "
                            "connectors.json mcp_connectors (with its mutating_tools) before a read_only "
                            "role may use it (fail-closed, H1)")
                    required = mut[server]
                    if required and not required.issubset(denied_server):
                        raise ValueError(f"{name}: read_only MCP server {server} lacks mutation denials")
            skills_declared = config.get("skills", [])
            if not isinstance(skills_declared, list) or any(not isinstance(x, str) or not x for x in skills_declared):
                raise ValueError(f"{name}: {host} skills must be a list of plugin:skill ids")
            for sid in skills_declared:
                meta = skills_reg.get(sid)
                if not isinstance(meta, dict):
                    raise ValueError(
                        f"{name}: {host} binds skill {sid!r} that is NOT in the skills registry "
                        "(config/skills.json) — register it before a role may bind it (fail-closed)")
                if not skill_md_path(sid).exists():
                    raise ValueError(
                        f"{name}: {host} binds skill {sid!r} but its SKILL.md is missing at "
                        f"{skill_md_path(sid)} — the in-repo plugin skill is unresolvable (fail-closed)")
                if host not in (meta.get("hosts") or []):
                    raise ValueError(
                        f"{name}: {host} binds skill {sid!r}, which the registry does not offer on host {host}")
                plugin = sid.partition(":")[0]
                plugin_ok, plugin_reason = integrations.plugin_effective(host, plugin, inv=inventory)
                if not plugin_ok:
                    raise ValueError(
                        f"{name}: {host} plugin {plugin!r} is not observed effective ({plugin_reason}) — "
                        "installed/enabled proof is required before binding (fail-closed)")
                if meta.get("kind") == "write" and role["read_only"]:
                    raise ValueError(
                        f"{name}: read_only role may not bind write-skill {sid!r} "
                        "(a write skill reaching a read-only seat — fail-closed)")
                cap = meta.get("required_capability")
                if not seat_has_capability(role["seat"], cap, providers_data, connectors, inventory=inventory):
                    raise ValueError(
                        f"{name}: seat {role['seat']!r} lacks capability {cap!r} required by skill {sid!r} "
                        "(active connector available_on, or a non-connector coarse capability) — fail-closed")
        for host in set(role) & set(HOSTS):
            if host not in hosts:
                raise ValueError(f"{name}: config supplied for host {host}, but host is not enabled")


def load(roles_path: Path, providers_path: Path, inventory=None) -> dict:
    providers_data = json.loads(Path(providers_path).read_text())
    roles_data = json.loads(Path(roles_path).read_text())
    mapping = provider_levels(providers_data)
    validate_roles(roles_data, mapping, providers_data, inventory=inventory)
    return {"providers": providers_data, "roles": roles_data["roles"], "mapping": mapping}


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
        lines.append("skills: " + ", ".join(config["skills"]))
    if config.get("mcpServers"):
        lines.append("mcpServers: [" + ", ".join(json.dumps(x) for x in config["mcpServers"]) + "]")
    denied_mcp = role.get("mcp_deny_tools", {}).get("claude", {})
    denied_tools = [tool for server in config.get("mcpServers", []) for tool in denied_mcp.get(server, [])]
    if denied_tools:
        lines.append("disallowedTools: " + ", ".join(denied_tools))
    return "\n".join(lines) + f"\n---\n\n{role['prompt']}\n\n" + restriction_lines(role)


def grok(role: dict, name: str) -> str:
    config = host_config(role, "grok")
    tools = ", ".join(config["tools"])
    lines = [
        "---",
        f"name: mb-{name}",
        f"description: {json.dumps(role['description'])}",
        f"tools: {tools}",
    ]
    if config.get("skills"):
        lines.append("skills: [" + ", ".join(json.dumps(x) for x in config["skills"]) + "]")
    return "\n".join(lines) + f"\n---\n\n{role['prompt']}\n\n" + restriction_lines(role)


def toml_quote(s: str) -> str:
    return json.dumps(s)


def toml_list(values) -> str:
    return "[" + ", ".join(toml_quote(x) for x in values) + "]"


def codex(reg: dict, roles: dict) -> str:
    providers_data = reg["providers"]
    mapping = reg["mapping"]
    out = [
        "# Generated role registry fragment. Owner applies this to ~/.codex/config.toml.",
        "# No new seats, credentials, or live MCP connections.",
        "# Capability levels are durable; model and seat names are replaceable providers (config/providers.json).",
        "",
    ]
    providers_by_level = {lvl: [pid for pid, l in mapping.items() if l == lvl] for lvl in LEVELS}
    for level in LEVELS:
        spec = providers_data["capability_levels"][level]
        out += [
            f"[capability_levels.{level}]",
            f"job = {toml_quote(spec['job'])}",
            f"providers = {toml_list(providers_by_level[level])}",
            "",
        ]
    out += [
        "[review]",
        f"order = {toml_list(providers_data['review_order'])}",
        "",
    ]
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


def artifacts(reg: dict, claude_dir: Path, grok_dir: Path, codex_output: Path) -> dict[Path, str]:
    outputs = {}
    roles = reg["roles"]
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
    outputs[codex_output] = codex(reg, codex_roles)
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
    ap.add_argument("--roles", type=Path, default=DEFAULTS["roles"])
    ap.add_argument("--providers", type=Path, default=DEFAULTS["providers"])
    ap.add_argument("--claude-dir", type=Path, default=DEFAULTS["claude"])
    ap.add_argument("--grok-dir", type=Path, default=DEFAULTS["grok"])
    ap.add_argument("--codex-output", type=Path, default=DEFAULTS["codex"])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    reg = load(args.roles, args.providers)
    outputs = artifacts(reg, args.claude_dir, args.grok_dir, args.codex_output)
    if not args.check:
        for path, text in outputs.items():
            write_atomic(path, text)
    print(f"validated {len(reg['roles'])} roles; {'checked' if args.check else f'wrote {len(outputs)} artifacts'}")


if __name__ == "__main__":
    main()
