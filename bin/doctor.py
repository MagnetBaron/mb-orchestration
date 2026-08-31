#!/usr/bin/env python3
"""doctor — validate the whole mb-orchestration setup so it stays durable.

Two layers:
  ERRORS (always fail): the machine contract — config parses, schema holds, and
    every cross-reference resolves (providers ↔ subscriptions ↔ connectors ↔
    entrypoints ↔ usage-windows ↔ roles ↔ review-depth). No forbidden model is
    selected. Fable declarations agree across files. This is what lets a new
    user drop in their own subscriptions.json and trust the routing.
  WARNINGS (report; fail only with --strict): prose hygiene — broken internal
    links, references to moved/old paths, and raw live IDs that should live in
    config/connectors.json instead of going stale in prose.

No network calls and no runtime-inventory writes. Doctor parses allowlisted
integration manifests read-only. `jsonschema` is used when importable; otherwise the built-in
structural checks below are authoritative. Exit 0 = clean; 1 = errors (or
warnings under --strict).
"""
from __future__ import annotations
import argparse, importlib.util, json, re, sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mborch  # noqa: E402
import dispatch_evidence  # noqa: E402
import handoff_policy  # noqa: E402
import integrations  # noqa: E402

ROOT = HERE.parent
CONFIG = ROOT / "config"
LEVELS = ("frontier", "sole", "terra", "luna")

ERRORS: list[str] = []
WARNINGS: list[str] = []
INFO: list[str] = []

# Gitignored runtime files that are legitimately absent in a clean checkout.
ALLOWED_MISSING = {"config/usage-ledger.json", "usage-ledger.json"}


def err(msg):
    ERRORS.append(msg)


def warn(msg):
    WARNINGS.append(msg)


def info(msg):
    INFO.append(msg)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


model_registry = load_module("model_registry_doctor_contract", HERE / "model-registry.py")


def load_json(name, required=True):
    path = mborch.find_config(name)
    if not path.exists():
        if required:
            err(f"missing config file: {name} (looked in {[str(d) for d in mborch.config_dirs()]})")
        return None
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        err(f"{name}: JSON parse error: {exc}")
        return None


def schema_validate(datas):
    try:
        import jsonschema  # type: ignore
    except Exception:
        info("jsonschema not installed — relying on built-in structural checks (schema file is the published contract).")
        return
    schema = json.loads(mborch.find_config("orchestration.schema.json").read_text())
    for key, data in datas.items():
        if data is None:
            continue
        sub = dict(schema)
        sub["$ref"] = f"#/$defs/{key}"
        try:
            jsonschema.validate(instance=data, schema=sub)
        except jsonschema.ValidationError as e:  # pragma: no cover
            err(f"schema[{key}]: {e.message} at {list(e.path)}")


def check_providers(providers):
    if not providers:
        return {}, set(), set()
    cl = providers.get("capability_levels", {})
    if tuple(cl) != LEVELS:
        err("providers.json capability_levels must be frontier, sole, terra, luna in order")
    provs = providers.get("providers", {})
    forbidden = set()
    for fid, meta in (providers.get("forbidden_models") or {}).items():
        forbidden.add(fid)
        forbidden.update(meta.get("aliases", []))
    families = set(providers.get("families", {}))
    ids = set(provs)
    review_fns = {}
    for pid, p in provs.items():
        for key in ("enabled", "wired", "review_eligible", "dispatch_eligible"):
            if key in p and type(p.get(key)) is not bool:
                err(f"provider {pid}: {key} must be a boolean when present")
        if p.get("level") not in LEVELS:
            err(f"provider {pid}: bad level {p.get('level')!r}")
        if p.get("family") not in families:
            err(f"provider {pid}: family {p.get('family')!r} not declared in families")
        if not p.get("functions"):
            err(f"provider {pid}: empty functions")
        if mborch.model_is_forbidden(p.get("model"), providers.get("forbidden_models")):
            err(f"provider {pid}: selects FORBIDDEN model {p.get('model')!r} (listed in providers.json forbidden_models)")
        if p.get("billing") not in (None, "included", "metered"):
            err(f"provider {pid}: billing must be 'included' or 'metered', got {p.get('billing')!r}")
        if p.get("review_eligible") is True:
            if "review" not in (p.get("functions") or []):
                err(f"provider {pid}: review_eligible requires review function")
            if "review" not in (p.get("capabilities") or []):
                err(f"provider {pid}: review_eligible requires review capability")
        sup = p.get("supersedes")
        if sup is not None:
            if sup not in provs:
                err(f"provider {pid}: supersedes unknown provider {sup!r}")
            elif (provs[sup].get("enabled", True) is True
                  and not provs[sup].get("compatibility_fallback")):
                warn(f"provider {pid} supersedes {sup!r}, but {sup} is still enabled — disable/remove the incumbent (clean slot-in) or mark it compatibility_fallback")
        review_fns[pid] = p.get("functions", [])
    order = list(dict.fromkeys((providers.get("review_order") or []) +
                               (providers.get("review_fallbacks") or [])))
    for pid in order:
        if pid not in ids:
            err(f"review order/fallback references unknown provider {pid!r}")
        elif provs[pid].get("enabled", True) is not True:
            err(f"review order/fallback provider {pid!r} is not enabled with exact true")
        elif provs[pid].get("review_eligible") is not True:
            err(f"review order/fallback provider {pid!r} is not review_eligible")
    for pid, p in provs.items():
        dependency_id = p.get("overflow_after_provider")
        if dependency_id is not None:
            if not isinstance(dependency_id, str) or not dependency_id:
                err(f"provider {pid}: overflow_after_provider must be a non-empty string")
            elif dependency_id == pid:
                err(f"provider {pid}: overflow_after_provider must not reference itself")
            elif dependency_id not in provs:
                err(
                    f"provider {pid}: overflow_after_provider references unknown provider "
                    f"{dependency_id!r}"
                )
            else:
                dependency_seat = provs[dependency_id].get("usage_seat")
                if not isinstance(dependency_seat, str) or not dependency_seat:
                    err(
                        f"provider {pid}: overflow dependency {dependency_id!r} must "
                        "declare a non-empty usage_seat"
                    )
        if p.get("dispatch_eligible") is True:
            if "dispatch" not in (p.get("functions") or []):
                err(f"provider {pid}: dispatch_eligible requires dispatch function")
            if "dispatch" not in (p.get("capabilities") or []):
                err(f"provider {pid}: dispatch_eligible requires dispatch capability")
            evidence = p.get("dispatch_evidence") or {}
            if evidence.get("status") != "passed":
                err(f"provider {pid}: dispatch_eligible requires passed dispatch_evidence")
            trials = evidence.get("trials")
            if not isinstance(trials, int) or trials < 1 or evidence.get("completed") != trials:
                err(f"provider {pid}: dispatch_evidence requires all trials completed")
            if evidence.get("reversals") != 0:
                err(f"provider {pid}: dispatch_evidence requires zero observed reversals")
            valid_receipt, receipt_reason = dispatch_evidence.validate(pid, p)
            if not valid_receipt:
                err(f"provider {pid}: dispatch_evidence {receipt_reason}")
    return provs, ids, forbidden


def check_subscriptions(subs, provider_ids):
    fable_seats = set()
    if not subs:
        return fable_seats
    for sid, s in subs.get("subscriptions", {}).items():
        for pid in s.get("backs_providers", []):
            if pid not in provider_ids:
                err(f"subscription {sid}: backs unknown provider {pid!r}")
        if s.get("grants", {}).get("fable"):
            fable_seats.add(s.get("seat_id") or sid)
    return fable_seats


