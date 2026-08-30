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


def load_doctor():
    spec = importlib.util.spec_from_file_location("doctor_integrations", HERE / "doctor.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name) / "data"
        self.fixture = Path(self.tmp.name) / "observed.json"
        self.old_data = os.environ.get("MB_DATA_DIR")
        self.old_fixture = os.environ.get("MB_INTEGRATION_FIXTURE")
        self.old_source_root = os.environ.get("MB_INTEGRATION_SOURCE_ROOT")
        self.old_session = os.environ.get("MB_INTEGRATION_SESSION")
        self.old_session_nonce = os.environ.get("MB_INTEGRATION_SESSION_NONCE")
        self.addCleanup(self._restore_environment)
        self.addCleanup(integrations.reset_process_cache)
        os.environ["MB_DATA_DIR"] = str(self.data)
        os.environ["MB_INTEGRATION_FIXTURE"] = str(self.fixture)
        self.session_nonce = "unit-test-process-challenge-00000001"
        os.environ["MB_INTEGRATION_SESSION_NONCE"] = self.session_nonce
        os.environ.pop("MB_INTEGRATION_SESSION", None)
        self.write([record()])
        integrations.reset_process_cache()

    def _restore_environment(self):
        for key, value in (
            ("MB_DATA_DIR", self.old_data),
            ("MB_INTEGRATION_FIXTURE", self.old_fixture),
            ("MB_INTEGRATION_SOURCE_ROOT", self.old_source_root),
            ("MB_INTEGRATION_SESSION", self.old_session),
            ("MB_INTEGRATION_SESSION_NONCE", self.old_session_nonce),
        ):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def write(self, records):
        self.fixture.write_text(json.dumps({"records": records}))

    def session_document(self, runtime, records, **times):
        return integrations.build_session_document(
            runtime, records, os.environ["MB_INTEGRATION_SESSION_NONCE"], **times
        )

    def write_session(self, path, runtime, records, **times):
        path.write_text(json.dumps(self.session_document(runtime, records, **times)))
        path.chmod(0o600)

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
        self.write_session(session_file, "codex", [record()])
        overlay = integrations.load_session(str(session_file))
        ok, _ = integrations.effective("codex", "mcp", "github", require_callable=True,
                                       inv=inv, overlay=overlay)
        self.assertTrue(ok)
        wrong, _ = integrations.effective("claude", "mcp", "github", require_callable=True,
                                          inv=inv, overlay=overlay)
        self.assertFalse(wrong)
        self.assertEqual(before, integrations.cache_path().read_bytes())
        self.assertNotIn("session", integrations.cache_path().read_text())

        self.write_session(session_file, "codex", [record(runtime="claude")])
        with self.assertRaisesRegex(integrations.InventoryError, "cross runtime"):
            integrations.load_session(str(session_file))

    def test_session_only_grokbot_alias_and_value_free_provenance(self):
        self.write([])
        inv = integrations.refresh(force=True)
        session_file = Path(self.tmp.name) / "grokbot-session.json"
        row = record(runtime="grokbot-cursor", kind="capability", ident="visual-qa")
        self.write_session(session_file, "grokbot-cursor", [row])
        overlay = integrations.load_session(str(session_file))
        ok, _ = integrations.effective(
            "grokbot-cursor", "capability", "visual_qa", require_callable=True,
            inv=inv, overlay=overlay,
        )
        self.assertTrue(ok)
        provenance = integrations.session_provenance(overlay)
        self.assertEqual(provenance["runtime"], "grokbot-cursor")
        self.assertEqual(provenance["canonical_ids"], ["visual_qa"])
        self.assertEqual(set(provenance["attestation"]), {
            "source", "observed_at", "expires_at", "digest",
        })
        self.assertNotIn("nonce", json.dumps(provenance))
        self.assertNotIn(self.session_nonce, json.dumps(provenance))
        self.assertNotIn("must-not-escape", json.dumps(integrations.session_provenance(overlay)))

        failed = record(runtime="grokbot-cursor", kind="capability", ident="browser", callable=False)
        self.write_session(session_file, "grokbot-cursor", [failed])
        failed_provenance = integrations.session_provenance(integrations.load_session(str(session_file)))
        self.assertEqual(failed_provenance["runtime"], "grokbot-cursor")
        self.assertEqual(failed_provenance["canonical_ids"], [])

        unknown = record(runtime="grokbot-cursor", kind="capability", ident="not-registered")
        self.write_session(session_file, "grokbot-cursor", [unknown])
        unknown_provenance = integrations.session_provenance(integrations.load_session(str(session_file)))
        self.assertEqual(unknown_provenance["runtime"], "grokbot-cursor")
        self.assertEqual(unknown_provenance["canonical_ids"], [])

        self.write_session(session_file, "grokbot-cursor", [])
        empty_provenance = integrations.session_provenance(integrations.load_session(str(session_file)))
        self.assertEqual(empty_provenance["runtime"], "grokbot-cursor")
        self.assertEqual(empty_provenance["canonical_ids"], [])

    def test_session_attestation_rejects_stale_future_tampered_reused_and_secret_fields(self):
        path = Path(self.tmp.name) / "attestation.json"
        now = datetime.now(timezone.utc)

        self.write_session(
            path, "codex", [record()],
            observed_at=now - timedelta(seconds=90),
            expires_at=now + timedelta(seconds=10),
        )
        with self.assertRaisesRegex(integrations.InventoryError, "stale"):
            integrations.load_session(str(path))

        self.write_session(
            path, "codex", [record()],
            observed_at=now + timedelta(seconds=10),
            expires_at=now + timedelta(seconds=50),
        )
        with self.assertRaisesRegex(integrations.InventoryError, "future"):
            integrations.load_session(str(path))

        document = self.session_document("codex", [record()])
        document["records"][0]["callable"] = False
        path.write_text(json.dumps(document))
        path.chmod(0o600)
        with self.assertRaisesRegex(integrations.InventoryError, "digest mismatch"):
            integrations.load_session(str(path))

        secret_record = record(token="must-not-escape")
        path.write_text(json.dumps(self.session_document("codex", [secret_record])))
        path.chmod(0o600)
        with self.assertRaisesRegex(integrations.InventoryError, "unknown fields"):
            integrations.load_session(str(path))

        self.write_session(path, "codex", [record()])
        first = integrations.load_session(str(path))
        digest = first["attestation"]["digest"]
        self.assertNotIn("must-not-escape", json.dumps(integrations.session_provenance(first)))
        with self.assertRaisesRegex(integrations.InventoryError, "already consumed"):
            integrations.load_session(str(path))
        self.assertRegex(digest, r"^sha256:[a-f0-9]{64}$")

        wrong_nonce = integrations.build_session_document("codex", [record()], "different-process-challenge-000000")
        path.write_text(json.dumps(wrong_nonce))
        path.chmod(0o600)
        with self.assertRaisesRegex(integrations.InventoryError, "process challenge"):
            integrations.load_session(str(path))

        self.write_session(path, "codex", [record(ident="dfs-mcp")])
        path.chmod(0o644)
        with self.assertRaisesRegex(integrations.InventoryError, "owner-only"):
            integrations.load_session(str(path))

        os.environ["MB_INTEGRATION_SESSION"] = json.dumps(self.session_document("codex", []))
        with self.assertRaisesRegex(integrations.InventoryError, "inline session JSON is forbidden"):
            integrations.load_session()

    def test_manifest_denials_are_monotonic_over_positive_session_attestation(self):
        path = Path(self.tmp.name) / "positive-session.json"
        self.write_session(path, "codex", [record()])
        overlay = integrations.load_session(str(path))
        config = integrations.load_adapters()
        positive = integrations._record(config, "codex", "mcp", "github")
        self.assertTrue(integrations.effective(
            "codex", "mcp", "github", require_callable=True,
            inv={"records": [positive]}, overlay=overlay,
        )[0])
        denials = (
            dict(positive, blocked=True, health="blocked"),
            dict(positive, enabled=False),
            dict(positive, configured=False),
            dict(positive, installed=False),
            dict(positive, health="needs_auth"),
        )
        for denied in denials:
            with self.subTest(denied=denied):
                ok, reason = integrations.effective(
                    "codex", "mcp", "github", require_callable=True,
                    inv={"records": [denied]}, overlay=overlay,
                )
                self.assertFalse(ok)
                self.assertIn("explicitly denied", reason)
                merged = integrations.merged_records({"records": [denied]}, overlay)
                self.assertTrue(integrations._explicit_negative(merged[0]))

        # A later positive duplicate must not erase earlier negative evidence in
        # the merged diagnostic view, either.
        merged = integrations.merged_records(
            {"records": [denials[0], positive]}, overlay,
        )
        self.assertEqual(len(merged), 1)
        self.assertTrue(integrations._explicit_negative(merged[0]))

    def test_session_denials_coalesce_across_order_aliases_routing_and_provenance(self):
        path = Path(self.tmp.name) / "contradictory-session.json"
        config = integrations.load_adapters()
        base_positive = integrations._record(config, "codex", "mcp", "github")
        session_positive = record()
        session_negative = record(enabled=False)

        # A negative session observation defeats a positive manifest and does
        # not enter the routing capability set.
        self.write_session(path, "codex", [session_negative])
        overlay = integrations.load_session(str(path))
        ok, reason = integrations.effective(
            "codex", "mcp", "github", require_callable=True,
            inv={"records": [base_positive]}, overlay=overlay,
        )
        self.assertFalse(ok)
        self.assertIn("explicitly denied", reason)
        connectors = {"mcp_connectors": {"github": {
            "status": "active", "available_on": ["codex-sol"], "class": "code",
        }}}
        capabilities = routing.capabilities_of(
            "codex-sol", {"capabilities": []}, connectors,
            inventory={"records": [base_positive]}, session=overlay,
        )
        self.assertNotIn("github", capabilities)

        # Contradictory session records are order-independent: denial wins.
        for rows in (
            [session_negative, session_positive],
            [session_positive, session_negative],
        ):
            with self.subTest(order=[row["enabled"] for row in rows]):
                self.write_session(path, "codex", rows)
                overlay = integrations.load_session(str(path))
                self.assertFalse(integrations.effective(
                    "codex", "mcp", "github", require_callable=True,
                    inv={"records": [base_positive]}, overlay=overlay,
                )[0])
                merged = integrations.merged_records(
                    {"records": [base_positive]}, overlay,
                )
                github = [row for row in merged if row.get("canonical_id") == "github"]
                self.assertEqual(len(github), 1)
                self.assertTrue(integrations._explicit_negative(github[0]))

        # Different aliases resolving to one canonical capability also coalesce
        # with denial winning, and the denied ID is absent from provenance.
        alias_positive = record(
            runtime="grokbot-cursor", kind="capability", ident="visual-qa",
        )
        canonical_negative = record(
            runtime="grokbot-cursor", kind="capability", ident="visual_qa",
            blocked=True,
        )
        for rows in (
            [alias_positive, canonical_negative],
            [canonical_negative, alias_positive],
        ):
            self.write_session(path, "grokbot-cursor", rows)
            overlay = integrations.load_session(str(path))
            self.assertFalse(integrations.effective(
                "grokbot-cursor", "capability", "visual_qa", require_callable=True,
                inv={"records": []}, overlay=overlay,
            )[0])
            self.assertEqual(integrations.session_provenance(overlay)["canonical_ids"], [])
            merged = integrations.merged_records({"records": []}, overlay)
            self.assertEqual(len(merged), 1)
            self.assertTrue(integrations._explicit_negative(merged[0]))

    def test_plugin_removal_denials_defeat_positive_manifest_and_session(self):
        path = Path(self.tmp.name) / "plugin-removal-session.json"
        plugin_id = "magnet-baron-skills@magnet-baron"
        positive = record(kind="plugin", ident=plugin_id, callable=False)
        base = integrations._validate_record(positive, session=False)
        base["canonical_id"] = "magnet-baron-skills"
        base["registered"] = True
        denials = (
            record(kind="plugin", ident=plugin_id, installed=False, callable=False),
            record(kind="plugin", ident=plugin_id, enabled=False, callable=False),
            record(kind="plugin", ident=plugin_id, blocked=True, callable=False),
        )
        for negative in denials:
            for rows in ([positive, negative], [negative, positive]):
                with self.subTest(negative=negative, order=[r.get("installed") for r in rows]):
                    self.write_session(path, "codex", rows)
                    overlay = integrations.load_session(str(path))
                    ok, reason = integrations.plugin_effective(
                        "codex", "magnet-baron-skills",
                        inv={"records": [base]}, overlay=overlay,
                    )
                    self.assertFalse(ok)
                    self.assertIn("explicitly denied", reason)
                    merged = integrations.merged_records({"records": [base]}, overlay)
                    plugins = [row for row in merged if row.get("canonical_id") == "magnet-baron-skills"]
                    self.assertEqual(len(plugins), 1)
                    self.assertTrue(integrations._explicit_negative(plugins[0]))

    def test_codex_plugin_config_cache_profile_and_project_layers_are_not_install_inventory(self):
        os.environ.pop("MB_INTEGRATION_FIXTURE", None)
        source_root = Path(self.tmp.name) / "codex-plugin-home"
        os.environ["MB_INTEGRATION_SOURCE_ROOT"] = str(source_root)
        config_path = source_root / ".codex/config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            '[plugins."magnet-baron-skills@magnet-baron"]\nenabled = true\n'
            '[profiles.shop.plugins."magnet-baron-skills@magnet-baron"]\nenabled = true\n'
        )
        project_config = source_root / "project/.codex/config.toml"
        project_config.parent.mkdir(parents=True, exist_ok=True)
        project_config.write_text(
            '[plugins."magnet-baron-skills@magnet-baron"]\nenabled = true\n'
        )
        cached_manifest = (
            source_root / ".codex/plugins/cache/magnet-baron/magnet-baron-skills/0.2.9/"
            ".codex-plugin/plugin.json"
        )
        cached_manifest.parent.mkdir(parents=True, exist_ok=True)
        cached_manifest.write_text('{"name":"magnet-baron-skills"}')
        integrations.reset_process_cache()
        records, events = integrations.discover(integrations.load_adapters())
        self.assertEqual(events, [])
        self.assertFalse(any(r["runtime"] == "codex" and r["kind"] == "plugin" for r in records))
        inv = {"records": records}
        self.assertFalse(integrations.plugin_effective(
            "codex", "magnet-baron-skills", inv=inv
        )[0])

        installed = Path(self.tmp.name) / "installed-session.json"
        self.write_session(installed, "codex", [record(
            kind="plugin", ident="magnet-baron-skills@magnet-baron", callable=False,
        )])
        active_overlay = integrations.load_session(str(installed))
        self.assertTrue(integrations.plugin_effective(
            "codex", "magnet-baron-skills", inv=inv, overlay=active_overlay
        )[0])

        removed = Path(self.tmp.name) / "removed-session.json"
        self.write_session(removed, "codex", [])
        removed_overlay = integrations.load_session(str(removed))
        self.assertFalse(integrations.plugin_effective(
            "codex", "magnet-baron-skills", inv=inv, overlay=removed_overlay
        )[0])

    def test_pid_owned_lock_protects_normal_live_owner_and_reclaims_recycled_or_dead(self):
        path = Path(self.tmp.name) / "owned.lock"
        path.write_text(json.dumps({"pid": os.getpid(), "owner": "live", "created_at": "recent"}))
        recent = datetime.now(timezone.utc).timestamp() - 60
        os.utime(path, (recent, recent))
        with self.assertRaisesRegex(integrations.InventoryError, "lock timeout"):
            integrations._lock(path, 0.05)
        self.assertTrue(path.exists())

        recycled = datetime.now(timezone.utc).timestamp() - integrations.LOCK_RECYCLED_PID_MAX_AGE_SECONDS - 1
        os.utime(path, (recycled, recycled))
        token = integrations._lock(path, 0.1)
        self.assertNotEqual(token, "live")
        integrations._unlock(path, token)
        self.assertFalse(path.exists())

        path.write_text(json.dumps({"pid": 2_000_000_000, "owner": "dead", "created_at": "now"}))
        token = integrations._lock(path, 0.1)
        self.assertNotEqual(token, "dead")
        integrations._unlock(path, token)
        self.assertFalse(path.exists())

    def test_manifest_configured_is_distinct_from_current_callable(self):
        self.write([record(callable=False, health="unknown")])
        inv = integrations.refresh(force=True)
        configured, _ = integrations.effective("codex", "mcp", "github", require_callable=False, inv=inv)
        callable_now, _ = integrations.effective("codex", "mcp", "github", require_callable=True, inv=inv)
        self.assertTrue(configured)
        self.assertFalse(callable_now)

        config = integrations.load_adapters()
        manifest = integrations._record(config, "codex", "mcp", "github")
        self.assertIsNone(manifest["installed"])
        self.assertTrue(integrations.effective(
            "codex", "mcp", "github", require_callable=False, inv={"records": [manifest]}
        )[0])
        explicitly_absent = dict(manifest, installed=False)
        self.assertFalse(integrations.effective(
            "codex", "mcp", "github", require_callable=False,
            inv={"records": [explicitly_absent]},
        )[0])

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
        self.assertTrue(hits[("mcp", "github")]["blocked"])
        self.assertFalse(hits[("mcp", "github")]["enabled"])
        self.assertEqual(hits[("mcp", "github")]["health"], "blocked")
        self.assertNotIn(("plugin", "magnet-baron-skills"), hits)

    def test_real_manifest_discover_capabilities_and_role_validation_without_fixture(self):
        os.environ.pop("MB_INTEGRATION_FIXTURE", None)
        source_root = Path(self.tmp.name) / "real-home"
        os.environ["MB_INTEGRATION_SOURCE_ROOT"] = str(source_root)
        claude = source_root / ".claude.json"
        claude.parent.mkdir(parents=True, exist_ok=True)
        claude.write_text(json.dumps({"mcpServers": {"gsc-indexing": {}, "dataforseo": {}}}))
        claude_plugins = source_root / ".claude/plugins/installed_plugins.json"
        claude_plugins.parent.mkdir(parents=True, exist_ok=True)
        claude_plugins.write_text(json.dumps({"plugins": {"magnet-baron-skills@magnet-baron": {}}}))
        codex = source_root / ".codex/config.toml"
        codex.parent.mkdir(parents=True, exist_ok=True)
        codex.write_text('[apps.browser]\nenabled = true\n')
        grok = source_root / ".grok/config.toml"
        grok.parent.mkdir(parents=True, exist_ok=True)
        grok.write_text(
            '[mcp_servers.shopify-mb-internal]\nenabled = true\n'
            '[mcp_servers.github]\nenabled = true\n'
            '[plugins]\nenabled = ["magnet-baron-skills"]\ndisabled = []\n'
        )
        integrations.reset_process_cache()
        config = integrations.load_adapters()
        records, events = integrations.discover(config)
        self.assertEqual(events, [])
        inv = {"records": records}
        shopify = next(r for r in records if r.get("canonical_id") == "shopify-mb-internal")
        self.assertIsNone(shopify["installed"])
        browser_app = next(r for r in records if r.get("canonical_id") == "browser" and r["kind"] == "app")
        self.assertIsNone(browser_app["installed"])
        self.assertTrue(integrations.effective(
            "codex", "app", "browser", require_callable=False, inv=inv
        )[0])
        self.assertFalse(integrations.effective(
            "codex", "app", "browser", require_callable=True, inv=inv
        )[0])
        provider_data = json.loads((ROOT / "config/providers.json").read_text())
        provider = provider_data["providers"]["grok-build"]
        connectors = json.loads((ROOT / "config/connectors.json").read_text())
        runtime_caps = routing.capabilities_of(
            "grok-build", provider, connectors, inventory=inv
        )
        configured_caps = routing.capabilities_of(
            "grok-build", provider, connectors, inventory=inv, require_callable=False
        )
        self.assertNotIn("shopify-mb-internal", runtime_caps)
        self.assertIn("shopify-mb-internal", configured_caps)
        loaded = gen.load(ROOT / "config/roles.json", ROOT / "config/providers.json", inventory=inv)
        self.assertIn("shopify-theme-build", loaded["roles"])

    def test_doctor_discovery_is_read_only_and_checks_grokbot_alias_coverage(self):
        os.environ.pop("MB_INTEGRATION_FIXTURE", None)
        os.environ["MB_INTEGRATION_SOURCE_ROOT"] = str(Path(self.tmp.name) / "empty-home")
        doctor = load_doctor()
        adapters = json.loads((ROOT / "config/integration-adapters.json").read_text())
        providers = json.loads((ROOT / "config/providers.json").read_text())
        doctor.check_integration_adapters(adapters, providers)
        self.assertEqual(doctor.ERRORS, [])
        self.assertFalse(integrations.cache_path().exists())
        self.assertFalse(integrations.events_path().exists())

        del adapters["session_only_aliases"]["grokbot-cursor"]["capability"]["browser"]
        doctor.ERRORS.clear()
        doctor.check_integration_adapters(adapters, providers)
        self.assertTrue(any("do not cover grok-bot-review-d" in e for e in doctor.ERRORS), doctor.ERRORS)

    def test_cli_session_merge_json_and_check(self):
        self.write([])
        session_file = Path(self.tmp.name) / "session.json"
        self.write_session(session_file, "codex", [record()])
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

        routed = subprocess.run(
            [sys.executable, str(HERE / "resolve-route.py"), "--class", "repo-code",
             "--intake-provider", "opus-5", "--integration-session", str(session_file),
             "--json", "--no-record"],
            capture_output=True, text=True, cwd=ROOT, env=env,
        )
        self.assertEqual(routed.returncode, 0, routed.stderr)
        routed_session = json.loads(routed.stdout)["integration_session"]
        self.assertEqual(routed_session["runtime"], "codex")
        self.assertEqual(routed_session["canonical_ids"], ["github"])
        self.assertRegex(routed_session["attestation"]["digest"], r"^sha256:[a-f0-9]{64}$")
        human = subprocess.run(
            [sys.executable, str(HERE / "resolve-route.py"), "--class", "repo-code",
             "--intake-provider", "opus-5", "--integration-session", str(session_file),
             "--no-record"],
            capture_output=True, text=True, cwd=ROOT, env=env,
        )
        self.assertEqual(human.returncode, 0, human.stderr)
        self.assertIn("integration session: runtime=codex canonical_ids=github source=dispatcher-runtime-v1", human.stdout)

        self.write_session(session_file, "codex", [])
        empty = subprocess.run(
            [sys.executable, str(HERE / "resolve-route.py"), "--class", "repo-code",
             "--intake-provider", "opus-5", "--integration-session", str(session_file),
             "--json", "--no-record"],
            capture_output=True, text=True, cwd=ROOT, env=env,
        )
        self.assertEqual(empty.returncode, 0, empty.stderr)
        empty_session = json.loads(empty.stdout)["integration_session"]
        self.assertEqual(empty_session["runtime"], "codex")
        self.assertEqual(empty_session["canonical_ids"], [])
        empty_human = subprocess.run(
            [sys.executable, str(HERE / "resolve-route.py"), "--class", "repo-code",
             "--intake-provider", "opus-5", "--integration-session", str(session_file),
             "--no-record"],
            capture_output=True, text=True, cwd=ROOT, env=env,
        )
        self.assertEqual(empty_human.returncode, 0, empty_human.stderr)
        self.assertIn("integration session: runtime=codex canonical_ids=[]", empty_human.stdout)


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
