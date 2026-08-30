#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("sync_grok_agents_test_target", HERE / "sync-grok-agents.py")
target = importlib.util.module_from_spec(spec)
spec.loader.exec_module(target)


class SyncGrokAgentsTests(unittest.TestCase):
    def test_generator_rejects_write_capability_for_standing_roles(self):
        roles = json.loads((HERE.parent / "config" / "roles.json").read_text())
        roles["roles"]["review-d"]["tools"]["grok"] = ["Read", "Grep", "Glob", "Write"]
        with mock.patch.object(target.mborch, "load_config", side_effect=lambda n, **_: {
            "roles.json": roles,
            "providers.json": json.loads((HERE.parent / "config" / "providers.json").read_text()),
        }[n]):
            with self.assertRaisesRegex(ValueError, "must be exact"):
                target.expected()

    def test_distribution_rejects_unknown_grok_tools_such_as_taskcreate(self):
        roles = json.loads((HERE.parent / "config" / "roles.json").read_text())
        providers = json.loads((HERE.parent / "config" / "providers.json").read_text())
        roles["roles"]["review-d"]["tools"]["grok"] = ["Read", "Grep", "Glob", "TaskCreate"]
        with mock.patch.object(target.mborch, "load_config", side_effect=lambda n, **_: {
            "roles.json": roles,
            "providers.json": providers,
        }[n]):
            with self.assertRaisesRegex(ValueError, "must be exact"):
                target.expected()

    def test_main_reports_generation_failure_without_writing(self):
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(target, "expected", side_effect=ValueError("unsafe role")):
            rc = target.main(["--target-home", td])
            self.assertEqual(rc, 2)
            self.assertFalse((Path(td) / ".grok").exists())

    def test_expected_profiles_honor_config_overlay(self):
        with tempfile.TemporaryDirectory() as td:
            overlay = Path(td)
            roles = json.loads((HERE.parent / "config" / "roles.json").read_text())
            providers = json.loads((HERE.parent / "config" / "providers.json").read_text())
            roles["roles"]["review-d"]["prompt"] += " OVERLAY-PROOF"
            (overlay / "roles.json").write_text(json.dumps(roles))
            (overlay / "providers.json").write_text(json.dumps(providers))
            with mock.patch.dict(os.environ, {"MB_CONFIG_DIR": str(overlay)}):
                profiles = target.expected()
        self.assertIn("OVERLAY-PROOF", profiles["mb-review-d.md"])


if __name__ == "__main__":
    unittest.main()
