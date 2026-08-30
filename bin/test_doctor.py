#!/usr/bin/env python3
"""Regression tests for active-prose contradiction detection and seat-exec recipes."""
from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
spec = importlib.util.spec_from_file_location("doctor_policy_test", HERE / "doctor.py")
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)
rb_spec = importlib.util.spec_from_file_location("run_brief_seat_exec", HERE / "run-brief.py")
run_brief = importlib.util.module_from_spec(rb_spec)
rb_spec.loader.exec_module(run_brief)


class StalePolicyTests(unittest.TestCase):
    def test_retired_checkout_is_rejected_case_insensitively(self):
        self.assertTrue(doctor.stale_policy_matches("Read ~/GIT/ORCASTRATE/AGENTS.md"))

    def test_retired_opus_prohibitions_are_rejected(self):
        samples = [
            "Opus 5 is forbidden in every orchestration seat.",
            "Banned outright: OPUS-5.",
            "Default model: opus-4.8 (Not Opus-5).",
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertTrue(doctor.stale_policy_matches(sample))

    def test_current_flexible_policy_is_clean(self):
        text = (
            "Opus 5 is the operational Anthropic gate. Opus 4.8 is a "
            "time-bounded fallback. Opus 5 is not auto-forbidden."
        )
        self.assertEqual([], doctor.stale_policy_matches(text))


class SeatExecTeamclaudeTests(unittest.TestCase):
    """TeamClaude-hosted Anthropic routes must never render the auth-blocked direct Claude CLI."""

    EXPECTED_MODELS = {
        "opus-5": "claude-opus-5",
        "opus-4.8": "claude-opus-4-8",
        "fable-5": "claude-fable-5",
    }

    @classmethod
    def setUpClass(cls):
        cls.seat_exec = json.loads((ROOT / "config" / "seat-exec.json").read_text())
        cls.providers = json.loads((ROOT / "config" / "providers.json").read_text())
        cls.registry = json.loads((ROOT / "config" / "model-registry.json").read_text())
        cls.provs = cls.providers["providers"]
        cls.ids = set(cls.provs)

    def setUp(self):
        self._errors = doctor.ERRORS[:]
        doctor.ERRORS.clear()

    def tearDown(self):
        doctor.ERRORS[:] = self._errors

    def _route(self, pid):
        return self.registry["routes"][self.provs[pid]["route"]]

    def test_live_anthropic_recipes_render_teamclaude_with_exact_model_ids(self):
        ctx = {
            "brief_path": "brief.md", "worktree": ".worktrees/lane-x", "branch": "lane-x",
            "repo": ".", "output_path": "out", "preview_url": "http://example.invalid",
        }
        for pid, model in self.EXPECTED_MODELS.items():
            with self.subTest(pid=pid):
                recipe = self.seat_exec["recipes"][pid]
                cmd = run_brief.render_cmd(recipe, ctx)
                self.assertEqual(cmd[:3], ["teamclaude", "run", "--"])
                self.assertIn("--model", cmd)
                self.assertEqual(cmd[cmd.index("--model") + 1], model)
                self.assertEqual(self._route(pid).get("host"), "teamclaude")
                self.assertEqual(self._route(pid).get("invocation_id"), model)
                self.assertIsNone(doctor.teamclaude_recipe_error(pid, recipe, self._route(pid)))

    def test_live_seat_exec_stays_clean(self):
        doctor.check_seat_exec(self.seat_exec, self.provs, self.ids, self.registry)
        self.assertEqual([], doctor.ERRORS)

    def test_direct_claude_recipe_for_teamclaude_provider_is_rejected(self):
        mutated = copy.deepcopy(self.seat_exec)
        mutated["recipes"]["opus-5"]["bin"] = "claude"
        mutated["recipes"]["opus-5"]["args_template"] = [
            "-p", "review the git diff on {branch}; verdict ship|fix-list|blocked",
        ]
        doctor.check_seat_exec(mutated, self.provs, self.ids, self.registry)
        blob = "\n".join(doctor.ERRORS)
        self.assertIn("opus-5", blob)
        self.assertIn("teamclaude", blob)
        self.assertIn("auth_blocked", blob)

    def test_teamclaude_recipe_missing_model_id_is_rejected(self):
        recipe = copy.deepcopy(self.seat_exec["recipes"]["fable-5"])
        recipe["args_template"] = ["run", "--", "-p", "architecture pass on the git diff on {branch}"]
        err = doctor.teamclaude_recipe_error("fable-5", recipe, self._route("fable-5"))
        self.assertIsNotNone(err)
        self.assertIn("claude-fable-5", err)

    def test_wrong_model_id_is_rejected(self):
        recipe = copy.deepcopy(self.seat_exec["recipes"]["opus-4.8"])
        recipe["args_template"] = [
            "run", "--", "-p", "review", "--model", "claude-opus-5",
        ]
        err = doctor.teamclaude_recipe_error("opus-4.8", recipe, self._route("opus-4.8"))
        self.assertIsNotNone(err)
        self.assertIn("claude-opus-4-8", err)

    def test_non_teamclaude_provider_is_outside_this_check(self):
        recipe = self.seat_exec["recipes"]["codex-sol"]
        self.assertIsNone(doctor.teamclaude_recipe_error("codex-sol", recipe, self._route("codex-sol")))


if __name__ == "__main__":
    unittest.main()
