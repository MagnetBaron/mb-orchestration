#!/usr/bin/env python3
"""Deterministic tests for self-healing integration observation and grant gates."""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import integrations  # noqa: E402
import routing  # noqa: E402


def load_generate():
    spec = importlib.util.spec_from_file_location("generate_roles_integrations", HERE / "generate-roles.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gen = load_generate()


def record(runtime="codex", kind="mcp", ident="github", **changes):
    row = {
        "runtime": runtime, "kind": kind, "id": ident,
        "installed": True, "enabled": True, "configured": True,
        "blocked": False, "health": "verified", "callable": True,
    }
    row.update(changes)
    return row


class IntegrationInventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name) / "data"
        self.fixture = Path(self.tmp.name) / "observed.json"
        self.old_data = os.environ.get("MB_DATA_DIR")
        self.old_fixture = os.environ.get("MB_INTEGRATION_FIXTURE")
        self.old_source_root = os.environ.get("MB_INTEGRATION_SOURCE_ROOT")
        os.environ["MB_DATA_DIR"] = str(self.data)
        os.environ["MB_INTEGRATION_FIXTURE"] = str(self.fixture)
        self.write([record()])
        integrations.reset_process_cache()

    def tearDown(self):
        for key, value in (("MB_DATA_DIR", self.old_data), ("MB_INTEGRATION_FIXTURE", self.old_fixture)):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if self.old_source_root is None:
            os.environ.pop("MB_INTEGRATION_SOURCE_ROOT", None)
        else:
            os.environ["MB_INTEGRATION_SOURCE_ROOT"] = self.old_source_root
        integrations.reset_process_cache()
        self.tmp.cleanup()

    def write(self, records):
        self.fixture.write_text(json.dumps({"records": records}))

    def test_add_remove_disable_and_fingerprint_refresh(self):
        first = integrations.refresh()
        self.assertEqual(first["refresh_reason"], "missing_cache")
        self.assertEqual([r["canonical_id"] for r in first["records"]], ["github"])

        self.write([record(), record(ident="dfs-mcp")])
        integrations.reset_process_cache()
        added = integrations.refresh()
        self.assertEqual(added["refresh_reason"], "fingerprint_changed")
        self.assertEqual({r["canonical_id"] for r in added["records"]}, {"github", "dataforseo"})

        self.write([record(ident="dfs-mcp", enabled=False, configured=False, blocked=True, health="blocked", callable=False)])
        integrations.reset_process_cache()
        disabled = integrations.refresh()
        ok, _ = integrations.effective("codex", "mcp", "dataforseo", require_callable=True, inv=disabled)
        self.assertFalse(ok)

        self.write([])
        integrations.reset_process_cache()
        removed = integrations.refresh()
        ok, reason = integrations.effective("codex", "mcp", "github", require_callable=True, inv=removed)
        self.assertFalse(ok)
        self.assertIn("not freshly observed", reason)

    def test_corrupt_schema_old_missing_and_ttl_recover(self):
        path = integrations.cache_path()
        path.parent.mkdir(parents=True)
        path.write_text("{truncated")
        got = integrations.refresh()
        self.assertEqual(got["refresh_reason"], "corrupt_cache")

        cached = json.loads(path.read_text())
        cached["schema_version"] = 0
        path.write_text(json.dumps(cached))
        integrations.reset_process_cache()
        got = integrations.refresh()
        self.assertEqual(got["refresh_reason"], "schema_old")

        cached = json.loads(path.read_text())
        cached["generated_at"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        path.write_text(json.dumps(cached))
        integrations.reset_process_cache()
        got = integrations.refresh()
        self.assertEqual(got["refresh_reason"], "ttl_expired")

        path.unlink()
        integrations.reset_process_cache()
        got = integrations.refresh()
        self.assertEqual(got["refresh_reason"], "missing_cache")

    def test_atomic_concurrent_refresh_and_mode_0600(self):
        errors = []
        stale_lock = Path(str(integrations.cache_path()) + ".lock")
        stale_lock.parent.mkdir(parents=True, exist_ok=True)
        stale_lock.write_text("")
        os.utime(stale_lock, (1, 1))

        def worker():
            try:
                integrations.refresh(force=True)
            except Exception as exc:  # pragma: no cover - assertion reports exact error
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertFalse(errors, errors)
        path = integrations.cache_path()
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertIsInstance(json.loads(path.read_text())["records"], list)
        self.assertFalse(Path(str(path) + ".lock").exists())

    def test_unregistered_and_secret_fields_are_not_retained(self):
        secret = "super-secret-token-value"
        self.write([record(ident="not-vetted", token=secret, source=secret,
                           canonical_id=secret, url=f"https://u:{secret}@example.test")])
        inv = integrations.refresh(force=True)
        self.assertFalse(inv["records"][0]["registered"])
        blob = integrations.cache_path().read_text()
        self.assertNotIn(secret, blob)
        self.assertNotIn("url", blob)
        self.assertNotIn("token", blob)

    def test_session_is_runtime_bound_ephemeral_and_not_cached(self):
        self.write([])
        inv = integrations.refresh(force=True)
        before = integrations.cache_path().read_bytes()
        session_file = Path(self.tmp.name) / "session.json"
        session_file.write_text(json.dumps({"runtime": "codex", "records": [record()]}))
        overlay = integrations.load_session(str(session_file))
        ok, _ = integrations.effective("codex", "mcp", "github", require_callable=True,
                                       inv=inv, overlay=overlay)
        self.assertTrue(ok)
        wrong, _ = integrations.effective("claude", "mcp", "github", require_callable=True,
                                          inv=inv, overlay=overlay)
        self.assertFalse(wrong)
        self.assertEqual(before, integrations.cache_path().read_bytes())
        self.assertNotIn("session", integrations.cache_path().read_text())

        session_file.write_text(json.dumps({"runtime": "codex", "records": [record(runtime="claude")]}))
        with self.assertRaisesRegex(integrations.InventoryError, "cross runtime"):
            integrations.load_session(str(session_file))

    def test_manifest_configured_is_distinct_from_current_callable(self):
        self.write([record(callable=False, health="unknown")])
        inv = integrations.refresh(force=True)
        configured, _ = integrations.effective("codex", "mcp", "github", require_callable=False, inv=inv)
        callable_now, _ = integrations.effective("codex", "mcp", "github", require_callable=True, inv=inv)
        self.assertTrue(configured)
        self.assertFalse(callable_now)

    def test_allowlisted_manifest_enabled_false_is_detected(self):
        os.environ.pop("MB_INTEGRATION_FIXTURE", None)
        source_root = Path(self.tmp.name) / "home"
        os.environ["MB_INTEGRATION_SOURCE_ROOT"] = str(source_root)
        codex = source_root / ".codex/config.toml"
        codex.parent.mkdir(parents=True)
        codex.write_text(
            '[mcp_servers.github]\nenabled = false\n'
            '[plugins."magnet-baron-skills@magnet-baron"]\nenabled = false\n'
        )
        integrations.reset_process_cache()
        inv = integrations.refresh(force=True)
        hits = {(r["kind"], r["canonical_id"]): r for r in inv["records"] if r.get("canonical_id")}
        for key in (("mcp", "github"), ("plugin", "magnet-baron-skills")):
            self.assertTrue(hits[key]["blocked"])
            self.assertFalse(hits[key]["enabled"])
            self.assertEqual(hits[key]["health"], "blocked")

    def test_cli_session_merge_json_and_check(self):
        self.write([])
        session_file = Path(self.tmp.name) / "session.json"
        session_file.write_text(json.dumps({"runtime": "codex", "records": [record()]}))
        env = dict(os.environ)
        got = subprocess.run(
            [sys.executable, str(HERE / "detect-integrations.py"), "--json", "--session", str(session_file), "--check"],
            capture_output=True, text=True, cwd=ROOT, env=env,
        )
        self.assertEqual(got.returncode, 0, got.stderr)
        data = json.loads(got.stdout)
        self.assertEqual(data["session_runtime"], "codex")
        self.assertFalse(data["session_persisted"])
        self.assertIn("codex:mcp:github", data["effective"])
        stdio = subprocess.run(
            [sys.executable, str(HERE / "detect-integrations.py"), "--json", "--session", "-"],
            input=session_file.read_text(), capture_output=True, text=True, cwd=ROOT, env=env,
        )
        self.assertEqual(stdio.returncode, 0, stdio.stderr)
        self.assertEqual(json.loads(stdio.stdout)["session_runtime"], "codex")


class GrantBypassTests(unittest.TestCase):
    def setUp(self):
        integrations.reset_process_cache()
        self.connectors = {
            "mcp_connectors": {
                "github": {"status": "active", "available_on": ["codex-terra"],
                           "mutating_tools": ["push"], "class": "code"}
            }
        }
        self.provider = {"capabilities": ["mcp_bulk"]}
        self.empty = {"records": []}
        self.observed = {
            "records": [{
                "runtime": "codex", "kind": "mcp", "observed_id": "github",
                "canonical_id": "github", "registered": True, "suggested": False,
                "installed": True, "enabled": True, "configured": True, "blocked": False,
                "health": "verified", "callable": True, "source": "fixture",
            }]
        }

    def test_capabilities_of_has_no_static_active_bypass(self):
        self.assertNotIn("github", routing.capabilities_of(
            "codex-terra", self.provider, self.connectors, inventory=self.empty))
        self.assertIn("github", routing.capabilities_of(
            "codex-terra", self.provider, self.connectors, inventory=self.observed))

    def test_mcp_volume_matches_has_no_static_active_bypass(self):
        missing, reason = routing.mcp_volume_matches(
            "github", self.connectors, "codex-terra", inventory=self.empty)
        self.assertFalse(missing)
        self.assertIn("not freshly observed", reason)
        found, _ = routing.mcp_volume_matches(
            "github", self.connectors, "codex-terra", inventory=self.observed)
        self.assertEqual(found[0][0], "github")

    def test_role_skill_gate_and_mutation_map_use_observed_predicate(self):
        providers = {"providers": {"codex-terra": self.provider}}
        self.assertFalse(gen.seat_has_capability(
            "codex-terra", "github", providers, self.connectors, inventory=self.empty))
        self.assertTrue(gen.seat_has_capability(
            "codex-terra", "github", providers, self.connectors, inventory=self.observed))

        original = gen.mborch.load_config
        gen.mborch.load_config = lambda name, required=False: self.connectors if name == "connectors.json" else original(name, required)
        try:
            self.assertNotIn("github", gen.mcp_mutation_map("codex", inventory=self.empty))
            self.assertEqual(gen.mcp_mutation_map("codex", inventory=self.observed)["github"], {"push"})
        finally:
            gen.mborch.load_config = original


if __name__ == "__main__":
    unittest.main()
