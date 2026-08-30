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
ga_spec = importlib.util.spec_from_file_location("grok_agent_doctor_test_mod", HERE / "grok-agent.py")
grok_agent = importlib.util.module_from_spec(ga_spec)
ga_spec.loader.exec_module(grok_agent)


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


class ProviderBooleanContractTests(unittest.TestCase):
    def setUp(self):
        self.providers = json.loads((ROOT / "config" / "providers.json").read_text())
        self._errors = doctor.ERRORS[:]
        self._warnings = doctor.WARNINGS[:]
        doctor.ERRORS.clear()
        doctor.WARNINGS.clear()

    def tearDown(self):
        doctor.ERRORS[:] = self._errors
        doctor.WARNINGS[:] = self._warnings

    def test_provider_enabled_and_wired_require_exact_booleans(self):
        mutated = copy.deepcopy(self.providers)
        mutated["providers"]["grok-build"]["enabled"] = "false"
        mutated["providers"]["grok-bot-review-d"]["wired"] = "false"
        mutated["providers"]["opus-5"]["review_eligible"] = "false"
        mutated["providers"]["codex-terra"]["dispatch_eligible"] = "true"
        doctor.check_providers(mutated)
        blob = "\n".join(doctor.ERRORS)
        self.assertIn("grok-build: enabled must be a boolean", blob)
        self.assertIn("grok-bot-review-d: wired must be a boolean", blob)
        self.assertIn("opus-5: review_eligible must be a boolean", blob)
        self.assertIn("codex-terra: dispatch_eligible must be a boolean", blob)

    def test_all_present_provider_boolean_fields_reject_non_boolean_scalars(self):
        for field in ("enabled", "wired", "review_eligible", "dispatch_eligible"):
            for value in (None, 0, 1):
                with self.subTest(field=field, value=value):
                    doctor.ERRORS.clear()
                    mutated = copy.deepcopy(self.providers)
                    mutated["providers"]["grok-bot-review-d"][field] = value
                    doctor.check_providers(mutated)
                    self.assertTrue(any(
                        f"grok-bot-review-d: {field} must be a boolean" in error
                        for error in doctor.ERRORS
                    ), doctor.ERRORS)

    def test_review_order_and_fallback_require_enabled_review_eligible_provider(self):
        mutated = copy.deepcopy(self.providers)
        mutated["providers"]["opus-5"]["enabled"] = False
        mutated["providers"]["opus-4.8"]["review_eligible"] = False
        doctor.check_providers(mutated)
        blob = "\n".join(doctor.ERRORS)
        self.assertIn("review order/fallback provider 'opus-5' is not enabled", blob)
        self.assertIn("review order/fallback provider 'opus-4.8' is not review_eligible", blob)

    def test_review_eligibility_requires_provider_function_and_capability(self):
        mutated = copy.deepcopy(self.providers)
        provider = mutated["providers"]["grok-bot-review-d"]
        provider["review_eligible"] = True
        doctor.check_providers(mutated)
        blob = "\n".join(doctor.ERRORS)
        self.assertIn("review_eligible requires review function", blob)
        self.assertIn("review_eligible requires review capability", blob)


class ProviderBackingContractTests(unittest.TestCase):
    def setUp(self):
        self.providers = json.loads((ROOT / "config" / "providers.json").read_text())
        self.subscriptions = json.loads((ROOT / "config" / "subscriptions.json").read_text())
        self.windows = json.loads((ROOT / "config" / "usage-windows.json").read_text())
        self._errors = doctor.ERRORS[:]
        doctor.ERRORS.clear()

    def tearDown(self):
        doctor.ERRORS[:] = self._errors

    def test_canonical_provider_backings_are_bidirectionally_owned(self):
        doctor.check_provider_backings(
            self.providers["providers"], self.subscriptions, self.windows
        )
        self.assertEqual(doctor.ERRORS, [])

    def test_enabled_provider_rejects_missing_unknown_or_cross_family_backing(self):
        for value in (None, "", "missing-plan", "codex-200"):
            with self.subTest(value=value):
                doctor.ERRORS.clear()
                mutated = copy.deepcopy(self.providers)
                mutated["providers"]["grok-build"]["backed_by"] = value
                doctor.check_provider_backings(
                    mutated["providers"], self.subscriptions, self.windows
                )
                self.assertTrue(any(
                    "grok-build" in error and (
                        "backed_by" in error or "usage-window" in error
                    ) for error in doctor.ERRORS
                ), doctor.ERRORS)

    def test_usage_seat_must_belong_to_provider_backing_and_family(self):
        mutated = copy.deepcopy(self.providers)
        mutated["providers"]["grok-build"]["usage_seat"] = "codex-plan"
        doctor.check_provider_backings(
            mutated["providers"], self.subscriptions, self.windows
        )
        self.assertTrue(any(
            "grok-build" in error and "not owned" in error for error in doctor.ERRORS
        ), doctor.ERRORS)