def check_provider_backings(provs, subs, windows):
    """Require provider↔subscription↔usage-window quota ownership to agree."""
    subscriptions = (subs or {}).get("subscriptions")
    seats = (windows or {}).get("seats")
    if not isinstance(subscriptions, dict) or not isinstance(seats, dict):
        return
    group_backings = {"claude-any-seat", "claude-fable-capable-seats"}
    for pid, provider in (provs or {}).items():
        if not isinstance(provider, dict) or provider.get("enabled", True) is not True:
            continue
        referenced_subscriptions = {
            sid for sid, meta in subscriptions.items()
            if isinstance(meta, dict) and pid in (meta.get("backs_providers") or [])
        }
        special_seat_present = pid == "review-e" and "review-e" in seats
        # providers.json is an inherited catalog. A user/example layer provisions a
        # provider by naming it from a subscription (or by carrying the explicit
        # Review E metered seat). Unprovisioned catalog entries remain dormant and
        # runtime provider_seats() returns no authority for them.
        if not referenced_subscriptions and not special_seat_present:
            continue
        backing = provider.get("backed_by")
        family = provider.get("family")
        if not isinstance(backing, str) or not backing:
            err(f"provider {pid}: enabled provider requires a non-empty backed_by binding")
            continue
        if backing == "fireworks-api":
            eligible = [
                (seat, meta) for seat, meta in seats.items()
                if seat == "review-e" and isinstance(meta, dict)
                and meta.get("subscription") is None and meta.get("family") == family == "open-weight"
                and meta.get("billing") == "metered"
            ] if pid == "review-e" else []
        elif backing in group_backings:
            if family != "anthropic":
                eligible = []
            else:
                eligible_subscriptions = {
                    sid for sid, meta in subscriptions.items()
                    if sid in referenced_subscriptions
                    and (
                        backing != "claude-fable-capable-seats"
                        or (meta.get("grants") or {}).get("fable") is True
                    )
                }
                eligible = [
                    (seat, meta) for seat, meta in seats.items()
                    if isinstance(meta, dict)
                    and meta.get("subscription") in eligible_subscriptions
                    and meta.get("family") == family
                    and (
                        backing != "claude-fable-capable-seats"
                        or meta.get("fable") is True
                    )
                ]
        else:
            subscription = subscriptions.get(backing)
            eligible = [
                (seat, meta) for seat, meta in seats.items()
                if isinstance(meta, dict) and meta.get("subscription") == backing
                and meta.get("family") == family
            ] if (
                isinstance(subscription, dict)
                and pid in (subscription.get("backs_providers") or [])
            ) else []
        usage_seat = provider.get("usage_seat")
        if usage_seat is not None:
            if not isinstance(usage_seat, str) or not usage_seat:
                err(f"provider {pid}: usage_seat must be a non-empty string when present")
            elif usage_seat not in {seat for seat, _meta in eligible}:
                err(
                    f"provider {pid}: usage_seat {usage_seat!r} is not owned by "
                    f"backed_by {backing!r} with family {family!r}"
                )
        elif not eligible:
            err(
                f"provider {pid}: backed_by {backing!r} has no bidirectionally owned "
                "usage-window seat"
            )
    for sid, subscription in subscriptions.items():
        if not isinstance(subscription, dict):
            continue
        for pid in subscription.get("backs_providers") or []:
            provider = (provs or {}).get(pid)
            if not isinstance(provider, dict):
                continue
            backing = provider.get("backed_by")
            valid = backing == sid
            if backing == "claude-any-seat":
                valid = provider.get("family") == "anthropic"
            elif backing == "claude-fable-capable-seats":
                valid = (
                    provider.get("family") == "anthropic"
                    and (subscription.get("grants") or {}).get("fable") is True
                )
            if not valid:
                err(
                    f"subscription {sid}: backs provider {pid!r}, but provider backed_by "
                    f"is {backing!r}"
                )


def check_connectors(conns, provider_ids):
    if not conns:
        return
    for name, m in conns.get("mcp_connectors", {}).items():
        for pid in m.get("available_on", []):
            if pid not in provider_ids:
                err(f"connector {name}: available_on unknown provider {pid!r}")
    modes = (((conns.get("grok_cli") or {}).get("visual_qa") or {}).get("modes") or {})
    scalar_fields = ["role:", "mode:", "store:", "site:", "url:"]
    expected_fields = {
        "preview-review": [*scalar_fields, "changed-path:", "page:"],
        "live-storefront-audit": [*scalar_fields, "page:"],
    }
    for mode, expected in expected_fields.items():
        actual = (modes.get(mode) or {}).get("required_fields")
        if actual != expected:
            err(
                f"connectors.grok_cli.visual_qa.modes.{mode}.required_fields must "
                f"mirror the exact code-owned packet order {expected!r}"
            )


def check_runtime_tool_mappings(conns):
    """Bind every code-owned stdin namespace reduction to a configured connector."""
    connectors = (conns or {}).get("mcp_connectors") or {}
    mappings = integrations.runtime_tool_connector_mappings()
    for runtime, namespaces in mappings.items():
        if not isinstance(runtime, str) or not runtime:
            err("runtime tool mapping has an invalid runtime id")
            continue
        for namespace, rule in namespaces.items():
            connector = rule.get("connector")
            required_tools = rule.get("required_tools")
            if connector not in connectors:
                err(
                    f"runtime tool mapping {runtime}:{namespace} references unknown "
                    f"connector {connector!r}"
                )
            if (
                not isinstance(required_tools, list)
                or not required_tools
                or any(
                    not isinstance(tool, str)
                    or not re.fullmatch(r"[A-Za-z0-9_]+", tool)
                    for tool in required_tools
                )
            ):
                err(
                    f"runtime tool mapping {runtime}:{namespace} requires a non-empty "
                    "exact safe tool surface"
                )


def check_integration_adapters(adapters, providers_data):
    if not adapters:
        return
    providers_data = providers_data or {}
    provs = providers_data.get("providers") or {}
    provider_ids = set(provs)
    try:
        integ = load_module("integrations_doctor", HERE / "integrations.py")
        integ.load_adapters()
    except Exception as exc:
        err(f"integration-adapters.json invalid: {exc}")
        return
    mapped = set((adapters.get("provider_runtimes") or {}))
    connectors = (load_json("connectors.json") or {}).get("mcp_connectors", {})
    connector_providers = {
        pid for meta in connectors.values()
        for pid in (meta.get("available_on") or [])
    }
    for pid in sorted(connector_providers - mapped):
        err(f"integration-adapters: connector provider {pid!r} lacks an explicit runtime mapping")
    for pid in sorted(mapped - provider_ids):
        err(f"integration-adapters: runtime mapping references unknown provider {pid!r}")
    skills = (load_json("skills.json", required=False) or {}).get("skills", {})
    registered_plugins = {sid.partition(":")[0] for sid in skills}
    for runtime, kinds in (adapters.get("aliases") or {}).items():
        if not isinstance(kinds, dict):
            err(f"integration-adapters: aliases.{runtime} must be an object")
            continue
        for kind, aliases in kinds.items():
            if not isinstance(aliases, dict):
                err(f"integration-adapters: aliases.{runtime}.{kind} must be an object")
                continue
            allowed = set(connectors) if kind == "mcp" else registered_plugins if kind == "plugin" else set()
            for observed, canonical in aliases.items():
                if not isinstance(observed, str) or not observed or not isinstance(canonical, str) or not canonical:
                    err(f"integration-adapters: aliases.{runtime}.{kind} needs non-empty string names")
                elif kind in {"mcp", "plugin"} and canonical not in allowed:
                    err(f"integration-adapters: alias {runtime}:{kind}:{observed} maps to unregistered {canonical!r}")
    session_aliases = adapters.get("session_only_aliases") or {}
    grok_runtime_capabilities = {"browser", "pixels", "clarity-auth", "deposited-evidence"}
    capability_catalog = set((providers_data.get("capability_catalog") or {})) - {"_note"}
    for runtime, kinds in session_aliases.items():
        if not isinstance(kinds, dict):
            err(f"integration-adapters: session_only_aliases.{runtime} must be an object")
            continue
        for kind, aliases in kinds.items():
            if kind not in {"app", "capability"}:
                err(f"integration-adapters: session_only_aliases.{runtime}.{kind} must be app or capability")
                continue
            if not isinstance(aliases, dict):
                err(f"integration-adapters: session_only_aliases.{runtime}.{kind} must be an object")
                continue
            for observed, canonical in aliases.items():
                if not isinstance(observed, str) or not observed or not isinstance(canonical, str) or not canonical:
                    err(f"integration-adapters: session_only_aliases.{runtime}.{kind} needs non-empty string names")
                elif (kind == "capability" and canonical not in capability_catalog
                      and not (runtime == "grok" and canonical in grok_runtime_capabilities)):
                    err(f"integration-adapters: session-only capability maps to unknown {canonical!r}")
    expected_grok_capabilities = {name: name for name in sorted(grok_runtime_capabilities)}
    actual_grok_capabilities = ((session_aliases.get("grok") or {}).get("capability") or {})
    if actual_grok_capabilities != expected_grok_capabilities:
        err(
            "integration-adapters: grok capability aliases must exactly define the "
            f"launcher preflight vocabulary {expected_grok_capabilities!r}"
        )
    expected_cursor_aliases = {"capability": {"code": "code", "ide": "ide"}}
    actual_cursor_aliases = session_aliases.get("cursor")
    if actual_cursor_aliases != expected_cursor_aliases:
        err(
            "integration-adapters: cursor session-only aliases must be exactly "
            "code+ide; generic Cursor must not claim specialized Grokbot capabilities"
        )
    cursor_caps = set(((actual_cursor_aliases or {}).get("capability") or {}).values())
    cursor_providers = {
        pid: p for pid, p in provs.items()
        if (adapters.get("provider_runtimes") or {}).get(pid) == "cursor"
    }
    for pid, provider in sorted(cursor_providers.items()):
        excess = sorted(set(provider.get("capabilities") or []) - cursor_caps)
        if excess:
            err(
                f"integration-adapters: generic cursor runtime provider {pid} claims "
                f"non-code/ide capability aliases: {excess}"
            )
    specialized_grokbots = {
        "grok-bot-review-d", "grok-bot-heat-map", "grok-bot-marketplace-intelligence",
    }
    for pid in sorted(specialized_grokbots):
        if (adapters.get("provider_runtimes") or {}).get(pid) != "grok":
            err(
                f"integration-adapters: specialized provider {pid} must stay on the "
                "grok runtime and may not be satisfied by generic Cursor"
            )
    try:
        records, events = integ.discover(adapters)
        unregistered = sum(1 for r in records if not r.get("registered"))
        info(f"integration inventory read-only discovery: {len(records)} observed, {unregistered} unregistered, "
             f"{len(events)} unavailable source(s); runtime grants still require "
             "product-authenticated callable proof")
    except Exception as exc:
        err(f"integration inventory read-only discovery failed closed: {exc}")


