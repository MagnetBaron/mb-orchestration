#!/usr/bin/env python3
"""detect-agents — inventory local transports and discover unregistered CLIs.

Makes the provider registry self-checking and modular:
  * For every provider in config/providers.json, run its `detect` spec and report
    transport/credential presence separately from configured route state. Presence
    never certifies that a provider or standing role is executable.
  * Scan PATH for KNOWN agent binaries that are NOT yet registered, so a new CLI
    agent is surfaced ("register it") instead of silently ignored.
  * `--register-template <cmd>` prints a ready-to-paste providers.json entry.

Detection is informational: absent transports are normal (a portable setup rarely
has every provider). Exit is always 0 unless config is unreadable. No network calls.
"""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mborch  # noqa: E402
import teamclaude_status  # noqa: E402

# Binaries that are plausibly CLI coding/agent tools worth registering if found.
KNOWN_AGENT_BINARIES = {
    "claude": "Claude Code (Anthropic)",
    "codex": "Codex CLI (OpenAI)",
    "grok": "Grok Build CLI (xAI)",
    "cursor": "Cursor CLI",
    "cursor-agent": "Cursor agent CLI",
    "aider": "Aider (open-source pair programmer)",
    "gemini": "Gemini CLI (Google)",
    "ollama": "Ollama (local models)",
    "llm": "simonw/llm CLI",
    "goose": "Goose (Block)",
    "opencode": "opencode CLI",
    "amp": "Amp (Sourcegraph)",
    "qwen": "Qwen Code CLI",
}

STANDING_GROK_SEATS = {
    "grok-bot-review-d",
    "grok-bot-heat-map",
    "grok-bot-marketplace-intelligence",
}
def load_providers():
    return mborch.load_config("providers.json", required=True)


def load_model_registry():
    return mborch.load_config("model-registry.json", required=True)


def npm_global_has(pkg: str) -> bool:
    npm = shutil.which("npm")
    if not npm:
        return False
    try:
        out = subprocess.run([npm, "ls", "-g", "--depth=0", pkg],
                             capture_output=True, text=True, timeout=20)
        return pkg in out.stdout
    except Exception:
        return False


def _exact_flag(data: dict, key: str, *, default: bool) -> tuple[bool, str | None]:
    raw = data.get(key, default)
    if not isinstance(raw, bool):
        return False, f"{key} must be an exact JSON boolean"
    return raw is True, None


def _route_state(p: dict, registry: dict) -> tuple[str | None, str | None, str | None]:
    route_id = p.get("route")
    if route_id is None:
        return None, None, None
    if not isinstance(route_id, str) or not route_id:
        return None, None, "route must be a non-empty string"
    route = (registry.get("routes") or {}).get(route_id)
    if not isinstance(route, dict):
        return route_id, None, f"route {route_id!r} is absent from model-registry.json"
    state = route.get("route_state")
    if not isinstance(state, str) or not state:
        return route_id, None, f"route {route_id!r} has no valid route_state"
    return route_id, state, None


def _standing_readiness(
    *,
    enabled: bool,
    wired: bool,
    transport_present: bool | None,
    route_id: str | None,
    route_state: str | None,
) -> tuple[bool | None, str, list[str]]:
    """Return only provable negative readiness; never infer a positive from PATH."""
    limitations = []
    if not enabled:
        limitations.append("provider enabled is not exact true")
    if not wired:
        limitations.append("provider wired is not exact true")
    if transport_present is not True:
        limitations.append("CLI transport is not present")
    if route_state != "live_verified":
        limitations.append(
            f"catalog route {route_id or '<missing>'} is {route_state or '<missing>'}, "
            "not live_verified"
        )
    limitations.append(
        "detect-agents does not validate the installed named profile, code-owned input "
        "binding, fresh callable capabilities, or bin/grok-agent.py launch preflight"
    )
    blocked = any((not enabled, not wired, transport_present is not True,
                   route_state != "live_verified"))
    return (False if blocked else None,
            "blocked" if blocked else "not evaluated",
            limitations)