class MonitoringSourceContractTests(unittest.TestCase):
    def setUp(self):
        self._errors = doctor.ERRORS[:]
        doctor.ERRORS.clear()

    def tearDown(self):
        doctor.ERRORS[:] = self._errors

    def test_monitoring_source_enabled_must_be_exact_boolean(self):
        for enabled in ("false", "true", 0, 1, None, [], {}):
            with self.subTest(enabled=enabled):
                doctor.ERRORS.clear()
                doctor.check_monitoring_sources({
                    "sources": {"teamclaude": {
                        "enabled": enabled,
                        "cmd": "teamclaude status --json",
                    }}
                })
                self.assertTrue(any(
                    "enabled must be a boolean" in error for error in doctor.ERRORS
                ), doctor.ERRORS)


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

    def _wrappers(self):
        return self.seat_exec["wrappers"]

    def test_live_anthropic_recipes_render_teamclaude_with_exact_model_ids(self):
        ctx = {
            "brief_path": "brief.md", "worktree": ".worktrees/lane-x", "branch": "lane-x",
            "repo": ".", "output_path": "out", "preview_url": "http://example.invalid",
        }
        spec = self._wrappers()["teamclaude"]
        want_prefix = [spec["bin"], *spec["prefix"]]
        for pid, model in self.EXPECTED_MODELS.items():
            with self.subTest(pid=pid):
                recipe = self.seat_exec["recipes"][pid]
                cmd = run_brief.render_cmd(recipe, ctx)
                self.assertEqual(cmd[: len(want_prefix)], want_prefix)
                self.assertEqual(cmd.count(spec["model_flag"]), 1)
                self.assertEqual(cmd[cmd.index(spec["model_flag"]) + 1], model)
                self.assertEqual(self._route(pid).get("host"), "teamclaude")
                self.assertEqual(self._route(pid).get("invocation_id"), model)
                self.assertIsNone(
                    doctor.wrapped_recipe_error(pid, recipe, self._route(pid), self._wrappers()))

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
        err = doctor.wrapped_recipe_error("fable-5", recipe, self._route("fable-5"), self._wrappers())
        self.assertIsNotNone(err)
        self.assertIn("claude-fable-5", err)

    def test_wrong_model_id_is_rejected(self):
        recipe = copy.deepcopy(self.seat_exec["recipes"]["opus-4.8"])
        recipe["args_template"] = [
            "run", "--", "-p", "review", "--model", "claude-opus-5",
        ]
        err = doctor.wrapped_recipe_error("opus-4.8", recipe, self._route("opus-4.8"), self._wrappers())
        self.assertIsNotNone(err)
        self.assertIn("claude-opus-4-8", err)

    def test_duplicate_model_flag_is_rejected(self):
        recipe = copy.deepcopy(self.seat_exec["recipes"]["opus-5"])
        recipe["args_template"] = [
            "run", "--", "-p", "review", "--model", "claude-opus-5", "--model", "claude-sonnet-5",
        ]
        err = doctor.wrapped_recipe_error("opus-5", recipe, self._route("opus-5"), self._wrappers())
        self.assertIsNotNone(err)
        self.assertIn("exactly one", err)

    def test_dangling_model_flag_is_rejected(self):
        recipe = copy.deepcopy(self.seat_exec["recipes"]["opus-5"])
        recipe["args_template"] = ["run", "--", "-p", "review", "--model"]
        err = doctor.wrapped_recipe_error("opus-5", recipe, self._route("opus-5"), self._wrappers())
        self.assertIsNotNone(err)

    def test_direct_claude_with_absent_route_fails_closed(self):
        recipe = {"bin": "claude", "args_template": ["-p", "review"]}
        err = doctor.wrapped_recipe_error("opus-5", recipe, None, self._wrappers())
        self.assertIsNotNone(err)
        self.assertIn("auth_blocked", err)

    def test_direct_claude_with_auth_blocked_route_fails_closed(self):
        recipe = {"bin": "claude", "args_template": ["-p", "review"]}
        route = self.registry["routes"]["opus-5-direct-claude"]
        self.assertEqual(route.get("route_state"), "auth_blocked")
        err = doctor.wrapped_recipe_error("opus-5", recipe, route, self._wrappers())
        self.assertIsNotNone(err)
        self.assertIn("auth_blocked", err)

    def test_malformed_wrapper_spec_fails_closed(self):
        recipe = self.seat_exec["recipes"]["opus-5"]
        wrappers = {"teamclaude": {"bin": "teamclaude"}}
        err = doctor.wrapped_recipe_error("opus-5", recipe, self._route("opus-5"), wrappers)
        self.assertIsNotNone(err)
        self.assertIn("fail closed", err)

    def test_non_teamclaude_provider_is_outside_this_check(self):
        recipe = self.seat_exec["recipes"]["codex-sol"]
        self.assertIsNone(
            doctor.wrapped_recipe_error("codex-sol", recipe, self._route("codex-sol"), self._wrappers()))

    def test_codex_sol_carries_separate_invocation_when_dispatcher(self):
        self.assertIs(self.seat_exec["recipes"]["codex-sol"]["separate_invocation_when_dispatcher"], True)


