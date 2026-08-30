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
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mborch  # noqa: E402
import integrations  # noqa: E402


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
    if f"name: {agent}" not in profile.read_text(errors="replace"):
        return f"installed profile {profile} has the wrong agent name"
    return None


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
    if prompt_file is None or not prompt_file.is_file():
        problems.append("prompt file does not exist")

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
        recipes = mborch.load_config("seat-exec.json", required=True)["recipes"]
        agent = recipes[args.seat].get("required_agent")
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
        if recipes[args.seat].get("args_template") != expected_template:
            problems.append("recipe argv differs from the approved Grok named-agent contract")
        result = {"seat": args.seat, "agent": agent, "smoke": True,
                  "ready": not problems, "problems": problems}
        if problems or not args.execute:
            print(json.dumps(result, indent=2 if args.json else None))
            return 0 if not problems else 2
        cmd = ["grok", "--cwd", str(cwd), "--agent", str(profile), "--model", "grok-4.6",
               "--reasoning-effort", "high", "--no-subagents", "--output-format", "plain",
               "-p", "CLI transport smoke only. Use no tools and return exactly: cli-agent-ok"]
        return subprocess.run(cmd, cwd=cwd, check=False).returncode

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