def detect_one(pid: str, p: dict, registry: dict | None = None) -> dict:
    registry = registry or {}
    det = p.get("detect") or {}
    method = det.get("method")
    enabled, enabled_problem = _exact_flag(p, "enabled", default=True)
    wired, wired_problem = _exact_flag(p, "wired", default=True)
    route_id, route_state, route_problem = _route_state(p, registry)
    config_problems = [
        problem for problem in (enabled_problem, wired_problem, route_problem) if problem
    ]
    result = {"provider": pid, "label": p.get("label"), "family": p.get("family"),
              "level": p.get("level"), "method": method, "enabled": enabled,
              "wired": wired, "route": route_id, "route_state": route_state,
              "detect_note": det.get("note") if isinstance(det.get("note"), str) else None,
              "detection_scope": "transport_presence_only",
              "config_problems": config_problems}
    transport_present: bool | None = None
    if not enabled:
        result["status"] = ("disabled (template)" if not enabled_problem else
                            "invalid config (enabled is not an exact JSON boolean)")
    elif method == "command" or method == "local":
        cmd = det.get("cmd")
        path = shutil.which(cmd) if cmd else None
        transport_present = bool(path)
        result["status"] = (f"transport present ({path}); role readiness not evaluated"
                            if path else "transport absent")
    elif method == "npm":
        pkg = det.get("pkg", "")
        ok = npm_global_has(pkg)
        transport_present = ok
        result["status"] = (f"transport present (npm -g {pkg}); role readiness not evaluated"
                            if ok else f"transport absent (npm -g {pkg})")
    elif method == "api":
        env = det.get("env", "")
        ok = bool(os.environ.get(env))
        transport_present = ok
        result["detection_scope"] = "credential_presence_only"
        result["status"] = (f"credential signal env {env} set; readiness not evaluated"
                            if ok else f"credential signal env {env} unset")
    elif method == "app":
        result["detection_scope"] = "manual_transport_inventory"
        result["status"] = "app-only (manual; no CLI/API — see grokbot-connection.md)"
    elif method == "capability":
        grant = det.get("grant", "?")
        result["detection_scope"] = "subscription_grant_inventory"
        result["status"] = f"subscription grant '{grant}' — run bin/detect-capability.py"
    else:
        result["detection_scope"] = "unknown"
        result["status"] = f"unknown detect method {method!r}"
    # `present` is retained as a compatibility alias. Its name and value describe
    # only the detected transport/credential signal, never executable readiness.
    result["transport_present"] = transport_present
    result["present"] = transport_present
    result["executable_ready"] = None
    result["readiness"] = "not evaluated"
    result["readiness_limitations"] = [
        "detect-agents reports presence and configured state; resolve-route and the "
        "provider-specific launcher enforce executable readiness"
    ]
    if pid in STANDING_GROK_SEATS:
        ready, readiness, limitations = _standing_readiness(
            enabled=enabled,
            wired=wired,
            transport_present=transport_present,
            route_id=route_id,
            route_state=route_state,
        )
        result["executable_ready"] = ready
        result["readiness"] = readiness
        result["readiness_limitations"] = limitations
    return result


def discover_unregistered(providers_data) -> list[dict]:
    registered_cmds = set()
    for p in providers_data.get("providers", {}).values():
        det = p.get("detect") or {}
        if det.get("method") in ("command", "local") and det.get("cmd"):
            registered_cmds.add(det["cmd"])
    found = []
    for binname, desc in KNOWN_AGENT_BINARIES.items():
        if binname in registered_cmds:
            continue
        path = shutil.which(binname)
        if path:
            found.append({"cmd": binname, "path": path, "desc": desc})
    return found


def register_template(cmd: str) -> str:
    label = KNOWN_AGENT_BINARIES.get(cmd, f"{cmd} CLI")
    entry = {
        f"{cmd}-seat": {
            "label": label, "level": "terra", "family": "open-weight", "kind": "cli",
            "model": None, "functions": ["implement"], "review_eligible": False,
            "enabled": False, "wired": False,
            "detect": {"method": "command", "cmd": cmd},
            "notes": (
                f"INERT template for {label}. Add a validated backed_by subscription, set an "
                "exact route/capability contract, then deliberately enable/wire it."
            )
        }
    }
    return json.dumps(entry, indent=2)


def detect_rotation() -> dict:
    """Report aggregate live rotation state; never copy native account identities."""
    return teamclaude_status.inspect_status()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Detect installed CLI agents; discover unregistered ones.")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--register-template", metavar="CMD",
                    help="print a providers.json entry template for a discovered binary")
    args = ap.parse_args(argv)

    providers_data = load_providers()

    if args.register_template:
        print(register_template(args.register_template))
        return 0

    registry = load_model_registry()
    rows = [
        detect_one(pid, p, registry)
        for pid, p in providers_data.get("providers", {}).items()
    ]
    unregistered = discover_unregistered(providers_data)
    rotation = detect_rotation()

    if args.json:
        print(json.dumps({"detected": rows, "unregistered_on_path": unregistered,
                          "rotation": rotation}, indent=2))
        return 0

    print("detect-agents  (config/providers.json)")
    print("-" * 72)
    for r in rows:
        state = (
            f"enabled={str(r['enabled']).lower()} wired={str(r['wired']).lower()} "
            f"route={r['route'] or '-'}:{r['route_state'] or '-'}"
        )
        print(f"{r['provider']:<20} {str(r['method'] or '-'):<10} {r['status']} [{state}]")
        if r.get("detect_note"):
            print(f"  detect.note: {r['detect_note']}")
        if r["provider"] in STANDING_GROK_SEATS:
            print(f"  executable role readiness: {r['readiness']}")
            for limitation in r["readiness_limitations"]:
                print(f"    - {limitation}")
        for problem in r.get("config_problems", []):
            print(f"  config problem: {problem}")
    print("-" * 72)
    if unregistered:
        print("UNREGISTERED agent binaries found on PATH (modular add — register with")
        print("bin/detect-agents.py --register-template <cmd>, paste into providers.json, run doctor):")
        for u in unregistered:
            print(f"  + {u['cmd']:<14} {u['path']}  — {u['desc']}")
    else:
        print("no unregistered known agent binaries on PATH.")
    print("-" * 72)
    print(f"rotation ({rotation['tool']}): {rotation['status']}")
    print("-" * 72)
    print("absent transports are normal on a portable setup; resolve-route routes around them.")
    print("transport presence never proves provider or standing-role executable readiness.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