VALID_CONNECTOR_STATUS = ("active", "ready", "primed")
_SERVER_TRANSPORTS = ("stdio", "http", "sse")
# Keys that would smuggle a credential VALUE into the repo — the sanctioned channel is
# `env_keys` (env-var NAMES the admin sets out of band). Any of these on a server block fails.
_CREDENTIAL_KEYS = {
    "token", "secret", "secrets", "key", "keys", "api_key", "apikey", "password", "passwd",
    "pass", "credential", "credentials", "bearer", "auth", "authorization", "access_token",
    "refresh_token", "client_secret", "private_key", "passphrase",
}


def _check_server_block(name, server):
    """SHAPE-only validation of a bundled server DEFINITION. Reads strings; never runs
    `command`, never opens `url`. Enforces the no-credentials-in-repo rule."""
    if not isinstance(server, dict):
        err(f"connector {name}: server block must be an object")
        return
    for k in server:
        if str(k).lower() in _CREDENTIAL_KEYS:
            err(f"connector {name}: server block key {k!r} looks like an inline credential — "
                "no secrets in-repo; name the env var in 'env_keys' (NAMES only) and set the value out of band")
    transport = server.get("transport")
    if transport not in _SERVER_TRANSPORTS:
        err(f"connector {name}: server.transport {transport!r} not one of {_SERVER_TRANSPORTS}")
    ek = server.get("env_keys", [])
    if not isinstance(ek, list) or any(not isinstance(x, str) or not x for x in ek):
        err(f"connector {name}: server.env_keys must be a list of env-var NAME strings")
    else:
        for x in ek:
            if "=" in x or len(x) > 64:
                err(f"connector {name}: server.env_keys entry {x!r} must be a bare env-var NAME (no value)")
    if transport == "stdio":
        cmd = server.get("command")
        if not isinstance(cmd, str) or not cmd:
            err(f"connector {name}: stdio server needs a non-empty 'command' string")
        args = server.get("args", [])
        if not isinstance(args, list) or any(not isinstance(a, str) for a in args):
            err(f"connector {name}: server.args must be a list of strings")
    elif transport in ("http", "sse"):
        url = server.get("url")
        if not isinstance(url, str) or "://" not in url:
            err(f"connector {name}: {transport} server needs a 'url' string")
        elif "@" in url.split("://", 1)[1].split("/", 1)[0]:
            err(f"connector {name}: server.url must not embed userinfo credentials (user:pass@host)")


def check_connector_lifecycle(conns, providers):
    """Validate the MCP strap-in lifecycle (status enum + optional bundled server block) and
    PROVE inertness: a connector that is not 'active' (i.e. primed/ready) must never be treated
    as live — the router must not grant it to any provider, including seats outside available_on
    and providers that copied the connector name or class into coarse capabilities. Rejects
    capability/connector-derived-label (id/alias/class) collisions, and rejects connector
    ID/alias names that collide with the coarse vocabulary (class labels may match a catalog
    key and stay coarse). This is SHAPE + pure-logic
    only; it NEVER opens a socket, spawns a subprocess, or hits the network (the whole point
    of priming)."""
    if not conns:
        return
    prov = (providers or {}).get("providers", {})
    try:
        routing = load_module("routing_doc", HERE / "routing.py")
    except Exception as exc:  # pragma: no cover
        routing = None
        err(f"connector lifecycle: cannot import routing for the inertness proof: {exc}")
    derived = routing.connector_derived_labels(conns) if routing is not None else set()
    catalog = {k for k in (providers or {}).get("capability_catalog", {}) if k != "_note"}
    if routing is not None and catalog and catalog != set(routing.COARSE_CAPABILITIES):
        err(
            f"capability_catalog {sorted(catalog)} != routing.COARSE_CAPABILITIES "
            f"{sorted(routing.COARSE_CAPABILITIES)} — coarse vocabulary must stay enumerated "
            "and not connector-derived"
        )
    coarse = set(routing.COARSE_CAPABILITIES) if routing is not None else catalog
    for pid, p in prov.items():
        for cap in (p.get("capabilities") or []) if isinstance(p, dict) else []:
            if cap in derived:
                err(
                    f"provider {pid}: capability {cap!r} collides with a connector id/alias/class — "
                    "connector access is granted only via connectors.json available_on + status=active, "
                    "never as a coarse provider capability"
                )
    for name, m in conns.get("mcp_connectors", {}).items():
        if name in coarse:
            err(
                f"connector {name}: id {name!r} collides with coarse capability vocabulary — "
                "IDs and aliases are always connector-derived; rename the connector"
            )
        if not isinstance(m, dict):
            err(f"connector {name}: must be an object")
            continue
        alias = m.get("alias")
        if alias in coarse:
            err(
                f"connector {name}: alias {alias!r} collides with coarse capability vocabulary — "
                "IDs and aliases are always connector-derived; rename the alias"
            )
        status = m.get("status")
        if status not in VALID_CONNECTOR_STATUS:
            err(
                f"connector {name}: status {status!r} is required (active|ready|primed); "
                "missing/unknown defaults inert, never active"
            )
        server = m.get("server")
        if server is not None:
            _check_server_block(name, server)
            # a repo-carried launch spec is pre-activation scaffolding: it may ride only on a
            # non-active entry, so it can never be mistaken for a live/wired connector.
            if status == "active":
                err(f"connector {name}: carries a bundled 'server' block but status is 'active' — "
                    "a repo-carried server definition must stay primed/ready (inert) until the admin activates it")
        # INERTNESS PROOF (pure function): a non-active connector is granted to NO provider,
        # not only those listed in available_on (coarse-label leaks must not hide).
        if status != "active" and routing is not None:
            alias = m.get("alias")
            cls = m.get("class")
            mcp = conns.get("mcp_connectors") or {}
            for pid in prov:
                caps = routing.capabilities_of(pid, prov.get(pid, {}), conns)
                if name in caps or (alias and alias in caps):
                    err(f"connector {name}: status={status} but the router still grants it to seat "
                        f"{pid!r} — a non-active connector MUST be inert (never routed). "
                        "See bin/routing.connector_is_active.")
                if cls and cls in derived and cls in caps:
                    others_active = any(
                        n2 != name
                        and isinstance(m2, dict)
                        and m2.get("class") == cls
                        and routing.connector_is_active(m2)
                        and pid in (m2.get("available_on") or [])
                        for n2, m2 in mcp.items()
                    )
                    if not others_active:
                        err(
                            f"connector {name}: status={status} but class {cls!r} is still granted "
                            f"to seat {pid!r} — a non-active connector class MUST be inert unless "
                            "another active connector of that class is assigned to the seat."
                        )


def check_skills(skills, providers, conns):
    """skills.json registry hygiene (mirrors check_connectors for MCP): every skill's
    required_capability resolves to a known coarse capability (providers.json `capability_catalog`
    / `COARSE_CAPABILITIES`) or a known connector-derived label (id/alias/class); hosts are valid;
    and each skill's in-repo SKILL.md resolves through the repo marketplace (host-discoverable).
    The FAIL-CLOSED binding enforcement itself (unregistered skill, write-skill on a read_only role,
    seat missing a required_capability) runs in generate-roles.load via check_roles_and_windows_run."""
    if not skills:
        return
    try:
        routing = load_module("routing_skills", HERE / "routing.py")
    except Exception:
        routing = None
    coarse = set(routing.COARSE_CAPABILITIES) if routing is not None else {
        k for k in (providers or {}).get("capability_catalog", {}) if k != "_note"
    }
    catalog = {k for k in (providers or {}).get("capability_catalog", {}) if k != "_note"}
    if catalog:
        coarse |= catalog
    connector_names = routing.connector_derived_labels(conns) if routing is not None else set()
    connector_names |= routing.connector_ids(conns) if routing is not None else set(
        (conns or {}).get("mcp_connectors", {})
    )
    coarse -= connector_names
    try:
        gen = load_module("gen_roles_skills", HERE / "generate-roles.py")
    except Exception as exc:
        gen = None
        warn(f"skills.json: cannot load generate-roles for SKILL.md resolution: {exc}")
    for sid, meta in skills.get("skills", {}).items():
        if not isinstance(meta, dict):
            err(f"skill {sid!r}: entry must be an object")
            continue
        if meta.get("kind") not in ("read", "write"):
            err(f"skill {sid!r}: kind must be 'read' or 'write', got {meta.get('kind')!r}")
        cap = meta.get("required_capability")
        if cap is not None and cap not in coarse and cap not in connector_names:
            err(f"skill {sid!r}: required_capability {cap!r} is neither a providers.json capability "
                "nor a connectors.json connector — unresolvable capability gate")
        hosts = meta.get("hosts")
        if not isinstance(hosts, list) or not hosts or any(h not in ("claude", "grok", "codex") for h in hosts):
            err(f"skill {sid!r}: hosts must be a non-empty subset of claude, grok, codex")
        if gen is not None and not gen.skill_md_path(sid).exists():
            err(f"skill {sid!r}: SKILL.md not found at {gen.skill_md_path(sid)} — in-repo plugin skill unresolvable")


