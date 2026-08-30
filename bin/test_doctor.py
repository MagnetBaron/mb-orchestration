#!/usr/bin/env python3
"""Regression tests for active-prose contradiction detection."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("doctor_policy_test", HERE / "doctor.py")
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)


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


if __name__ == "__main__":
    unittest.main()
