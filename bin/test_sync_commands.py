#!/usr/bin/env python3
"""Host-distribution regression tests using an isolated install root."""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "sync-commands.sh"
CANON = ROOT / ".claude" / "commands" / "orchestrate.md"
SKILL = ROOT / "skills" / "orca" / "SKILL.md"


class SyncCommandsTests(unittest.TestCase):
    def run_sync(self, install_root, *args, repo=ROOT, trusted_origin=None, script=SCRIPT):
        env = os.environ.copy()
        env.pop("CLAUDE_CONFIG_DIR", None)
        env["MB_ORCHESTRATION_HOME"] = str(install_root)
        env["ORCA_REPO"] = str(repo)
        origin = subprocess.run(
            ["git", "-C", str(ROOT), "remote", "get-url", "origin"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        env["ORCA_TRUSTED_ORIGIN"] = trusted_origin or origin
        return subprocess.run(
            [str(script), *args], cwd=ROOT, env=env,
            capture_output=True, text=True, check=False,
        )

    @staticmethod
    def github_slug(origin):
        value = origin.rstrip("/")
        if value.endswith(".git"):
            value = value[:-4]
        for prefix in ("https://github.com/", "git@github.com:", "ssh://git@github.com/"):
            if value.startswith(prefix):
                return value[len(prefix):]
        raise AssertionError(f"test checkout does not use a GitHub origin: {origin}")

    def test_sync_check_and_drift_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            skipped = home / ".claude-skipped"
            skipped.mkdir()
            profile = home / ".claude-profile"
            profile.mkdir()
            (profile / "settings.json").write_text("{}\n")

            installed = self.run_sync(home)
            self.assertEqual(0, installed.returncode, installed.stderr)
            self.assertIn("SKIP", installed.stderr)
            self.assertEqual(CANON.read_bytes(), (home / ".codex/prompts/orca.md").read_bytes())
            self.assertEqual(SKILL.read_bytes(), (home / ".agents/skills/orca/SKILL.md").read_bytes())
            self.assertTrue((profile / "commands/orca.md").samefile(CANON))

            checked = self.run_sync(home, "--check")
            self.assertEqual(0, checked.returncode, checked.stderr)

            actual_origin = subprocess.run(
                ["git", "-C", str(ROOT), "remote", "get-url", "origin"],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            slug = self.github_slug(actual_origin)
            for trusted in (
                f"https://github.com/{slug}",
                f"git@github.com:{slug}",
                f"ssh://git@github.com/{slug}.git/",
            ):
                with self.subTest(trusted=trusted):
                    variant = self.run_sync(home, "--check", trusted_origin=trusted)
                    self.assertEqual(0, variant.returncode, variant.stderr)

            drifted = home / ".codex/prompts/orca.md"
            drifted.write_text("stale\n")
            before = drifted.read_bytes()
            failed = self.run_sync(home, "--check")
            self.assertNotEqual(0, failed.returncode)
            self.assertEqual(before, drifted.read_bytes(), "--check mutated a stale copy")

    def test_noncanonical_checkout_is_refused_before_host_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            fake = Path(tmp) / "other-repo"
            home.mkdir()
            fake.mkdir()
            result = self.run_sync(home, repo=fake)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("refusing non-canonical checkout", result.stderr)
            self.assertFalse((home / ".codex/prompts/orca.md").exists())

    def test_symlinked_checkout_path_normalizes_physically(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            linked = Path(tmp) / "repo-link"
            home.mkdir()
            linked.symlink_to(ROOT, target_is_directory=True)
            result = self.run_sync(home, repo=ROOT, script=linked / "sync-commands.sh")
            self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
