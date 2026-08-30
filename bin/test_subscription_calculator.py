#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "subscription_calculator_test_target", HERE / "subscription-calculator.py"
)
target = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(target)
USAGE_SPEC = importlib.util.spec_from_file_location(
    "usage_record_test_target", HERE / "usage-record.py"
)
usage_target = importlib.util.module_from_spec(USAGE_SPEC)
USAGE_SPEC.loader.exec_module(usage_target)


def habits(**overrides):
    values = {
        "implement_hours_per_day": 0,
        "reviews_per_week": 0,
        "mcp_bulk_per_week": 0,
        "cross_family": False,
        "codex_available": True,
        "third_party_safe_review": False,
        "storefront_pixels": False,
        "analytics": False,
        "ide_hours_per_day": 0,
        "team_size": 1,
    }
    values.update(overrides)
    return values


class SubscriptionCalculatorTests(unittest.TestCase):
    HISTORY_NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)

    def test_parked_standing_role_needs_do_not_justify_grok_plan(self):
        stack, reasons, monthly = target.recommend(
            habits(storefront_pixels=True, analytics=True)
        )
        self.assertNotIn("grok-heavy", stack)
        self.assertEqual(monthly, 0)
        reason = " ".join(reasons)
        self.assertIn("future needs only", reason)
        self.assertIn("hard-parked before inputs", reason)

    def test_real_implementation_volume_still_justifies_grok_plan(self):
        stack, reasons, monthly = target.recommend(
            habits(implement_hours_per_day=1, storefront_pixels=True)
        )
        self.assertEqual(stack.get("grok-heavy"), 1)
        self.assertEqual(monthly, target.PRICES["grok-heavy"])
        self.assertTrue(any("Grok Build implementation volume" in item for item in reasons))

    def test_explicit_no_codex_keeps_unwired_review_e_unserved(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = target.main([
                "--cross-family",
                "--no-codex",
                "--third-party-safe-review",
                "--json",
            ])
        self.assertEqual(rc, 0)
        result = json.loads(stdout.getvalue())
        self.assertFalse(result["habits"]["codex_available"])
        self.assertNotIn("codex-200", result["recommended_stack"])
        self.assertNotIn("fireworks-review-e", result["recommended_stack"])
        self.assertEqual(result["recommended_stack"].get("claude-max"), 1)
        self.assertEqual(result["monthly_usd_indicative"], target.PRICES["claude-max"])
        reason = " ".join(result["reasons"])
        self.assertIn("remains unserved", reason)
        self.assertIn("future setup candidate", reason)
        self.assertIn("currently unwired", reason)

    def test_no_codex_does_not_send_unsanitized_risk_work_to_review_e(self):
        stack, reasons, _monthly = target.recommend(
            habits(cross_family=True, codex_available=False)
        )
        self.assertNotIn("codex-200", stack)
        self.assertNotIn("fireworks-review-e", stack)
        reason = " ".join(reasons)
        self.assertIn("remains unserved", reason)
        self.assertIn("Secrets and PII stay parked", reason)

    def test_string_booleans_cannot_cross_safety_or_availability_gates(self):
        with self.assertRaisesRegex(ValueError, "third_party_safe_review"):
            target.recommend(
                habits(
                    cross_family=True,
                    codex_available=False,
                    third_party_safe_review="false",
                )
            )
        with self.assertRaisesRegex(ValueError, "codex_available"):
            target.recommend(
                habits(cross_family=True, codex_available="false")
            )

    def test_explicit_null_codex_availability_does_not_default_to_available(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "habits.json"
            source.write_text(json.dumps({"codex_available": None}))
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                rc = target.main(["--from-json", str(source), "--json"])
            self.assertEqual(rc, 2)
            self.assertIn("codex_available must be an exact JSON boolean", stderr.getvalue())

    def test_from_json_cannot_mask_explicit_cli_safety_flags(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "habits.json"
            source.write_text(json.dumps({"codex_available": True, "cross_family": False}))
            for flag in ("--no-codex", "--cross-family"):
                with self.subTest(flag=flag):
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr):
                        rc = target.main(["--from-json", str(source), flag, "--json"])
                    self.assertEqual(rc, 2)
                    self.assertIn("cannot be mixed", stderr.getvalue())

    def test_empty_plain_result_does_not_claim_an_unreturned_plan(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = target.main([])
        self.assertEqual(rc, 0)
        text = stdout.getvalue()
        self.assertIn("No paid stack is indicated", text)
        self.assertIn("~$0/mo", text)
        self.assertNotIn("Claude Pro ($25)", text)

    def test_partial_history_does_not_treat_unobserved_subscription_as_zero_use(self):
        monitoring = {"sources": {}}
        subscriptions = {
            "subscriptions": {
                "observed-sub": {"product": "Observed", "monthly_usd": 200},
                "unknown-sub": {"product": "Unknown", "monthly_usd": 200},
            }
        }
        windows = {
            "seats": {
                "observed-seat": {"subscription": "observed-sub"},
                "unknown-seat": {"subscription": "unknown-sub"},
            }
        }
        configs = {
            "monitoring.json": monitoring,
            "subscriptions.json": subscriptions,
            "usage-windows.json": windows,
        }
        history = [{
            "ts": "2026-08-20T12:00:00+00:00",
            "seat": "observed-seat", "pct": 10, "tier": "available",
            "billing": "included",
        }]
        with mock.patch.object(
            target.mborch, "load_config", side_effect=lambda name, **_: configs[name]
        ), mock.patch.object(target.mborch, "read_history", return_value=history):
            result = target.from_history(now=self.HISTORY_NOW)
        text = " ".join(result["recommendations"])
        self.assertIn("observed-sub", text)
        self.assertNotIn("unknown-sub", text)
        self.assertNotIn("DOWNGRADE", text)
        self.assertIn("INSUFFICIENT downgrade evidence", text)

    def test_spent_snapshots_count_transitions_not_repeated_observations(self):
        configs = {
            "monitoring.json": {"sources": {}},
            "subscriptions.json": {
                "subscriptions": {
                    "observed-sub": {"product": "Observed", "monthly_usd": 200},
                }
            },
            "usage-windows.json": {
                "seats": {"observed-seat": {"subscription": "observed-sub"}},
            },
        }

        def row(minute, tier):
            return {
                "ts": f"2026-08-01T00:{minute:02d}:00+00:00",
                "seat": "observed-seat", "pct": 90, "tier": tier,
                "billing": "included",
            }

        def recommendations(history):
            with mock.patch.object(
                target.mborch, "load_config", side_effect=lambda name, **_: configs[name]
            ), mock.patch.object(target.mborch, "read_history", return_value=history):
                return " ".join(
                    target.from_history(now=self.HISTORY_NOW)["recommendations"]
                )

        consecutive = recommendations([row(0, "spent"), row(1, "spent"), row(2, "spent")])
        self.assertNotIn("ADD capacity", consecutive)

        episodes = recommendations([
            row(0, "spent"), row(1, "available"), row(2, "spent"),
            row(3, "available"), row(4, "spent"),
        ])
        self.assertIn("ADD capacity", episodes)
        self.assertIn("spent state 3x", episodes)

    def test_spent_transition_count_uses_pre_window_state_as_baseline(self):
        configs = {
            "monitoring.json": {"sources": {}},
            "subscriptions.json": {
                "subscriptions": {"plan": {"product": "Plan", "monthly_usd": 200}},
            },
            "usage-windows.json": {
                "seats": {"seat": {"subscription": "plan"}},
            },
        }
        history = [
            {"ts": "2026-07-31T11:59:59+00:00", "seat": "seat", "pct": 100,
             "tier": "spent", "billing": "included"},
            {"ts": "2026-08-01T00:00:00+00:00", "seat": "seat", "pct": 100,
             "tier": "spent", "billing": "included"},
            {"ts": "2026-08-02T00:00:00+00:00", "seat": "seat", "pct": 10,
             "tier": "available", "billing": "included"},
            {"ts": "2026-08-03T00:00:00+00:00", "seat": "seat", "pct": 100,
             "tier": "spent", "billing": "included"},
            {"ts": "2026-08-04T00:00:00+00:00", "seat": "seat", "pct": 10,
             "tier": "available", "billing": "included"},
            {"ts": "2026-08-05T00:00:00+00:00", "seat": "seat", "pct": 100,
             "tier": "spent", "billing": "included"},
        ]
        with mock.patch.object(
            target.mborch, "load_config", side_effect=lambda name, **_: configs[name]
        ), mock.patch.object(target.mborch, "read_history", return_value=history):
            result = target.from_history(now=self.HISTORY_NOW)
        text = " ".join(result["recommendations"])
        self.assertEqual(result["analyzed_records"], 5)
        self.assertNotIn("ADD capacity", text)
        self.assertEqual(result["utilization"][0]["times_spent"], 2)

    def test_exhaustion_recommendation_does_not_require_percent_samples(self):
        configs = {
            "monitoring.json": {"sources": {}},
            "subscriptions.json": {
                "subscriptions": {"plan": {"product": "Plan", "monthly_usd": 200}},
            },
            "usage-windows.json": {
                "seats": {"seat": {"subscription": "plan"}},
            },
        }

        def row(day, tier, pct=None):
            return {
                "ts": f"2026-08-{day:02d}T00:00:00+00:00", "seat": "seat",
                "pct": pct, "tier": tier, "billing": "included",
            }

        histories = (
            [row(1, "spent"), row(2, "available"), row(3, "spent"),
             row(4, "available"), row(5, "spent")],
            [row(1, "spent", 10), row(2, "available"), row(3, "spent"),
             row(4, "available"), row(5, "spent")],
        )
        for history in histories:
            with self.subTest(history=history), mock.patch.object(
                target.mborch, "load_config", side_effect=lambda name, **_: configs[name]
            ), mock.patch.object(target.mborch, "read_history", return_value=history):
                result = target.from_history(now=self.HISTORY_NOW)
            text = " ".join(result["recommendations"])
            self.assertIn("ADD capacity near plan", text)
            self.assertIn("spent state 3x", text)
            self.assertNotIn("DOWNGRADE", text)
            self.assertNotIn("INSUFFICIENT downgrade evidence", text)

    def test_downgrade_requires_samples_for_every_configured_subscription_seat(self):
        configs = {
            "monitoring.json": {"sources": {}},
            "subscriptions.json": {
                "subscriptions": {
                    "codex-200": {"product": "Codex", "monthly_usd": 200},
                }
            },
            "usage-windows.json": {
                "seats": {
                    "codex-sol": {"subscription": "codex-200"},
                    "codex-plan": {"subscription": "codex-200"},
                },
            },
        }
        history = [{
            "ts": "2026-08-20T12:00:00+00:00", "seat": "codex-sol",
            "pct": 10, "tier": "available", "billing": "included",
        }]
        with mock.patch.object(
            target.mborch, "load_config", side_effect=lambda name, **_: configs[name]
        ), mock.patch.object(target.mborch, "read_history", return_value=history):
            result = target.from_history(now=self.HISTORY_NOW)
        self.assertNotIn("DOWNGRADE", " ".join(result["recommendations"]))

    def test_downgrade_requires_longitudinal_coverage_and_then_can_recommend(self):
        configs = {
            "monitoring.json": {"sources": {}},
            "subscriptions.json": {
                "subscriptions": {
                    "plan": {"product": "Plan", "monthly_usd": 200},
                }
            },
            "usage-windows.json": {
                "seats": {"seat": {"subscription": "plan"}},
            },
        }

        def analyze(history):
            with mock.patch.object(
                target.mborch, "load_config", side_effect=lambda name, **_: configs[name]
            ), mock.patch.object(target.mborch, "read_history", return_value=history):
                return " ".join(
                    target.from_history(now=self.HISTORY_NOW)["recommendations"]
                )

        one_sample = [{
            "ts": "2026-08-01T12:00:00+00:00", "seat": "seat", "pct": 10,
            "tier": "available", "billing": "included",
        }]
        sparse = analyze(one_sample)
        self.assertNotIn("DOWNGRADE candidate", sparse)
        self.assertIn("INSUFFICIENT downgrade evidence", sparse)

        days = list(range(1, 21)) + [29]
        sufficient = [
            {
                "ts": f"2026-08-{day:02d}T12:00:00+00:00",
                "seat": "seat", "pct": 10, "tier": "available",
                "billing": "included",
            }
            for day in days
        ]
        recommendation = analyze(sufficient)
        self.assertIn("DOWNGRADE candidate: plan", recommendation)
        self.assertNotIn("INSUFFICIENT downgrade evidence", recommendation)

    def test_near_cap_peak_is_not_reported_as_an_exhaustion_event(self):
        configs = {
            "monitoring.json": {"sources": {}},
            "subscriptions.json": {
                "subscriptions": {
                    "plan": {"product": "Plan", "monthly_usd": 200},
                }
            },
            "usage-windows.json": {
                "seats": {"seat": {"subscription": "plan"}},
            },
        }
        history = [{
            "ts": "2026-08-20T12:00:00+00:00", "seat": "seat", "pct": 95,
            "tier": "available", "billing": "included",
        }]
        with mock.patch.object(
            target.mborch, "load_config", side_effect=lambda name, **_: configs[name]
        ), mock.patch.object(target.mborch, "read_history", return_value=history):
            result = target.from_history(now=self.HISTORY_NOW)
        text = " ".join(result["recommendations"])
        self.assertIn("REVIEW capacity", text)
        self.assertIn("near-cap evidence", text)
        self.assertNotIn("entered the spent state", text)
        self.assertNotIn("losing throughput", text)

    def test_metered_history_does_not_invent_an_included_equivalent(self):
        configs = {
            "monitoring.json": {"sources": {}},
            "subscriptions.json": {
                "subscriptions": {"metered": {"product": "Metered", "monthly_usd": 0}},
            },
            "usage-windows.json": {
                "seats": {"seat": {"subscription": "metered", "billing": "metered"}},
            },
        }
        history = [{
            "ts": "2026-08-20T12:00:00+00:00", "seat": "seat", "pct": 50,
            "tier": "available", "billing": "metered",
        }]
        with mock.patch.object(
            target.mborch, "load_config", side_effect=lambda name, **_: configs[name]
        ), mock.patch.object(target.mborch, "read_history", return_value=history):
            result = target.from_history(now=self.HISTORY_NOW)
        text = " ".join(result["recommendations"])
        self.assertIn("Metered use observed", text)
        self.assertIn("does not prove", text)
        self.assertNotIn("would cut API billing", text)

    def test_history_advice_excludes_old_and_malformed_timestamps(self):
        configs = {
            "monitoring.json": {"sources": {}},
            "subscriptions.json": {
                "subscriptions": {
                    "plan": {"product": "Plan", "monthly_usd": 200},
                }
            },
            "usage-windows.json": {
                "seats": {"seat": {"subscription": "plan"}},
            },
        }
        history = [
            {"ts": "2025-09-01T00:00:00+00:00", "seat": "seat", "pct": 99,
             "tier": "spent", "billing": "included"},
            {"ts": "not-a-time", "seat": "seat", "pct": 99,
             "tier": "spent", "billing": "included"},
        ]
        with mock.patch.object(
            target.mborch, "load_config", side_effect=lambda name, **_: configs[name]
        ), mock.patch.object(target.mborch, "read_history", return_value=history):
            result = target.from_history(now=self.HISTORY_NOW)
        self.assertEqual(result["retained_records"], 2)
        self.assertEqual(result["analyzed_records"], 0)
        text = " ".join(result["recommendations"])
        self.assertIn("No usable timestamped usage history", text)
        self.assertNotIn("capacity near", text)

    def test_history_ignores_malformed_seat_percent_tier_and_billing_rows(self):
        configs = {
            "monitoring.json": {"sources": {}},
            "subscriptions.json": {
                "subscriptions": {"plan": {"product": "Plan", "monthly_usd": 200}},
            },
            "usage-windows.json": {
                "seats": {"seat": {"subscription": "plan", "billing": "included"}},
            },
        }
        base = {"ts": "2026-08-20T12:00:00+00:00", "seat": "seat"}
        history = [
            dict(base, pct=True, tier="available", billing="included"),
            dict(base, pct=float("inf"), tier="available", billing="included"),
            dict(base, pct=-1, tier="available", billing="included"),
            dict(base, pct=101, tier="available", billing="included"),
            dict(base, pct=50, tier="garbage", billing="included"),
            dict(base, pct=50, tier="available", billing="credits"),
            {"ts": base["ts"], "seat": ["unhashable"], "pct": 50,
             "tier": "available", "billing": "included"},
        ]
        with mock.patch.object(
            target.mborch, "load_config", side_effect=lambda name, **_: configs[name]
        ), mock.patch.object(target.mborch, "read_history", return_value=history):
            result = target.from_history(now=self.HISTORY_NOW)
        self.assertEqual(result["analyzed_records"], 0)
        self.assertEqual(result["utilization"], [])
        self.assertNotIn("capacity", " ".join(result["recommendations"]).lower())

    def test_owner_percent_parser_rejects_unknown_nonfinite_and_out_of_range_values(self):
        seats = {"codex-sol": {}}
        for value in ("nan", "inf", "-1", "101", "not-a-number"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                usage_target.parse_owner_pairs([f"codex-sol={value}"], seats)
        with self.assertRaisesRegex(ValueError, "not configured"):
            usage_target.parse_owner_pairs(["unknown=50"], seats)
        self.assertEqual(
            usage_target.parse_owner_pairs(["codex-sol=50"], seats),
            [("codex-sol", 50.0)],
        )

    def test_monitoring_source_command_requires_exact_enabled_true(self):
        for enabled in (False, "false", "true", 0, 1, None, [], {}):
            with self.subTest(enabled=enabled), mock.patch.object(
                usage_target.shutil, "which"
            ) as which, mock.patch.object(usage_target.subprocess, "run") as run:
                data, note = usage_target.run_source(
                    "teamclaude",
                    {"sources": {"teamclaude": {
                        "enabled": enabled, "cmd": "teamclaude status --json",
                    }}},
                )
                self.assertIsNone(data)
                self.assertIn("not enabled", note)
                which.assert_not_called()
                run.assert_not_called()

    def test_successful_external_probe_cannot_claim_history_capture(self):
        proc = mock.Mock(stdout='{"accounts": []}\n', returncode=0)
        with mock.patch.object(usage_target.shutil, "which", return_value="/bin/tool"), \
                mock.patch.object(usage_target.subprocess, "run", return_value=proc):
            data, note = usage_target.run_source(
                "teamclaude",
                {"sources": {"teamclaude": {
                    "enabled": True, "cmd": "teamclaude status --json",
                }}},
            )
        self.assertEqual(data, {"accounts": []})
        self.assertIn("probe", note)
        self.assertIn("0 history rows persisted", note)
        self.assertNotIn("captured", note)

    def test_failed_external_probe_cannot_turn_error_json_into_success(self):
        proc = mock.Mock(stdout='{"error": "not authenticated"}\n', returncode=3)
        with mock.patch.object(usage_target.shutil, "which", return_value="/bin/tool"), \
                mock.patch.object(usage_target.subprocess, "run", return_value=proc):
            data, note = usage_target.run_source(
                "teamclaude",
                {"sources": {"teamclaude": {
                    "enabled": True, "cmd": "teamclaude status --json",
                }}},
            )
        self.assertIsNone(data)
        self.assertIn("exited 3", note)
        self.assertIn("0 history rows persisted", note)
        self.assertNotIn("parse ok", note)


if __name__ == "__main__":
    unittest.main()