def check_entrypoints(entry, provs, provider_ids):
    if not entry:
        return
    disp = entry.get("dispatcher", {})
    if disp.get("selection_mode") != "intake-provider-first":
        err("entrypoints dispatcher.selection_mode must be 'intake-provider-first'")
    if disp.get("relay_known_unqualified_intake") is not True:
        err("entrypoints dispatcher.relay_known_unqualified_intake must be true")
    default = disp.get("default_provider")
    fallback = disp.get("fallback_order") or []
    for label, pid in [("default_provider", default)] + [("fallback_order", p) for p in fallback]:
        if pid not in provider_ids:
            err(f"entrypoints dispatcher.{label} {pid!r} is not a known provider")
        elif provs.get(pid, {}).get("enabled", True) is not True:
            err(f"entrypoints dispatcher.{label} {pid!r} is not enabled with exact true")
        elif provs.get(pid, {}).get("dispatch_eligible") is not True:
            err(f"entrypoints dispatcher.{label} {pid!r} is not dispatch_eligible")
    if len(fallback) != len(set(fallback)):
        err("entrypoints dispatcher.fallback_order must be unique")
    if default not in fallback:
        err("entrypoints dispatcher.default_provider must appear in fallback_order")
    surfaces = entry.get("entry_surfaces", {})
    if not any(s.get("can_dispatch") for s in surfaces.values()):
        err("entrypoints: at least one dispatch-capable surface is required")
    for name, s in surfaces.items():
        pids = s.get("providers") or []
        for p in pids:
            if p not in provider_ids:
                err(f"entry surface {name}: provider {p!r} unknown")
            elif provs.get(p, {}).get("enabled", True) is not True:
                err(f"entry surface {name}: provider {p!r} is not enabled with exact true")
            elif (s.get("can_dispatch")
                  and provs.get(p, {}).get("dispatch_eligible") is not True):
                err(f"entry surface {name}: can_dispatch includes unqualified provider {p!r}")
    for name, profile in (entry.get("profiles") or {}).items():
        p = profile.get("preferred_dispatcher")
        if (p not in provider_ids
                or provs.get(p, {}).get("enabled", True) is not True
                or provs.get(p, {}).get("dispatch_eligible") is not True):
            err(f"entrypoints profile {name}: preferred_dispatcher {p!r} is not dispatch_eligible")
    if "default" not in (entry.get("profiles") or {}):
        err("entrypoints profiles.default is required")
    rules = entry.get("rules") or {}
    if rules.get("single_dispatcher_per_run") is not True:
        err("entrypoints rules.single_dispatcher_per_run must be true")
    if rules.get("authorship_does_not_change_handoff_authority") is not True:
        err("entrypoints rules.authorship_does_not_change_handoff_authority must be true")


def check_handoff_policy(policy):
    if not policy:
        return
    ordinary = policy.get("ordinary_artifacts") or []
    restricted = policy.get("restricted_artifacts") or []
    if not ordinary or not restricted:
        err("handoff-policy: ordinary_artifacts and restricted_artifacts must be non-empty")
    configured_restricted = {
        value for value in restricted if isinstance(value, str)
    } if isinstance(restricted, list) else set()
    minimum_restricted = set(handoff_policy.IMMUTABLE_MINIMUM_RESTRICTED_ARTIFACTS)
    missing_minimum = sorted(minimum_restricted - configured_restricted)
    if missing_minimum:
        err(
            "handoff-policy: restricted_artifacts cannot remove immutable minimum "
            f"class(es): {missing_minimum}"
        )
    ordinary_classes = {
        value for value in ordinary if isinstance(value, str)
    } if isinstance(ordinary, list) else set()
    immutable_in_ordinary = sorted(ordinary_classes & minimum_restricted)
    if immutable_in_ordinary:
        err(
            "handoff-policy: immutable restricted class(es) cannot be ordinary: "
            f"{immutable_in_ordinary}"
        )
    overlap = sorted(ordinary_classes & configured_restricted)
    if overlap:
        err(f"handoff-policy: artifact classes overlap: {overlap}")
    rules = policy.get("rules") or {}
    expected = {
        "configured_provider_handoffs": "preauthorized",
        "authorship_never_requires_permission": True,
        "ordinary_requires_user_permission": False,
        "restricted_action": "park",
        "unknown_artifact_action": "park",
        "no_permission_escalation_loop": True,
        "minimum_necessary_only": True,
    }
    for key, value in expected.items():
        if rules.get(key) != value:
            err(f"handoff-policy rules.{key} must be {value!r}")
    expected_auth = {
        "provider_scope": "all-configured-review-providers",
        "artifact_scope": "ordinary_artifacts",
        "per_review_approval_required": False,
        "intake_family_may_review": True,
        "intake_family_review_scope": "artifact-only",
        "intake_family_must_not_be_sole_reviewer": True,
        "separate_physical_invocation_required": True,
    }
    auth = policy.get("standing_review_authorization")
    if not isinstance(auth, dict):
        err("handoff-policy: standing_review_authorization object is required")
    else:
        expected_keys = set(expected_auth) | {"effective_date"}
        extra = sorted(set(auth) - expected_keys)
        if extra:
            err(f"handoff-policy standing_review_authorization unexpected field(s): {extra}")
        missing = sorted(expected_keys - set(auth))
        if missing:
            err(f"handoff-policy standing_review_authorization missing field(s): {missing}")
        for key, value in expected_auth.items():
            if key in auth and auth.get(key) != value:
                err(f"handoff-policy standing_review_authorization.{key} must be {value!r}")
        raw_date = auth.get("effective_date")
        if "effective_date" in auth:
            if not isinstance(raw_date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date):
                err("handoff-policy standing_review_authorization.effective_date must be ISO YYYY-MM-DD")
            else:
                try:
                    parsed = date.fromisoformat(raw_date)
                except ValueError:
                    err("handoff-policy standing_review_authorization.effective_date is not a valid calendar date")
                else:
                    if parsed > date.today():
                        err("handoff-policy standing_review_authorization.effective_date must not be in the future")


def check_windows(windows, subs_ids, fable_from_subs, provs=None):
    fable_from_windows = set()
    if not windows:
        return
    usage_ids = set(windows.get("seats", {}))
    for pid, p in (provs or {}).items():
        usage_seat = p.get("usage_seat")
        if usage_seat and p.get("backed_by") in subs_ids and usage_seat not in usage_ids:
            err(f"provider {pid}: usage_seat {usage_seat!r} is not in usage-windows.json")
    for seat, w in windows.get("seats", {}).items():
        sub = w.get("subscription")
        if sub is not None and sub not in subs_ids:
            err(f"usage-window seat {seat}: subscription {sub!r} not in subscriptions.json")
        for win in w.get("windows", []):
            if win.get("kind") not in ("weekly", "monthly", "rolling", "none"):
                err(f"usage-window seat {seat}: bad window kind {win.get('kind')!r}")
        drain = w.get("drain", "full")
        if drain not in ("full", "reserve"):
            err(f"usage-window seat {seat}: drain must be 'full' or 'reserve', got {drain!r}")
        billing = w.get("billing", "included")
        if billing not in ("included", "metered"):
            err(f"usage-window seat {seat}: billing must be 'included' or 'metered', got {billing!r}")
        monthly_cap = w.get("monthly_cap_usd")
        if monthly_cap is not None and (
            isinstance(monthly_cap, bool)
            or not isinstance(monthly_cap, (int, float))
            or monthly_cap <= 0
        ):
            err(f"usage-window seat {seat}: monthly_cap_usd must be positive or null, got {monthly_cap!r}")
        provider = (provs or {}).get(seat) or {}
        if provider.get("wired") is True and billing == "metered" and monthly_cap is None:
            err(f"usage-window seat {seat}: wired metered provider requires monthly_cap_usd")
        rp = w.get("reserve_pct", w.get("soft_cap_pct"))
        if rp is not None and not (isinstance(rp, (int, float)) and 0 <= rp <= 100):
            err(f"usage-window seat {seat}: reserve_pct must be 0-100 or null, got {rp!r}")
        if w.get("fable"):
            fable_from_windows.add(seat)
    # Fable declarations must agree between subscriptions and windows (drift = latent downgrade bug)
    if fable_from_subs != fable_from_windows:
        err(f"Fable declaration drift: subscriptions say {sorted(fable_from_subs)} but usage-windows say "
            f"{sorted(fable_from_windows)} — reconcile grants.fable and seat.fable")


def check_review_depth(depth):
    if not depth:
        return
    order = depth.get("levels_order", [])
    if order != ["none", "self-check", "single-frontier", "cross-family"]:
        err(f"review-depth levels_order wrong: {order}")
    for cid, spec in depth.get("classes", {}).items():
        for col in ("routine", "elevated", "risk"):
            if spec.get(col) not in order:
                err(f"review-depth class {cid}: {col}={spec.get(col)!r} not a valid level")


def rendered_recipe_argv(recipe):
    """Planner-facing argv for a seat-exec recipe: `bin` plus string args_template tokens."""
    out = []
    bin_ = recipe.get("bin") if isinstance(recipe, dict) else None
    if bin_:
        out.append(bin_)
    args = recipe.get("args_template") if isinstance(recipe, dict) else None
    if isinstance(args, list):
        out.extend(a for a in args if isinstance(a, str))
    return out


DIRECT_CLAUDE_BIN = "claude"


def wrapper_spec_error(host, spec):
    """A seat-exec `wrappers` entry must fully describe the wrapper argv, or every recipe
    on that host fails closed (an unverifiable wrapper is as bad as a missing one)."""
    if not isinstance(spec, dict):
        return f"seat-exec wrappers[{host!r}]: must be an object with bin, prefix, model_flag"
    bin_, prefix, flag = spec.get("bin"), spec.get("prefix"), spec.get("model_flag")
    if not (isinstance(bin_, str) and bin_):
        return f"seat-exec wrappers[{host!r}]: bin must be a non-empty string"
    if not (isinstance(prefix, list) and all(isinstance(t, str) for t in prefix)):
        return f"seat-exec wrappers[{host!r}]: prefix must be a list of strings"
    if not (isinstance(flag, str) and flag):
        return f"seat-exec wrappers[{host!r}]: model_flag must be a non-empty string"
    return None


