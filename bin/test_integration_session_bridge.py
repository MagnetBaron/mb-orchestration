#!/usr/bin/env python3
"""Regression tests for the one-invocation dynamic MCP session bridge."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import integrations  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


resolve_route = _load("resolve_route_bridge_tests", HERE / "resolve-route.py")
doctor = _load("doctor_bridge_tests", HERE / "doctor.py")


class IntegrationSessionBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old_env = {
            key: os.environ.get(key)
            for key in ("MB_DATA_DIR", "MB_INTEGRATION_FIXTURE", "MB_INTEGRATION_SESSION",
                        "MB_INTEGRATION_SESSION_NONCE")
        }
        self.addCleanup(self._restore)
        self.data = Path(self.tmp.name) / "data"
        self.fixture = Path(self.tmp.name) / "inventory.json"
        self.fixture.write_text('{"records":[]}')
        os.environ["MB_DATA_DIR"] = str(self.data)
        os.environ["MB_INTEGRATION_FIXTURE"] = str(self.fixture)
        os.environ.pop("MB_INTEGRATION_SESSION", None)
        os.environ.pop("MB_INTEGRATION_SESSION_NONCE", None)
        integrations.reset_process_cache()

    def _restore(self):
        integrations.reset_process_cache()
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    @staticmethod
    def _tool_blob() -> str:
        return json.dumps({
            "mcp__dfs_mcp__api_request": True,
            "mcp__github__get_me": True,
            "mcp__github__get_file_contents": True,
            "mcp__dfs_mcp_extra__near_collision": True,
            "mcp__githubish__near_collision": True,
            "mcp__gsc_indexing__get_indexing_status": True,
            "mcp__gsc_indexing__get_search_analytics": True,
            "mcp__gsc_indexing__get_sitemaps": True,
            "mcp__gsc_indexing__list_gsc_sites": True,
            "mcp__gsc_indexing__submit_sitemap": False,
            "mcp__google_workspace__get_status": True,
            "mcp__google_workspace__search": True,
            "mcp__google_workspace__download_file": True,
            "mcp__google_workspace__upload_file": True,
            "mcp__google_workspace__empty_trash": False,
            "mcp__google_analytics__report": True,
            "mcp__gadgetduke__admin": True,
            "plain_unknown_tool": True,
        })

    def test_exact_namespaces_reduce_to_value_free_non_authoritative_observation(self):
        observation = integrations.build_runtime_tool_observation("codex", self._tool_blob())
        self.assertEqual(
            observation["reported_callable_ids"],
            ["dataforseo", "github", "google-drive", "google-search-console"],
        )
        self.assertEqual(observation["reported_unavailable_ids"], [])
        self.assertIs(observation["dispatch_authority"], False)
        self.assertEqual(observation["source"], "caller-runtime-tool-list-v1")
        self.assertEqual(set(observation), {
            "runtime", "reported_callable_ids", "reported_unavailable_ids",
            "observed_at", "source", "dispatch_authority",
        })
        serialized = json.dumps(observation)
        for forbidden in (
            "keyword_overview", "get_file_contents", "gsc_indexing",
            "google_workspace", "google_analytics", "gadgetduke", "installed",
            "enabled", "configured", "health", "attestation", "digest",
        ):
            self.assertNotIn(forbidden, serialized)
        with self.assertRaisesRegex(integrations.InventoryError, "observation-only"):
            integrations.build_runtime_tool_overlay("codex", self._tool_blob())

    def test_false_or_incomplete_namespace_is_reported_unavailable_not_granted(self):
        observation = integrations.build_runtime_tool_observation(
            "codex", '{"mcp__github__get_me":true,"mcp__github__get_file_contents":false}'
        )
        self.assertEqual(observation["reported_callable_ids"], [])
        self.assertEqual(observation["reported_unavailable_ids"], ["github"])

    def test_mutation_only_tools_cannot_report_read_connectors(self):
        observation = integrations.build_runtime_tool_observation(
            "codex",
            json.dumps({
                "mcp__gsc_indexing__submit_sitemap": True,
                "mcp__google_workspace__empty_trash": True,
            }),
        )
        self.assertEqual(observation["reported_callable_ids"], [])
        self.assertEqual(observation["reported_unavailable_ids"], [])

    def test_malformed_duplicate_and_non_boolean_input_fail_closed(self):
        with self.assertRaisesRegex(integrations.InventoryError, "duplicate"):
            integrations.parse_runtime_tool_states('{"mcp__github__a":true,"mcp__github__a":false}')
        with self.assertRaisesRegex(integrations.InventoryError, "booleans"):
            integrations.parse_runtime_tool_states('{"mcp__github__a":"true"}')
        with self.assertRaisesRegex(integrations.InventoryError, "bounded size"):
            integrations.parse_runtime_tool_states(b"{" + b"x" * integrations.RUNTIME_TOOLS_MAX_BYTES)

    def test_resolver_records_observation_without_affecting_non_mcp_route(self):
        observation = integrations.build_runtime_tool_observation("codex", self._tool_blob())
        first_out = io.StringIO()
        with contextlib.redirect_stdout(first_out):
            rc = resolve_route.main(
                ["--class", "repo-code", "--intake-provider", "opus-5", "--json", "--no-record"],
                integration_observation=observation,
            )
        self.assertEqual(rc, 0)
        first = json.loads(first_out.getvalue())
        self.assertTrue(first["routing_satisfied"], first)
        self.assertEqual(first["integration_observation"], observation)
        self.assertNotIn("integration_session", first)
        second_out = io.StringIO()
        with contextlib.redirect_stdout(second_out):
            rc = resolve_route.main(
                ["--class", "repo-code", "--intake-provider", "opus-5", "--json", "--no-record"]
            )
        self.assertEqual(rc, 0)
        self.assertNotIn("integration_observation", json.loads(second_out.getvalue()))
        self.assertIsNone(integrations.session())

    def test_resolver_rejects_legacy_caller_overlay_as_authority(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                resolve_route.main(
                    ["--class", "repo-code", "--json", "--no-record"],
                    integration_overlay={"runtime": "codex", "dispatch_authority": True},
                )

    def test_bridge_records_observation_but_mcp_parks(self):
        env = dict(os.environ)
        secret_suffix = "do_not_persist_7d21"
        payload = json.dumps({
            f"mcp__github__{secret_suffix}": True,
            "mcp__github__get_me": True,
            "mcp__github__get_file_contents": True,
            "mcp__dfs_mcp__api_request": True,
        })
        got = subprocess.run(
            [sys.executable, str(HERE / "build-integration-session.py"),
             "--runtime", "codex", "--", "--class", "repo-code", "--scale", "routine",
             "--implement", "--needs-mcp", "dataforseo",
             "--intake-provider", "opus-5", "--json", "--no-record"],
            input=payload, capture_output=True, text=True, cwd=ROOT, env=env,
        )
        self.assertEqual(got.returncode, 0, got.stderr)
        decision = json.loads(got.stdout)
        self.assertEqual(
            decision["integration_observation"]["reported_callable_ids"],
            ["dataforseo", "github"],
        )
        self.assertIs(decision["integration_observation"]["dispatch_authority"], False)
        self.assertNotIn("integration_session", decision)
        self.assertFalse(decision["routing_satisfied"], decision)
        self.assertIn(
            "product-authenticated callable proof is unavailable",
            decision["implement"][0]["why"],
        )
        self.assertNotIn(secret_suffix, got.stdout)
        self.assertNotIn("dfs-mcp", got.stdout)
        for path in self.data.rglob("*") if self.data.exists() else []:
            if path.is_file():
                self.assertNotIn(secret_suffix, path.read_text(errors="ignore"))

    def test_run_brief_all_true_stdin_still_parks_and_records_observation(self):
        env = dict(os.environ)
        got = subprocess.run(
            [sys.executable, str(HERE / "run-brief.py"), "--dry-run",
             "--runtime-tools", "codex", "--class", "repo-code", "--scale", "routine",
             "--needs-mcp", "dataforseo", "--intake-provider", "opus-5",
             "--json", "--no-record-observability"],
            input=self._tool_blob(), capture_output=True, text=True, cwd=ROOT, env=env,
        )
        self.assertEqual(got.returncode, 0, got.stderr)
        plan = json.loads(got.stdout)
        self.assertEqual(
            plan["integration_observation"]["reported_callable_ids"],
            ["dataforseo", "github", "google-drive", "google-search-console"],
        )
        self.assertFalse(plan["routing_satisfied"])
        self.assertEqual(plan["implement_decision"][0]["seat"], "(none)")
        self.assertIn("dispatch_authority=false", plan["implement_decision"][0]["why"])

    def test_observation_cannot_piggyback_synthetic_positive_inventory(self):
        env = dict(os.environ)
        env["MB_INTEGRATION_FIXTURE"] = str(
            ROOT / "model-evals" / "fixtures" / "integrations" / "all-observed.json"
        )
        got = subprocess.run(
            [sys.executable, str(HERE / "run-brief.py"), "--dry-run",
             "--runtime-tools", "codex", "--class", "repo-code",
             "--needs-mcp", "dataforseo", "--intake-provider", "opus-5",
             "--json", "--no-record-observability"],
            input=self._tool_blob(), capture_output=True, text=True, cwd=ROOT, env=env,
        )
        self.assertEqual(got.returncode, 0, got.stderr)
        plan = json.loads(got.stdout)
        self.assertFalse(plan["routing_satisfied"], plan)
        self.assertIn("product-authenticated callable proof is unavailable",
                      plan["implement_decision"][0]["why"])

    def test_doctor_validates_namespace_connector_mapping(self):
        connectors = json.loads((ROOT / "config/connectors.json").read_text())
        saved = doctor.ERRORS[:]
        self.addCleanup(lambda: doctor.ERRORS.__setitem__(slice(None), saved))
        doctor.ERRORS.clear()
        doctor.check_runtime_tool_mappings(connectors)
        self.assertEqual(doctor.ERRORS, [])
        del connectors["mcp_connectors"]["dataforseo"]
        doctor.check_runtime_tool_mappings(connectors)
        self.assertTrue(any("dfs_mcp" in error and "unknown connector" in error
                            for error in doctor.ERRORS), doctor.ERRORS)

    def test_cursor_runtime_is_generic_and_cannot_claim_specialized_bot_roles(self):
        adapters = json.loads((ROOT / "config/integration-adapters.json").read_text())
        runtimes = adapters["provider_runtimes"]
        self.assertEqual(runtimes["cursor-grok"], "cursor")
        self.assertEqual(runtimes["cursor-other-400"], "cursor")
        self.assertEqual(set(adapters["session_only_aliases"]["cursor"]), {"capability"})
        self.assertEqual(
            adapters["session_only_aliases"]["cursor"]["capability"],
            {"code": "code", "ide": "ide"},
        )
        for provider in ("grok-bot-review-d", "grok-bot-heat-map",
                         "grok-bot-marketplace-intelligence"):
            self.assertEqual(runtimes[provider], "grok")


if __name__ == "__main__":
    unittest.main()
