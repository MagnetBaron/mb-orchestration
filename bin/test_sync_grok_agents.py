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
        with mock.patch.object(target.gen, "WRITE_TOOLS", set(target.gen.WRITE_TOOLS) | {"Read"}):
            with self.assertRaisesRegex(ValueError, "contains write tools"):
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