def wrapped_recipe_error(pid, recipe, route, wrappers):
    """Fail closed on Anthropic invocation drift. The expected wrapper argv is DERIVED from
    the provider's registry route `host` plus the seat-exec `wrappers` config, never hardcoded.
    Returns an error string, or None when the recipe is clean:
      - a recipe rendering the direct `claude` CLI errors whenever its route is absent,
        unresolved, or not live_verified (direct Claude is auth_blocked);
      - a route on a wrapper-managed host must render `<bin> <prefix...>` plus exactly one
        model_flag token immediately followed by the route's exact invocation_id."""
    argv = rendered_recipe_argv(recipe)
    host = route.get("host") if isinstance(route, dict) else None
    spec = (wrappers or {}).get(host) if host else None
    if spec is None:
        # Host is not wrapper-managed: only the auth-blocked direct Claude CLI fails closed here.
        if not argv or argv[0] != DIRECT_CLAUDE_BIN:
            return None
        if not isinstance(route, dict):
            return (
                f"seat-exec recipe {pid!r}: renders the direct `claude` CLI but the provider "
                "route is absent or unresolved — direct Claude is auth_blocked; fail closed "
                "(route Anthropic seats through a wrapper host)"
            )
        state = route.get("route_state")
        if state != "live_verified":
            return (
                f"seat-exec recipe {pid!r}: renders the direct `claude` CLI on a route with "
                f"route_state={state!r} — direct Claude is auth_blocked; fail closed"
            )
        return None
    bad_spec = wrapper_spec_error(host, spec)
    if bad_spec:
        return f"{bad_spec} — cannot verify recipe {pid!r}; fail closed"
    want = [spec["bin"], *spec["prefix"]]
    flag = spec["model_flag"]
    inv = route.get("invocation_id")
    if argv[: len(want)] != want:
        shown = argv[: len(want)] if argv else ["<empty>"]
        want_model = f"{flag} {inv}" if inv else f"{flag} <invocation_id>"
        return (
            f"seat-exec recipe {pid!r}: registry route host is {host!r} but the recipe "
            f"renders a direct command starting {shown!r} — must be `{' '.join(want)}` "
            f"with `{want_model}`; direct Claude is auth_blocked"
        )
    if not inv:
        return (
            f"seat-exec recipe {pid!r}: wrapper host {host!r} route has no invocation_id — "
            "cannot pin the model; fail closed"
        )
    flag_idx = [i for i, tok in enumerate(argv) if tok == flag]
    if len(flag_idx) != 1:
        return (
            f"seat-exec recipe {pid!r}: expected exactly one `{flag}` token, found "
            f"{len(flag_idx)} — must be `{flag} {inv}` (exact registry invocation_id); "
            "a duplicate or missing flag can silently select another model"
        )
    i = flag_idx[0]
    if i + 1 >= len(argv) or argv[i + 1] != inv:
        return (
            f"seat-exec recipe {pid!r}: `{flag}` must be immediately followed by {inv!r} "
            "(exact registry invocation_id); a wrong or dangling value can silently select "
            "another model"
        )
    return None

