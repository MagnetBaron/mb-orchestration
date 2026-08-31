#!/usr/bin/env python3
"""Focused tests for the privacy-safe TeamClaude status adapter."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tc = _load("teamclaude_status_test", "teamclaude_status.py")
usage = _load("usage_status_teamclaude_test", "usage-status.py")
agents = _load("detect_agents_teamclaude_test", "detect-agents.py")
capability = _load("detect_capability_teamclaude_test", "detect-capability.py")
resolve = _load("resolve_route_teamclaude_test", "resolve-route.py")


def subscriptions(count: int, *, fable: int | None = None) -> dict:
    fable = count if fable is None else fable
    rows = {}
    for index in range(count):
        rows[f"declared-{index}"] = {
            "vendor": "Anthropic",
            "seat_id": f"seat-{index}",
            "grants": {"opus": True, "fable": index < fable},
        }
    rows["other-provider"] = {
        "vendor": "OpenAI",
        "grants": {"opus": True, "fable": True},
    }
    return {"subscriptions": rows}


def account(
    name: str,
    *,
    five_hour: float | None = 0.1,
    shared_weekly: float | None = 0.2,
    fable_weekly: float | None = 0.3,
    status: str = "active",
    disabled: bool = False,
    unified_status: str | None = "allowed",
    five_hour_status: str | None = None,
    shared_weekly_status: str | None = None,
    fable_weekly_status: str | None = None,
    fable_capability: str | None = None,
) -> dict:
    return {
        "name": name,
        "type": "oauth",
        "disabled": disabled,
        "status": status,
        "quota": {
            "unified5h": five_hour,
            "unified7d": shared_weekly,
            "unified7dFable": fable_weekly,
            "unified7dSonnet": None,
            "unifiedStatus": unified_status,
            "unified5hStatus": five_hour_status,
            "unified7dStatus": shared_weekly_status,
            "unified7dFableStatus": fable_weekly_status,
            "unified7dSonnetStatus": None,
            "fableCapability": fable_capability,
        },
    }


def native(accounts: list[dict], *, threshold: float = 0.98) -> dict:
    probed_at = datetime.now(timezone.utc).isoformat()
    return {
        "switchThreshold": threshold,
        "blockedModels": [],
        "accounts": accounts,
        "probe": {
            "enabled": True,
            "intervalSeconds": 300,
            "accounts": [
                {"name": item["name"], "status": "ok", "lastProbedAt": probed_at}
                for item in accounts
            ],
        },
        "routes": [{
            "name": "fable",
            "match": ["*fable*"],
            "accounts": [
                # This is TeamClaude's own (currently insufficient) eligibility
                # bit.  The adapter deliberately recomputes quota eligibility.
                {"name": item["name"], "eligible": True} for item in accounts
            ],
        }],
        "persistence": {
            "healthy": True,
            "lastSuccessAt": probed_at,
            "lastErrorAt": None,
            "errorCode": None,
        },
    }


class TeamClaudeEligibilityTests(unittest.TestCase):
    def test_fable_requires_shared_5h_shared_weekly_and_family_weekly(self):
        cases = (
            (1.0, 0.1, 0.1),
            (0.1, 1.0, 0.1),
            (0.1, 0.1, 1.0),
            (None, 0.1, 0.1),
            (0.1, None, 0.1),
            (0.1, 0.1, None),
        )
        for five_hour, shared, family in cases:
            with self.subTest(five_hour=five_hour, shared=shared, family=family):
                doc = native([account(
                    "private-account-name",
                    five_hour=five_hour,
                    shared_weekly=shared,
                    fable_weekly=family,
                )])
                report = tc.summarize_status(
                    doc,
                    subscriptions=subscriptions(1),
                    models=("claude-fable-5",),
                )
                self.assertEqual(report["models"]["fable"]["eligible_account_count"], 0)
                self.assertIs(report["available"], False)

    def test_switch_threshold_does_not_discard_remaining_quota(self):
        report = tc.summarize_status(
            native([
                account(
                    "drain-the-remainder",
                    five_hour=0.98,
                    shared_weekly=0.98,
                    fable_weekly=0.98,
                ),
            ], threshold=0.98),
            subscriptions=subscriptions(1),
            models=("claude-fable-5",),
        )
        row = report["models"]["fable"]
        self.assertEqual(row["capable_account_count"], 1)
        self.assertEqual(row["eligible_account_count"], 1)
        self.assertIs(row["all_capable_quota_exhausted"], False)
        self.assertIs(report["available"], True)

    def test_low_family_bucket_does_not_override_spent_shared_weekly_bucket(self):
        doc = native([
            account("spent-shared", shared_weekly=1.0, fable_weekly=0.05),
            account("healthy-overflow", shared_weekly=0.25, fable_weekly=0.15),
        ])
        report = tc.summarize_status(
            doc,
            subscriptions=subscriptions(2),
            models=("claude-fable-5",),
        )
        row = report["models"]["fable"]
        self.assertEqual(row["capable_account_count"], 2)
        self.assertEqual(row["eligible_account_count"], 1)
        self.assertIs(report["available"], True)

    def test_all_capable_quota_exhaustion_requires_positive_fresh_bucket_evidence(self):
        spent = tc.summarize_status(
            native([
                account("one", shared_weekly=1.0),
                account("two", fable_weekly=1.0),
            ]),
            subscriptions=subscriptions(2),
            models=("claude-fable-5",),
        )
        self.assertIs(
            spent["models"]["fable"]["all_capable_quota_exhausted"], True
        )

        stale = native([account("stale", fable_weekly=1.0)])
        stale["probe"]["accounts"][0]["lastProbedAt"] = (
            datetime.now(timezone.utc) - timedelta(hours=2)
        ).isoformat()
        stale_report = tc.summarize_status(
            stale,
            subscriptions=subscriptions(1),
            models=("claude-fable-5",),
        )
        self.assertIs(
            stale_report["models"]["fable"]["all_capable_quota_exhausted"], False
        )

    def test_native_teamclaude_route_eligibility_is_an_additional_gate(self):
        doc = native([account("native-refused")])
        doc["routes"][0]["accounts"][0]["eligible"] = False
        report = tc.summarize_status(
            doc,
            subscriptions=subscriptions(1),
            models=("claude-fable-5",),
        )
        self.assertEqual(report["models"]["fable"]["capable_account_count"], 1)
        self.assertEqual(report["models"]["fable"]["eligible_account_count"], 0)
        self.assertIs(report["models"]["fable"]["all_capable_quota_exhausted"], False)

    def test_api_key_account_cannot_masquerade_as_included_subscription_capacity(self):
        api = account("paid-api")
        api["type"] = "apikey"
        doc = native([api])
        doc["probe"]["accounts"][0].update({
            "status": "not-applicable",
            "lastProbedAt": None,
        })
        report = tc.summarize_status(
            doc,
            subscriptions=subscriptions(1),
            models=("claude-fable-5",),
        )
        self.assertEqual(report["observed"]["account_count"], 0)
        self.assertEqual(report["observed"]["excluded_non_oauth_account_count"], 1)
        self.assertEqual(report["models"]["fable"]["capable_account_count"], 0)
        self.assertEqual(report["models"]["fable"]["eligible_account_count"], 0)
        self.assertIs(report["available"], False)

    def test_explicit_fable_capability_overrides_bucket_presence_for_capacity(self):
        doc = native([
            account("supported", fable_weekly=None, fable_capability="supported"),
            account("unsupported", fable_weekly=0.1, fable_capability="unsupported"),
            account("unknown", fable_weekly=0.1, fable_capability="unknown"),
        ])
        report = tc.summarize_status(
            doc,
            subscriptions=subscriptions(3, fable=1),
            models=("claude-fable-5",),
        )
        self.assertEqual(report["models"]["fable"]["capable_account_count"], 1)
        self.assertEqual(report["models"]["fable"]["eligible_account_count"], 0)

    def test_rejected_disabled_and_throttled_accounts_are_not_eligible(self):
        doc = native([
            account("rejected", unified_status="rejected"),
            account("disabled", disabled=True),
            account("throttled", status="throttled"),
        ])
        report = tc.summarize_status(
            doc,
            subscriptions=subscriptions(3),
            models=("claude-fable-5",),
        )
        self.assertEqual(report["models"]["fable"]["eligible_account_count"], 0)
        self.assertIs(report["available"], False)

    def test_bucket_specific_rejection_is_authoritative_without_utilization(self):
        cases = (
            {"five_hour": None, "five_hour_status": "rejected"},
            {"shared_weekly": None, "shared_weekly_status": "rejected"},
            {"fable_weekly": None, "fable_weekly_status": "rejected"},
        )
        for fields in cases:
            with self.subTest(fields=fields):
                report = tc.summarize_status(
                    native([account("rejected-bucket", **fields)]),
                    subscriptions=subscriptions(1),
                    models=("claude-fable-5",),
                )
                self.assertEqual(
                    report["models"]["fable"]["eligible_account_count"], 0
                )
                self.assertIs(report["available"], False)

        family_rejected = tc.summarize_status(
            native([account(
                "family-rejected",
                fable_weekly=None,
                fable_weekly_status="rejected",
            )]),
            subscriptions=subscriptions(1),
            models=("claude-fable-5",),
        )
        self.assertEqual(
            family_rejected["models"]["fable"]["capable_account_count"], 1
        )
        self.assertIs(
            family_rejected["models"]["fable"]["all_capable_quota_exhausted"],
            True,
        )

    def test_smaller_live_subset_is_usable_but_reports_inventory_drift(self):
        doc = native([
            account("one"),
            account("two"),
            account("three"),
        ])
        report = tc.summarize_status(
            doc,
            subscriptions=subscriptions(5, fable=3),
            models=("claude-opus-5", "claude-fable-5"),
        )
        self.assertIs(report["reconciled"], True)
        self.assertIs(report["available"], True)
        self.assertEqual(report["observed"]["account_count"], 3)
        self.assertEqual(report["declared"]["account_count"], 5)
        self.assertEqual(report["models"]["opus"]["capable_account_count"], 3)
        self.assertEqual(report["models"]["fable"]["capable_account_count"], 3)
        self.assertEqual(report["problems"], [])
        self.assertTrue(any("degraded subset" in item for item in report["warnings"]))

    def test_live_accounts_or_capability_above_declared_ceiling_fail_closed(self):
        too_many = tc.summarize_status(
            native([account("one"), account("two")]),
            subscriptions=subscriptions(1),
            models=("claude-opus-5",),
        )
        self.assertIs(too_many["reconciled"], False)
        self.assertIs(too_many["available"], False)
        self.assertTrue(any("exceeds" in item for item in too_many["problems"]))

        undeclared_fable = tc.summarize_status(
            native([account("one")]),
            subscriptions=subscriptions(1, fable=0),
            models=("claude-fable-5",),
        )
        self.assertIs(undeclared_fable["reconciled"], True)
        self.assertIs(undeclared_fable["available"], False)
        self.assertIs(undeclared_fable["models"]["fable"]["blocked_by_policy"], True)
        self.assertTrue(any("fable capability exceeds" in item
                            for item in undeclared_fable["warnings"]))

        separated = tc.summarize_status(
            native([account("one")]),
            subscriptions=subscriptions(1, fable=0),
            models=("claude-opus-5", "claude-fable-5"),
        )
        self.assertGreater(separated["models"]["opus"]["eligible_account_count"], 0)
        self.assertIs(separated["models"]["opus"]["blocked_by_policy"], False)
        self.assertIs(separated["models"]["fable"]["blocked_by_policy"], True)

    def test_disabled_probe_configuration_fails_reconciliation(self):
        doc = native([account("one")])
        doc["probe"]["enabled"] = False
        report = tc.summarize_status(
            doc,
            subscriptions=subscriptions(1),
            models=("claude-fable-5",),
        )
        self.assertIs(report["available"], False)
        self.assertIs(report["reconciled"], False)
        self.assertTrue(any("probe" in problem for problem in report["problems"]))

    def test_excessive_probe_interval_cannot_make_old_state_fresh(self):
        doc = native([account("one")])
        doc["probe"]["intervalSeconds"] = 86_400
        report = tc.summarize_status(
            doc,
            subscriptions=subscriptions(1),
            models=("claude-fable-5",),
        )
        self.assertIs(report["reconciled"], False)
        self.assertIs(report["available"], False)
        self.assertTrue(any("freshness ceiling" in item for item in report["problems"]))

    def test_one_stale_probe_excludes_only_that_account(self):
        doc = native([account("fresh"), account("stale")])
        doc["probe"]["accounts"][1]["lastProbedAt"] = (
            datetime.now(timezone.utc) - timedelta(hours=2)
        ).isoformat()
        report = tc.summarize_status(
            doc,
            subscriptions=subscriptions(2),
            models=("claude-fable-5",),
        )
        self.assertIs(report["reconciled"], True)
        self.assertIs(report["available"], True)
        self.assertEqual(report["models"]["fable"]["eligible_account_count"], 1)
        self.assertTrue(any("1 excluded" in warning for warning in report["warnings"]))

    def test_only_stale_probe_leaves_no_eligible_account_without_global_drift(self):
        doc = native([account("stale")])
        doc["probe"]["accounts"][0]["lastProbedAt"] = (
            datetime.now(timezone.utc) - timedelta(hours=2)
        ).isoformat()
        report = tc.summarize_status(
            doc,
            subscriptions=subscriptions(1),
            models=("claude-fable-5",),
        )
        self.assertIs(report["reconciled"], True)
        self.assertIs(report["available"], False)
        self.assertEqual(report["models"]["fable"]["eligible_account_count"], 0)
        self.assertTrue(any("1 excluded" in warning for warning in report["warnings"]))

    def test_timeout_probe_state_is_schema_valid_but_not_eligible(self):
        doc = native([account("timed-out")])
        doc["probe"]["accounts"][0].update({
            "status": "timeout",
            "lastProbedAt": None,
        })
        report = tc.summarize_status(
            doc,
            subscriptions=subscriptions(1),
            models=("claude-fable-5",),
        )
        self.assertIs(report["schema_valid"], True)
        self.assertEqual(report["models"]["fable"]["eligible_account_count"], 0)

    def test_persistence_degradation_is_visible_without_stranding_live_quota(self):
        doc = native([account("one")])
        doc["persistence"] = {
            "healthy": False,
            "lastSuccessAt": None,
            "lastErrorAt": datetime.now(timezone.utc).isoformat(),
            "errorCode": "ENOSPC",
        }
        report = tc.summarize_status(
            doc,
            subscriptions=subscriptions(1),
            models=("claude-fable-5",),
        )
        self.assertIs(report["available"], True)
        self.assertEqual(
            report["persistence"],
            {"reported": True, "healthy": False, "error_code": "ENOSPC"},
        )
        self.assertTrue(any("persistence is degraded" in item
                            for item in report["warnings"]))

    def test_missing_persistence_health_is_a_degraded_compatibility_warning(self):
        doc = native([account("one")])
        del doc["persistence"]
        report = tc.summarize_status(
            doc,
            subscriptions=subscriptions(1),
            models=("claude-fable-5",),
        )
        self.assertIs(report["available"], True)
        self.assertIs(report["persistence"]["reported"], False)
        self.assertTrue(any("upgrade required" in item for item in report["warnings"]))

    def test_route_and_blocklist_restrictions_are_enforced(self):
        doc = native([account("allowed"), account("excluded")])
        doc["routes"][0]["accounts"] = [{"name": "allowed", "eligible": True}]
        report = tc.summarize_status(
            doc,
            subscriptions=subscriptions(2, fable=1),
            models=("claude-fable-5",),
        )
        self.assertEqual(report["models"]["fable"]["capable_account_count"], 1)
        self.assertEqual(report["models"]["fable"]["eligible_account_count"], 1)
        self.assertIs(report["reconciled"], True)

        doc["blockedModels"] = ["*fable*"]
        blocked = tc.summarize_status(
            doc,
            subscriptions=subscriptions(2, fable=0),
            models=("claude-fable-5",),
        )
        self.assertIs(blocked["models"]["fable"]["blocked_by_policy"], True)
        self.assertEqual(blocked["models"]["fable"]["eligible_account_count"], 0)


class TeamClaudePrivacyAndProcessTests(unittest.TestCase):
    def test_successful_report_never_contains_native_account_names(self):
        secret_names = ("owner-email@example.test", "second-private-profile")
        doc = native([account(name) for name in secret_names])
        result = tc.CommandResult(0, json.dumps(doc), "")
        report = tc.inspect_status(
            executable="/mock/teamclaude",
            runner=lambda _argv: result,
            subscriptions=subscriptions(2),
            models=("claude-fable-5",),
        )
        rendered = json.dumps(report)
        for name in secret_names:
            self.assertNotIn(name, rendered)
        self.assertIs(report["available"], True)

    def test_command_failure_does_not_echo_sensitive_stderr(self):
        secret = "private-account-name@example.test"
        report = tc.inspect_status(
            executable="/mock/teamclaude",
            runner=lambda _argv: tc.CommandResult(1, "", f"failed for {secret}"),
            subscriptions=subscriptions(1),
        )
        self.assertNotIn(secret, json.dumps(report))
        self.assertEqual(report["error_code"], "service_unreachable")
        self.assertIs(report["available"], False)

    def test_absent_transport_is_graceful_and_never_ready(self):
        with mock.patch.object(tc.shutil, "which", return_value=None):
            report = tc.inspect_status()
        self.assertIs(report["transport_present"], False)
        self.assertIs(report["available"], False)
        self.assertEqual(report["readiness"], "blocked")

    def test_schema_mismatch_fails_closed_without_echoing_values(self):
        secret = "private-account-name@example.test"
        malformed = native([account(secret)])
        malformed["accounts"][0]["disabled"] = "false"
        report = tc.inspect_status(
            executable="/mock/teamclaude",
            runner=lambda _argv: tc.CommandResult(0, json.dumps(malformed), ""),
            subscriptions=subscriptions(1),
        )
        self.assertEqual(report["error_code"], "schema_mismatch")
        self.assertIs(report["available"], False)
        self.assertNotIn(secret, json.dumps(report))

    def test_subprocess_output_is_actually_bounded(self):
        with self.assertRaises(tc.OutputLimitError):
            tc.run_bounded(
                [sys.executable, "-c", "import os; os.write(1, b'x' * 8192)"],
                timeout=3,
                max_output_bytes=1024,
            )


class TeamClaudeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.report = {
            "tool": "teamclaude",
            "transport_present": True,
            "service_reachable": True,
            "schema_valid": True,
            "available": True,
            "readiness": "ready",
            "reconciled": True,
            "models": {
                "fable": {
                    "eligible_account_count": 2,
                    "capable_account_count": 3,
                    "declared_seat_count": 3,
                }
            },
            "status": "live rotation ready",
        }

    def test_usage_status_uses_schema_bound_adapter(self):
        with mock.patch.object(
            usage.teamclaude_status, "inspect_status", return_value=self.report
        ) as inspect:
            self.assertIs(usage.rotation_status(), self.report)
        inspect.assert_called_once_with()

    def test_detect_agents_uses_schema_bound_adapter(self):
        with mock.patch.object(
            agents.teamclaude_status, "inspect_status", return_value=self.report
        ) as inspect:
            self.assertIs(agents.detect_rotation(), self.report)
        inspect.assert_called_once_with()

    def test_detect_capability_uses_aggregate_fable_state(self):
        with mock.patch.object(
            capability.teamclaude_status, "inspect_status", return_value=self.report
        ) as inspect:
            live, note, returned = capability.teamclaude_fable_report()
        inspect.assert_called_once_with(models=("claude-fable-5",))
        self.assertIs(live, True)
        self.assertIn("2 eligible / 3 capable / 3 declared", note)
        self.assertIs(returned, self.report)

    def test_detect_capability_does_not_call_quota_exhaustion_a_downgrade(self):
        exhausted = json.loads(json.dumps(self.report))
        exhausted["available"] = False
        exhausted["models"]["fable"]["eligible_account_count"] = 0
        with mock.patch.object(
            capability.teamclaude_status, "inspect_status", return_value=exhausted
        ):
            present, _note, _returned = capability.teamclaude_fable_report()
        self.assertIs(present, True)

    def test_detect_capability_preserves_two_value_compatibility_api(self):
        with mock.patch.object(
            capability, "teamclaude_fable_report", return_value=(True, "ready", self.report)
        ):
            self.assertEqual(capability.teamclaude_fable(), (True, "ready"))

    def test_runtime_routing_uses_model_specific_anonymous_pool(self):
        providers = resolve.mborch.load_config("providers.json", required=True)
        row = {
            "seat": "claude-max",
            "subscription": "claude-max-200",
            "family": "anthropic",
            "fable": True,
            "billing": "included",
            "tier": "available",
            "usable": True,
            "available": True,
            "window_kinds": ["rolling"],
            "runway_seconds": None,
            "intake": False,
            "teamclaude_rotation": self.report,
        }
        seats = resolve.provider_seats("fable-5", providers, [row])
        self.assertEqual([item["seat"] for item in seats], ["teamclaude-fable-pool"])
        self.assertEqual(seats[0]["runtime_eligible_accounts"], 2)

        # Overall readiness may be false because another requested model is
        # exhausted; the requested model's fresh eligible pool remains usable.
        partial = dict(self.report, available=False)
        partial_seats = resolve.provider_seats(
            "fable-5", providers,
            [dict(row, teamclaude_rotation=partial)],
        )
        self.assertEqual([item["seat"] for item in partial_seats],
                         ["teamclaude-fable-pool"])

        blocked = dict(self.report, available=False, reconciled=False)
        self.assertEqual(
            resolve.provider_seats(
                "fable-5", providers,
                [dict(row, teamclaude_rotation=blocked)],
            ),
            [],
        )

    def test_runtime_routing_preserves_only_positive_quota_spent_aggregate(self):
        providers = resolve.mborch.load_config("providers.json", required=True)
        base_row = {
            "seat": "claude-max",
            "subscription": "claude-max-200",
            "family": "anthropic",
            "fable": True,
            "billing": "included",
            "tier": "available",
            "usable": True,
            "available": True,
            "window_kinds": ["rolling"],
            "runway_seconds": None,
            "intake": False,
        }
        spent = json.loads(json.dumps(self.report))
        spent["available"] = False
        spent["models"]["fable"].update({
            "eligible_account_count": 0,
            "all_capable_quota_exhausted": True,
            "blocked_by_policy": False,
        })
        rows = resolve.provider_seats(
            "fable-5", providers,
            [dict(base_row, teamclaude_rotation=spent)],
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["tier"], "spent")
        self.assertIs(rows[0]["runtime_quota_spent"], True)

        stale = json.loads(json.dumps(spent))
        stale["models"]["fable"]["all_capable_quota_exhausted"] = False
        self.assertEqual(
            resolve.provider_seats(
                "fable-5", providers,
                [dict(base_row, teamclaude_rotation=stale)],
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
