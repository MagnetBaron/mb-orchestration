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

    def test_exact_codex_namespaces_only_and_challenge_is_not_environmental(self):
        first = integrations.build_runtime_tool_overlay("codex", self._tool_blob())
        second = integrations.build_runtime_tool_overlay("codex", self._tool_blob())
        first_provenance = integrations.session_provenance(first)
        self.assertEqual(
            first_provenance["canonical_ids"],
            ["dataforseo", "github", "google-drive", "google-search-console"],
        )
        self.assertNotEqual(
            first["attestation"]["digest"], second["attestation"]["digest"]
        )
        self.assertNotIn("MB_INTEGRATION_SESSION_NONCE", os.environ)
        serialized = json.dumps(first)
        for forbidden in ("keyword_overview", "get_file_contents", "gsc_indexing",
                          "google_workspace", "google_analytics", "gadgetduke"):
            self.assertNotIn(forbidden, serialized)

    def test_false_only_namespace_is_explicitly_unavailable(self):
        overlay = integrations.build_runtime_tool_overlay(
            "codex", '{"mcp__github__get_me":true,"mcp__github__get_file_contents":false}'
        )
        provenance = integrations.session_provenance(overlay)
        self.assertEqual(provenance["canonical_ids"], [])
        ok, reason = integrations.effective(
            "codex", "mcp", "github", require_callable=True,
            inv={"records": []}, overlay=overlay,
        )
        self.assertFalse(ok)
        self.assertIn("explicitly denied", reason)

    def test_mutation_only_tools_cannot_prove_read_connectors(self):
        overlay = integrations.build_runtime_tool_overlay(
            "codex",
            json.dumps({
                "mcp__gsc_indexing__submit_sitemap": True,
                "mcp__google_workspace__empty_trash": True,
            }),
        )
        self.assertEqual(integrations.session_provenance(overlay)["canonical_ids"], [])
        for connector in ("google-search-console", "google-drive"):
            ok, _ = integrations.effective(
                "codex", "mcp", connector, require_callable=True,
                inv={"records": []}, overlay=overlay,
            )
            self.assertFalse(ok)

    def test_unrelated_false_mutation_does_not_withdraw_complete_read_surface(self):
        overlay = integrations.build_runtime_tool_overlay("codex", self._tool_blob())
        self.assertEqual(
            integrations.session_provenance(overlay)["canonical_ids"],
            ["dataforseo", "github", "google-drive", "google-search-console"],
        )

    def test_malformed_duplicate_and_non_boolean_input_fail_closed(self):
        with self.assertRaisesRegex(integrations.InventoryError, "duplicate"):
            integrations.parse_runtime_tool_states('{"mcp__github__a":true,"mcp__github__a":false}')
        with self.assertRaisesRegex(integrations.InventoryError, "booleans"):
            integrations.parse_runtime_tool_states('{"mcp__github__a":"true"}')
        with self.assertRaisesRegex(integrations.InventoryError, "bounded size"):
            integrations.parse_runtime_tool_states(b"{" + b"x" * integrations.RUNTIME_TOOLS_MAX_BYTES)

    def test_resolver_explicit_overlay_does_not_leak_to_next_invocation(self):
        overlay = integrations.build_runtime_tool_overlay("codex", self._tool_blob())
        first_out = io.StringIO()
        with contextlib.redirect_stdout(first_out):
            rc = resolve_route.main(
                ["--class", "repo-code", "--intake-provider", "opus-5", "--json", "--no-record"],
                integration_overlay=overlay,
            )
        self.assertEqual(rc, 0)
        self.assertEqual(
            json.loads(first_out.getvalue())["integration_session"]["canonical_ids"],
            ["dataforseo", "github", "google-drive", "google-search-console"],
        )
        second_out = io.StringIO()
        with contextlib.redirect_stdout(second_out):
            rc = resolve_route.main(
                ["--class", "repo-code", "--intake-provider", "opus-5", "--json", "--no-record"]
            )
        self.assertEqual(rc, 0)
        self.assertNotIn("integration_session", json.loads(second_out.getvalue()))
        self.assertIsNone(integrations.session())

    def test_resolver_consumes_clean_overlay_exactly_once(self):
        overlay = integrations.build_runtime_tool_overlay("codex", self._tool_blob())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(resolve_route.main(
                ["--class", "repo-code", "--json", "--no-record"],
                integration_overlay=overlay,
            ), 0)
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                resolve_route.main(
                    ["--class", "repo-code", "--json", "--no-record"],
                    integration_overlay=overlay,
                )

    def test_bridge_invokes_resolver_once_and_emits_value_free_provenance(self):
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
             "--intake-provider", "opus-5", "--json", "--no-record"],
            input=payload, capture_output=True, text=True, cwd=ROOT, env=env,
        )
        self.assertEqual(got.returncode, 0, got.stderr)
        decision = json.loads(got.stdout)
        self.assertEqual(
            decision["integration_session"]["canonical_ids"], ["dataforseo", "github"]
        )
        self.assertNotIn(secret_suffix, got.stdout)
        self.assertNotIn("dfs-mcp", got.stdout)
        for path in self.data.rglob("*") if self.data.exists() else []:
            if path.is_file():
                self.assertNotIn(secret_suffix, path.read_text(errors="ignore"))

    def test_run_brief_threads_same_overlay_into_its_single_resolver_call(self):
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
            plan["integration_session"]["canonical_ids"],
            ["dataforseo", "github", "google-drive", "google-search-console"],
        )
        self.assertTrue(plan["routing_satisfied"])
        self.assertEqual(plan["implement_decision"][0]["seat"], "codex-terra")

    def test_dynamic_google_read_connectors_route_but_indexing_mutation_stays_parked(self):
        env = dict(os.environ)
        for connector in ("google-drive", "google-search-console"):
            with self.subTest(connector=connector):
                got = subprocess.run(
                    [sys.executable, str(HERE / "run-brief.py"), "--dry-run",
                     "--runtime-tools", "codex", "--class", "repo-code",
                     "--needs-mcp", connector, "--intake-provider", "opus-5",
                     "--json", "--no-record-observability"],
                    input=self._tool_blob(), capture_output=True, text=True,
                    cwd=ROOT, env=env,
                )
                self.assertEqual(got.returncode, 0, got.stderr)
                plan = json.loads(got.stdout)
                self.assertTrue(plan["routing_satisfied"], plan)
                self.assertEqual(plan["implement_decision"][0]["seat"], "codex-terra")

        mutation = subprocess.run(
            [sys.executable, str(HERE / "run-brief.py"), "--dry-run",
             "--runtime-tools", "codex", "--class", "repo-code",
             "--needs-mcp", "gsc-indexing", "--intake-provider", "opus-5",
             "--json", "--no-record-observability"],
            input=self._tool_blob(), capture_output=True, text=True,
            cwd=ROOT, env=env,
        )
        self.assertEqual(mutation.returncode, 0, mutation.stderr)
        plan = json.loads(mutation.stdout)
        self.assertFalse(plan["routing_satisfied"])
        self.assertTrue(any(
            "not an observed-effective connector" in str(step.get("why"))
            for step in plan["implement_decision"]
        ), plan)

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