def check_seat_exec(seat_exec, provs, provider_ids, registry=None):
    """seat-exec.json recipes must not drift from the registry: every recipe keys a known
    provider; the never_metered_host marker matches providers.json `billing` (the secrets/PII
    executor guard, as data); `bin` matches `kind` (CLI seats have a bin, app/api/local
    seats do not); and a route on a wrapper-managed host (seat-exec `wrappers`) must render
    that wrapper's argv with the route's exact invocation_id — the direct `claude` CLI is
    auth_blocked and fails closed on an absent/unresolved/non-live route. Consumed by
    bin/run-brief.py."""
    if not seat_exec:
        return
    registry = registry if isinstance(registry, dict) else (load_json("model-registry.json") or {})
    recipes = seat_exec.get("recipes", {})
    if not recipes:
        err("seat-exec.json: no recipes defined")
        return
    valid_reads = {"brief", "git-diff", "preview-url", "analytics", "marketplace-evidence", "none"}
    routes = (registry or {}).get("routes") or {}
    wrappers = seat_exec.get("wrappers") or {}
    for host, spec in wrappers.items():
        bad = wrapper_spec_error(host, spec)
        if bad:
            err(bad)
    for pid, r in recipes.items():
        if pid not in provider_ids:
            err(f"seat-exec recipe {pid!r}: not a known provider (config/providers.json)")
            continue
        p = provs.get(pid, {})
        kind, billing = p.get("kind"), p.get("billing", "included")
        nmh = r.get("never_metered_host")
        if not isinstance(nmh, bool):
            err(f"seat-exec recipe {pid!r}: never_metered_host must be a boolean")
        elif billing == "metered" and nmh is not False:
            err(f"seat-exec recipe {pid!r}: provider billing=metered → never_metered_host must be false "
                "(the executor must never shell a metered inference host — secrets/PII ban)")
        elif billing == "included" and nmh is not True:
            err(f"seat-exec recipe {pid!r}: provider billing=included → never_metered_host must be true")
        bin_ = r.get("bin")
        if kind in ("cli", "ide") and not (isinstance(bin_, str) and bin_):
            err(f"seat-exec recipe {pid!r}: provider kind={kind} needs a CLI bin (non-empty string)")
        if kind in ("app", "api", "local") and bin_ is not None:
            err(f"seat-exec recipe {pid!r}: provider kind={kind} has no CLI → bin must be null")
        if r.get("reads") not in valid_reads:
            err(f"seat-exec recipe {pid!r}: reads={r.get('reads')!r} not in {sorted(valid_reads)}")
        if not isinstance(r.get("args_template"), list):
            err(f"seat-exec recipe {pid!r}: args_template must be a list")
        if not isinstance(r.get("worktree"), bool):
            err(f"seat-exec recipe {pid!r}: worktree must be a boolean")
        if pid == "grok-build":
            expected_model = p.get("model")
            route_id = p.get("route")
            route = ((registry or {}).get("routes") or {}).get(route_id)
            if not isinstance(expected_model, str) or not expected_model:
                err("provider 'grok-build': selectable model must be a non-empty string")
            if not isinstance(route, dict) or route.get("model") != expected_model:
                err(
                    f"provider 'grok-build': model {expected_model!r} must match "
                    f"model-registry route {route_id!r}"
                )
            raw_args = r.get("args_template")
            args = raw_args if isinstance(raw_args, list) else []
            if bin_ != "grok":
                err("seat-exec recipe 'grok-build': bin must be exact installed CLI 'grok'")
            approved_args = [
                "--cwd", "{worktree}",
                "--prompt-file", "{brief_path}",
                "--model", expected_model,
                "--reasoning-effort", "xhigh",
                "--no-subagents",
            ]
            if args != approved_args:
                err(
                    "seat-exec recipe 'grok-build': args_template must match the exact "
                    f"approved argv {approved_args!r}; got {args!r}. Unknown, duplicate, "
                    "positional, reordered, and permission-bypassing flags are forbidden"
                )
        if pid == "cursor-grok":
            route_id = p.get("route")
            route = routes.get(route_id) if route_id else None
            detect = p.get("detect") or {}
            expected_invocation = "cursor-grok-4.6-xhigh"
            prompt = (
                "Read the scoped brief at {brief_path}. Implement only the authorized file "
                "scope in that brief inside this workspace; preserve unrelated changes and "
                "stop on any conflict."
            )
            approved_args = [
                "--trust", "--print", "--workspace", "{worktree}",
                "--model", expected_invocation, prompt,
            ]
            if detect != {"method": "command", "cmd": "cursor-agent"}:
                err(
                    "provider 'cursor-grok': detect must be exact command "
                    "'cursor-agent' (the `cursor` app binary does not prove Agent CLI access)"
                )
            if set(p.get("functions") or []) - {"implement", "ide"} \
                    or not ({"implement", "ide"} & set(p.get("functions") or [])):
                err("provider 'cursor-grok': overflow must be implementation-only (implement/ide)")
            if p.get("review_eligible") is not False or p.get("dispatch_eligible") is True:
                err("provider 'cursor-grok': overflow must never review or dispatch")
            if {"review", "dispatch"} & set(p.get("capabilities") or []):
                err("provider 'cursor-grok': overflow capabilities must not grant review/dispatch")
            if bin_ != "cursor-agent":
                err("seat-exec recipe 'cursor-grok': bin must be exact 'cursor-agent'")
            if r.get("args_template") != approved_args:
                err(
                    "seat-exec recipe 'cursor-grok': args_template must match the exact "
                    f"approved argv {approved_args!r}; invalid --workdir/--brief, --yolo, "
                    "missing --trust/--print, wrong model, extra positionals, duplicates, "
                    "and reordered flags are forbidden"
                )
            if not isinstance(route, dict):
                err(f"provider 'cursor-grok': route {route_id!r} is missing")
            else:
                expected_identity = {
                    "model": "grok-4.6", "provider": "cursor-grok", "host": "cursor",
                    "harness": "cursor-agent", "invocation_id": expected_invocation,
                }
                for key, want in expected_identity.items():
                    if route.get(key) != want:
                        err(
                            f"provider 'cursor-grok': route {route_id!r} {key} must be "
                            f"exact {want!r}, got {route.get(key)!r}"
                        )
                local_smoke = (route.get("attestations") or {}).get("local_access_smoke") or {}
                route_state = route.get("route_state")
                if route_state == "catalog_verified":
                    if route.get("evidence_strength") != "cli_listing":
                        err(
                            "provider 'cursor-grok': catalog route must retain exact "
                            "cli_listing evidence strength"
                        )
                    if local_smoke.get("state") != "missing":
                        err(
                            "provider 'cursor-grok': catalog local_access_smoke must remain "
                            "missing until the exact Cursor invocation returns a terminal receipt"
                        )
                    listed = [
                        ev for ev in (route.get("evidence") or [])
                        if isinstance(ev, dict) and ev.get("kind") == "cli_listing"
                    ]
                    if not listed:
                        err("provider 'cursor-grok': exact invocation needs dated cli_listing evidence")
                    else:
                        latest = sorted(listed, key=lambda ev: str(ev.get("date") or ""))[-1]
                        source = str(latest.get("source") or "")
                        if ("cursor-agent --list-models" not in source
                                or expected_invocation not in source
                                or "no inference" not in source.lower()
                                or latest.get("signal") in {"direct_invocation", "standing_provider"}):
                            err(
                                "provider 'cursor-grok': cli_listing evidence must name the live "
                                "listing command and exact model id, state that no inference ran, "
                                "and must not masquerade as a live invocation signal"
                            )
                elif route_state == "live_verified":
                    if route.get("evidence_strength") != "local_smoke":
                        err(
                            "provider 'cursor-grok': live promotion requires exact "
                            "local_smoke evidence strength"
                        )
                    if not (
                        local_smoke.get("state") == "attested"
                        and local_smoke.get("signal") == "direct_invocation"
                        and local_smoke.get("evidence_kind") == "direct_invocation"
                    ):
                        err(
                            "provider 'cursor-grok': live promotion requires an attested "
                            "direct_invocation local_access_smoke"
                        )
                    evidence = [
                        ev for ev in (route.get("evidence") or [])
                        if isinstance(ev, dict)
                    ]
                    latest = sorted(
                        evidence,
                        key=lambda ev: str(ev.get("date") or ""),
                    )[-1] if evidence else {}
                    expected_receipt = {
                        "harness": "cursor-agent",
                        "invocation_id": expected_invocation,
                        "exit_code": 0,
                        "completed": True,
                    }
                    if not (
                        latest.get("route_state") == "live_verified"
                        and latest.get("kind") == "terminal_inference_receipt"
                        and latest.get("signal") == "direct_invocation"
                        and latest.get("terminal_receipt") == expected_receipt
                    ):
                        err(
                            "provider 'cursor-grok': live promotion requires the latest "
                            "evidence to be an exact successful terminal inference receipt"
                        )
                    if not model_registry.route_is_live(registry, route_id):
                        err(
                            "provider 'cursor-grok': live promotion must satisfy the generic "
                            "model-registry live predicate; corrected identity cannot inherit "
                            "the frozen legacy waiver"
                        )
                else:
                    err(
                        "provider 'cursor-grok': route_state must be catalog_verified or "
                        "a receipt-attested live_verified promotion"
                    )
        if pid == "cursor-other-400":
            detect = p.get("detect") or {}
            if detect != {"method": "command", "cmd": "cursor-agent"}:
                err("provider 'cursor-other-400': detect must be exact command 'cursor-agent'")
            if r.get("args_template") != []:
                err(
                    "seat-exec recipe 'cursor-other-400': metered owner-only route must keep "
                    "an empty argv (never guess a model or retain unsupported Cursor flags)"
                )
        if pid in {"grok-bot-review-d", "grok-bot-heat-map", "grok-bot-marketplace-intelligence"}:
            expected_model = p.get("model")
            route_id = p.get("route")
            route = routes.get(route_id) if route_id else None
            agent = r.get("required_agent")
            approved_agents = {
                "grok-bot-review-d": "mb-review-d",
                "grok-bot-heat-map": "mb-heat-map",
                "grok-bot-marketplace-intelligence": "mb-marketplace-intelligence",
            }
            approved_capabilities = {
                "grok-bot-review-d": ["browser", "pixels"],
                "grok-bot-heat-map": ["browser", "clarity-auth"],
                "grok-bot-marketplace-intelligence": ["deposited-evidence"],
            }
            if bin_ != "grok":
                err(f"seat-exec recipe {pid!r}: bin must be exact installed CLI 'grok'")
            if agent != approved_agents[pid]:
                err(f"seat-exec recipe {pid!r}: required_agent must be {approved_agents[pid]!r}")
            if expected_model != "grok-4.6" or not isinstance(route, dict) or route.get("model") != expected_model:
                err(f"seat-exec recipe {pid!r}: provider and bound route must pin exact model 'grok-4.6'")
            if isinstance(route, dict) and route.get("provider") != pid:
                err(f"seat-exec recipe {pid!r}: bound route provider must be exact {pid!r}")
            if isinstance(route, dict) and (route.get("host"), route.get("harness")) != ("grok-cli", "grok"):
                err(f"seat-exec recipe {pid!r}: bound route must use host='grok-cli' and harness='grok'")
            if isinstance(route, dict) and route.get("invocation_id") != approved_agents[pid]:
                err(
                    f"seat-exec recipe {pid!r}: bound route invocation_id must be exact "
                    f"{approved_agents[pid]!r}"
                )
            grok_agent_mod = load_module("grok_agent_doctor_recipe", HERE / "grok-agent.py")
            execution_binding = grok_agent_mod.EXECUTION_INPUT_BINDINGS.get(pid)
            if execution_binding is None and (
                p.get("wired") is True
                or (isinstance(route, dict) and route.get("route_state") == "live_verified")
            ):
                err(
                    f"standing provider {pid!r}: wired/live_verified promotion is forbidden "
                    "until its shared code-owned execution input binding is implemented"
                )
            if execution_binding is None and p.get("wired") is not False:
                err(f"standing provider {pid!r}: must remain explicitly wired=false while parked")
            if execution_binding is None and (
                not isinstance(route, dict) or route.get("route_state") != "unwired"
            ):
                err(f"standing provider {pid!r}: bound route must remain explicitly unwired while parked")
            approved_args = list(grok_agent_mod.APPROVED_STANDING_TEMPLATE)
            if approved_args.count("{sandbox_profile}") != 1:
                err("standing recipe validator must contain exactly one {sandbox_profile} token")
            sandbox_idx = approved_args.index("--sandbox") if "--sandbox" in approved_args else -1
            if sandbox_idx < 0 or approved_args[sandbox_idx + 1] != "{sandbox_profile}":
                err(
                    f"seat-exec recipe {pid!r}: --sandbox must be followed by "
                    "{{sandbox_profile}}; hard-coding a shadowable profile name is forbidden"
                )
            if "mb-standing" in approved_args:
                err(
                    f"seat-exec recipe {pid!r}: hard-coded mb-standing sandbox name is forbidden"
                )
            if "--deny" not in approved_args or "MCPTool(*)" not in approved_args:
                err(f"seat-exec recipe {pid!r}: must deny MCPTool(*) exactly")
            if "--tools" not in approved_args or "read_file,grep,list_dir" not in approved_args:
                err(
                    f"seat-exec recipe {pid!r}: must pin Grok built-in tool ids "
                    "read_file,grep,list_dir"
                )
            if "--no-subagents" not in approved_args or "--disable-web-search" not in approved_args:
                err(f"seat-exec recipe {pid!r}: must disable subagents and web search/fetch")
            if r.get("args_template") != approved_args:
                err(
                    f"seat-exec recipe {pid!r}: args_template must match exact approved argv "
                    f"{approved_args!r}; removing, renaming, duplicating, reordering, or "
                    "hard-coding {{sandbox_profile}} is forbidden"
                )
            caps = r.get("required_capabilities")
            if not isinstance(caps, list) or any(not isinstance(x, str) or not x for x in caps):
                err(f"seat-exec recipe {pid!r}: required_capabilities must be a string list")
            elif caps != approved_capabilities[pid]:
                err(
                    f"seat-exec recipe {pid!r}: required_capabilities must be exact "
                    f"runtime-attested list {approved_capabilities[pid]!r}"
                )
            connector_role_names = {
                "grok-bot-review-d": "review-d",
                "grok-bot-heat-map": "heat-map",
                "grok-bot-marketplace-intelligence": "marketplace-intelligence",
            }
            connector_roles = (((load_json("connectors.json") or {}).get("grok_cli") or {}).get("roles") or {})
            connector_role = connector_roles.get(connector_role_names[pid]) or {}
            connector_requires = connector_role.get("requires")
            if connector_requires != approved_capabilities[pid]:
                err(
                    f"connectors.grok_cli.roles.{connector_role_names[pid]}.requires must match "
                    f"seat-exec runtime capabilities {approved_capabilities[pid]!r}"
                )
            if connector_role.get("seat") != pid or connector_role.get("agent") != approved_agents[pid]:
                err(
                    f"connectors.grok_cli.roles.{connector_role_names[pid]} must bind "
                    f"seat={pid!r} and agent={approved_agents[pid]!r}"
                )
        route_id = p.get("route")
        route = routes.get(route_id) if route_id else None
        mismatch = wrapped_recipe_error(pid, r, route, wrappers)
        if mismatch:
            err(mismatch)
        flag = r.get("separate_invocation_when_dispatcher")
        if flag is not None and flag is not True and flag is not False:
            err(f"seat-exec recipe {pid!r}: separate_invocation_when_dispatcher must be a boolean")
    grok_agent = load_module("grok_agent_doctor", HERE / "grok-agent.py")
    if grok_agent.STAGED_SANDBOX_PLACEHOLDER != "<ephemeral-sandbox-profile>":
        err("inspect must show the non-executable <ephemeral-sandbox-profile> placeholder")
    dummy_profile = grok_agent.SANDBOX_PROFILE_PREFIX + ("0" * 32)
    socket_snapshot = ()
    try:
        grok_agent.validate_sandbox_profile_name(dummy_profile)
        socket_snapshot = grok_agent.capture_runtime_socket_snapshot()
        profile_text = grok_agent._sandbox_profile_text(
            dummy_profile, socket_snapshot=socket_snapshot
        )
    except ValueError as exc:
        err(f"standing Grok sandbox profile failed closed: {exc}")
        profile_text = ""
    if profile_text and 'extends = "strict"' not in profile_text:
        err("standing Grok sandbox profile must extend strict")
    if grok_agent._runtime_socket_snapshot_incompatible(socket_snapshot):
        if sys.platform != "darwin":
            err(
                "symlink runtime-socket endpoints on a non-macOS host must PARK; "
                "restrict_network=false is macOS-only"
            )
        elif "restrict_network = false" not in profile_text:
            err(
                "Grok 1.0.13 runtime-socket auto-deny fails when well-known "
                "endpoints are symlinks; standing launcher must set "
                "restrict_network=false and deny only resolved non-symlink sockets"
            )
        else:
            info(
                "Grok 1.0.13 cannot auto-deny symlink runtime sockets; standing "
                "roles keep extends=strict, skip inherited restrict_network on macOS, and "
                "deny resolved non-symlink socket targets only"
            )
    for pid, p in (provs or {}).items():
        if (p.get("review_eligible") is True
                and p.get("dispatch_eligible") is True):
            recipe = recipes.get(pid)
            if not isinstance(recipe, dict) or recipe.get("separate_invocation_when_dispatcher") is not True:
                err(f"seat-exec: provider {pid!r} is review_eligible and dispatch_eligible so "
                    "separate_invocation_when_dispatcher must be true")


