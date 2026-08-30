#!/usr/bin/env python3
"""Focused truthfulness tests for detect-agents transport inventory."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent


def _load_module():
    spec = importlib.util.spec_from_file_location("detect_agents", HERE / "detect-agents.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


detect = _load_module()


def standing_provider(*, wired=False, enabled=True):
    return {
        "label": "Review D",
        "family": "xai",
        "level": "terra",
        "enabled": enabled,
        "wired": wired,
        "route": "grok-cli-review-d",
        "detect": {
            "method": "command",
            "cmd": "grok",
            "note": "CLI/profile presence is transport-only; a pixel binding is required.",
        },
    }


def registry(state="unwired"):
    return {"routes": {"grok-cli-review-d": {"route_state": state}}}


class DetectAgentTruthTests(unittest.TestCase):
    def test_registration_template_is_inert_and_has_no_usable_backing(self):
        entry = json.loads(detect.register_template("aider"))["aider-seat"]
        self.assertIs(entry["enabled"], False)
        self.assertIs(entry["wired"], False)
        self.assertNotIn("backed_by", entry)
        self.assertIn("INERT", entry["notes"])

    def test_teamclaude_binary_presence_does_not_claim_live_rotation(self):
        with mock.patch.object(detect.shutil, "which", return_value="/opt/bin/teamclaude"):
            rotation = detect.detect_rotation()
        self.assertIs(rotation["transport_present"], True)
        self.assertIsNone(rotation["available"])
        self.assertEqual(rotation["readiness"], "not evaluated")
        self.assertNotIn("rotation live", rotation["status"])

    def test_reference_config_exposes_all_three_standing_seat_boundaries(self):
        providers = json.loads((HERE.parent / "config/providers.json").read_text())
        model_registry = json.loads((HERE.parent / "config/model-registry.json").read_text())
        expected_routes = {
            "grok-bot-review-d": "grok-cli-review-d",
            "grok-bot-heat-map": "grok-cli-heat-map",
            "grok-bot-marketplace-intelligence": "grok-cli-marketplace-intelligence",
        }
        with mock.patch.object(detect.shutil, "which", return_value="/opt/bin/grok"):
            for seat, route in expected_routes.items():
                with self.subTest(seat=seat):
                    row = detect.detect_one(
                        seat, providers["providers"][seat], model_registry
                    )
                    self.assertIs(row["transport_present"], True)
                    self.assertIs(row["enabled"], True)
                    self.assertIs(row["wired"], False)
                    self.assertEqual(row["route"], route)
                    self.assertEqual(row["route_state"], "unwired")
                    self.assertIn("transport-only", row["detect_note"])
                    self.assertIs(row["executable_ready"], False)

    def test_present_standing_cli_reports_transport_and_static_blockers(self):
        with mock.patch.object(detect.shutil, "which", return_value="/opt/bin/grok"):
            row = detect.detect_one(
                "grok-bot-review-d", standing_provider(), registry()
            )

        self.assertIs(row["transport_present"], True)
        self.assertIs(row["present"], True)
        self.assertIn("transport present", row["status"])
        self.assertNotEqual(row["status"], "present")
        self.assertIs(row["enabled"], True)
        self.assertIs(row["wired"], False)
        self.assertEqual(row["route"], "grok-cli-review-d")
        self.assertEqual(row["route_state"], "unwired")
        self.assertEqual(
            row["detect_note"],
            "CLI/profile presence is transport-only; a pixel binding is required.",
        )
        self.assertIs(row["executable_ready"], False)
        self.assertEqual(row["readiness"], "blocked")
        self.assertTrue(any("wired" in item for item in row["readiness_limitations"]))
        self.assertTrue(any("unwired" in item for item in row["readiness_limitations"]))
        self.assertTrue(any("grok-agent.py" in item for item in row["readiness_limitations"]))

    def test_even_live_config_and_present_transport_do_not_claim_role_ready(self):
        with mock.patch.object(detect.shutil, "which", return_value="/opt/bin/grok"):
            row = detect.detect_one(
                "grok-bot-review-d",
                standing_provider(wired=True),
                registry("live_verified"),
            )

        self.assertIs(row["transport_present"], True)
        self.assertIsNone(row["executable_ready"])
        self.assertEqual(row["readiness"], "not evaluated")
        self.assertTrue(any("input binding" in item for item in row["readiness_limitations"]))

    def test_enabled_and_wired_use_exact_json_booleans(self):
        provider = standing_provider(enabled="true", wired="false")
        with mock.patch.object(detect.shutil, "which") as which:
            row = detect.detect_one("grok-bot-review-d", provider, registry())

        which.assert_not_called()
        self.assertIs(row["enabled"], False)
        self.assertIs(row["wired"], False)
        self.assertEqual(
            row["config_problems"],
            [
                "enabled must be an exact JSON boolean",
                "wired must be an exact JSON boolean",
            ],
        )
        self.assertIn("invalid config", row["status"])

    def test_json_output_surfaces_transport_note_route_and_readiness(self):
        providers = {"providers": {"grok-bot-review-d": standing_provider()}}
        stdout = io.StringIO()
        with mock.patch.object(detect, "load_providers", return_value=providers), \
             mock.patch.object(detect, "load_model_registry", return_value=registry()), \
             mock.patch.object(detect, "discover_unregistered", return_value=[]), \
             mock.patch.object(detect, "detect_rotation", return_value={
                 "tool": "teamclaude", "available": False, "path": None,
                 "status": "unavailable",
             }), \
             mock.patch.object(detect.shutil, "which", return_value="/opt/bin/grok"), \
             contextlib.redirect_stdout(stdout):
            self.assertEqual(detect.main(["--json"]), 0)

        row = json.loads(stdout.getvalue())["detected"][0]
        self.assertIs(row["transport_present"], True)
        self.assertIs(row["wired"], False)
        self.assertEqual(row["route_state"], "unwired")
        self.assertIn("transport-only", row["detect_note"])
        self.assertIs(row["executable_ready"], False)


if __name__ == "__main__":
    unittest.main()
