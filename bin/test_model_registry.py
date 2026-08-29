#!/usr/bin/env python3
"""Fail-closed routing, independence, stale evidence, route-state, scoring tests."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent


def load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mr = load_mod("model_registry", HERE / "model-registry.py")
ev = load_mod("model_eval", HERE / "model-eval.py")
LIVE = REPO / "config" / "model-registry.json"


def live():
    return json.loads(LIVE.read_text())


class LiveCatalogTests(unittest.TestCase):
    def test_live_validates(self):
        registry = live()
        providers = json.loads((REPO / "config" / "providers.json").read_text())
        errors = mr.validate(registry, as_of=date(2026, 8, 28), providers=providers)
        self.assertEqual(errors, [])

    def test_required_roles_present(self):
        registry = live()
        self.assertTrue(set(mr.REQUIRED_ROLES).issubset(registry["roles"]))
        self.assertTrue(set(mr.REQUIRED_ROLES).issubset(registry["rankings"]))

    def test_matrix_idempotent(self):
        registry = live()
        first = mr.render_matrix(registry)
        second = mr.render_matrix(registry)
        self.assertEqual(first, second)
        self.assertTrue(first.endswith("\n"))


class FailClosedTests(unittest.TestCase):
    def test_unwired_never_resolves(self):
        decision = mr.resolve(live(), "research_synthesis")
        ids = [r["route"] for r in decision["routes"]]
        self.assertNotIn("kimi-k3-unwired", ids)
        self.assertNotIn("glm-5.3-flash-unwired", ids)
        self.assertTrue(decision["ok"])

    def test_catalog_verified_never_resolves(self):
        decision = mr.resolve(live(), "implementation")
        ids = [r["route"] for r in decision["routes"]]
        self.assertNotIn("gpt-5.5-codex", ids)
        self.assertNotIn("grok-4.5-cli", ids)

    def test_auth_blocked_never_resolves(self):
        decision = mr.resolve(live(), "code_review", n=5)
        ids = [r["route"] for r in decision["routes"]]
        self.assertNotIn("opus-5-direct-claude", ids)

    def test_unknown_role_fails_closed(self):
        decision = mr.resolve(live(), "not-a-role")
        self.assertFalse(decision["ok"])
        self.assertEqual(decision["routes"], [])

    def test_missing_capability_fails_closed(self):
        decision = mr.resolve(live(), "visual_qa", required_capabilities=["teleport"])
        self.assertFalse(decision["ok"])


class IndependenceTests(unittest.TestCase):
    def test_cross_family_rejects_same_family(self):
        decision = mr.resolve(live(), "code_review", family_diversity=2)
        self.assertTrue(decision["ok"])
        families = [r["family"] for r in decision["routes"]]
        self.assertEqual(len(families), len(set(families)))
        self.assertEqual(set(families), {"anthropic", "openai"})
        self.assertNotIn("fable-5-teamclaude", [r["route"] for r in decision["routes"]])

    def test_forced_same_family_fails(self):
        decision = mr.resolve(
            live(), "architecture_spec_critique",
            family_diversity=2,
            exclude_families=["openai", "xai", "google", "moonshot", "zhipu", "alibaba", "deepseek", "meta", "open-weight"],
        )
        self.assertFalse(decision["ok"])
        self.assertIn("fail-closed", decision["reason"])


class StaleEvidenceTests(unittest.TestCase):
    def test_stale_live_verified_fails_validation(self):
        data = copy.deepcopy(live())
        data["routes"]["opus-5-teamclaude"]["evidence_date"] = "2024-01-01"
        data["routes"]["opus-5-teamclaude"]["evidence"] = [
            {"date": "2024-01-01", "route_state": "live_verified"}
        ]
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(any("stale" in e for e in errors))

    def test_contradictory_same_date_fails(self):
        data = copy.deepcopy(live())
        data["routes"]["opus-5-teamclaude"]["evidence"] = [
            {"date": "2026-08-28", "route_state": "live_verified"},
            {"date": "2026-08-28", "route_state": "unwired"},
        ]
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(any("contradictory" in e for e in errors))

    def test_latest_evidence_mismatch_fails(self):
        data = copy.deepcopy(live())
        data["routes"]["opus-5-teamclaude"]["route_state"] = "live_verified"
        data["routes"]["opus-5-teamclaude"]["evidence"] = [
            {"date": "2026-08-01", "route_state": "catalog_verified"},
            {"date": "2026-08-28", "route_state": "unwired"},
        ]
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(any("contradicts latest evidence" in e for e in errors))


class RouteStateSeparationTests(unittest.TestCase):
    def test_inventory_keeps_unwired_visible(self):
        rows = mr.inventory(live())
        states = {r["route"]: r["route_state"] for r in rows}
        self.assertEqual(states["kimi-k3-unwired"], "unwired")
        self.assertEqual(states["opus-5-teamclaude"], "live_verified")
        self.assertEqual(states["opus-5-direct-claude"], "auth_blocked")
        self.assertEqual(states["gpt-5.5-codex"], "catalog_verified")

    def test_quality_rank_is_not_selection(self):
        impl = mr.rankings_for(live(), "implementation")
        q1 = impl["quality"][0]["route"]
        s1 = impl["selection"][0]["route"]
        self.assertNotEqual(q1, s1)
        self.assertEqual(s1, "grok-4.6-build")
        self.assertFalse(impl["authority_grants"])

    def test_resolve_does_not_grant_authority_keys(self):
        decision = mr.resolve(live(), "implementation")
        self.assertFalse(decision["authority_grants"])
        blob = json.dumps(decision)
        for key in mr.AUTHORITY_KEYS:
            self.assertNotIn(f'"{key}"', blob)


class PerformanceOrderingTests(unittest.TestCase):
    def test_selection_not_quality_for_implementation(self):
        by_sel = mr.resolve(live(), "implementation")
        by_q = mr.resolve(live(), "implementation", use_quality=True)
        self.assertEqual(by_sel["routes"][0]["route"], "grok-4.6-build")
        # Sol ranks higher on quality but lacks implement `code` on that route, so
        # quality resolve still fails closed onto a capable live route or empty.
        if by_q["ok"]:
            self.assertIn("code", by_q["routes"][0]["capabilities"])

    def test_quota_spent_skips_bucket(self):
        decision = mr.resolve(live(), "mcp_volume", quota_spent=["codex-200"])
        self.assertFalse(decision["ok"])


class ReceiptScoringTests(unittest.TestCase):
    def test_cases_validate(self):
        cases = ev.load_cases()
        self.assertEqual(ev.validate_cases(cases), [])

    def test_correctness_and_token_efficiency(self):
        cases = {c["id"]: c for c in ev.load_cases()["cases"]}
        case = cases["token-eff-1"]
        tight = ev.score_receipt(
            {"case_id": "token-eff-1", "output": "Yes, Opus 5.", "tokens_out": 8, "latency_ms": 90000},
            case,
        )
        verbose = ev.score_receipt(
            {"case_id": "token-eff-1", "output": "Yes, Opus 5. " + ("padding " * 80), "tokens_out": 400, "latency_ms": 10},
            case,
        )
        self.assertGreater(tight["token_efficiency"], verbose["token_efficiency"])
        self.assertEqual(tight["latency_weight"], 0.0)
        self.assertGreater(tight["total"], verbose["total"])
        self.assertFalse(tight["authority_grants"])

    def test_latency_does_not_win(self):
        cases = {c["id"]: c for c in ev.load_cases()["cases"]}
        case = cases["defect-review-1"]
        slow_right = ev.score_receipt(
            {"case_id": "defect-review-1",
             "output": "blocked: assignment used instead of comparison on an auth path",
             "tokens_out": 40, "latency_ms": 120000},
            case,
        )
        fast_wrong = ev.score_receipt(
            {"case_id": "defect-review-1", "output": "ship it looks fine", "tokens_out": 8, "latency_ms": 20},
            case,
        )
        self.assertGreater(slow_right["total"], fast_wrong["total"])

    def test_jsonl_round_trip(self):
        cases = ev.load_cases()
        lines = [
            json.dumps({"case_id": "brief-routing-1", "output": "Use grok-build, then Review D. Not Google MCP bulk.", "tokens_out": 24, "latency_ms": 1000}),
            json.dumps({"case_id": "evidence-1", "output": "No snapshot was provided; cannot invent GSC clicks.", "tokens_out": 18, "latency_ms": 800}),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.jsonl"
            path.write_text("\n".join(lines) + "\n")
            blob = ev.score_file(path, cases)
        self.assertEqual(blob["n"], 2)
        self.assertEqual(blob["latency_weight"], 0.0)
        self.assertFalse(blob["authority_grants"])
        self.assertGreater(blob["mean_correctness"], 0.5)


if __name__ == "__main__":
    unittest.main()