class StandingGrokSandboxRecipeTests(unittest.TestCase):
    def setUp(self):
        self.seat_exec = json.loads((ROOT / "config" / "seat-exec.json").read_text())
        self.providers = json.loads((ROOT / "config" / "providers.json").read_text())
        self.registry = json.loads((ROOT / "config" / "model-registry.json").read_text())
        self.provs = self.providers["providers"]
        self.ids = set(self.provs)
        self._errors = doctor.ERRORS[:]
        doctor.ERRORS.clear()

    def tearDown(self):
        doctor.ERRORS[:] = self._errors

    def test_live_standing_recipes_pin_sandbox_immediately_after_cwd(self):
        for pid in (
            "grok-bot-review-d", "grok-bot-heat-map", "grok-bot-marketplace-intelligence",
        ):
            args = self.seat_exec["recipes"][pid]["args_template"]
            self.assertEqual(args[0:4], ["--cwd", "{repo}", "--sandbox", "{sandbox_profile}"])
            self.assertEqual(args, grok_agent.APPROVED_STANDING_TEMPLATE)

    def test_removing_or_weakening_sandbox_fails_closed(self):
        mutations = [
            lambda args: [tok for tok in args if tok not in ("--sandbox", "{sandbox_profile}")],
            lambda args: ["--cwd", "{repo}", "--sandbox", "workspace", *args[4:]],
            lambda args: ["--cwd", "{repo}", "--sandbox", "read-only", *args[4:]],
            lambda args: ["--cwd", "{repo}", "--agent", "{agent_profile}", "--sandbox", "{sandbox_profile}", *args[6:]],
            lambda args: ["--cwd", "{repo}", "--sandbox", "{sandbox_profile}", "--sandbox", "{sandbox_profile}", *args[4:]],
            lambda args: ["--cwd", "{repo}", "--sandbox", "mb-standing", *args[4:]],
            lambda args: ["--cwd", "{repo}", "--sandbox", "{sandbox_profile_renamed}", *args[4:]],
        ]
        for mutate in mutations:
            mutated = copy.deepcopy(self.seat_exec)
            mutated["recipes"]["grok-bot-review-d"]["args_template"] = mutate(
                mutated["recipes"]["grok-bot-review-d"]["args_template"]
            )
            doctor.ERRORS.clear()
            doctor.check_seat_exec(mutated, self.provs, self.ids, self.registry)
            blob = "\n".join(doctor.ERRORS)
            self.assertIn("grok-bot-review-d", blob)
            self.assertIn("--sandbox", blob)

    def test_doctor_records_symlink_runtime_socket_workaround(self):
        doctor.ERRORS.clear()
        doctor.INFO.clear()
        doctor.check_seat_exec(self.seat_exec, self.provs, self.ids, self.registry)
        self.assertFalse(any("restrict_network" in x for x in doctor.ERRORS))
        if target_incompatible():
            self.assertTrue(any("symlink" in x for x in doctor.INFO))

    def test_doctor_rejects_standing_route_promotion_without_shared_input_binding(self):
        providers = copy.deepcopy(self.provs)
        registry = copy.deepcopy(self.registry)
        providers["grok-bot-marketplace-intelligence"]["wired"] = True
        registry["routes"]["grok-cli-marketplace-intelligence"][
            "route_state"
        ] = "live_verified"
        doctor.check_seat_exec(self.seat_exec, providers, self.ids, registry)
        self.assertTrue(any(
            "grok-bot-marketplace-intelligence" in problem
            and "code-owned execution input binding" in problem
            for problem in doctor.ERRORS
        ))

    def test_doctor_rejects_standing_route_for_a_different_named_agent(self):
        registry = copy.deepcopy(self.registry)
        registry["routes"]["grok-cli-review-d"]["invocation_id"] = "mb-unrelated-agent"
        doctor.check_seat_exec(self.seat_exec, self.provs, self.ids, registry)
        self.assertTrue(any(
            "grok-bot-review-d" in problem
            and "invocation_id must be exact 'mb-review-d'" in problem
            for problem in doctor.ERRORS
        ))


def target_incompatible():
    spec = importlib.util.spec_from_file_location(
        "grok_agent_doctor_test", Path(__file__).resolve().parent / "grok-agent.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.auto_runtime_socket_deny_incompatible()


if __name__ == "__main__":
    unittest.main()
