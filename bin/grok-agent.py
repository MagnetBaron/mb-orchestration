#!/usr/bin/env python3
"""Validate and launch the three standing Grok roles through the real Grok CLI.

This is deliberately narrower than the general executor. It never uses Slack, never
constructs a shell string, and only renders recipes already pinned in seat-exec.json.
Normal execution fails closed unless the provider is wired and its catalog route is
live_verified. ``--smoke`` only proves CLI/profile/model selection; it does not prove
browser, Clarity, marketplace access, or a role result.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mborch  # noqa: E402
import integrations  # noqa: E402
import connectors as connector_packets  # noqa: E402

_SYNC_SPEC = importlib.util.spec_from_file_location(
    "grok_agent_sync_profiles", Path(__file__).resolve().parent / "sync-grok-agents.py"
)
sync_profiles = importlib.util.module_from_spec(_SYNC_SPEC)
_SYNC_SPEC.loader.exec_module(sync_profiles)


SEATS = (
    "grok-bot-review-d",
    "grok-bot-heat-map",
    "grok-bot-marketplace-intelligence",
)


def _render(recipe: dict, *, cwd: Path, prompt_file: Path, agent_profile: Path) -> list[str]:
    context = {
        "repo": str(cwd),
        "brief_path": str(prompt_file),
        "agent_profile": str(agent_profile),
    }
    argv = [str(recipe.get("bin") or "")]
    for raw in recipe.get("args_template") or []:
        token = str(raw)
        for key, value in context.items():
            token = token.replace("{" + key + "}", value)
        argv.append(token)
    return argv


def _profile_problem(profile: Path | None, agent: str | None) -> str | None:
    if not agent or profile is None or not profile.is_file() or profile.is_symlink():
        return f"required Grok agent profile {agent!r} is not installed as a regular file"
    try:
        expected = sync_profiles.expected().get(profile.name)
        actual = profile.read_text()
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        return f"cannot validate installed profile {profile}: {exc}"
    if expected is None or actual != expected:
        return f"installed profile {profile} does not byte-match generated read-only policy"
    return None


def _prompt_problem(seat: str, prompt_file: Path | None) -> str | None:
    if prompt_file is None or not prompt_file.is_file() or prompt_file.is_symlink():
        return "prompt file must be a regular non-symlink file"
    try:
        raw = prompt_file.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        return f"prompt file is not readable UTF-8: {exc}"
    if not raw or len(raw) > 65_536 or "\x00" in text:
        return "prompt file must be non-empty UTF-8 and at most 65536 bytes"
    if seat == "grok-bot-review-d":
        config = connector_packets.load()
        allowed = {
            body.rstrip("\n")
            for store in (config.get("stores") or {})
            for body in _safe_review_d_packets(config, store)
        }
        if text.rstrip("\n") not in allowed:
            return "Review D prompt must byte-match a validated bin/connectors.py packet"
        return None
    required_role = {
        "grok-bot-heat-map": "heat-map",
        "grok-bot-marketplace-intelligence": "marketplace-intelligence",
    }.get(seat)
    fields = {}
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() and key.strip() not in fields:
            fields[key.strip()] = value.strip()
    if fields.get("role") != required_role:
        return f"prompt must declare exact role: {required_role}"
    allowed_sources = ({"approved-clarity-export"} if seat == "grok-bot-heat-map"
                       else {"owner-deposited", "authorized-api-output"})
    if fields.get("source") not in allowed_sources:
        return "prompt must declare an approved evidence source"
    evidence_raw = fields.get("evidence-path")
    digest = fields.get("evidence-sha256")
    if not evidence_raw or not digest or not digest.startswith("sha256:"):
        return "prompt must bind evidence-path and evidence-sha256"
    evidence = Path(evidence_raw).expanduser()
    if not evidence.is_absolute():
        evidence = (prompt_file.parent / evidence).resolve()
    if not evidence.is_file() or evidence.is_symlink():
        return "bound evidence must be a regular non-symlink file"
    try:
        actual_digest = "sha256:" + hashlib.sha256(evidence.read_bytes()).hexdigest()
    except OSError as exc:
        return f"bound evidence is unreadable: {exc}"
    if actual_digest != digest:
        return "bound evidence digest does not match evidence-sha256"
    return None


def _safe_review_d_packets(config: dict, store: str) -> list[str]:
    packets = []
    for render in (connector_packets.render_ticket, connector_packets.render_live_ticket):
        try:
            packets.append(render(config, store))
        except SystemExit:
            continue
    return packets


def inspect(seat: str, cwd: Path, prompt_file: Path | None, agent_dir: Path) -> dict:
    providers = mborch.load_config("providers.json", required=True)["providers"]
    recipes = mborch.load_config("seat-exec.json", required=True)["recipes"]
    registry = mborch.load_config("model-registry.json", required=True)
    provider = providers.get(seat) or {}
    recipe = recipes.get(seat) or {}
    route_id = provider.get("route")
    route = (registry.get("routes") or {}).get(route_id) or {}
    agent = recipe.get("required_agent")
    profile = agent_dir / f"{agent}.md" if agent else None
    binary = shutil.which(str(recipe.get("bin") or ""))
    problems: list[str] = []

    if provider.get("kind") != "cli":
        problems.append("provider is not a CLI seat")
    if provider.get("model") != "grok-4.6" or route.get("model") != "grok-4.6":
        problems.append("provider and route must pin exact model grok-4.6")
    if route.get("host") != "grok-cli" or route.get("harness") != "grok":
        problems.append("provider route is not the Grok CLI harness")
    if not provider.get("wired"):
        problems.append("provider wired is not true")
    if route.get("route_state") != "live_verified":
        problems.append(f"route {route_id!r} is not live_verified")
    if not binary:
        problems.append("grok executable is not on PATH")
    profile_problem = _profile_problem(profile, agent)
    if profile_problem:
        problems.append(profile_problem)
    prompt_problem = _prompt_problem(seat, prompt_file)
    if prompt_problem:
        problems.append(prompt_problem)

    argv = _render(
        recipe,
        cwd=cwd,
        prompt_file=prompt_file or Path("<prompt-file>"),
        agent_profile=profile or Path("<agent-profile>"),
    )
    if argv[0] != "grok":
        problems.append("recipe binary must be exact grok")
    expected = [
        "--cwd", str(cwd), "--agent", str(profile), "--prompt-file",
        str(prompt_file or Path("<prompt-file>")), "--model", "grok-4.6",
        "--reasoning-effort", "high", "--no-subagents", "--output-format", "plain",
    ]
    if argv[1:] != expected:
        problems.append("recipe argv differs from the approved Grok named-agent contract")
    for capability in recipe.get("required_capabilities") or []:
        ok, reason = integrations.effective(
            "grok", "capability", capability, require_callable=True
        )
        if not ok:
            problems.append(f"required runtime capability {capability!r} is unavailable: {reason}")

    return {
        "seat": seat,
        "agent": agent,
        "route": route_id,
        "route_state": route.get("route_state"),
        "required_capabilities": recipe.get("required_capabilities") or [],
        "binary": binary,
        "profile": str(profile) if profile else None,
        "argv": argv,
        "ready": not problems,
        "problems": problems,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed Grok named-agent launcher (no Slack).")
    ap.add_argument("--seat", required=True, choices=SEATS)
    ap.add_argument("--prompt-file", type=Path)
    ap.add_argument("--cwd", type=Path, default=mborch.REPO)
    ap.add_argument("--agent-dir", type=Path, default=Path.home() / ".grok" / "agents")
    ap.add_argument("--integration-session", metavar="FILE|-",
                    help="fresh process-scoped Grok capability attestation")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--smoke", action="store_true",
                    help="prove only CLI/profile/model selection with a fixed no-tool prompt")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    cwd = args.cwd.resolve()
    if args.integration_session:
        try:
            integrations.load_session(args.integration_session)
        except integrations.InventoryError as exc:
            print(f"PARK: invalid integration session: {exc}", file=sys.stderr)
            return 2

    if args.smoke:
        recipes = mborch.load_config("seat-exec.json", required=True).get("recipes") or {}
        recipe = recipes.get(args.seat)
        if not isinstance(recipe, dict):
            print(json.dumps({"seat": args.seat, "smoke": True, "ready": False,
                              "problems": ["seat recipe is missing"]}))
            return 2
        agent = recipe.get("required_agent")
        profile = args.agent_dir / f"{agent}.md"
        binary = shutil.which("grok")
        problems = []
        if not binary:
            problems.append("grok executable is not on PATH")
        profile_problem = _profile_problem(profile, agent)
        if profile_problem:
            problems.append(profile_problem)
        expected_template = [
            "--cwd", "{repo}", "--agent", "{agent_profile}", "--prompt-file", "{brief_path}",
            "--model", "grok-4.6", "--reasoning-effort", "high", "--no-subagents",
            "--output-format", "plain",
        ]
        if recipe.get("args_template") != expected_template:
            problems.append("recipe argv differs from the approved Grok named-agent contract")
        result = {"seat": args.seat, "agent": agent, "smoke": True,
                  "ready": not problems, "problems": problems}
        if problems or not args.execute:
            print(json.dumps(result, indent=2 if args.json else None))
            return 0 if not problems else 2
        with tempfile.TemporaryDirectory(prefix="grok-agent-smoke-") as smoke_dir:
            cmd = ["grok", "--cwd", smoke_dir, "--agent", str(profile), "--model", "grok-4.6",
                   "--reasoning-effort", "high", "--no-subagents", "--output-format", "plain",
                   "-p", "CLI transport smoke only. Use no tools and return exactly: cli-agent-path-ok"]
            completed = subprocess.run(
                cmd, cwd=smoke_dir, check=False, text=True, capture_output=True
            )
            if completed.stdout:
                print(completed.stdout, end="")
            if completed.stderr:
                print(completed.stderr, end="", file=sys.stderr)
            last_line = (completed.stdout or "").rstrip().splitlines()[-1:]
            if completed.returncode != 0 or last_line != ["cli-agent-path-ok"]:
                print("PARK: Grok CLI smoke did not return exact cli-agent-path-ok", file=sys.stderr)
                return 2
            return 0

    result = inspect(args.seat, cwd, args.prompt_file, args.agent_dir)
    if args.json or not args.execute:
        print(json.dumps(result, indent=2))
    if not result["ready"]:
        if args.execute and not args.json:
            print("PARK: " + "; ".join(result["problems"]), file=sys.stderr)
        return 2
    if not args.execute:
        return 0
    return subprocess.run(result["argv"], cwd=cwd, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
