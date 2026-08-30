#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import hashlib
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
        self.assertEqual(
            seats["grok-bot-marketplace-intelligence"]["required_capabilities"],
            ["deposited-evidence"],
        )

    def test_profile_must_byte_match_generated_policy(self):
        with tempfile.TemporaryDirectory() as td:
            profile = Path(td) / "mb-review-d.md"
            expected = target.sync_profiles.expected()[profile.name]
            profile.write_text(expected)
            self.assertIsNone(target._profile_problem(profile, "mb-review-d"))
            profile.write_text(expected + "\n# unsafe drift\n")
            self.assertIn("byte-match", target._profile_problem(profile, "mb-review-d"))

    def test_review_d_prompt_must_match_config_renderer(self):
        with tempfile.TemporaryDirectory() as td:
            prompt = Path(td) / "review.md"
            config = target.connector_packets.load()
            prompt.write_text(target.connector_packets.render_live_ticket(config, "magnet-baron"))
            self.assertIsNone(target._prompt_problem("grok-bot-review-d", prompt))
            prompt.write_text("role: review-d\nmode: live-storefront-audit\nurl: https://evil.example/\n")
            self.assertIn("byte-match", target._prompt_problem("grok-bot-review-d", prompt))

    def test_marketplace_prompt_binds_evidence_digest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence = root / "sold.csv"
            evidence.write_text("price\n12.00\n")
            digest = "sha256:" + hashlib.sha256(evidence.read_bytes()).hexdigest()
            prompt = root / "market.md"
            prompt.write_text(
                "role: marketplace-intelligence\nsource: owner-deposited\n"
                "artifact-class: synthetic-eval\n"
                f"evidence-path: {evidence}\nevidence-sha256: {digest}\n"
            )
            self.assertIsNone(target._prompt_problem("grok-bot-marketplace-intelligence", prompt))
            evidence.write_text("price\n999.00\n")
            self.assertIn("digest", target._prompt_problem("grok-bot-marketplace-intelligence", prompt))

    def test_evidence_prompt_rejects_duplicate_or_unknown_fields(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence = root / "sold.csv"
            evidence.write_text("price\n12.00\n")
            digest = "sha256:" + hashlib.sha256(evidence.read_bytes()).hexdigest()
            base = (
                "role: marketplace-intelligence\nsource: owner-deposited\n"
                "artifact-class: synthetic-eval\n"
                f"evidence-path: {evidence}\nevidence-sha256: {digest}\n"
            )
            prompt = root / "market.md"
            prompt.write_text(base + "evidence-path: /etc/hosts\n")
            self.assertIn("duplicate", target._prompt_problem(
                "grok-bot-marketplace-intelligence", prompt
            ))
            prompt.write_text(base + "extra-artifact: /etc/hosts\n")
            self.assertIn("unknown", target._prompt_problem(
                "grok-bot-marketplace-intelligence", prompt
            ))
            prompt.write_text(base.replace("artifact-class: synthetic-eval", "artifact-class: credentials"))
            self.assertIn("non-restricted", target._prompt_problem(
                "grok-bot-marketplace-intelligence", prompt
            ))
            restricted_missing = base.replace(
                "artifact-class: synthetic-eval", "artifact-class: credentials"
            ).replace(str(evidence), str(root / "missing.csv"))
            prompt.write_text(restricted_missing)
            self.assertIn("non-restricted", target._prompt_problem(
                "grok-bot-marketplace-intelligence", prompt
            ))

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
                "connectors.json": json.loads((HERE.parent / "config" / "connectors.json").read_text()),
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

    def test_smoke_rejects_cross_seat_agent_substitution(self):
        configs = {
            name: json.loads((HERE.parent / "config" / name).read_text())
            for name in ("seat-exec.json", "roles.json", "providers.json")
        }
        recipe = configs["seat-exec.json"]["recipes"]["grok-bot-review-d"]
        recipe["required_agent"] = "mb-marketplace-intelligence"
        with tempfile.TemporaryDirectory() as td:
            agents = Path(td) / "agents"
            agents.mkdir()
            profile = agents / "mb-marketplace-intelligence.md"
            profile.write_text(target.sync_profiles.expected()[profile.name])
            with mock.patch.object(target.mborch, "load_config", side_effect=lambda n, **_: configs[n]), \
                 mock.patch.object(target.shutil, "which", return_value="/usr/local/bin/grok"), \
                 mock.patch.object(target.subprocess, "run") as run:
                rc = target.main([
                    "--seat", "grok-bot-review-d", "--smoke", "--execute",
                    "--agent-dir", str(agents),
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

    def test_smoke_requires_exact_sentinel_and_uses_empty_temporary_cwd(self):
        with tempfile.TemporaryDirectory() as td:
            agents = Path(td) / "agents"
            agents.mkdir()
            profile = agents / "mb-review-d.md"
            profile.write_text(target.sync_profiles.expected()[profile.name])
            good = subprocess.CompletedProcess([], 0, stdout="cli-agent-path-ok\n", stderr="")
            with mock.patch.object(target.shutil, "which", return_value="/usr/local/bin/grok"), \
                 mock.patch.object(target.subprocess, "run", return_value=good) as run:
                rc = target.main([
                    "--seat", "grok-bot-review-d", "--smoke", "--execute",
                    "--agent-dir", str(agents), "--cwd", str(HERE.parent),
                ])
            self.assertEqual(rc, 0)
            cmd = run.call_args.args[0]
            self.assertNotEqual(cmd[cmd.index("--cwd") + 1], str(HERE.parent))
            self.assertEqual(cmd[cmd.index("--agent") + 1], str(profile))

            bad = subprocess.CompletedProcess([], 0, stdout="almost-ok\n", stderr="")
            with mock.patch.object(target.shutil, "which", return_value="/usr/local/bin/grok"), \
                 mock.patch.object(target.subprocess, "run", return_value=bad):
                rc = target.main([
                    "--seat", "grok-bot-review-d", "--smoke", "--execute",
                    "--agent-dir", str(agents),
                ])
            self.assertEqual(rc, 2)

    def test_missing_smoke_recipe_parks_without_subprocess(self):
        with mock.patch.object(target.mborch, "load_config", return_value={"recipes": {}}), \
             mock.patch.object(target.subprocess, "run") as run:
            rc = target.main(["--seat", "grok-bot-review-d", "--smoke", "--execute"])
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

    def test_review_only_pixel_route_also_parks_on_review_d(self):
        result = subprocess.run([
            sys.executable, str(HERE / "resolve-route.py"),
            "--class", "storefront-theme", "--scale", "elevated",
            "--intake-provider", "codex-sol", "--pixels",
            "--artifacts", "brief,diff", "--json", "--no-record",
        ], cwd=HERE.parent, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        decision = json.loads(result.stdout)
        self.assertFalse(decision["routing_satisfied"])
        self.assertIn("PARK Review D", decision["park_reason"])
        self.assertTrue(any(step.get("input_seat") for step in decision["implement"]))

    def test_configured_review_d_flag_triggers_input_gate_for_any_class(self):
        with tempfile.TemporaryDirectory() as td:
            config = json.loads((HERE.parent / "config" / "review-depth.json").read_text())
            config["classes"]["catalog-data"]["review_d"] = True
            Path(td, "review-depth.json").write_text(json.dumps(config))
            env = dict(os.environ)
            env["MB_CONFIG_DIR"] = td
            result = subprocess.run([
                sys.executable, str(HERE / "resolve-route.py"),
                "--class", "catalog-data", "--scale", "elevated",
                "--intake-provider", "codex-sol", "--artifacts", "brief,diff",
                "--json", "--no-record",
            ], cwd=HERE.parent, env=env, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        decision = json.loads(result.stdout)
        self.assertTrue(decision["gates"]["review_d_pixels"])
        self.assertFalse(decision["routing_satisfied"])
        self.assertTrue(any(step.get("input_seat") for step in decision["implement"]))

    def test_launcher_rejects_mutable_capability_weakening(self):
        configs = {
            name: json.loads((HERE.parent / "config" / name).read_text())
            for name in (
                "providers.json", "roles.json", "seat-exec.json",
                "model-registry.json", "connectors.json",
            )
        }
        configs["seat-exec.json"]["recipes"]["grok-bot-review-d"]["required_capabilities"] = []
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            prompt = root / "review.md"
            prompt.write_text(target.connector_packets.render_live_ticket(
                target.connector_packets.load(), "magnet-baron"
            ))
            agents = root / "agents"
            agents.mkdir()
            profile = agents / "mb-review-d.md"
            profile.write_text(target.sync_profiles.expected()[profile.name])
            with mock.patch.object(target.mborch, "load_config", side_effect=lambda n, **_: configs[n]), \
                 mock.patch.object(target.shutil, "which", return_value="/usr/local/bin/grok"), \
                 mock.patch.object(target.integrations, "effective", return_value=(True, "observed")) as effective:
                result = target.inspect("grok-bot-review-d", root, prompt, agents)
        self.assertFalse(result["ready"])
        self.assertTrue(any("required_capabilities must be exact" in x for x in result["problems"]))
        self.assertEqual(effective.call_count, 2)

    def test_launcher_rejects_invalid_registry_promotion(self):
        configs = {
            name: json.loads((HERE.parent / "config" / name).read_text())
            for name in ("providers.json", "seat-exec.json", "model-registry.json")
        }
        configs["providers.json"]["providers"]["grok-bot-review-d"]["wired"] = True
        configs["model-registry.json"]["routes"]["grok-cli-review-d"]["route_state"] = "live_verified"
        with mock.patch.object(target.mborch, "load_config", side_effect=lambda n, **_: configs[n]), \
             mock.patch.object(target.shutil, "which", return_value="/usr/local/bin/grok"), \
             mock.patch.object(target, "_profile_problem", return_value=None), \
             mock.patch.object(target, "_prompt_problem", return_value=None), \
             mock.patch.object(target.integrations, "effective", return_value=(True, "observed")):
            result = target.inspect(
                "grok-bot-review-d", HERE.parent, HERE / "test_grok_agent.py",
                HERE.parent / "generated",
            )
        self.assertFalse(result["ready"])
        self.assertTrue(any("model registry is invalid" in x for x in result["problems"]))


if __name__ == "__main__":
    unittest.main()