def check_observability(monitoring):
    """Observability config is fail-closed when present and malformed. The privacy
    boundary cannot be switched off. Telemetry write failure is a runtime concern
    and must not be confused with a routing decision."""
    schema_path = CONFIG / "observability-event.schema.json"
    if not schema_path.exists():
        err("missing config/observability-event.schema.json")
    else:
        try:
            schema = json.loads(schema_path.read_text())
            if schema.get("required") != ["schema_version", "event_id", "run_id", "ts", "kind"]:
                err("observability-event.schema.json required fields drifted")
            if schema.get("additionalProperties") is not True:
                err("observability-event.schema.json must allow additionalProperties (future fields)")
        except Exception as exc:
            err(f"observability-event.schema.json: {exc}")
    try:
        obs_mod = load_module("observe_doc", HERE / "observe.py")
    except Exception as exc:
        err(f"observe.py cannot import: {exc}")
        return
    block = (monitoring or {}).get("observability") if monitoring is not None else None
    if monitoring is not None and not block:
        info("monitoring.json has no observability block — routing-quality telemetry is off")
    if block:
        for e in obs_mod.validate_config(block):
            err(e)
        privacy = block.get("privacy") or {}
        for key in ("forbid_task_bodies", "forbid_absolute_paths",
                    "forbid_credentials", "pseudonymous_actors_only"):
            if key in privacy and privacy[key] is not True:
                err(f"observability.privacy.{key} must remain true")
    try:
        ev = obs_mod.make_event(
            "route_decision", run_id="lane-doctor-obs", ts="2026-01-01T00:00:00+00:00",
            source="observe-cli", actor_id="profile:default", profile_id="default",
            intake={"requested": "opus-5", "effective": "opus-5", "fallback_used": False},
            task={"class": "repo-code", "scale": "routine", "risk_flags": [],
                  "review_depth": "single-frontier"},
            routing_satisfied=True,
            tokens={"measured": False},
        )
        eid = ev["event_id"]
        again = obs_mod.make_event(
            "route_decision", run_id="lane-doctor-obs", ts="2026-01-01T00:00:01+00:00",
            source="observe-cli", actor_id="profile:default", profile_id="default",
            intake={"requested": "opus-5", "effective": "opus-5", "fallback_used": False},
            task={"class": "repo-code", "scale": "routine", "risk_flags": [],
                  "review_depth": "single-frontier"},
            routing_satisfied=True,
            tokens={"measured": False},
        )
        if again["event_id"] != eid:
            err("observe event_id is not idempotent for the same decision fingerprint")
        folded = obs_mod.fold_run([ev, again])
        if folded["event_count"] != 1:
            err(f"observe fold did not dedupe idempotent event ids: {folded}")
        report = obs_mod.analyze([ev])
        if report.get("causal_claim") is not False:
            err("observe analyze must label results as non-causal")
        if report.get("tokens", {}).get("token_per_success") is not None:
            err("observe analyze fabricated token-per-success from unmeasured data")
    except Exception as exc:
        err(f"observe core round-trip raised: {exc}")
    fixture = ROOT / "model-evals" / "fixtures" / "observability" / "v1-correlated-runs.jsonl"
    if not fixture.exists():
        err("missing committed synthetic observability fixture "
            "model-evals/fixtures/observability/v1-correlated-runs.jsonl")
    else:
        events = obs_mod.read(fixture)
        if len(events) < 4:
            err("observability fixture is too small to exercise multi-run analysis")
        for ev in events:
            for problem in obs_mod.validate_event(ev):
                err(f"observability fixture {ev.get('event_id')}: {problem}")
            blob = json.dumps(ev)
            if "/Users/" in blob or "/home/" in blob:
                err("observability fixture contains an absolute user path")


def check_monitoring_sources(monitoring):
    if monitoring is None:
        return
    sources = monitoring.get("sources") if isinstance(monitoring, dict) else None
    if not isinstance(sources, dict):
        err("monitoring.sources must be an object")
        return
    for name, source in sources.items():
        if not isinstance(source, dict):
            err(f"monitoring source {name!r} must be an object")
            continue
        if type(source.get("enabled")) is not bool:
            err(f"monitoring source {name!r}: enabled must be a boolean")
        if "cmd" in source and (
            not isinstance(source.get("cmd"), str) or not source["cmd"].strip()
        ):
            err(f"monitoring source {name!r}: cmd must be a non-empty string when present")


def check_runledger():
    """The stateful spine must import and its pure fold must round-trip deterministically —
    a broken ledger silently loses run-state (fix-loop cap, starvation guard become vibes)."""
    try:
        rl = load_module("runledger_doc", HERE / "runledger.py")
    except Exception as exc:
        err(f"runledger cannot import: {exc}")
        return
    try:
        evs = [
            rl.make_event("lane-doctor", "created", "2026-01-01T00:00:00+00:00"),
            rl.make_event("lane-doctor", "classified", "2026-01-01T00:00:01+00:00",
                          **{"class": "repo-code", "review_depth": "single-frontier"}),
            rl.make_event("lane-doctor", "review-verdict", "2026-01-01T00:00:02+00:00",
                          seat="opus-5", verdict="fix-list"),
            rl.make_event("lane-doctor", "review-verdict", "2026-01-01T00:00:03+00:00",
                          seat="opus-5", verdict="ship"),
        ]
        st = rl.fold(evs)
        ok = (st["status"] == "review-passed" and st["class"] == "repo-code"
              and st["fix_loops"] == 1 and st["event_count"] == 4 and st["terminal"] is False)
        if not ok:
            err(f"runledger fold round-trip wrong: {st}")
    except Exception as exc:
        err(f"runledger fold raised: {exc}")


def check_roles_and_windows_run(providers_path, roles_path):
    try:
        gen = load_module("gen_roles", HERE / "generate-roles.py")
        integ = load_module("integrations_roles_fixture", HERE / "integrations.py")
        fixture = ROOT / "model-evals/fixtures/integrations/all-observed.json"
        gen.load(roles_path, providers_path, inventory=integ.fixture_inventory(fixture))
    except Exception as exc:
        err(f"roles registry invalid (generate-roles.load): {exc}")
    try:
        us = load_module("usage_status_doc", HERE / "usage-status.py")
        us.compute()
    except SystemExit as exc:
        err(f"usage-status cannot compute: {exc}")
    except Exception as exc:
        err(f"usage-status cannot compute: {exc}")


def check_doctrine_has_classes(depth):
    if not depth:
        return
    doctrine = ROOT / "DOCTRINE.md"
    if not doctrine.exists():
        warn("DOCTRINE.md missing — cannot confirm review-depth classes are documented")
        return
    text = doctrine.read_text()
    for cid in depth.get("classes", {}):
        if cid not in text:
            warn(f"review-depth class {cid!r} not mentioned in DOCTRINE.md §Review depth (doc/machine drift)")


