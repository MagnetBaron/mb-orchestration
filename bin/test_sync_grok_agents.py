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
REAL_STAT = os.stat


class SyncGrokAgentsTests(unittest.TestCase):
    def setUp(self):
        self.provenance = mock.patch.object(
            target, "canonical_checkout_problem", return_value=None
        )
        self.provenance.start()
        self.addCleanup(self.provenance.stop)

    def _sync_home(self, root: str) -> Path:
        self.assertEqual(target.main(["--target-home", root]), 0)
        return Path(root) / ".grok" / "agents"

    def test_generator_rejects_write_capability_for_standing_roles(self):
        roles = json.loads((HERE.parent / "config" / "roles.json").read_text())
        roles["roles"]["review-d"]["tools"]["grok"] = ["Read", "Grep", "Glob", "Write"]
        with mock.patch.object(target, "_load_canonical_json", side_effect=lambda n: {
            "roles.json": roles,
            "providers.json": json.loads((HERE.parent / "config" / "providers.json").read_text()),
        }[n]):
            with self.assertRaisesRegex(ValueError, "must be exact"):
                target.expected()

    def test_distribution_rejects_unknown_grok_tools_such_as_taskcreate(self):
        roles = json.loads((HERE.parent / "config" / "roles.json").read_text())
        providers = json.loads((HERE.parent / "config" / "providers.json").read_text())
        roles["roles"]["review-d"]["tools"]["grok"] = ["Read", "Grep", "Glob", "TaskCreate"]
        with mock.patch.object(target, "_load_canonical_json", side_effect=lambda n: {
            "roles.json": roles,
            "providers.json": providers,
        }[n]):
            with self.assertRaisesRegex(ValueError, "must be exact"):
                target.expected()

    def test_distribution_rejects_standing_grok_skills_or_extra_frontmatter(self):
        roles = json.loads((HERE.parent / "config" / "roles.json").read_text())
        providers = json.loads((HERE.parent / "config" / "providers.json").read_text())
        roles["roles"]["review-d"]["grok"] = {
            "tools": ["Read", "Grep", "Glob"],
            "skills": ["untrusted:skill"],
        }
        with mock.patch.object(target, "_load_canonical_json", side_effect=lambda n: {
            "roles.json": roles,
            "providers.json": providers,
        }[n]):
            with self.assertRaisesRegex(ValueError, "skills, plugins, MCP"):
                target.expected()

    def test_distribution_requires_standing_provider_enabled_absent_or_exact_true(self):
        roles = json.loads((HERE.parent / "config" / "roles.json").read_text())
        baseline = json.loads((HERE.parent / "config" / "providers.json").read_text())
        for value in (False, "false", 0, 1, None):
            with self.subTest(value=value):
                providers = json.loads(json.dumps(baseline))
                providers["providers"]["grok-bot-review-d"]["enabled"] = value
                with mock.patch.object(target, "_load_canonical_json", side_effect=lambda n: {
                    "roles.json": roles,
                    "providers.json": providers,
                }[n]):
                    with self.assertRaisesRegex(ValueError, "enabled with exact true"):
                        target.expected()

    def test_distribution_requires_each_standing_role_exact_seat_binding(self):
        roles = json.loads((HERE.parent / "config" / "roles.json").read_text())
        providers = json.loads((HERE.parent / "config" / "providers.json").read_text())
        roles["roles"]["review-d"]["seat"] = "grok-bot-heat-map"
        with mock.patch.object(target, "_load_canonical_json", side_effect=lambda n: {
            "roles.json": roles,
            "providers.json": providers,
        }[n]):
            with self.assertRaisesRegex(ValueError, "seat must be exact"):
                target.expected()

    def test_main_reports_generation_failure_without_writing(self):
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(target, "expected", side_effect=ValueError("unsafe role")):
            rc = target.main(["--target-home", td])
            self.assertEqual(rc, 2)
            self.assertFalse((Path(td) / ".grok").exists())

    def test_sync_and_check_reject_symlinked_profile_parent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / "home"
            outside = root / "outside"
            home.mkdir()
            outside.mkdir()
            (home / ".grok").symlink_to(outside, target_is_directory=True)
            self.assertEqual(target.main(["--target-home", str(home)]), 2)
            self.assertEqual(target.main(["--target-home", str(home), "--check"]), 2)
            self.assertFalse((outside / "agents").exists())

    def test_main_refuses_noncanonical_or_untrusted_checkout_before_generation(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(
            target, "canonical_checkout_problem", return_value="refusing non-canonical checkout"
        ), mock.patch.object(target, "expected") as expected:
            self.assertEqual(target.main(["--target-home", td]), 2)
            expected.assert_not_called()
            self.assertFalse((Path(td) / ".grok").exists())

    def test_expected_profiles_ignore_ambient_config_overlay(self):
        with tempfile.TemporaryDirectory() as td:
            overlay = Path(td)
            roles = json.loads((HERE.parent / "config" / "roles.json").read_text())
            providers = json.loads((HERE.parent / "config" / "providers.json").read_text())
            roles["roles"]["review-d"]["prompt"] += " OVERLAY-PROOF"
            (overlay / "roles.json").write_text(json.dumps(roles))
            (overlay / "providers.json").write_text(json.dumps(providers))
            with mock.patch.dict(os.environ, {"MB_CONFIG_DIR": str(overlay)}):
                profiles = target.expected()
        self.assertNotIn("OVERLAY-PROOF", profiles["mb-review-d.md"])

    def test_canonical_config_read_rejects_fifo_symlink_and_oversize(self):
        providers = (HERE.parent / "config" / "providers.json").read_bytes()
        roles = (HERE.parent / "config" / "roles.json").read_bytes()
        for case in ("fifo", "symlink", "oversize"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                config = root / "config"
                config.mkdir()
                (config / "providers.json").write_bytes(providers)
                roles_path = config / "roles.json"
                if case == "fifo":
                    os.mkfifo(roles_path)
                elif case == "symlink":
                    source = config / "roles-source.json"
                    source.write_bytes(roles)
                    roles_path.symlink_to(source)
                else:
                    roles_path.write_bytes(
                        b"x" * (target.MAX_CANONICAL_CONFIG_BYTES + 1)
                    )
                with mock.patch.object(target, "ROOT", root):
                    with self.assertRaisesRegex(ValueError, "cannot safely load"):
                        target.expected()

    def test_check_accepts_only_stable_exact_regular_profiles(self):
        with tempfile.TemporaryDirectory() as td:
            self._sync_home(td)
            self.assertEqual(target.main(["--target-home", td, "--check"]), 0)

    def test_check_rejects_wrong_mode_and_owner(self):
        with tempfile.TemporaryDirectory() as td:
            agents = self._sync_home(td)
            profile = agents / "mb-review-d.md"
            profile.chmod(0o666)
            self.assertEqual(target.main(["--target-home", td, "--check"]), 1)
            profile.chmod(target.EXPECTED_PROFILE_MODE)
            agents_fd = os.open(agents, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with mock.patch.object(target.os, "getuid", return_value=os.getuid() + 1):
                    with self.assertRaisesRegex(ValueError, "not owned"):
                        target._read_installed_profile_at(agents_fd, profile.name)
            finally:
                os.close(agents_fd)

    def test_check_rejects_fifo_oversize_and_invalid_utf8_without_hanging(self):
        cases = ("fifo", "oversize", "invalid-utf8")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as td:
                agents = self._sync_home(td)
                profile = agents / "mb-review-d.md"
                profile.unlink()
                if case == "fifo":
                    os.mkfifo(profile)
                elif case == "oversize":
                    profile.write_bytes(b"x" * (target.MAX_PROFILE_BYTES + 1))
                else:
                    profile.write_bytes(b"\xff\xfe")
                self.assertEqual(
                    target.main(["--target-home", td, "--check"]), 1
                )

    def test_check_rejects_path_swapped_to_symlink_after_descriptor_read(self):
        with tempfile.TemporaryDirectory() as td:
            agents = self._sync_home(td)
            profile = agents / "mb-review-d.md"
            replacement = agents / "replacement.md"
            replacement.write_text(target.expected()["mb-review-d.md"])
            swapped = False

            def swap_then_stat(path, *args, **kwargs):
                nonlocal swapped
                if (path == profile.name and kwargs.get("dir_fd") is not None
                        and kwargs.get("follow_symlinks") is False and not swapped):
                    swapped = True
                    profile.unlink()
                    profile.symlink_to(replacement)
                return REAL_STAT(path, *args, **kwargs)

            with mock.patch.object(target.os, "stat", side_effect=swap_then_stat):
                rc = target.main(["--target-home", td, "--check"])
            self.assertTrue(swapped)
            self.assertEqual(rc, 1)
            self.assertTrue(profile.is_symlink())


if __name__ == "__main__":
    unittest.main()
