#!/usr/bin/env python3
"""detect-agents — auto-detect installed CLI agents and discover unregistered ones.

Makes the provider registry self-checking and modular:
  * For every provider in config/providers.json, run its `detect` spec and report
    present / absent / manual — so a machine with a different toolset sees exactly
    which seats are live without editing prose.
  * Scan PATH for KNOWN agent binaries that are NOT yet registered, so a new CLI
    agent is surfaced ("register it") instead of silently ignored.
  * `--register-template <cmd>` prints a ready-to-paste providers.json entry.

Detection is informational: absent seats are normal (a portable setup rarely has
every provider). Exit is always 0 unless config is unreadable. No network calls.
"""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE.parent / "config"

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


def load_providers():
    path = CONFIG / "providers.json"
    if not path.exists():
        sys.exit(f"detect-agents: missing {path}")
    return json.loads(path.read_text())


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


def detect_one(pid: str, p: dict) -> dict:
    det = p.get("detect") or {}
    method = det.get("method")
    enabled = p.get("enabled", True)
    result = {"provider": pid, "label": p.get("label"), "family": p.get("family"),
              "level": p.get("level"), "method": method, "enabled": enabled}
    if not enabled:
        result["status"] = "disabled (template)"
        return result
    if method == "command" or method == "local":
        cmd = det.get("cmd")
        path = shutil.which(cmd) if cmd else None
        result["status"] = f"present ({path})" if path else "absent"
        result["present"] = bool(path)
    elif method == "npm":
        pkg = det.get("pkg", "")
        ok = npm_global_has(pkg)
        result["status"] = f"present (npm -g {pkg})" if ok else f"absent (npm -g {pkg})"
        result["present"] = ok
    elif method == "api":
        env = det.get("env", "")
        ok = bool(os.environ.get(env))
        result["status"] = f"env {env} set" if ok else f"env {env} unset (unwired)"
        result["present"] = ok
    elif method == "app":
        result["status"] = "app-only (manual; no CLI/API — see grokbot-connection.md)"
        result["present"] = None
    elif method == "capability":
        grant = det.get("grant", "?")
        result["status"] = f"subscription grant '{grant}' — run bin/detect-fable.py"
        result["present"] = None
    else:
        result["status"] = f"unknown detect method {method!r}"
        result["present"] = None
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
            "enabled": True, "backed_by": None,
            "detect": {"method": "command", "cmd": cmd},
            "notes": f"Registered {label}. Adjust level/family/functions, then run bin/doctor.py."
        }
    }
    return json.dumps(entry, indent=2)


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

    rows = [detect_one(pid, p) for pid, p in providers_data.get("providers", {}).items()]
    unregistered = discover_unregistered(providers_data)

    if args.json:
        print(json.dumps({"detected": rows, "unregistered_on_path": unregistered}, indent=2))
        return 0

    print("detect-agents  (config/providers.json)")
    print("-" * 72)
    for r in rows:
        print(f"{r['provider']:<20} {str(r['method'] or '-'):<10} {r['status']}")
    print("-" * 72)
    if unregistered:
        print("UNREGISTERED agent binaries found on PATH (modular add — register with")
        print("bin/detect-agents.py --register-template <cmd>, paste into providers.json, run doctor):")
        for u in unregistered:
            print(f"  + {u['cmd']:<14} {u['path']}  — {u['desc']}")
    else:
        print("no unregistered known agent binaries on PATH.")
    print("-" * 72)
    print("absent seats are normal on a portable setup; resolve-route routes around them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