STALE_PATHS = [
    "roles/generate.py", "roles/roles.json", "roles/record-429.sh", "roles/test_generate.py",
    "roles/README.md", "roles/PROPOSAL.md",
]
STALE_POLICY_PATTERNS = [
    (re.compile(r"(?:^|[~/])git/orcastrate(?:/|\b)", re.IGNORECASE),
     "retired orchestration checkout"),
    (re.compile(r"\bopus[ -]?5\b.{0,32}\b(?:is|remains|must be)\s+(?:strictly\s+)?(?:forbidden|banned)\b", re.IGNORECASE),
     "retired Opus 5 prohibition"),
    (re.compile(r"\b(?:forbid|forbidden|ban|banned)\b.{0,32}\bopus[ -]?5\b", re.IGNORECASE),
     "retired Opus 5 prohibition"),
    (re.compile(r"\bnot\s+opus[ -]?5\b", re.IGNORECASE),
     "retired Opus 4.8-only pin"),
]
RAW_IDS = ["wpxqdpcski", "wpxjicd0hx", "151997710406", "151997775942", "151997743174", "C0BS66SEV0R"]


def stale_policy_matches(text):
    """Return retired operational-policy references found in active prose."""
    return [(pattern.pattern, meaning) for pattern, meaning in STALE_POLICY_PATTERNS
            if pattern.search(text)]


def prose_hygiene():
    md_files = list(ROOT.glob("*.md")) + list((ROOT / ".claude").rglob("*.md"))
    link_re = re.compile(r"\]\(([\w./-]+\.(?:md|json|py|sh|toml))\)")
    backtick_re = re.compile(r"`((?:bin|config|roles|\.claude|\.cursor)/[\w./-]+|[A-Z][\w-]+\.md)`")
    for md in md_files:
        rel = md.relative_to(ROOT).as_posix()
        text = md.read_text()
        # broken internal links + backtick repo paths
        for m in list(link_re.finditer(text)) + list(backtick_re.finditer(text)):
            target = m.group(1)
            if target.startswith("http"):
                continue
            if target.startswith("./"):
                target = target[2:]
            target = target.rstrip("/") or target
            if target in ALLOWED_MISSING or target.startswith("generated/"):
                continue
            if not (ROOT / target).exists():
                warn(f"{rel}: reference to missing repo path '{m.group(1)}'")
        for sp in STALE_PATHS:
            if sp in text:
                warn(f"{rel}: references removed path '{sp}' (moved under bin/ or config/)")
        for stale, meaning in stale_policy_matches(text):
            err(f"{rel}: contains {meaning} text matching {stale!r}")
        for rid in RAW_IDS:
            if rid in text:
                warn(f"{rel}: contains raw live id '{rid}' — should come from config/connectors.json via bin/connectors.py")


_BIN_REF_RE = re.compile(r"\bbin/([A-Za-z0-9_][A-Za-z0-9_.-]*\.(?:py|sh))\b")


def check_bin_references():
    """Referential integrity for CITED scripts (ERROR, not just a prose warning): every
    bin/<script>.(py|sh) named in a config/*.json (across the active config layer) OR in prose
    (*.md) MUST exist under bin/. prose_hygiene only WARNS on backtick repo paths and never
    scans JSON at all — so a config file citing a renamed/removed script (e.g. the
    detect-fable.py → detect-capability.py rename) passed doctor clean while mis-pointing every
    reader. Fail closed: a dangling bin/ citation is a hard error."""
    sources: list[Path] = []
    seen: set[Path] = set()
    for d in mborch.config_dirs():
        rd = d.resolve()
        if rd in seen or not d.exists():
            continue
        seen.add(rd)
        sources += sorted(d.glob("*.json"))
    sources += sorted(ROOT.glob("*.md")) + sorted((ROOT / ".claude").rglob("*.md"))
    reported: set[tuple[str, str]] = set()
    for src in sources:
        try:
            text = src.read_text()
        except Exception:
            continue
        try:
            rel = src.relative_to(ROOT).as_posix()
        except ValueError:
            rel = str(src)
        for m in _BIN_REF_RE.finditer(text):
            script = m.group(1)
            if (ROOT / "bin" / script).exists():
                continue
            key = (rel, script)
            if key in reported:
                continue
            reported.add(key)
            err(f"{rel}: cites bin/{script} which does not exist under bin/ "
                "(renamed or removed? fix the reference or restore the script)")


def check_forbidden_matcher():
    """Forbidden models are the explicit providers.json map only. Opus 5 must NOT be
    auto-blocked (it is the operational Anthropic gate). is_opus5_zero remains a
    classifier for the 5 GA line vs later minors."""
    if mborch.model_is_forbidden("claude-opus-5", {}):
        err("forbidden-matcher regression: Opus 5 is auto-forbidden; it must route")
    if mborch.model_is_forbidden("opus-5", {}):
        err("forbidden-matcher regression: bare opus-5 is auto-forbidden; it must route")
    if not mborch.is_opus5_zero("claude-opus-5") or not mborch.is_opus5_zero("opus-5"):
        err("classifier regression: Opus 5 GA forms should still match is_opus5_zero")
    if mborch.is_opus5_zero("opus-5-1") or mborch.is_opus5_zero("claude-opus-4-8"):
        err("classifier regression: 5.1+ / 4.8 must not match is_opus5_zero")
    fake = {"do-not-run": {"aliases": ["never-this-model"]}}
    if not mborch.model_is_forbidden("never-this-model", fake):
        err("forbidden-matcher regression: explicit alias was not forbidden")
    if mborch.model_is_forbidden("claude-opus-5", fake):
        err("forbidden-matcher regression: Opus 5 blocked by an unrelated map")


def check_model_registry(providers, connectors=None):
    """The model catalog must parse, stay fresh, and stay bound to providers.json."""
    try:
        mr = load_module("model_registry_doc", HERE / "model-registry.py")
    except Exception as exc:
        err(f"model-registry.py cannot import: {exc}")
        return
    try:
        registry = mr.load()
    except Exception as exc:
        err(f"model-registry.json cannot load: {exc}")
        return
    for e in mr.validate(registry, providers=providers, connectors=connectors):
        err(e)
    try:
        mr.write_matrix(registry, check=True)
    except Exception as exc:
        err(f"generated/model-matrix.md: {exc}")
    try:
        cases_mod = load_module("model_eval_doc", HERE / "model-eval.py")
        cases = cases_mod.load_cases()
        for e in cases_mod.validate_cases(cases):
            err(e)
    except Exception as exc:
        err(f"model-evals/cases.json: {exc}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validate the mb-orchestration setup.")
    ap.add_argument("--strict", action="store_true", help="treat warnings as failures")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    providers = load_json("providers.json")
    subs = load_json("subscriptions.json")
    conns = load_json("connectors.json")
    integration_adapters = load_json("integration-adapters.json")
    entry = load_json("entrypoints.json")
    windows = load_json("usage-windows.json")
    roles = load_json("roles.json")
    depth = load_json("review-depth.json")
    monitoring = load_json("monitoring.json", required=False)
    seat_exec = load_json("seat-exec.json", required=False)
    skills = load_json("skills.json", required=False)
    model_reg = load_json("model-registry.json")
    handoff = load_json("handoff-policy.json")

    schema_validate({"providers": providers, "subscriptions": subs, "connectors": conns,
                     "integration_adapters": integration_adapters,
                     "entrypoints": entry, "usage_windows": windows, "roles": roles,
                     "review_depth": depth, "monitoring": monitoring, "seat_exec": seat_exec,
                     "skills": skills, "model_registry": model_reg, "handoff_policy": handoff})

    if monitoring is not None:
        rd = monitoring.get("retention_days")
        if not isinstance(rd, int) or rd < 0:
            err(f"monitoring.retention_days must be a non-negative integer, got {rd!r}")
    check_monitoring_sources(monitoring)
    check_observability(monitoring)

    provs, provider_ids, _ = check_providers(providers)
    fable_from_subs = check_subscriptions(subs, provider_ids)
    check_provider_backings(provs, subs, windows)
    check_connectors(conns, provider_ids)
    check_runtime_tool_mappings(conns)
    check_integration_adapters(integration_adapters, providers)
    check_connector_lifecycle(conns, providers)
    check_skills(skills, providers, conns)
    check_entrypoints(entry, provs, provider_ids)
    check_handoff_policy(handoff)
    subs_ids = set((subs or {}).get("subscriptions", {}))
    check_windows(windows, subs_ids, fable_from_subs, provs)
    check_review_depth(depth)
    check_doctrine_has_classes(depth)
    check_roles_and_windows_run(CONFIG / "providers.json", CONFIG / "roles.json")
    check_forbidden_matcher()
    check_model_registry(providers, conns)
    check_seat_exec(seat_exec, provs, provider_ids, model_reg)
    check_runledger()
    prose_hygiene()
    check_bin_references()

    if args.json:
        print(json.dumps({"errors": ERRORS, "warnings": WARNINGS, "info": INFO,
                          "ok": not ERRORS and (not WARNINGS or not args.strict)}, indent=2))
    else:
        print("doctor — mb-orchestration setup validation")
        print("=" * 72)
        if ERRORS:
            print(f"ERRORS ({len(ERRORS)}):")
            for e in ERRORS:
                print(f"  ✗ {e}")
        if WARNINGS:
            print(f"WARNINGS ({len(WARNINGS)}):")
            for w in WARNINGS:
                print(f"  ! {w}")
        if INFO:
            for i in INFO:
                print(f"  · {i}")
        if not ERRORS and not WARNINGS:
            print("  ✓ all checks passed — config integrity + prose hygiene clean")
        print("=" * 72)
        print(f"errors={len(ERRORS)} warnings={len(WARNINGS)} strict={args.strict}")

    if ERRORS or (args.strict and WARNINGS):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
