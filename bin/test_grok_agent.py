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
                    "--cwd", "{repo}", "--agent", agent, "--prompt-file", "{brief_path}",
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
            recipe, cwd=Path("/tmp/a repo"), prompt_file=Path("/tmp/a brief.md")
        )
        self.assertEqual(argv, ["grok", "--cwd", "/tmp/a repo", "--prompt-file", "/tmp/a brief.md"])

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
