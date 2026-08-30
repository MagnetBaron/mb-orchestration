#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("grok_agent_test_target", HERE / "grok-agent.py")
target = importlib.util.module_from_spec(spec)
spec.loader.exec_module(target)


class GrokAgentTests(unittest.TestCase):
    def test_all_standing_roles_have_exact_named_agent_cli_recipes(self):
        seats = json.loads((HERE.parent / "config" / "seat-exec.json").read_text())["recipes"]
        expected_agents = {
            "grok-bot-review-d": "mb-review-d",
            "grok-bot-heat-map": "mb-heat-map",
            "grok-bot-marketplace-intelligence": "mb-marketplace-intelligence",
        }
        for seat, agent in expected_agents.items():
            with self.subTest(seat=seat):
                recipe = seats[seat]
                self.assertEqual(recipe["bin"], "grok")
                self.assertEqual(recipe["required_agent"], agent)
                self.assertEqual(recipe["args_template"], [
                    "--cwd", "{repo}", "--agent", "{agent_profile}", "--prompt-file", "{brief_path}",
                    "--model", "grok-4.6", "--reasoning-effort", "high",
                    "--no-subagents", "--output-format", "plain",
                ])

    def test_inspect_fails_closed_for_unwired_routes_and_missing_profile(self):
        with tempfile.TemporaryDirectory() as td:
            prompt = Path(td) / "brief.md"
            prompt.write_text("safe fixture")
            with mock.patch.object(target.shutil, "which", return_value="/usr/local/bin/grok"):
                result = target.inspect(
                    "grok-bot-review-d", HERE.parent, prompt, Path(td) / "agents"
                )
        self.assertFalse(result["ready"])
        self.assertTrue(any("wired" in x for x in result["problems"]))
        self.assertTrue(any("live_verified" in x for x in result["problems"]))
        self.assertTrue(any("not installed" in x for x in result["problems"]))

    def test_renderer_preserves_spaces_without_shell_interpolation(self):
        recipe = {
            "bin": "grok",
            "args_template": ["--cwd", "{repo}", "--prompt-file", "{brief_path}"],
        }
        argv = target._render(
            recipe, cwd=Path("/tmp/a repo"), prompt_file=Path("/tmp/a brief.md"),
            agent_profile=Path("/tmp/agents/mb-review-d.md"),
        )
        self.assertEqual(argv, ["grok", "--cwd", "/tmp/a repo", "--prompt-file", "/tmp/a brief.md"])

    def test_inspect_rejects_tampered_template_and_unobserved_capabilities(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            prompt = root / "brief.md"
            prompt.write_text("safe fixture")
            agents = root / "agents"
            agents.mkdir()
            (agents / "mb-review-d.md").write_text("---\nname: mb-review-d\n---\n")
            configs = {
                "providers.json": {"providers": {"grok-bot-review-d": {
                    "kind": "cli", "model": "grok-4.6", "wired": True,
                    "route": "grok-cli-review-d",
                }}},
                "seat-exec.json": {"recipes": {"grok-bot-review-d": {
                    "bin": "grok", "required_agent": "mb-review-d",
                    "required_capabilities": ["browser", "pixels"],
                    "args_template": ["--future-flag"],
                }}},
                "model-registry.json": {"routes": {"grok-cli-review-d": {
                    "model": "grok-4.6", "host": "grok-cli", "harness": "grok",
                    "route_state": "live_verified",
                }}},
            }
            with mock.patch.object(target.mborch, "load_config", side_effect=lambda n, **_: configs[n]), \
                 mock.patch.object(target.shutil, "which", return_value="/usr/local/bin/grok"), \
                 mock.patch.object(target.integrations, "effective", return_value=(False, "not fresh")):
                result = target.inspect("grok-bot-review-d", root, prompt, agents)
        self.assertFalse(result["ready"])
        self.assertTrue(any("approved" in x for x in result["problems"]))
        self.assertEqual(sum("required runtime capability" in x for x in result["problems"]), 2)

    def test_wrong_profile_name_blocks_smoke_before_subprocess(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            agents = root / ".grok" / "agents"
            agents.mkdir(parents=True)
            (agents / "mb-review-d.md").write_text("---\nname: wrong-agent\n---\n")
            with mock.patch.object(target.shutil, "which", return_value="/usr/local/bin/grok"), \
                 mock.patch.object(target.subprocess, "run") as run:
                rc = target.main([
                    "--seat", "grok-bot-review-d", "--smoke", "--execute",
                    "--agent-dir", str(agents), "--cwd", str(HERE.parent),
                ])
        self.assertEqual(rc, 2)
        run.assert_not_called()

    def test_main_never_executes_when_normal_preflight_is_not_ready(self):
        with mock.patch.object(target, "inspect", return_value={
            "ready": False, "problems": ["parked"], "argv": ["grok"]
        }), mock.patch.object(target.subprocess, "run") as run:
            rc = target.main([
                "--seat", "grok-bot-review-d", "--execute",
                "--prompt-file", str(HERE / "test_grok_agent.py"),
            ])
        self.assertEqual(rc, 2)
        run.assert_not_called()

    def test_pixel_route_parks_when_cli_browser_capability_is_unwired(self):
        result = subprocess.run([
            sys.executable, str(HERE / "resolve-route.py"),
            "--class", "storefront-theme", "--scale", "elevated",
            "--intake-provider", "codex-sol", "--implement", "--pixels",
            "--artifacts", "brief,repo-source,diff,test-output", "--json", "--no-record",
        ], cwd=HERE.parent, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        decision = json.loads(result.stdout)
        self.assertFalse(decision["routing_satisfied"])
        self.assertIn("PARK Review D", decision["park_reason"])
        review_d = next(s for s in decision["implement"] if s.get("input_seat"))
        self.assertFalse(review_d["available"])


if __name__ == "__main__":
    unittest.main()
