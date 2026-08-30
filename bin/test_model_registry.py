#!/usr/bin/env python3
"""Fail-closed routing, independence, stale evidence, route-state, scoring tests."""
from __future__ import annotations

import copy
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
os.environ.setdefault(
    "MB_INTEGRATION_FIXTURE",
    str(REPO / "model-evals/fixtures/integrations/all-observed.json"),
)


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

    def test_marketplace_bot_is_cataloged_unwired_and_never_resolves(self):
        registry = live()
        route = registry["routes"]["grok-bot-marketplace-intelligence"]
        self.assertEqual(route["route_state"], "unwired")
        self.assertEqual(route["provider"], "grok-bot-marketplace-intelligence")
        self.assertEqual(route["capabilities"], ["marketplace_intelligence"])
        self.assertFalse(
            mr.route_is_live(
                registry, "grok-bot-marketplace-intelligence",
                as_of=date(2026, 8, 28),
            )
        )
        decision = mr.resolve(
            registry, "marketplace_intelligence", as_of=date(2026, 8, 28),
        )
        self.assertFalse(decision["ok"])
        self.assertEqual(decision["routes"], [])
        self.assertIn("fail-closed", decision["reason"])

    def test_grok_bot_marketplace_provider_has_no_selectable_model(self):
        provs = json.loads((REPO / "config" / "providers.json").read_text())
        provider = provs["providers"]["grok-bot-marketplace-intelligence"]
        self.assertEqual(provider["kind"], "app")
        self.assertIsNone(provider["model"])
        self.assertFalse(provider["wired"])
        self.assertFalse(provider["review_eligible"])

    def test_catalog_verified_never_resolves(self):
        decision = mr.resolve(live(), "implementation")
        ids = [r["route"] for r in decision["routes"]]
        self.assertNotIn("gpt-5.5-codex", ids)
        self.assertNotIn("grok-4.5-cli", ids)

    def test_opus_48_is_live_from_direct_smoke_and_excluded_from_review_order(self):
        registry = live()
        providers = json.loads((REPO / "config" / "providers.json").read_text())
        route = registry["routes"]["opus-4.8-teamclaude"]
        self.assertEqual(route["route_state"], "live_verified")
        self.assertEqual(route["evidence_strength"], "local_smoke")
        self.assertTrue(route["compatibility_fallback"])
        self.assertEqual(route["fallback_until"], "2026-12-31")
        self.assertEqual(registry["models"]["claude-opus-4-8"]["lifecycle"], "superseded")
        evidence = route["evidence"][0]
        self.assertEqual(evidence["kind"], "local_smoke")
        self.assertEqual(evidence["route_state"], "live_verified")
        self.assertIn("OPUS48_SMOKE_OK", evidence["source"])
        self.assertIn("claude-opus-4-8", evidence["source"])
        self.assertEqual(providers["review_order"], ["opus-5", "codex-sol", "review-e"])
        self.assertNotIn("opus-4.8", providers["review_order"])
        live_review = mr.live_review_providers(registry, providers)
        self.assertNotIn("opus-4.8", live_review)
        self.assertEqual(live_review, ["opus-5", "codex-sol"])
        review = mr.resolve(registry, "code_review", n=3)
        ids = [r["route"] for r in review["routes"]]
        self.assertEqual(ids[0], "opus-5-teamclaude")
        self.assertIn("opus-4.8-teamclaude", ids)
        impl = mr.resolve(registry, "implementation", n=2)
        self.assertNotIn("opus-4.8-teamclaude", [r["route"] for r in impl["routes"]])

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
        self.assertEqual(states["opus-4.8-teamclaude"], "live_verified")
        self.assertNotIn("deepseek-v4-unwired", states)
        self.assertEqual(states["deepseek-v4-pro-unwired"], "unwired")
        self.assertEqual(states["deepseek-v4-flash-unwired"], "unwired")

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

    def test_architecture_receipts_score_fail_closed_gold(self):
        path = REPO / "model-evals" / "receipts" / "2026-08-28-architecture-spec-critique.jsonl"
        blob = ev.score_file(path, ev.load_cases())
        self.assertEqual(blob["n"], 2)
        self.assertEqual(blob["latency_weight"], 0.0)
        self.assertFalse(blob["authority_grants"])
        by_model = {s["model"]: s for s in blob["results"]}
        self.assertEqual(by_model["claude-fable-5"]["correctness"], 1.0)
        self.assertEqual(by_model["claude-opus-5"]["correctness"], 1.0)
        self.assertEqual(by_model["claude-fable-5"]["tokens_out"], 1732)
        self.assertEqual(by_model["claude-opus-5"]["tokens_out"], 1986)
        cases = {c["id"]: c for c in ev.load_cases()["cases"]}
        self.assertEqual(cases["arch-spec-1"]["role"], "architecture_spec_critique")


class RankingClaimTests(unittest.TestCase):
    def test_kimi_k3_is_not_above_opus5_for_research_quality(self):
        rows = live()["rankings"]["research_synthesis"]["quality"]
        by_route = {row["route"]: row["rank"] for row in rows}
        self.assertLess(by_route["opus-5-teamclaude"], by_route["kimi-k3-unwired"])
        kimi = next(row for row in rows if row["route"] == "kimi-k3-unwired")
        self.assertEqual(kimi["confidence"], "low")

    def test_architecture_quality_ranks_opus5_before_fable(self):
        quality = live()["rankings"]["architecture_spec_critique"]["quality"]
        by_route = {row["route"]: row for row in quality}
        self.assertEqual(by_route["opus-5-teamclaude"]["rank"], 1)
        self.assertEqual(by_route["opus-5-teamclaude"]["confidence"], "high")
        self.assertEqual(by_route["opus-5-teamclaude"]["basis"], "local_same_harness")
        self.assertEqual(
            by_route["opus-5-teamclaude"]["source"],
            "model-evals/receipts/2026-08-28-architecture-spec-critique.jsonl",
        )
        self.assertEqual(by_route["fable-5-teamclaude"]["rank"], 2)
        self.assertEqual(by_route["fable-5-teamclaude"]["confidence"], "low")
        self.assertEqual(by_route["fable-5-teamclaude"]["basis"], "local_same_harness")
        self.assertEqual(
            by_route["fable-5-teamclaude"]["source"],
            "model-evals/receipts/2026-08-28-architecture-spec-critique.jsonl",
        )
        self.assertNotIn("long-horizon breadth", by_route["fable-5-teamclaude"]["rationale"].lower())
        joined = (
            by_route["opus-5-teamclaude"]["rationale"]
            + " "
            + by_route["fable-5-teamclaude"]["rationale"]
        ).lower()
        self.assertIn("same-harness", joined)
        self.assertIn("multi-case", joined)
        selection = live()["rankings"]["architecture_spec_critique"]["selection"]
        self.assertEqual([row["route"] for row in selection[:2]], [
            "opus-5-teamclaude",
            "fable-5-teamclaude",
        ])
        desc = live()["roles"]["architecture_spec_critique"]["description"].lower()
        self.assertIn("opus 5 first", desc)
        self.assertNotIn("fable is the escalation; opus 5 covers", desc)

    def test_independent_anchor_sources_are_direct_urls(self):
        required = {
            "claude-opus-5": [
                "https://artificialanalysis.ai/models/claude-opus-5",
                "https://artificialanalysis.ai/models/releases/claude-opus-5",
            ],
            "claude-fable-5": [
                "https://artificialanalysis.ai/models/claude-fable-5/",
            ],
            "grok-4.6": [
                "https://artificialanalysis.ai/models/releases/grok-4-6",
                "https://artificialanalysis.ai/articles/grok-4-6-benchmarks-and-analysis",
            ],
            "gpt-5.6-sol": [
                "https://artificialanalysis.ai/models/gpt-5-6-sol-xhigh/",
            ],
            "kimi-k3": [
                "https://artificialanalysis.ai/models/kimi-k3",
            ],
            "qwen-3.8-max": [
                "https://artificialanalysis.ai/models/qwen3-8-max",
            ],
            "glm-5.2": [
                "https://artificialanalysis.ai/models/glm-5-2",
            ],
        }
        by_model = {row["model"]: row for row in live()["independent_anchors"]}
        for model, urls in required.items():
            row = by_model[model]
            found = set(filter(None, [row.get("source"), *(row.get("sources") or [])]))
            for url in urls:
                self.assertIn(url, found, model)
            self.assertEqual(row["label"], "independent")
        glm_flash = by_model["glm-5.3-flash"]
        self.assertEqual(glm_flash["label"], "vendor_self_reported")
        self.assertEqual(glm_flash["source"], "https://z.ai/blog/glm-5.3-flash")

    def test_audit_report_has_direct_evidence_links_and_opus_first_architecture(self):
        report = (REPO / "docs" / "frontier-model-role-audit-2026-08-28.md").read_text()
        self.assertNotIn("Fable first on long-horizon breadth quality", report)
        self.assertIn("Opus 5 first at current evidence", report)
        self.assertIn("https://artificialanalysis.ai/models/claude-opus-5", report)
        self.assertIn("https://artificialanalysis.ai/models/releases/claude-opus-5", report)
        self.assertIn("https://artificialanalysis.ai/models/claude-fable-5/", report)
        self.assertIn("https://artificialanalysis.ai/models/releases/grok-4-6", report)
        self.assertIn("https://artificialanalysis.ai/articles/grok-4-6-benchmarks-and-analysis", report)
        self.assertIn("https://artificialanalysis.ai/models/gpt-5-6-sol-xhigh/", report)
        self.assertIn("https://artificialanalysis.ai/models/kimi-k3", report)
        self.assertIn("https://artificialanalysis.ai/models/qwen3-8-max", report)
        self.assertIn("https://artificialanalysis.ai/models/glm-5-2", report)
        self.assertIn("https://z.ai/blog/glm-5.3-flash", report)
        self.assertIn("https://openreview.net/attachment?id=AhXMZPnOPS&name=pdf", report)
        self.assertIn("https://openreview.net/pdf/8ee893eeebade004a09df53eef6d7ad289135999.pdf", report)
        self.assertIn("https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview", report)
        self.assertIn("https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works", report)
        self.assertIn("https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools", report)
        self.assertIn("almost tied", report)
        self.assertIn("does not enter the quality score", report)
        self.assertIn("untrusted evidence", report)
        self.assertNotIn("pay for themselves", report)
        self.assertNotIn("This catalog uses per-role, same-harness, same-effort tests", report)
        self.assertIn("hypothesis to measure", report)
        self.assertIn("existing_operational_state", report)
        self.assertIn("temporarily grandfathered", report)
        self.assertIn("evidence_kind", report)
        self.assertIn("structural_code", report)
        self.assertIn("legacy_waiver_routes", report)
        self.assertIn("allowed_domains_by_family", report)
        self.assertIn("compatibility_fallback_not_ranked", report)

    def test_context_scouting_quality_is_not_price(self):
        rows = live()["rankings"]["context_scouting"]["quality"]
        self.assertNotEqual(rows[0]["route"], "glm-5.3-flash-unwired")
        efficiency = live()["rankings"]["context_scouting"]["efficiency"]
        self.assertEqual(efficiency[0]["route"], "glm-5.3-flash-unwired")

    def test_implementation_default_remains_grok(self):
        impl = mr.rankings_for(live(), "implementation")
        self.assertEqual(impl["selection"][0]["route"], "grok-4.6-build")
        self.assertIn("evidence-bounded", impl["note"])

    def test_incubation_does_not_resolve_even_if_marked_live(self):
        data = copy.deepcopy(live())
        route = data["routes"]["glm-5.3-flash-unwired"]
        route["route_state"] = "live_verified"
        route["incubation"] = True
        route["host"] = "fake-host"
        route["evidence"] = [{"date": "2026-08-28", "route_state": "live_verified"}]
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(any("incubation" in e for e in errors))
        data["rankings"]["context_scouting"]["selection"] = [
            {"priority": 1, "route": "glm-5.3-flash-unwired", "confidence": "low", "rationale": "injected"},
            {"priority": 2, "route": "gpt-5.6-luna-codex", "confidence": "medium", "rationale": "live"},
        ]
        decision = mr.resolve(data, "context_scouting")
        self.assertNotIn("glm-5.3-flash-unwired", [r["route"] for r in decision["routes"]])


class CensusTests(unittest.TestCase):
    REQUIRED = (
        "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite", "gemini-3.1-pro-preview", "gemini-3-flash-preview",
        "kimi-k3", "kimi-k2.7-code", "kimi-k2.6",
        "deepseek-v4-pro", "deepseek-v4-flash",
        "muse-spark-1.2", "muse-code",
    )

    def test_census_scope_and_required_models(self):
        registry = live()
        census = registry["census"]
        self.assertEqual(census["cutoff"], "2026-08-28")
        self.assertIn("scoped", census["scope"].lower())
        self.assertNotIn("deepseek-v4", registry["models"])
        for mid in self.REQUIRED:
            self.assertIn(mid, registry["models"])
            routes = [r for r in registry["routes"].values() if r.get("model") == mid]
            self.assertTrue(routes, mid)
            self.assertTrue(all(r["route_state"] != "live_verified" for r in routes), mid)

    def test_opus5_direct_smoke_is_the_only_local_smoke_anthropic_gate(self):
        registry = live()
        providers = json.loads((REPO / "config" / "providers.json").read_text())
        self.assertEqual(registry["routes"]["opus-5-teamclaude"]["evidence_strength"], "local_smoke")
        self.assertIn("Direct live smoke", registry["routes"]["opus-5-teamclaude"]["evidence"][0]["source"])
        self.assertEqual(registry["routes"]["opus-4.8-teamclaude"]["evidence_strength"], "local_smoke")
        self.assertEqual(registry["routes"]["gpt-5.6-sol-codex"]["evidence_strength"], "cli_listing")
        self.assertNotIn("opus-4.8", providers["review_order"])
        self.assertEqual(mr.live_review_providers(registry, providers)[0], "opus-5")


class FableEvalLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fe = load_mod("fable_eval", HERE / "fable-eval.py")

    def test_default_comparison_arm_is_opus5(self):
        class Args:
            fable_model = None
            opus_model = None
            grader_model = None
        models = self.fe.resolve_models(Args())
        self.assertEqual(models["opus"], "claude-opus-5")
        self.assertEqual(self.fe.comparison_arm_label(models["opus"]), "Opus 5")
        line = self.fe.overall_outcome_line([], [{"axis": "coding"}], models["opus"])
        self.assertIn("Opus 5", line)
        self.assertNotIn("Opus 4.8", line)

    def test_label_follows_resolved_model(self):
        self.assertEqual(self.fe.comparison_arm_label("claude-opus-4-8"), "Opus 4.8")
        line = self.fe.overall_outcome_line(["coding"], [{"axis": "coding"}], "claude-opus-4-8")
        self.assertIn("Opus 4.8", line)
        self.assertIn("1 of 1", line)


rr = load_mod("resolve_route", HERE / "resolve-route.py")
doc = load_mod("doctor_mod", HERE / "doctor.py")


def providers():
    return json.loads((REPO / "config" / "providers.json").read_text())


def connectors():
    return json.loads((REPO / "config" / "connectors.json").read_text())


class ReviewEGateTests(unittest.TestCase):
    def test_wired_unwired_review_e_excluded_from_live_gate(self):
        registry = live()
        provs = providers()
        provs["providers"]["review-e"]["wired"] = True
        self.assertEqual(registry["routes"]["review-e-fireworks"]["route_state"], "unwired")
        live_ids = mr.live_review_providers(registry, provs)
        self.assertNotIn("review-e", live_ids)
        self.assertEqual(live_ids, ["opus-5", "codex-sol"])
        self.assertFalse(mr.provider_route_is_live(registry, provs["providers"]["review-e"]))

    def test_wired_unwired_review_e_does_not_satisfy_cross_family(self):
        registry = live()
        provs = providers()
        provs["providers"]["review-e"]["wired"] = True
        rows = [
            {"seat": "claude-max", "subscription": "claude-max-200", "tier": "available",
             "billing": "included", "family": "anthropic", "fable": True, "intake": False,
             "window_kinds": ["rolling"], "runway_seconds": 10000},
        ]
        reviewers = rr.live_reviewers(provs, rows, {}, registry)
        self.assertNotIn("review-e", [r["provider"] for r in reviewers])
        self.assertTrue(all(r["provider"] != "review-e" for r in reviewers))
        review = rr.pick_review(
            "cross-family", reviewers,
            mr.provider_route_is_live(registry, provs["providers"]["review-e"]), 0,
        )
        self.assertFalse(review["satisfied"])
        decision = mr.resolve(registry, "code_review", family_diversity=2)
        self.assertEqual(set(r["family"] for r in decision["routes"]), {"anthropic", "openai"})
        self.assertNotIn("review-e-fireworks", [r["route"] for r in decision["routes"]])


class OperationalLiveRouteTests(unittest.TestCase):
    def _rows(self):
        return [
            {"seat": "grok-heavy", "subscription": "grok-heavy", "tier": "available",
             "billing": "included", "intake": False, "window_kinds": ["weekly"],
             "runway_seconds": 864000, "family": "xai"},
            {"seat": "cursor-models", "subscription": "cursor-ultra", "tier": "available",
             "billing": "included", "intake": False, "window_kinds": ["monthly"],
             "runway_seconds": 864000 * 20, "family": "cursor-pool"},
            {"seat": "codex-plan", "subscription": "codex-200", "tier": "reserve",
             "billing": "included", "intake": True, "window_kinds": ["weekly"],
             "runway_seconds": 864000, "family": "openai"},
        ]

    def test_catalog_verified_grok_binding_is_not_selected(self):
        provs = providers()
        registry = live()
        provs["providers"]["grok-build"]["route"] = "gpt-5.5-codex"
        self.assertEqual(registry["routes"]["gpt-5.5-codex"]["route_state"], "catalog_verified")
        self.assertFalse(mr.route_is_live(registry, "gpt-5.5-codex"))
        steps = rr.pick_implement(
            provs, connectors(), self._rows(), "repo-code", "", "", False, 0, registry,
        )
        self.assertFalse(any(s.get("seat") == "grok-build" for s in steps))
        self.assertTrue(any(s.get("available") for s in steps))

    def test_unknown_route_state_fails_closed(self):
        registry = copy.deepcopy(live())
        registry["routes"]["grok-4.6-build"]["route_state"] = "who-knows"
        self.assertFalse(mr.route_is_live(registry, "grok-4.6-build"))
        self.assertNotIn("grok-4.6-build", mr.live_review_providers(registry, providers()))
        errors = mr.validate(registry, as_of=date(2026, 8, 28), providers=providers())
        self.assertTrue(any("who-knows" in e for e in errors))

    def test_missing_registry_parks_implement(self):
        steps = rr.pick_implement(
            providers(), connectors(), self._rows(), "repo-code", "", "", False, 0, None,
        )
        self.assertTrue(any("fail closed" in (s.get("why") or "") for s in steps))
        self.assertFalse(any(s.get("available") for s in steps))

    def test_auth_blocked_and_unwired_not_live(self):
        registry = live()
        self.assertFalse(mr.route_is_live(registry, "opus-5-direct-claude"))
        self.assertFalse(mr.route_is_live(registry, "review-e-fireworks"))
        self.assertFalse(mr.route_is_live(registry, "missing-route"))
        self.assertTrue(mr.route_is_live(registry, "grok-4.6-build", as_of=date(2026, 8, 28)))


class LastResortCodingTests(unittest.TestCase):
    """Last-resort coding names a concrete live implement/ide + code provider, else PARK."""

    def _spent_workers(self):
        return [
            {"seat": "grok-heavy", "subscription": "grok-heavy", "tier": "spent",
             "billing": "included", "intake": False, "window_kinds": ["weekly"],
             "runway_seconds": 864000, "family": "xai"},
            {"seat": "cursor-models", "subscription": "cursor-ultra", "tier": "spent",
             "billing": "included", "intake": False, "window_kinds": ["monthly"],
             "runway_seconds": 864000 * 20, "family": "cursor-pool"},
            {"seat": "codex-plan", "subscription": "codex-200", "tier": "reserve",
             "billing": "included", "intake": True, "window_kinds": ["weekly"],
             "runway_seconds": 864000, "family": "openai"},
        ]

    def _impl(self, provs, registry, rows=None):
        return rr.pick_implement(
            provs, connectors(), rows or self._spent_workers(),
            "repo-code", "", "", False, 0, registry,
        )

    def test_live_intake_without_coder_parks(self):
        steps = self._impl(providers(), live())
        self.assertFalse(any(s.get("last_resort") for s in steps))
        self.assertFalse(any(s.get("seat") == "dispatch/intake" for s in steps))
        self.assertTrue(any(not s.get("available") and "PARK" in (s.get("why") or "") for s in steps))
        for pid in ("codex-luna", "codex-terra", "codex-sol"):
            self.assertFalse(any(s.get("seat") == pid for s in steps), pid)

    def test_luna_terra_sol_are_not_coders(self):
        provs = providers()
        registry = live()
        for pid in ("codex-luna", "codex-terra", "codex-sol"):
            self.assertFalse(rr.provider_can_code(provs["providers"][pid], registry), pid)
        self.assertIsNone(rr.last_resort_coder(
            provs["providers"], registry, "codex-200", lambda pid: True,
        ))

    def test_concrete_intake_coder_is_named(self):
        provs = providers()
        registry = copy.deepcopy(live())
        luna = provs["providers"]["codex-luna"]
        luna["functions"] = list(luna["functions"]) + ["implement"]
        luna["capabilities"] = list(luna["capabilities"]) + ["code"]
        registry["routes"]["gpt-5.6-luna-codex"]["capabilities"] = list(
            registry["routes"]["gpt-5.6-luna-codex"]["capabilities"]
        ) + ["code"]
        self.assertTrue(rr.provider_can_code(luna, registry))
        self.assertEqual(
            rr.last_resort_coder(provs["providers"], registry, "codex-200", lambda pid: True),
            "codex-luna",
        )
        steps = self._impl(provs, registry)
        hit = [s for s in steps if s.get("last_resort")]
        self.assertEqual(len(hit), 1, steps)
        self.assertEqual(hit[0]["seat"], "codex-luna")
        self.assertEqual(hit[0]["on"], "codex-plan")
        self.assertNotEqual(hit[0]["seat"], "dispatch/intake")

    def test_code_on_provider_but_not_route_parks(self):
        provs = providers()
        registry = live()
        luna = provs["providers"]["codex-luna"]
        luna["functions"] = list(luna["functions"]) + ["implement"]
        luna["capabilities"] = list(luna["capabilities"]) + ["code"]
        self.assertNotIn("code", registry["routes"]["gpt-5.6-luna-codex"]["capabilities"])
        self.assertFalse(rr.provider_can_code(luna, registry))
        steps = self._impl(provs, registry)
        self.assertFalse(any(s.get("last_resort") for s in steps))
        self.assertTrue(any(not s.get("available") for s in steps))

    def test_implement_without_code_parks(self):
        provs = providers()
        registry = copy.deepcopy(live())
        luna = provs["providers"]["codex-luna"]
        luna["functions"] = list(luna["functions"]) + ["implement"]
        registry["routes"]["gpt-5.6-luna-codex"]["capabilities"] = (
            list(registry["routes"]["gpt-5.6-luna-codex"]["capabilities"]) + ["code"]
        )
        self.assertFalse(rr.provider_can_code(luna, registry))
        steps = self._impl(provs, registry)
        self.assertFalse(any(s.get("seat") == "codex-luna" for s in steps))


class NeedsMcpTests(unittest.TestCase):
    """--needs-mcp is a pipeline: connector match AND usable Terra, else PARK with no implement."""

    def _rows(self, terra_tier="reserve"):
        return [
            {"seat": "grok-heavy", "subscription": "grok-heavy", "tier": "available",
             "billing": "included", "intake": False, "window_kinds": ["weekly"],
             "runway_seconds": 864000, "family": "xai"},
            {"seat": "cursor-models", "subscription": "cursor-ultra", "tier": "available",
             "billing": "included", "intake": False, "window_kinds": ["monthly"],
             "runway_seconds": 864000 * 20, "family": "cursor-pool"},
            {"seat": "codex-plan", "subscription": "codex-200", "tier": terra_tier,
             "billing": "included", "intake": True, "window_kinds": ["weekly"],
             "runway_seconds": 864000, "family": "openai"},
        ]

    def _impl(self, needs_mcp, conns=None, provs=None, rows=None, registry=None):
        return rr.pick_implement(
            provs or providers(), conns or connectors(), rows if rows is not None else self._rows(),
            "repo-code", "", needs_mcp, False, 0, registry if registry is not None else live(),
        )

    def _assert_parked_no_continue(self, steps):
        self.assertTrue(
            any(not s.get("available") and "PARK" in (s.get("why") or "") for s in steps),
            steps,
        )
        self.assertFalse(
            any(s.get("seat") == "codex-terra" and s.get("available") for s in steps),
            steps,
        )
        self.assertFalse(any(s.get("seat") == "grok-build" for s in steps), steps)
        self.assertFalse(any(s.get("available") for s in steps), steps)

    def _assert_terra_then_implement(self, steps):
        self.assertTrue(
            any(s.get("seat") == "codex-terra" and s.get("available") for s in steps),
            steps,
        )
        self.assertTrue(
            any(s.get("seat") == "grok-build" and s.get("available") for s in steps),
            steps,
        )

    def test_active_id(self):
        self._assert_terra_then_implement(self._impl("google-search-console"))

    def test_active_alias(self):
        self._assert_terra_then_implement(self._impl("dfs-mcp"))

    def test_active_class(self):
        self._assert_terra_then_implement(self._impl("google-mcp"))

    def test_active_connector_available_terra_continues(self):
        steps = self._impl("google-search-console", rows=self._rows(terra_tier="available"))
        self._assert_terra_then_implement(steps)

    def test_active_connector_reserve_terra_continues(self):
        self._assert_terra_then_implement(self._impl("google-search-console"))

    def test_active_connector_spent_terra_parks(self):
        steps = self._impl("google-search-console", rows=self._rows(terra_tier="spent"))
        self._assert_parked_no_continue(steps)
        self.assertTrue(any("no currently usable seat" in (s.get("why") or "") for s in steps), steps)

    def test_active_connector_missing_terra_parks(self):
        provs = providers()
        del provs["providers"]["codex-terra"]
        steps = self._impl("google-search-console", provs=provs)
        self._assert_parked_no_continue(steps)
        self.assertTrue(any("missing" in (s.get("why") or "") for s in steps), steps)

    def test_active_connector_invalid_terra_route_parks(self):
        registry = copy.deepcopy(live())
        registry["routes"]["gpt-5.6-terra-codex"]["route_state"] = "catalog_verified"
        self.assertFalse(mr.route_is_live(registry, "gpt-5.6-terra-codex", as_of=date(2026, 8, 28)))
        steps = self._impl("google-search-console", registry=registry)
        self._assert_parked_no_continue(steps)
        self.assertTrue(any("no valid live route" in (s.get("why") or "") for s in steps), steps)

    def test_active_connector_wrong_terra_route_parks(self):
        provs = providers()
        provs["providers"]["codex-terra"]["route"] = "grok-4.6-build"
        steps = self._impl("google-search-console", provs=provs)
        self._assert_parked_no_continue(steps)
        self.assertTrue(any("wrong-route" in (s.get("why") or "") for s in steps), steps)

    def test_active_connector_no_terra_seat_parks(self):
        rows = [r for r in self._rows() if r["subscription"] != "codex-200"]
        steps = self._impl("google-search-console", rows=rows)
        self._assert_parked_no_continue(steps)
        self.assertTrue(any("no currently usable seat" in (s.get("why") or "") for s in steps), steps)

    def test_primed(self):
        self._assert_parked_no_continue(self._impl("mb-bundled-example"))

    def test_unknown(self):
        self._assert_parked_no_continue(self._impl("no-such-connector"))

    def test_wrong_seat(self):
        self._assert_parked_no_continue(self._impl("gsc-indexing"))

    def test_primed_active_id_parks(self):
        conns = connectors()
        conns["mcp_connectors"]["google-search-console"]["status"] = "primed"
        self._assert_parked_no_continue(self._impl("google-search-console", conns=conns))

    def test_missing_status_parks(self):
        conns = connectors()
        del conns["mcp_connectors"]["google-search-console"]["status"]
        self._assert_parked_no_continue(self._impl("google-search-console", conns=conns))

    def test_failed_connector_does_not_continue_even_if_terra_available(self):
        for label in ("mb-bundled-example", "no-such-connector", "gsc-indexing"):
            with self.subTest(label=label):
                self._assert_parked_no_continue(self._impl(label))

    def test_primed_alias_colliding_with_coarse_parks(self):
        conns = connectors()
        conns["mcp_connectors"]["mb-bundled-example"]["alias"] = "browser"
        self._assert_parked_no_continue(self._impl("browser", conns=conns))

    def test_live_terra_declares_mcp_bulk_conjunction(self):
        terra = providers()["providers"]["codex-terra"]
        self.assertTrue(rr.provider_can_mcp_bulk(terra, live()))
        self.assertEqual(mr.mcp_bulk_layer_flags(terra, live()), (True, True, True))


class McpBulkConjunctionTests(unittest.TestCase):
    """mcp_bulk must be present on functions, provider capabilities, and bound live-route."""

    LAYERS = (
        ("functions", ("functions",)),
        ("capabilities", ("capabilities",)),
        ("route", ("route",)),
        ("all", ("functions", "capabilities", "route")),
    )

    def _without(self, layers):
        provs = providers()
        registry = copy.deepcopy(live())
        terra = provs["providers"]["codex-terra"]
        if "functions" in layers:
            terra["functions"] = [x for x in terra["functions"] if x != "mcp_bulk"]
        if "capabilities" in layers:
            terra["capabilities"] = [x for x in terra["capabilities"] if x != "mcp_bulk"]
        if "route" in layers:
            rid = terra["route"]
            registry["routes"][rid]["capabilities"] = [
                x for x in registry["routes"][rid]["capabilities"] if x != "mcp_bulk"
            ]
        return provs, registry

    def _impl(self, provs, registry):
        rows = [
            {"seat": "grok-heavy", "subscription": "grok-heavy", "tier": "available",
             "billing": "included", "intake": False, "window_kinds": ["weekly"],
             "runway_seconds": 864000, "family": "xai"},
            {"seat": "codex-plan", "subscription": "codex-200", "tier": "reserve",
             "billing": "included", "intake": True, "window_kinds": ["weekly"],
             "runway_seconds": 864000, "family": "openai"},
        ]
        return rr.pick_implement(
            provs, connectors(), rows, "repo-code", "", "google-search-console",
            False, 0, registry,
        )

    def test_missing_each_layer_and_all_parks_without_terra_or_implement(self):
        for name, layers in self.LAYERS:
            with self.subTest(missing=name):
                provs, registry = self._without(layers)
                terra = provs["providers"]["codex-terra"]
                self.assertFalse(rr.provider_can_mcp_bulk(terra, registry), name)
                self.assertFalse(all(mr.mcp_bulk_layer_flags(terra, registry)), name)
                steps = self._impl(provs, registry)
                self.assertTrue(
                    any(not s.get("available") and "PARK" in (s.get("why") or "")
                        and "mcp_bulk" in (s.get("why") or "") for s in steps),
                    steps,
                )
                self.assertFalse(
                    any(s.get("seat") == "codex-terra" and s.get("available") for s in steps),
                    steps,
                )
                self.assertFalse(any(s.get("seat") == "grok-build" for s in steps), steps)
                self.assertFalse(any(s.get("available") for s in steps), steps)

    def test_validate_rejects_inconsistent_mcp_assignment(self):
        for name, layers in self.LAYERS:
            with self.subTest(missing=name):
                provs, registry = self._without(layers)
                errors = mr.validate(
                    registry, as_of=date(2026, 8, 28),
                    providers=provs, connectors=connectors(),
                )
                blob = "\n".join(errors)
                self.assertTrue(
                    any("codex-terra" in e and "mcp_bulk" in e and "inconsistent" in e
                        for e in errors),
                    blob,
                )

    def test_live_catalog_still_validates_with_connectors(self):
        errors = mr.validate(
            live(), as_of=date(2026, 8, 28),
            providers=providers(), connectors=connectors(),
        )
        self.assertEqual(errors, [])
        terra = providers()["providers"]["codex-terra"]
        self.assertTrue(rr.provider_can_mcp_bulk(terra, live()))


class DuplicateInvocationTests(unittest.TestCase):
    def test_cloned_teamclaude_opus5_under_openai_fails_closed(self):
        data = copy.deepcopy(live())
        spoof = copy.deepcopy(data["routes"]["opus-5-teamclaude"])
        spoof["model"] = "gpt-5.6-sol"
        spoof["provider"] = "codex-sol"
        data["routes"]["spoof-openai-opus"] = spoof
        errors = mr.validate(data, as_of=date(2026, 8, 28), providers=providers())
        blob = "\n".join(errors)
        self.assertTrue(
            "duplicate invocation" in blob or "official id of family" in blob,
            blob,
        )
        self.assertIn("teamclaude/claude-cli/claude-opus-5", blob)
        self.assertFalse(mr.route_is_live(data, "spoof-openai-opus", as_of=date(2026, 8, 28)))
        data["rankings"]["code_review"]["selection"] = [
            {"priority": 1, "route": "opus-5-teamclaude", "confidence": "high", "rationale": "real"},
            {"priority": 2, "route": "spoof-openai-opus", "confidence": "high", "rationale": "spoof"},
            {"priority": 3, "route": "gpt-5.6-sol-codex", "confidence": "high", "rationale": "sol"},
        ]
        decision = mr.resolve(
            data, "code_review", family_diversity=2, exclude_routes=["gpt-5.6-sol-codex"],
        )
        self.assertFalse(decision["ok"])
        self.assertIn("fail-closed", decision["reason"])
        self.assertNotIn("spoof-openai-opus", [r["route"] for r in decision["routes"]])
        families = [r["family"] for r in decision["routes"]]
        self.assertNotEqual(set(families), {"anthropic", "openai"})


class RouteLocalIdentityTests(unittest.TestCase):
    """Public resolve() and route_is_live share the route-local identity predicate."""

    def test_sol_invocation_spoofing_opus_is_not_live_or_resolvable(self):
        """Exact regression: Sol invocation_id = claude-opus-5 fails validate, live, and resolve."""
        data = copy.deepcopy(live())
        data["routes"]["gpt-5.6-sol-codex"]["invocation_id"] = "claude-opus-5"
        errors = mr.validate(data, as_of=date(2026, 8, 28), providers=providers())
        self.assertTrue(
            any("gpt-5.6-sol-codex" in e and "official id of family" in e for e in errors),
            errors,
        )
        self.assertFalse(mr.route_is_live(data, "gpt-5.6-sol-codex", as_of=date(2026, 8, 28)))
        decision = mr.resolve(data, "code_review", n=3, as_of=date(2026, 8, 28))
        ids = [r["route"] for r in decision["routes"]]
        self.assertNotIn("gpt-5.6-sol-codex", ids)
        direct = mr.resolve(data, "code_review", as_of=date(2026, 8, 28))
        self.assertNotIn("gpt-5.6-sol-codex", [r["route"] for r in direct["routes"]])
        if direct["ok"]:
            self.assertEqual(direct["routes"][0]["route"], "opus-5-teamclaude")

    def test_authority_keys_on_route_are_not_live(self):
        data = copy.deepcopy(live())
        data["routes"]["gpt-5.6-sol-codex"]["write_access"] = True
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(any("must not grant" in e and "gpt-5.6-sol-codex" in e for e in errors), errors)
        self.assertFalse(mr.route_is_live(data, "gpt-5.6-sol-codex", as_of=date(2026, 8, 28)))
        decision = mr.resolve(data, "code_review", as_of=date(2026, 8, 28))
        self.assertNotIn("gpt-5.6-sol-codex", [r["route"] for r in decision["routes"]])


class FamilyIndependenceLiveTests(unittest.TestCase):
    """Undeclared family/independence group fails route_is_live and cannot pair in resolve()."""

    OTHER_FAMILIES = [
        "openai", "xai", "google", "moonshot", "zhipu", "alibaba", "deepseek", "meta", "open-weight",
    ]

    def _resolve_pair(self, data):
        return mr.resolve(
            data, "code_review", family_diversity=2, as_of=date(2026, 8, 28),
            exclude_families=self.OTHER_FAMILIES,
        )

    def _assert_not_live_or_paired(self, data, route_id="opus-4.8-teamclaude", spoof_family=None):
        self.assertFalse(mr.route_is_live(data, route_id, as_of=date(2026, 8, 28)), route_id)
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(any(route_id in e for e in errors), errors)
        decision = mr.resolve(data, "code_review", family_diversity=2, as_of=date(2026, 8, 28))
        ids = [r["route"] for r in decision["routes"]]
        self.assertNotIn(route_id, ids)
        if spoof_family:
            self.assertNotIn(spoof_family, [r["family"] for r in decision["routes"]])
        isolated = self._resolve_pair(data)
        self.assertFalse(isolated["ok"], isolated)
        self.assertNotIn(route_id, [r["route"] for r in isolated["routes"]])

    def test_undeclared_spoof_family_does_not_pair_with_opus5(self):
        """Exact regression: mutate Opus 4.8 family to undeclared-spoof; resolve must not pair it with Opus 5."""
        data = copy.deepcopy(live())
        data["models"]["claude-opus-4-8"]["family"] = "undeclared-spoof"
        self.assertEqual(mr.independence_group_of(data, "undeclared-spoof"), "")
        self._assert_not_live_or_paired(data, spoof_family="undeclared-spoof")
        isolated = self._resolve_pair(data)
        self.assertIn("fail-closed", isolated["reason"])
        self.assertNotEqual(
            set(r["family"] for r in isolated["routes"]),
            {"anthropic", "undeclared-spoof"},
        )

    def test_missing_family_is_not_live(self):
        data = copy.deepcopy(live())
        del data["models"]["claude-opus-4-8"]["family"]
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(
            any("opus-4.8-teamclaude" in e and "has no family" in e for e in errors),
            errors,
        )
        self._assert_not_live_or_paired(data)

    def test_unknown_family_is_not_live(self):
        data = copy.deepcopy(live())
        data["models"]["claude-opus-4-8"]["family"] = "not-a-family"
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(
            any("opus-4.8-teamclaude" in e and "is not declared" in e for e in errors),
            errors,
        )
        self._assert_not_live_or_paired(data, spoof_family="not-a-family")

    def test_missing_independence_group_is_not_live(self):
        data = copy.deepcopy(live())
        data["families"]["anthropic"] = {
            "label": "Anthropic (Claude)",
            "independence_group": "",
        }
        self.assertEqual(mr.independence_group_of(data, "anthropic"), "")
        self.assertFalse(mr.route_is_live(data, "opus-5-teamclaude", as_of=date(2026, 8, 28)))
        self.assertFalse(mr.route_is_live(data, "opus-4.8-teamclaude", as_of=date(2026, 8, 28)))
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(any("independence_group" in e for e in errors), errors)
        decision = mr.resolve(data, "code_review", family_diversity=2, as_of=date(2026, 8, 28))
        self.assertNotIn("opus-5-teamclaude", [r["route"] for r in decision["routes"]])
        self.assertNotIn("opus-4.8-teamclaude", [r["route"] for r in decision["routes"]])

    def test_conflicting_route_family_is_not_live(self):
        data = copy.deepcopy(live())
        data["routes"]["opus-4.8-teamclaude"]["family"] = "openai"
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(
            any("opus-4.8-teamclaude" in e and "does not match model" in e for e in errors),
            errors,
        )
        self._assert_not_live_or_paired(data)

    def test_conflicting_route_model_identity_is_not_live(self):
        data = copy.deepcopy(live())
        data["routes"]["opus-4.8-teamclaude"]["model"] = "gpt-5.6-sol"
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(
            any("opus-4.8-teamclaude" in e and "official id of family" in e for e in errors),
            errors,
        )
        self.assertFalse(mr.route_is_live(data, "opus-4.8-teamclaude", as_of=date(2026, 8, 28)))
        decision = mr.resolve(data, "code_review", family_diversity=2, as_of=date(2026, 8, 28))
        self.assertNotIn("opus-4.8-teamclaude", [r["route"] for r in decision["routes"]])

    def test_family_matrix_adjacent_states(self):
        cases = [
            ("missing_family", lambda d: d["models"]["claude-opus-4-8"].pop("family", None)),
            ("unknown_family", lambda d: d["models"]["claude-opus-4-8"].__setitem__("family", "ghost")),
            ("missing_group", lambda d: d["families"]["anthropic"].pop("independence_group", None)),
            ("empty_group", lambda d: d["families"]["anthropic"].__setitem__("independence_group", "")),
            ("route_family_conflict", lambda d: d["routes"]["opus-4.8-teamclaude"].__setitem__("family", "xai")),
            ("route_model_conflict", lambda d: d["routes"]["opus-4.8-teamclaude"].__setitem__("model", "gpt-5.6-sol")),
        ]
        for name, mutate in cases:
            with self.subTest(name=name):
                data = copy.deepcopy(live())
                mutate(data)
                self.assertFalse(
                    mr.route_is_live(data, "opus-4.8-teamclaude", as_of=date(2026, 8, 28)),
                    name,
                )
                decision = mr.resolve(data, "code_review", family_diversity=2, as_of=date(2026, 8, 28))
                self.assertNotIn("opus-4.8-teamclaude", [r["route"] for r in decision["routes"]], name)


class LiveEvidenceTests(unittest.TestCase):
    def test_empty_evidence_fails(self):
        data = copy.deepcopy(live())
        data["routes"]["opus-5-teamclaude"]["evidence"] = []
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(any("non-empty" in e for e in errors))
        self.assertFalse(mr.route_is_live(data, "opus-5-teamclaude", as_of=date(2026, 8, 28)))

    def test_future_evidence_fails(self):
        data = copy.deepcopy(live())
        data["routes"]["opus-5-teamclaude"]["evidence_date"] = "2099-01-01"
        data["routes"]["opus-5-teamclaude"]["evidence"] = [
            {"date": "2099-01-01", "route_state": "live_verified", "signal": "direct_invocation",
             "kind": "local_smoke", "source": "future"},
        ]
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(any("future" in e for e in errors))

    def test_missing_attestations_fail(self):
        data = copy.deepcopy(live())
        del data["routes"]["opus-5-teamclaude"]["attestations"]
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(any("attestations" in e for e in errors))

    def test_missing_signal_fails(self):
        data = copy.deepcopy(live())
        for rec in data["routes"]["opus-5-teamclaude"]["evidence"]:
            rec.pop("signal", None)
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(any("signal" in e for e in errors))

    def test_default_as_of_is_today_not_registry_as_of(self):
        data = copy.deepcopy(live())
        data["as_of"] = "2020-01-01"
        errors = mr.validate(data, providers=providers())
        self.assertFalse(any("stale" in e or "future" in e for e in errors), errors)

    def test_as_of_override_freezes_clock(self):
        data = copy.deepcopy(live())
        errors = mr.validate(data, as_of=date(2026, 8, 28), providers=providers())
        self.assertEqual(errors, [])
        errors_fresh = mr.validate(data, as_of=date(2026, 9, 1), providers=providers())
        self.assertEqual(errors_fresh, [])
        errors_stale = mr.validate(data, as_of=date(2026, 12, 1), providers=providers())
        self.assertTrue(any("stale" in e for e in errors_stale))

    def test_live_routes_distinguish_standing_from_direct(self):
        registry = live()
        opus = registry["routes"]["opus-5-teamclaude"]
        self.assertEqual(opus["attestations"]["local_access_smoke"]["signal"], "direct_invocation")
        sol = registry["routes"]["gpt-5.6-sol-codex"]
        self.assertEqual(sol["attestations"]["local_access_smoke"]["signal"], "standing_provider")
        grok = registry["routes"]["grok-4.6-build"]
        self.assertEqual(grok["attestations"]["local_access_smoke"]["signal"], "standing_provider")
        cursor = registry["routes"]["grok-4.6-cursor"]
        self.assertEqual(cursor["evidence_strength"], "owner_eval")
        self.assertEqual(cursor["attestations"]["local_access_smoke"]["signal"], "standing_provider")


class ResolverLivePredicateTests(unittest.TestCase):
    """Public resolve() filters with route_is_live; it does not depend on CLI assert_valid."""

    def test_deleted_opus5_evidence_cannot_resolve_code_review(self):
        data = copy.deepcopy(live())
        del data["routes"]["opus-5-teamclaude"]["evidence"]
        self.assertFalse(mr.route_is_live(data, "opus-5-teamclaude", as_of=date(2026, 8, 28)))
        decision = mr.resolve(data, "code_review", n=3, as_of=date(2026, 8, 28))
        ids = [r["route"] for r in decision["routes"]]
        self.assertNotIn("opus-5-teamclaude", ids)
        self.assertIn("gpt-5.6-sol-codex", ids)

    def test_empty_evidence_does_not_resolve(self):
        data = copy.deepcopy(live())
        data["routes"]["opus-5-teamclaude"]["evidence"] = []
        decision = mr.resolve(data, "code_review", as_of=date(2026, 8, 28))
        self.assertNotIn("opus-5-teamclaude", [r["route"] for r in decision["routes"]])

    def test_stale_evidence_does_not_resolve(self):
        data = copy.deepcopy(live())
        data["routes"]["opus-5-teamclaude"]["evidence_date"] = "2024-01-01"
        data["routes"]["opus-5-teamclaude"]["evidence"] = [
            {"date": "2024-01-01", "route_state": "live_verified", "signal": "direct_invocation",
             "kind": "local_smoke", "source": "stale"},
        ]
        self.assertFalse(mr.route_is_live(data, "opus-5-teamclaude", as_of=date(2026, 8, 28)))
        decision = mr.resolve(data, "code_review", as_of=date(2026, 8, 28))
        self.assertNotIn("opus-5-teamclaude", [r["route"] for r in decision["routes"]])

    def test_future_evidence_does_not_resolve(self):
        data = copy.deepcopy(live())
        data["routes"]["opus-5-teamclaude"]["evidence_date"] = "2099-01-01"
        data["routes"]["opus-5-teamclaude"]["evidence"] = [
            {"date": "2099-01-01", "route_state": "live_verified", "signal": "direct_invocation",
             "kind": "local_smoke", "source": "future"},
        ]
        self.assertFalse(mr.route_is_live(data, "opus-5-teamclaude", as_of=date(2026, 8, 28)))
        decision = mr.resolve(data, "code_review", as_of=date(2026, 8, 28))
        self.assertNotIn("opus-5-teamclaude", [r["route"] for r in decision["routes"]])

    def test_unattested_does_not_resolve(self):
        data = copy.deepcopy(live())
        data["routes"]["opus-5-teamclaude"]["attestations"]["local_access_smoke"]["state"] = "missing"
        self.assertFalse(mr.route_is_live(data, "opus-5-teamclaude", as_of=date(2026, 8, 28)))
        decision = mr.resolve(data, "code_review", as_of=date(2026, 8, 28))
        self.assertNotIn("opus-5-teamclaude", [r["route"] for r in decision["routes"]])

    def test_mismatched_latest_evidence_does_not_resolve(self):
        data = copy.deepcopy(live())
        data["routes"]["opus-5-teamclaude"]["evidence"] = [
            {"date": "2026-08-01", "route_state": "live_verified", "signal": "direct_invocation"},
            {"date": "2026-08-28", "route_state": "unwired", "signal": "direct_invocation"},
        ]
        self.assertFalse(mr.route_is_live(data, "opus-5-teamclaude", as_of=date(2026, 8, 28)))
        decision = mr.resolve(data, "code_review", as_of=date(2026, 8, 28))
        self.assertNotIn("opus-5-teamclaude", [r["route"] for r in decision["routes"]])

    def test_missing_attestations_do_not_resolve(self):
        data = copy.deepcopy(live())
        del data["routes"]["opus-5-teamclaude"]["attestations"]
        self.assertFalse(mr.route_is_live(data, "opus-5-teamclaude", as_of=date(2026, 8, 28)))
        decision = mr.resolve(data, "code_review", as_of=date(2026, 8, 28))
        self.assertNotIn("opus-5-teamclaude", [r["route"] for r in decision["routes"]])

    def test_stale_as_of_fails_closed_without_assert_valid(self):
        decision = mr.resolve(live(), "code_review", as_of=date(2026, 12, 1))
        self.assertFalse(decision["ok"])
        self.assertEqual(decision["routes"], [])
        self.assertIn("fail-closed", decision["reason"])


class RequiredToolsVsCapabilitiesTests(unittest.TestCase):
    def test_required_tools_do_not_match_capabilities(self):
        data = copy.deepcopy(live())
        route = data["routes"]["opus-5-teamclaude"]
        route["tools"] = []
        route["capabilities"] = ["review"]
        decision = mr.resolve(data, "code_review", required_tools=["review"])
        self.assertFalse(decision["ok"])
        self.assertFalse(decision["authority_grants"])
        by_cap = mr.resolve(data, "code_review", required_capabilities=["review"])
        self.assertTrue(by_cap["ok"])
        self.assertEqual(by_cap["routes"][0]["route"], "opus-5-teamclaude")
        self.assertFalse(by_cap["authority_grants"])


class TypedAttestationTests(unittest.TestCase):
    def test_live_routes_use_typed_state_not_boolean(self):
        registry = live()
        required = registry["intake"]["promote_requires"]
        live_ids = [
            rid for rid, route in registry["routes"].items()
            if route.get("route_state") == "live_verified"
        ]
        self.assertGreaterEqual(len(live_ids), 10)
        for rid in live_ids:
            atts = registry["routes"][rid]["attestations"]
            for key in required:
                rec = atts[key]
                self.assertIn(rec["state"], mr.ATTESTATION_STATES, f"{rid}.{key}")
                self.assertNotIn("attested", rec)
                if rec["state"] == "attested":
                    src = f"{rec.get('source','')} {rec.get('rationale','')}"
                    self.assertFalse(mr._absence_markers_in(src), f"{rid}.{key} {src}")
                    self.assertIn(rec.get("evidence_kind"), mr.ATTESTED_EVIDENCE_KINDS[key], f"{rid}.{key}")
                if rec["state"] == "not_applicable":
                    self.assertIn(rec.get("structural_code"), mr.STRUCTURAL_CODES, f"{rid}.{key}")
                    self.assertTrue(
                        mr._structural_code_allowed(
                            rid, registry["routes"][rid]["model"], key, rec["structural_code"],
                        ),
                        f"{rid}.{key}",
                    )
                if rec["state"] == "waived":
                    self.assertEqual(rec["authority"], "existing_operational_state")
                    self.assertTrue(rec.get("expires"))
                    self.assertTrue(rec.get("rationale"))
                    self.assertNotIn("owner catalog promotion", (rec.get("source") or "").lower())
                    self.assertIn(rid, mr.LEGACY_WAIVER_ROUTES)

    def test_semantic_contradiction_cannot_be_attested(self):
        data = copy.deepcopy(live())
        rec = data["routes"]["opus-5-teamclaude"]["attestations"]["role_evals"]
        rec["state"] = "attested"
        rec["evidence_kind"] = "normalized_receipt"
        rec["source"] = "compatibility smoke only; evaluation suite absent"
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(any("absence" in e and "role_evals" in e for e in errors), errors)
        self.assertFalse(mr.route_is_live(data, "opus-5-teamclaude", as_of=date(2026, 8, 28)))

    def test_compatibility_smoke_only_cannot_attest_role_evals(self):
        data = copy.deepcopy(live())
        rec = data["routes"]["opus-4.8-teamclaude"]["attestations"]["role_evals"]
        rec["state"] = "attested"
        rec["evidence_kind"] = "normalized_receipt"
        rec["source"] = "compatibility smoke only; evaluation suite absent"
        rec.pop("structural_code", None)
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        blob = "\n".join(errors)
        self.assertTrue("role_evals" in blob and ("absence" in blob or "normalized_receipt" in blob or "receipt" in blob), errors)
        self.assertFalse(mr.route_is_live(data, "opus-4.8-teamclaude", as_of=date(2026, 8, 28)))

    def test_not_applicable_missing_eval_without_structural_code_fails(self):
        data = copy.deepcopy(live())
        rec = data["routes"]["opus-5-teamclaude"]["attestations"]["role_evals"]
        rec["state"] = "not_applicable"
        rec.pop("evidence_kind", None)
        rec.pop("structural_code", None)
        rec["rationale"] = "required evaluation is missing"
        rec["source"] = "none"
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        blob = "\n".join(errors)
        self.assertTrue(any("structural_code" in e and "role_evals" in e for e in errors), errors)
        self.assertIn("missing", blob)
        self.assertFalse(mr.route_is_live(data, "opus-5-teamclaude", as_of=date(2026, 8, 28)))

    def test_mutable_compatibility_flag_cannot_authorize_structural_na(self):
        data = copy.deepcopy(live())
        route = data["routes"]["opus-5-teamclaude"]
        route["compatibility_fallback"] = True
        route["fallback_until"] = "2026-12-31"
        rec = route["attestations"]["role_evals"]
        rec.clear()
        rec.update({
            "state": "not_applicable",
            "date": "2026-08-28",
            "source": "mutated route compatibility flag",
            "rationale": "Structurally a time-bounded compatibility fallback, not ranked.",
            "structural_code": "compatibility_fallback_not_ranked",
        })
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(any("structural_code" in e and "opus-5-teamclaude" in e for e in errors), errors)
        self.assertFalse(mr.route_is_live(data, "opus-5-teamclaude", as_of=date(2026, 8, 28)))

    def test_markdown_file_cannot_attest_owner_approval(self):
        data = copy.deepcopy(live())
        rec = data["routes"]["opus-5-teamclaude"]["attestations"]["owner_approval"]
        rec.clear()
        rec.update({
            "state": "attested",
            "date": "2026-08-28",
            "source": "README.md",
            "evidence_kind": "committed_owner_record",
        })
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(any("structured owner-record manifest" in e for e in errors), errors)
        self.assertFalse(mr.route_is_live(data, "opus-5-teamclaude", as_of=date(2026, 8, 28)))

    def test_attested_missing_source_or_date_fails(self):
        data = copy.deepcopy(live())
        rec = data["routes"]["opus-5-teamclaude"]["attestations"]["independent_evidence"]
        rec.pop("source", None)
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(any("independent_evidence" in e and "source" in e for e in errors), errors)
        rec["source"] = "https://artificialanalysis.ai/models/claude-opus-5"
        rec.pop("date", None)
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(any("independent_evidence" in e and "date" in e for e in errors), errors)

    def test_waiver_missing_source_date_or_expiry_fails(self):
        data = copy.deepcopy(live())
        rec = data["routes"]["gpt-5.6-sol-codex"]["attestations"]["role_evals"]
        self.assertEqual(rec["state"], "waived")
        rec.pop("expires", None)
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(any("role_evals" in e and "expiry" in e for e in errors), errors)
        rec["expires"] = "2026-11-26"
        rec.pop("date", None)
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(any("role_evals" in e and "date" in e for e in errors), errors)
        rec["date"] = "2026-08-28"
        rec.pop("source", None)
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(any("role_evals" in e and "source" in e for e in errors), errors)

    def test_expired_waiver_fails_closed(self):
        data = copy.deepcopy(live())
        rec = data["routes"]["gpt-5.6-sol-codex"]["attestations"]["role_evals"]
        rec["expires"] = "2026-08-01"
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(any("waiver expired" in e for e in errors), errors)
        self.assertFalse(mr.route_is_live(data, "gpt-5.6-sol-codex", as_of=date(2026, 8, 28)))

    def test_waiver_on_new_unwired_candidate_fails(self):
        data = copy.deepcopy(live())
        route = data["routes"]["kimi-k3-unwired"]
        route["route_state"] = "live_verified"
        route["host"] = "none"
        route["attestations"] = copy.deepcopy(data["routes"]["gpt-5.6-sol-codex"]["attestations"])
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(
            any("waiver forbidden" in e and "legacy_waiver_routes" in e for e in errors),
            errors,
        )
        self.assertFalse(mr.route_is_live(data, "kimi-k3-unwired", as_of=date(2026, 8, 28)))

    def test_kimi_cannot_self_qualify_legacy_waiver_by_mutation(self):
        data = copy.deepcopy(live())
        self.assertNotIn("kimi-k3-unwired", data["intake"]["legacy_waiver_routes"])
        self.assertNotIn("kimi-k3-unwired", mr.LEGACY_WAIVER_ROUTES)
        route = data["routes"]["kimi-k3-unwired"]
        template = data["routes"]["gpt-5.6-sol-codex"]
        route["route_state"] = "live_verified"
        route["host"] = "codex"
        route["harness"] = "gpt-wrapper"
        route["provider"] = "codex-sol"
        route["evidence_strength"] = "local_smoke"
        route["data_boundary"] = "subscription"
        route["evidence"] = [
            {
                "date": "2026-08-28",
                "route_state": "live_verified",
                "kind": "local_smoke",
                "source": "mutated to look live",
                "signal": "direct_invocation",
            }
        ]
        waived = copy.deepcopy(template["attestations"])
        for rec in waived.values():
            rec["state"] = "waived"
            rec["authority"] = "existing_operational_state"
            rec["date"] = "2026-08-28"
            rec["expires"] = "2026-11-26"
            rec["source"] = "config/providers.json mutated standing provider"
            rec["rationale"] = "Looks live after mutation; still not a grandfathered route id."
            rec.pop("evidence_kind", None)
            rec.pop("signal", None)
            rec.pop("structural_code", None)
        route["attestations"] = waived
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(
            any("waiver forbidden" in e and "legacy_waiver_routes" in e for e in errors),
            errors,
        )
        self.assertFalse(mr.route_is_live(data, "kimi-k3-unwired", as_of=date(2026, 8, 28)))

    def test_allowlisted_route_id_cannot_be_repointed_to_kimi(self):
        data = copy.deepcopy(live())
        route = data["routes"]["opus-4.8-teamclaude"]
        route["model"] = "kimi-k3"
        route["provider"] = None
        route["host"] = "moonshot-api"
        route["harness"] = "http"
        route["invocation_id"] = "kimi-k3"
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(
            any("waiver forbidden" in e and "frozen migration identity" in e for e in errors),
            errors,
        )
        self.assertFalse(mr.route_is_live(data, "opus-4.8-teamclaude", as_of=date(2026, 8, 28)))
        data["intake"]["legacy_waiver_routes"] = list(data["intake"]["legacy_waiver_routes"]) + [
            "kimi-k3-unwired"
        ]
        errors_added = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(
            any("legacy_waiver_routes must equal the frozen migration" in e for e in errors_added),
            errors_added,
        )
        self.assertFalse(mr.route_is_live(data, "kimi-k3-unwired", as_of=date(2026, 8, 28)))

    def test_local_json_path_is_not_official_id_attestation(self):
        data = copy.deepcopy(live())
        rec = data["routes"]["opus-5-teamclaude"]["attestations"]["official_id"]
        rec["source"] = "models.claude-opus-5.official_ids"
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(any("official https" in e for e in errors), errors)

    def test_boolean_attested_is_rejected(self):
        data = copy.deepcopy(live())
        rec = data["routes"]["opus-5-teamclaude"]["attestations"]["cost_context"]
        rec.pop("state", None)
        rec["attested"] = True
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(any("boolean attested" in e or "typed state" in e for e in errors), errors)


class QualityBasisTests(unittest.TestCase):
    def test_every_quality_row_has_basis(self):
        registry = live()
        for role, rnk in registry["rankings"].items():
            for i, row in enumerate(rnk.get("quality") or []):
                self.assertIn(row.get("basis"), mr.QUALITY_BASES, f"{role}[{i}]")
                if row["basis"] == "local_same_harness":
                    self.assertEqual(role, "architecture_spec_critique")
                    self.assertIn(row["route"], mr.LOCAL_SAME_HARNESS_ROUTES)

    def test_non_architecture_quality_is_not_local_same_harness(self):
        registry = live()
        for role, rnk in registry["rankings"].items():
            if role == "architecture_spec_critique":
                continue
            for row in rnk.get("quality") or []:
                self.assertNotEqual(row.get("basis"), "local_same_harness", role)

    def test_local_same_harness_on_other_role_fails(self):
        data = copy.deepcopy(live())
        data["rankings"]["code_review"]["quality"][0]["basis"] = "local_same_harness"
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(any("local_same_harness is only" in e for e in errors), errors)

    def test_missing_basis_fails(self):
        data = copy.deepcopy(live())
        data["rankings"]["dispatch"]["quality"][0].pop("basis", None)
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(any("basis must be" in e for e in errors), errors)

    def test_non_local_quality_confidence_is_not_high(self):
        registry = live()
        for role, rnk in registry["rankings"].items():
            for row in rnk.get("quality") or []:
                self.assertTrue(row.get("source"), f"{role} {row['route']}")
                if row.get("basis") != "local_same_harness":
                    self.assertNotEqual(row.get("confidence"), "high", f"{role} {row['route']}")

    def test_high_confidence_requires_local_same_harness_receipt(self):
        data = copy.deepcopy(live())
        row = data["rankings"]["architecture_spec_critique"]["quality"][0]
        row.pop("source", None)
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(
            any("local_same_harness" in e and "receipt" in e for e in errors),
            errors,
        )

    def test_high_independent_external_prior_without_source_fails(self):
        data = copy.deepcopy(live())
        row = data["rankings"]["code_review"]["quality"][0]
        self.assertEqual(row["basis"], "independent_external_prior")
        row["confidence"] = "high"
        row.pop("source", None)
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        blob = "\n".join(errors)
        self.assertTrue(any("confidence high is only allowed" in e for e in errors), errors)
        self.assertTrue(any("evidence/source pointer" in e for e in errors), errors)
        self.assertIn("independent_external_prior", blob)
        row["source"] = "https://artificialanalysis.ai/models/claude-opus-5"
        errors_with_source = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(
            any("confidence high is only allowed" in e for e in errors_with_source),
            errors_with_source,
        )


class OfficialSourceAndPlaceholderTests(unittest.TestCase):
    def test_every_census_model_has_official_https_source(self):
        registry = live()
        labs = registry["census"]["labs_in_scope"]
        for lab in mr.REQUIRED_CENSUS_LABS:
            self.assertIn(lab, labs)
        self.assertFalse(any("review e" in str(x).lower() or "open-weight" in str(x).lower() for x in labs))
        for mid, model in registry["models"].items():
            if mr._model_is_placeholder(model):
                self.assertEqual(mr.official_urls_for_model(registry, mid, model), [])
                continue
            urls = mr.official_urls_for_model(registry, mid, model)
            self.assertTrue(urls, mid)
            self.assertTrue(all(u.startswith("https://") for u in urls), mid)
            family = model.get("family")
            for url in urls:
                self.assertTrue(mr._url_allowed_for_family(registry, family, url), (mid, url))
        domains = registry["official_sources"]["allowed_domains_by_family"]
        self.assertIn("openai.com", domains["openai"])
        self.assertIn("anthropic.com", domains["anthropic"])
        self.assertTrue(any(d.endswith("claude.com") or d == "claude.com" for d in domains["anthropic"]))
        self.assertIn("x.ai", domains["xai"])
        self.assertIn("ai.google.dev", domains["google"])
        self.assertTrue("kimi.ai" in domains["moonshot"] or "moonshot.ai" in domains["moonshot"])
        self.assertIn("z.ai", domains["zhipu"])
        self.assertTrue("alibabacloud.com" in domains["alibaba"] or "alibabagroup.com" in domains["alibaba"])
        self.assertTrue(any("deepseek.com" in d for d in domains["deepseek"]))
        self.assertTrue("ai.meta.com" in domains["meta"] or "meta.com" in domains["meta"])
        self.assertEqual(sorted(registry["intake"]["legacy_waiver_routes"]), sorted(mr.LEGACY_WAIVER_ROUTES))

    def test_review_e_is_local_placeholder_outside_census(self):
        registry = live()
        model = registry["models"]["open-weight-review-e"]
        self.assertTrue(mr._model_is_placeholder(model))
        self.assertIn("open-weight-review-e", registry["census"]["placeholder_model_ids"])
        self.assertEqual(registry["routes"]["review-e-fireworks"]["route_state"], "unwired")
        self.assertFalse(mr.route_is_live(registry, "review-e-fireworks", as_of=date(2026, 8, 28)))

    def test_official_domain_poisoning_is_rejected(self):
        data = copy.deepcopy(live())
        data["models"]["claude-opus-5"]["official_sources"] = ["https://example.com/claude-opus-5"]
        data["official_sources"]["by_family"]["anthropic"]["urls"] = ["https://example.com/claude-opus-5"]
        data["routes"]["opus-5-teamclaude"]["attestations"]["official_id"]["source"] = (
            "https://example.com/claude-opus-5"
        )
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        blob = "\n".join(errors)
        self.assertIn("example.com", blob)
        self.assertTrue(any("allowed official domain" in e for e in errors), errors)
        data = copy.deepcopy(live())
        data["routes"]["opus-5-teamclaude"]["attestations"]["official_id"]["source"] = (
            "https://openai.com/index/gpt-5-6/"
        )
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(
            any("not an allowed official domain for family 'anthropic'" in e for e in errors),
            errors,
        )
        data = copy.deepcopy(live())
        data["models"]["kimi-k3"]["official_sources"] = ["https://www.anthropic.com/news/claude-opus-5"]
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(
            any("kimi-k3" in e and "allowed official domain" in e for e in errors),
            errors,
        )

    def test_catalog_cannot_add_example_com_to_anthropic_trust_root(self):
        data = copy.deepcopy(live())
        data["official_sources"]["allowed_domains_by_family"]["anthropic"].append("example.com")
        data["models"]["claude-opus-5"]["official_sources"] = ["https://example.com/claude-opus-5"]
        data["official_sources"]["by_family"]["anthropic"]["urls"] = [
            "https://example.com/claude-opus-5"
        ]
        data["routes"]["opus-5-teamclaude"]["attestations"]["official_id"]["source"] = (
            "https://example.com/claude-opus-5"
        )
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(any("code-owned official-domain trust root" in e for e in errors), errors)
        self.assertTrue(any("example.com" in e and "allowed official domain" in e for e in errors), errors)


class OperationalPriorTrustRootTests(unittest.TestCase):
    def test_arbitrary_existing_readme_cannot_support_operational_prior(self):
        data = copy.deepcopy(live())
        row = data["rankings"]["dispatch"]["quality"][0]
        self.assertEqual(row["basis"], "operational_prior")
        row["source"] = "README.md"
        errors = mr.validate(data, as_of=date(2026, 8, 28))
        self.assertTrue(any("code-approved structured source" in e and "README.md" in e for e in errors), errors)

    def test_every_operational_prior_uses_exact_approved_structured_binding(self):
        registry = live()
        for role, ranking in registry["rankings"].items():
            for i, row in enumerate(ranking.get("quality") or []):
                if row.get("basis") != "operational_prior":
                    continue
                key = (role, row["route"])
                self.assertIn(key, mr.OPERATIONAL_PRIOR_SOURCES, key)
                self.assertEqual(row["source"], mr.OPERATIONAL_PRIOR_SOURCES[key])
                self.assertEqual(
                    mr._quality_row_errors(
                        registry, role, i, row, registry["routes"], registry["models"],
                    ),
                    [],
                    key,
                )

    def test_review_e_placeholder_remains_exempt_from_official_domains(self):
        registry = live()
        model = registry["models"]["open-weight-review-e"]
        self.assertTrue(mr._model_is_placeholder(model))
        self.assertEqual(mr.official_urls_for_model(registry, "open-weight-review-e", model), [])
        self.assertNotIn("open-weight", registry["official_sources"].get("allowed_domains_by_family", {}))
        self.assertNotIn("review-e", registry["official_sources"].get("by_family", {}))

    def test_placeholder_cannot_be_promoted_or_wired(self):
        data = copy.deepcopy(live())
        data["routes"]["review-e-fireworks"]["route_state"] = "live_verified"
        data["routes"]["review-e-fireworks"]["host"] = "fireworks"
        errors = mr.validate(data, as_of=date(2026, 8, 28), providers=providers())
        self.assertTrue(any("placeholder" in e and "live_verified" in e for e in errors), errors)
        data = copy.deepcopy(live())
        provs = providers()
        provs["providers"]["review-e"]["wired"] = True
        errors = mr.validate(data, as_of=date(2026, 8, 28), providers=provs)
        self.assertTrue(any("cannot be wired" in e for e in errors), errors)

    def test_inventory_and_matrix_show_waivers(self):
        registry = live()
        rows = {r["route"]: r for r in mr.inventory(registry)}
        self.assertTrue(rows["gpt-5.6-sol-codex"]["waivers"])
        self.assertTrue(any(w["field"] == "role_evals" for w in rows["gpt-5.6-sol-codex"]["waivers"]))
        self.assertTrue(rows["review-e-fireworks"]["placeholder"])
        matrix = mr.render_matrix(registry)
        self.assertIn("grandfathered", matrix)
        self.assertIn("local placeholder", matrix.lower())
        self.assertIn("https://openai.com/index/gpt-5-6/", matrix)
        self.assertIn("local_same_harness", matrix)


class TokenEfficiencyClaimTests(unittest.TestCase):
    def test_intake_requires_before_after_receipts_to_claim_savings(self):
        intake = live()["intake"]["future_evaluations"]["token_efficiency_savings"]
        self.assertEqual(intake["status"], "hypothesis_to_measure")
        self.assertIn("before_after_token_receipts", intake["requires_before_claiming_savings"])
        self.assertIn("token-eff-1", " ".join(intake["requires_before_claiming_savings"]))
        receipt = (REPO / "model-evals" / "receipts" / "2026-08-28-architecture-spec-critique.jsonl").read_text()
        self.assertNotIn("token-eff-1", receipt)

    def test_role_copy_does_not_claim_realized_savings(self):
        desc = live()["roles"]["context_scouting"]["description"].lower()
        self.assertIn("hypothesis to measure", desc)
        self.assertNotIn("pay for themselves", desc)


class DispatcherAuthorityTests(unittest.TestCase):
    def setUp(self):
        doc.ERRORS.clear()
        doc.WARNINGS.clear()

    def _check(self, entry, provs=None):
        doc.ERRORS.clear()
        p = provs or providers()["providers"]
        doc.check_entrypoints(entry, p, set(p))
        return list(doc.ERRORS)

    def _entry(self, **surface_overrides):
        entry = json.loads((REPO / "config" / "entrypoints.json").read_text())
        entry["entry_surfaces"].update(surface_overrides)
        return entry

    def test_live_entrypoints_define_one_dispatcher_per_run(self):
        entry = json.loads((REPO / "config" / "entrypoints.json").read_text())
        self.assertEqual(self._check(entry), [])
        self.assertTrue(entry["rules"]["single_dispatcher_per_run"])
        self.assertGreaterEqual(sum(bool(s["can_dispatch"]) for s in entry["entry_surfaces"].values()), 2)

    def test_multiple_dispatch_capable_surfaces_are_valid(self):
        entry = self._entry()
        entry["entry_surfaces"]["codex-cli"]["can_dispatch"] = True
        self.assertEqual(self._check(entry), [])

    def test_zero_dispatch_capable_surfaces_fail(self):
        entry = self._entry()
        for surface in entry["entry_surfaces"].values():
            surface["can_dispatch"] = False
        errors = self._check(entry)
        self.assertTrue(any("at least one dispatch-capable surface" in e for e in errors), errors)

    def test_dispatch_surface_cannot_list_unqualified_provider(self):
        entry = self._entry()
        entry["entry_surfaces"]["claude-code"]["providers"].append("cursor-grok")
        errors = self._check(entry)
        self.assertTrue(any("unqualified provider 'cursor-grok'" in e for e in errors), errors)

    def test_profile_provider_must_be_dispatch_eligible(self):
        entry = json.loads((REPO / "config" / "entrypoints.json").read_text())
        entry["profiles"]["default"]["preferred_dispatcher"] = "cursor-grok"
        errors = self._check(entry)
        self.assertTrue(any("profile default" in e and "cursor-grok" in e for e in errors), errors)

    def test_default_profile_is_required(self):
        entry = json.loads((REPO / "config" / "entrypoints.json").read_text())
        del entry["profiles"]["default"]
        errors = self._check(entry)
        self.assertTrue(any("profiles.default" in e for e in errors), errors)


class DynamicDispatchAndHandoffTests(unittest.TestCase):
    def _rows(self, spent=()):
        def tier(name, default="available"):
            return "spent" if name in spent else default
        return [
            {"seat": "codex-sol", "subscription": "codex-200", "tier": tier("codex-sol", "reserve"),
             "billing": "included", "family": "openai", "intake": False, "window_kinds": ["weekly"]},
            {"seat": "codex-plan", "subscription": "codex-200", "tier": tier("codex-plan", "reserve"),
             "billing": "included", "family": "openai", "intake": True, "window_kinds": ["rolling"]},
            {"seat": "grok-heavy", "subscription": "grok-heavy", "tier": tier("grok-heavy"),
             "billing": "included", "family": "xai", "intake": False, "window_kinds": ["weekly"]},
            {"seat": "cursor-models", "subscription": "cursor-ultra", "tier": tier("cursor-models"),
             "billing": "included", "family": "cursor-pool", "intake": False, "window_kinds": ["monthly"]},
            {"seat": "claude-max", "subscription": "claude-max-200", "tier": tier("claude-max"),
             "billing": "included", "family": "anthropic", "fable": True, "intake": False,
             "window_kinds": ["rolling"]},
            {"seat": "claude-pro-a", "subscription": "claude-pro-25-a", "tier": tier("claude-pro-a"),
             "billing": "included", "family": "anthropic", "fable": False, "intake": False,
             "window_kinds": ["rolling"]},
        ]

    def _entry(self):
        return json.loads((REPO / "config" / "entrypoints.json").read_text())

    def _live_review_e(self, *, wired=True):
        provs = providers()
        provs["providers"]["review-e"]["wired"] = wired
        registry = live()
        registry["routes"]["review-e-fireworks"]["route_state"] = "live_verified"
        return provs, registry

    def _review_e_route_probe(self):
        """Treat the Review E test route as live after the test promotes it.

        The checked-in Review E model is intentionally a non-routable placeholder,
        so a unit matrix cannot make it genuinely live without fabricating the named
        model and its six promotion attestations. This patch isolates the routing
        matrix at the already-validated live-route boundary.
        """
        real = rr.modelreg.provider_route_is_live
        return mock.patch.object(
            rr.modelreg,
            "provider_route_is_live",
            side_effect=lambda registry, provider, as_of=None: (
                registry["routes"]["review-e-fireworks"].get("route_state") == "live_verified"
                if (provider or {}).get("route") == "review-e-fireworks"
                else real(registry, provider, as_of=as_of)
            ),
        )

    def test_every_tested_dispatch_target_honors_user_selection(self):
        provs = providers()
        for pid in ("codex-sol", "opus-5", "opus-4.8", "grok-build", "fable-5",
                    "codex-terra", "codex-luna"):
            got = rr.select_dispatcher(self._entry(), provs, self._rows(), live(), requested=pid)
            self.assertTrue(got["satisfied"], (pid, got))
            self.assertEqual(got["effective"], pid)
            self.assertFalse(got["fallback_used"])

    def test_spent_requested_model_falls_back_by_evidence_order(self):
        got = rr.select_dispatcher(
            self._entry(), providers(), self._rows(spent=("grok-heavy",)), live(),
            requested="grok-build",
        )
        self.assertTrue(got["satisfied"], got)
        self.assertEqual(got["effective"], "codex-terra")
        self.assertTrue(got["fallback_used"])

    def test_unavailable_requested_route_falls_back(self):
        registry = live()
        registry["routes"]["grok-4.6-build"]["route_state"] = "quota_spent"
        got = rr.select_dispatcher(
            self._entry(), providers(), self._rows(), registry, requested="grok-build",
        )
        self.assertTrue(got["satisfied"], got)
        self.assertTrue(got["fallback_used"])
        self.assertNotEqual(got["effective"], "grok-build")

    def test_sol_usage_is_not_borrowed_from_generic_codex_intake_row(self):
        got = rr.select_dispatcher(
            self._entry(), providers(), self._rows(spent=("codex-sol",)), live(),
            requested="codex-sol",
        )
        self.assertTrue(got["fallback_used"], got)
        self.assertNotEqual(got["effective"], "codex-sol")

    def test_fable_downgrade_ledger_removes_fable_from_dispatch(self):
        got = rr.select_dispatcher(
            self._entry(), providers(), self._rows(), live(), requested="fable-5",
            ledger={"fable-downgrade:claude-max": {}},
        )
        self.assertTrue(got["satisfied"], got)
        self.assertTrue(got["fallback_used"])
        self.assertNotEqual(got["effective"], "fable-5")

    def test_unknown_requested_dispatcher_fails_closed(self):
        got = rr.select_dispatcher(self._entry(), providers(), self._rows(), live(), requested="not-a-provider")
        self.assertFalse(got["satisfied"], got)
        self.assertIsNone(got["effective"])
        self.assertFalse(got["fallback_used"])

    def test_known_non_dispatch_intake_relays_without_gaining_authority(self):
        got = rr.select_dispatcher(self._entry(), providers(), self._rows(), live(), requested="cursor-grok")
        self.assertTrue(got["satisfied"], got)
        self.assertTrue(got["intake_relay"])
        self.assertNotEqual(got["effective"], "cursor-grok")

    def test_only_declared_non_dispatch_entry_surface_may_relay(self):
        for pid in ("review-e", "grok-bot-heat-map", "local-llm-example"):
            got = rr.select_dispatcher(self._entry(), providers(), self._rows(), live(), requested=pid)
            self.assertFalse(got["satisfied"], (pid, got))
            self.assertFalse(got.get("intake_relay", False))

    def test_explicit_intake_provider_overrides_irrelevant_profile_name(self):
        got = rr.select_dispatcher(
            self._entry(), providers(), self._rows(), live(),
            requested="codex-sol", profile="another-users-missing-profile",
        )
        self.assertTrue(got["satisfied"], got)
        self.assertEqual(got["effective"], "codex-sol")

    def test_incomplete_or_retracting_dispatch_evidence_fails_closed(self):
        for mutation in ({"completed": 1}, {"reversals": 1}, {"status": "pending"},
                         {"date": ""}, {"date": "not-a-date"}, {"date": "2999-01-01"},
                         {"source": ""}, {"source": "unverifiable prose"}):
            provs = providers()
            provs["providers"]["codex-sol"]["dispatch_evidence"].update(mutation)
            got = rr.select_dispatcher(self._entry(), provs, self._rows(), live(), requested="codex-sol")
            self.assertFalse(got["satisfied"], (mutation, got))

    def test_sol_dispatch_makes_opus_primary_and_sol_artifact_only(self):
        reviewers = rr.live_reviewers(providers(), self._rows(), {}, live(), dispatcher="codex-sol")
        self.assertEqual(reviewers[0]["provider"], "opus-5")
        sol = next(r for r in reviewers if r["provider"] == "codex-sol")
        self.assertFalse(sol["dispatch_independent"])
        self.assertEqual(sol["review_scope"], "artifact-only")
        review = rr.pick_review("cross-family", reviewers, False, 0)
        self.assertTrue(review["satisfied"], review)
        self.assertTrue(any(r["dispatch_independent"] for r in review["chain"]))

    def test_same_pipe_reviewer_cannot_validate_dispatch_intent(self):
        reviewers = rr.live_reviewers(
            providers(), self._rows(), {}, live(), dispatcher="opus-5",
        )
        opus48 = next(r for r in reviewers if r["provider"] == "opus-4.8")
        sol = next(r for r in reviewers if r["provider"] == "codex-sol")
        self.assertFalse(opus48["dispatch_independent"])
        self.assertEqual(opus48["review_scope"], "artifact-only")
        self.assertTrue(sol["dispatch_independent"])
        self.assertEqual(reviewers[0]["provider"], "codex-sol")

    def test_same_codex_pipe_cannot_validate_terra_dispatch(self):
        reviewers = rr.live_reviewers(
            providers(), self._rows(), {}, live(), dispatcher="codex-terra",
        )
        sol = next(r for r in reviewers if r["provider"] == "codex-sol")
        self.assertFalse(sol["dispatch_independent"])
        self.assertEqual(sol["review_scope"], "artifact-only")
        self.assertEqual(reviewers[0]["provider"], "opus-5")

    def test_implementer_is_excluded_from_review_chain(self):
        reviewers = rr.live_reviewers(
            providers(), self._rows(), {}, live(), dispatcher="opus-5", authors=("codex-sol",),
        )
        self.assertNotIn("codex-sol", [r["provider"] for r in reviewers])
        review = rr.pick_review("cross-family", reviewers, False, 0)
        self.assertFalse(review["satisfied"], review)

    def test_dispatcher_only_review_cannot_satisfy_gate(self):
        only = [{"provider": "codex-sol", "seat": "codex-sol", "family": "openai",
                 "tier": "reserve", "row": self._rows()[0], "dispatch_independent": False,
                 "review_scope": "artifact-only"}]
        self.assertFalse(rr.pick_review("single-frontier", only, False, 0)["satisfied"])

    def test_ordinary_handoff_never_prompts_and_authorship_does_not_matter(self):
        policy = json.loads((REPO / "config" / "handoff-policy.json").read_text())
        got = rr.evaluate_handoff(policy, ["brief", "repo-source", "diff", "test-output"])
        self.assertTrue(got["allowed"])
        self.assertFalse(got["requires_user_permission"])
        self.assertFalse(got["authorship_changes_authority"])
        self.assertEqual(got["authorization_basis"], "standing_review_authorization")
        self.assertEqual(got["standing_review_authorization"]["provider_scope"],
                         "all-configured-review-providers")
        self.assertEqual(got["standing_review_authorization"]["artifact_scope"],
                         "ordinary_artifacts")
        self.assertFalse(got["standing_review_authorization"]["per_review_approval_required"])
        self.assertTrue(got["standing_review_authorization"]["intake_family_may_review"])
        self.assertEqual(got["standing_review_authorization"]["intake_family_review_scope"],
                         "artifact-only")
        self.assertTrue(got["standing_review_authorization"]["intake_family_must_not_be_sole_reviewer"])
        self.assertTrue(got["standing_review_authorization"]["separate_physical_invocation_required"])
        self.assertRegex(got["standing_review_authorization"]["effective_date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertLessEqual(
            date.fromisoformat(got["standing_review_authorization"]["effective_date"]),
            date.today(),
        )

    def test_restricted_and_unknown_handoffs_park_without_permission_loop(self):
        policy = json.loads((REPO / "config" / "handoff-policy.json").read_text())
        for artifact, basis in (("credentials", "fail-closed-restricted"),
                                ("future-unclassified-artifact", "fail-closed-unknown")):
            got = rr.evaluate_handoff(policy, ["brief", artifact])
            self.assertFalse(got["allowed"], got)
            self.assertEqual(got["action"], "park")
            self.assertFalse(got["requires_user_permission"])
            self.assertEqual(got["authorization_basis"], basis)
            self.assertIsNotNone(got["standing_review_authorization"])
            self.assertEqual(got["standing_review_authorization"]["artifact_scope"],
                             "ordinary_artifacts")

    def test_immutable_restricted_minimum_wins_runtime_config_mutation(self):
        base = json.loads((REPO / "config" / "handoff-policy.json").read_text())
        minimum = rr.handoff_policy.IMMUTABLE_MINIMUM_RESTRICTED_ARTIFACTS
        self.assertTrue(minimum.issubset(set(base["restricted_artifacts"])))
        for artifact in sorted(minimum):
            with self.subTest(artifact=artifact):
                mutated = copy.deepcopy(base)
                mutated["restricted_artifacts"] = [
                    value for value in mutated["restricted_artifacts"] if value != artifact
                ]
                mutated["ordinary_artifacts"].append(artifact)
                got = rr.evaluate_handoff(mutated, ["brief", artifact])
                self.assertFalse(got["allowed"], got)
                self.assertEqual(got["authorization_basis"], "fail-closed-restricted")
                self.assertIn(artifact, got["restricted"])
                self.assertFalse(got["requires_user_permission"])

    def test_unknown_intake_parks_handoff_and_is_not_a_participant(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = rr.main(["--class", "internal-notes", "--intake-provider", "not-a-provider", "--json"])
        got = json.loads(buf.getvalue())
        self.assertEqual(rc, 0)
        self.assertFalse(got["handoff"]["allowed"])
        self.assertEqual(got["handoff"]["action"], "park")
        self.assertNotIn("not-a-provider", got["handoff"]["participants"])

    def test_dispatcher_avoidance_never_outranks_included_over_metered(self):
        rows = self._rows(spent=("cursor-models",)) + [
            {"seat": "cursor-other-400", "subscription": "cursor-ultra", "tier": "available",
             "billing": "metered", "family": "cursor-pool", "intake": False,
             "window_kinds": ["none"]},
        ]
        steps = rr.pick_implement(
            providers(), connectors(), rows, "repo-code", "", "", False, 0, live(),
            avoid_provider="grok-build",
        )
        implement = next(s for s in steps if not s.get("input_seat"))
        self.assertEqual(implement["seat"], "grok-build", steps)
        self.assertEqual(implement["billing"], "included")

    def test_non_dispatch_included_worker_beats_dispatcher_within_billing_class(self):
        rows = self._rows()
        next(r for r in rows if r["seat"] == "cursor-models")["tier"] = "reserve"
        steps = rr.pick_implement(
            providers(), connectors(), rows, "repo-code", "", "", False, 0, live(),
            avoid_provider="grok-build",
        )
        implement = next(s for s in steps if not s.get("input_seat"))
        self.assertEqual(implement["seat"], "cursor-grok", steps)
        self.assertEqual(implement["billing"], "included")

    def test_intake_family_pairing_is_artifact_only_and_not_sole_reviewer(self):
        reviewers = rr.live_reviewers(
            providers(), self._rows(), {}, live(), dispatcher="opus-5",
        )
        by_id = {r["provider"]: r for r in reviewers}
        self.assertEqual(by_id["opus-5"]["review_scope"], "artifact-only")
        self.assertFalse(by_id["opus-5"]["dispatch_independent"])
        self.assertTrue(by_id["codex-sol"]["dispatch_independent"])
        review = rr.pick_review("cross-family", reviewers, False, 0)
        self.assertTrue(review["satisfied"], review)
        chain_ids = [c["provider"] for c in review["chain"]]
        self.assertIn("codex-sol", chain_ids)
        self.assertNotEqual(chain_ids, ["opus-5"])

    def test_single_frontier_refuses_dispatcher_as_sole_reviewer(self):
        only = [{"provider": "opus-5", "seat": "opus-5", "family": "anthropic",
                 "tier": "available", "row": self._rows()[0], "dispatch_independent": False,
                 "review_scope": "artifact-only"}]
        got = rr.pick_review("single-frontier", only, False, 0)
        self.assertFalse(got["satisfied"], got)

    def test_missing_standing_review_authorization_parks_ordinary_handoff(self):
        policy = json.loads((REPO / "config" / "handoff-policy.json").read_text())
        del policy["standing_review_authorization"]
        got = rr.evaluate_handoff(policy, ["brief", "repo-source", "diff", "test-output"])
        self.assertFalse(got["allowed"], got)
        self.assertEqual(got["action"], "park")
        self.assertFalse(got["requires_user_permission"])
        self.assertEqual(got["authorization_basis"],
                         "fail-closed-standing-review-authorization")
        self.assertIsNone(got["standing_review_authorization"])

    def test_weakened_standing_review_authorization_parks_ordinary_handoff(self):
        policy = json.loads((REPO / "config" / "handoff-policy.json").read_text())
        policy["standing_review_authorization"]["per_review_approval_required"] = True
        got = rr.evaluate_handoff(policy, ["brief", "repo-source"])
        self.assertFalse(got["allowed"], got)
        self.assertEqual(got["action"], "park")
        self.assertFalse(got["requires_user_permission"])
        self.assertEqual(got["authorization_basis"],
                         "fail-closed-standing-review-authorization")
        self.assertIsNone(got["standing_review_authorization"])
        policy = json.loads((REPO / "config" / "handoff-policy.json").read_text())
        policy["standing_review_authorization"]["artifact_scope"] = "any"
        got = rr.evaluate_handoff(policy, ["brief"])
        self.assertFalse(got["allowed"], got)
        self.assertFalse(got["requires_user_permission"])

    def test_restricted_park_reason_wins_when_authorization_is_missing(self):
        policy = json.loads((REPO / "config" / "handoff-policy.json").read_text())
        del policy["standing_review_authorization"]
        got = rr.evaluate_handoff(policy, ["brief", "credentials"])
        self.assertFalse(got["allowed"], got)
        self.assertEqual(got["action"], "park")
        self.assertFalse(got["requires_user_permission"])
        self.assertEqual(got["authorization_basis"], "fail-closed-restricted")

    def test_standing_review_authorization_weakening_fails_doctor(self):
        doc = load_mod("doctor_handoff", HERE / "doctor.py")
        policy = json.loads((REPO / "config" / "handoff-policy.json").read_text())
        saved = list(doc.ERRORS)
        doc.ERRORS.clear()
        try:
            doc.check_handoff_policy(policy)
            self.assertEqual(doc.ERRORS, [])
            weak = copy.deepcopy(policy)
            weak["standing_review_authorization"]["per_review_approval_required"] = True
            doc.check_handoff_policy(weak)
            self.assertTrue(any("per_review_approval_required" in e for e in doc.ERRORS), doc.ERRORS)
            doc.ERRORS.clear()
            missing = copy.deepcopy(policy)
            del missing["standing_review_authorization"]
            doc.check_handoff_policy(missing)
            self.assertTrue(any("standing_review_authorization" in e for e in doc.ERRORS), doc.ERRORS)
            doc.ERRORS.clear()
            extra = copy.deepcopy(policy)
            extra["standing_review_authorization"]["bonus"] = True
            doc.check_handoff_policy(extra)
            self.assertTrue(any("unexpected field" in e for e in doc.ERRORS), doc.ERRORS)
            doc.ERRORS.clear()
            future = copy.deepcopy(policy)
            future["standing_review_authorization"]["effective_date"] = (
                date.today() + timedelta(days=2)
            ).isoformat()
            doc.check_handoff_policy(future)
            self.assertTrue(any("future" in e for e in doc.ERRORS), doc.ERRORS)
            doc.ERRORS.clear()
            bad = copy.deepcopy(policy)
            bad["standing_review_authorization"]["effective_date"] = "2026-13-40"
            doc.check_handoff_policy(bad)
            self.assertTrue(any("effective_date" in e for e in doc.ERRORS), doc.ERRORS)
        finally:
            doc.ERRORS[:] = saved

    def test_immutable_restricted_minimum_mutation_fails_doctor_and_schema(self):
        doc = load_mod("doctor_restricted_minimum", HERE / "doctor.py")
        policy = json.loads((REPO / "config" / "handoff-policy.json").read_text())
        saved = list(doc.ERRORS)
        doc.ERRORS.clear()
        try:
            removed = copy.deepcopy(policy)
            removed["restricted_artifacts"].remove("secrets")
            doc.check_handoff_policy(removed)
            self.assertTrue(any("immutable minimum" in e and "secrets" in e for e in doc.ERRORS), doc.ERRORS)

            moved = copy.deepcopy(policy)
            moved["restricted_artifacts"].remove("credentials")
            moved["ordinary_artifacts"].append("credentials")
            doc.ERRORS.clear()
            doc.check_handoff_policy(moved)
            self.assertTrue(any("cannot be ordinary" in e and "credentials" in e for e in doc.ERRORS), doc.ERRORS)
        finally:
            doc.ERRORS[:] = saved

        try:
            import jsonschema
        except ImportError:  # pragma: no cover - doctor has an authoritative built-in check
            return
        schema = json.loads((REPO / "config" / "orchestration.schema.json").read_text())
        handoff_schema = dict(schema)
        handoff_schema["$ref"] = "#/$defs/handoff_policy"
        jsonschema.validate(policy, handoff_schema)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(removed, handoff_schema)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(moved, handoff_schema)

    def test_malformed_future_or_extra_authorization_parks_ordinary_handoff(self):
        policy = json.loads((REPO / "config" / "handoff-policy.json").read_text())
        extra = copy.deepcopy(policy)
        extra["standing_review_authorization"]["extra"] = 1
        got = rr.evaluate_handoff(extra, ["brief"])
        self.assertFalse(got["allowed"])
        self.assertFalse(got["requires_user_permission"])
        future = copy.deepcopy(policy)
        future["standing_review_authorization"]["effective_date"] = "2099-01-01"
        got = rr.evaluate_handoff(future, ["brief"])
        self.assertFalse(got["allowed"])
        malformed = copy.deepcopy(policy)
        malformed["standing_review_authorization"]["effective_date"] = "30 Aug 2026"
        got = rr.evaluate_handoff(malformed, ["brief"])
        self.assertFalse(got["allowed"])
        self.assertEqual(got["authorization_basis"],
                         "fail-closed-standing-review-authorization")

    def _handoff_load_config(self, mutate):
        orig = rr.mborch.load_config
        def fake(name, required=True):
            data = orig(name, required=required)
            if name == "handoff-policy.json" and isinstance(data, dict):
                data = copy.deepcopy(data)
                mutate(data)
            return data
        return fake

    def test_rr_main_parks_missing_standing_authorization(self):
        def mutate(policy):
            del policy["standing_review_authorization"]
        buf = io.StringIO()
        with mock.patch.object(rr.mborch, "load_config", self._handoff_load_config(mutate)):
            with contextlib.redirect_stdout(buf):
                rc = rr.main(["--class", "internal-notes", "--intake-provider", "grok-build", "--json"])
        got = json.loads(buf.getvalue())
        self.assertEqual(rc, 0)
        self.assertFalse(got["routing_satisfied"])
        self.assertFalse(got["handoff"]["allowed"])
        self.assertFalse(got["handoff"]["requires_user_permission"])
        self.assertEqual(got["handoff"]["authorization_basis"],
                         "fail-closed-standing-review-authorization")
        self.assertIsNone(got["handoff"]["standing_review_authorization"])
        self.assertIn("standing_review_authorization", got["park_reason"])

    def test_rr_main_parks_weakened_standing_authorization(self):
        def mutate(policy):
            policy["standing_review_authorization"]["per_review_approval_required"] = True
        buf = io.StringIO()
        with mock.patch.object(rr.mborch, "load_config", self._handoff_load_config(mutate)):
            with contextlib.redirect_stdout(buf):
                rc = rr.main(["--class", "internal-notes", "--intake-provider", "grok-build", "--json"])
        got = json.loads(buf.getvalue())
        self.assertEqual(rc, 0)
        self.assertFalse(got["handoff"]["allowed"])
        self.assertFalse(got["handoff"]["requires_user_permission"])
        self.assertEqual(got["handoff"]["action"], "park")
        self.assertEqual(got["handoff"]["authorization_basis"],
                         "fail-closed-standing-review-authorization")

    def test_neutral_family_dispatcher_keeps_doctrinal_review_order(self):
        rows = self._rows()
        next(r for r in rows if r["seat"] == "codex-sol").update(
            {"window_kinds": ["weekly"], "runway_seconds": 3600, "intake": False}
        )
        next(r for r in rows if r["seat"] == "claude-pro-a").update(
            {"window_kinds": ["weekly"], "runway_seconds": 86400 * 20, "intake": True}
        )
        reviewers = rr.live_reviewers(
            providers(), rows, {}, live(), dispatcher="grok-build",
        )
        ids = [r["provider"] for r in reviewers if r["provider"] in ("opus-5", "codex-sol")]
        self.assertEqual(ids[:2], ["opus-5", "codex-sol"], reviewers)
        self.assertTrue(all(r["dispatch_independent"] for r in reviewers
                            if r["provider"] in ("opus-5", "codex-sol")))

    def test_spent_reviewer_stays_excluded_when_order_is_doctrinal(self):
        reviewers = rr.live_reviewers(
            providers(), self._rows(spent=("codex-sol",)), {}, live(), dispatcher="grok-build",
        )
        self.assertNotIn("codex-sol", [r["provider"] for r in reviewers])
        self.assertEqual(reviewers[0]["provider"], "opus-5")

    def test_review_e_live_does_not_preempt_available_native_families(self):
        provs, registry = self._live_review_e()
        with self._review_e_route_probe():
            reviewers = rr.live_reviewers(
                provs, self._rows(), {}, registry, dispatcher="grok-build",
            )
        ids = [r["provider"] for r in reviewers]
        self.assertNotIn("review-e", ids)
        review = rr.pick_review("cross-family", reviewers, True, 0)
        self.assertTrue(review["satisfied"], review)
        self.assertEqual(
            {r["independence_group"] for r in review["chain"]},
            {"anthropic", "openai"},
        )

    def test_review_e_opens_only_for_positive_native_quota_spent_evidence(self):
        provs, registry = self._live_review_e()
        with self._review_e_route_probe():
            reviewers = rr.live_reviewers(
                provs, self._rows(spent=("codex-sol",)), {}, registry,
                dispatcher="grok-build",
            )
        ids = [r["provider"] for r in reviewers]
        self.assertIn("opus-5", ids)
        self.assertIn("review-e", ids)
        review = rr.pick_review("cross-family", reviewers, True, 0)
        self.assertTrue(review["satisfied"], review)
        self.assertEqual(
            {r["independence_group"] for r in review["chain"]},
            {"anthropic", "open-weight"},
        )

    def test_review_e_stays_after_native_intake_family_artifact_review(self):
        provs, registry = self._live_review_e()
        with self._review_e_route_probe():
            reviewers = rr.live_reviewers(
                provs, self._rows(spent=("codex-sol",)), {}, registry,
                dispatcher="opus-5",
            )
        self.assertEqual(reviewers[0]["provider"], "opus-5", reviewers)
        self.assertEqual(reviewers[0]["review_scope"], "artifact-only")
        self.assertFalse(reviewers[0]["dispatch_independent"])
        self.assertEqual(reviewers[-1]["provider"], "review-e", reviewers)
        review = rr.pick_review("cross-family", reviewers, True, 0)
        self.assertTrue(review["satisfied"], review)
        self.assertEqual([r["provider"] for r in review["chain"]], ["opus-5", "review-e"])
        self.assertTrue(any(r["dispatch_independent"] for r in review["chain"]))

    def test_native_outage_does_not_open_review_e(self):
        provs, registry = self._live_review_e()
        registry["routes"]["gpt-5.6-sol-codex"]["route_state"] = "unavailable"
        with self._review_e_route_probe():
            reviewers = rr.live_reviewers(
                provs, self._rows(), {}, registry, dispatcher="grok-build",
            )
        ids = [r["provider"] for r in reviewers]
        self.assertNotIn("codex-sol", ids)
        self.assertNotIn("review-e", ids)
        review = rr.pick_review("cross-family", reviewers, True, 0)
        self.assertFalse(review["satisfied"], review)

    def test_review_e_live_route_still_requires_wired_true(self):
        provs, registry = self._live_review_e(wired=False)
        with self._review_e_route_probe():
            reviewers = rr.live_reviewers(
                provs, self._rows(spent=("codex-sol",)), {}, registry,
                dispatcher="grok-build",
            )
        self.assertNotIn("review-e", [r["provider"] for r in reviewers])
        review = rr.pick_review("cross-family", reviewers, False, 0)
        self.assertFalse(review["satisfied"], review)

    def test_reserve_reviewer_still_sorts_after_available(self):
        rows = self._rows()
        next(r for r in rows if r["seat"] == "codex-sol")["tier"] = "available"
        next(r for r in rows if r["seat"] == "claude-pro-a")["tier"] = "reserve"
        reviewers = rr.live_reviewers(
            providers(), rows, {}, live(), dispatcher="grok-build",
        )
        by = {r["provider"]: r for r in reviewers}
        self.assertEqual(by["codex-sol"]["tier"], "available")
        self.assertEqual(by["opus-5"]["tier"], "reserve")
        ids = [r["provider"] for r in reviewers if r["provider"] in ("opus-5", "codex-sol")]
        self.assertEqual(ids[0], "codex-sol")

    def test_dual_eligible_review_dispatch_requires_separate_invocation_flag(self):
        doc = load_mod("doctor_seat_exec", HERE / "doctor.py")
        seat = json.loads((REPO / "config" / "seat-exec.json").read_text())
        provs = providers()
        saved = list(doc.ERRORS)
        doc.ERRORS.clear()
        try:
            doc.check_seat_exec(seat, provs["providers"], set(provs["providers"]))
            self.assertEqual(doc.ERRORS, [])
            weak = copy.deepcopy(seat)
            del weak["recipes"]["codex-sol"]["separate_invocation_when_dispatcher"]
            doc.check_seat_exec(weak, provs["providers"], set(provs["providers"]))
            self.assertTrue(
                any("codex-sol" in e and "separate_invocation" in e for e in doc.ERRORS),
                doc.ERRORS,
            )
        finally:
            doc.ERRORS[:] = saved

    def test_grok_command_shape_uses_only_installed_cli_contract(self):
        doc = load_mod("doctor_grok_command", HERE / "doctor.py")
        seat = json.loads((REPO / "config" / "seat-exec.json").read_text())
        provs = providers()
        expected = [
            "--cwd", "{worktree}", "--prompt-file", "{brief_path}",
            "--model", "grok-4.6", "--reasoning-effort", "xhigh",
            "--no-subagents",
        ]
        self.assertEqual(seat["recipes"]["grok-build"]["args_template"], expected)
        self.assertEqual(provs["providers"]["grok-build"]["model"], "grok-4.6")
        self.assertEqual(live()["models"]["grok-4.6"]["official_ids"], ["grok-4.6"])

        saved = list(doc.ERRORS)
        doc.ERRORS.clear()
        try:
            doc.check_seat_exec(seat, provs["providers"], set(provs["providers"]))
            self.assertEqual(doc.ERRORS, [])

            rejected_vectors = {
                "unknown": expected + ["--future-flag"],
                "duplicate": expected + ["--no-subagents"],
                "positional": expected + ["implement-now"],
                "permission-bypass": expected + ["--always-approve"],
                "wrong-aliases": [
                    "--workdir", "{worktree}", "--brief", "{brief_path}",
                    "--model", "grok-4.6", "--reasoning-effort", "xhigh",
                    "--no-subagents",
                ],
            }
            for case, vector in rejected_vectors.items():
                with self.subTest(case=case):
                    invalid = copy.deepcopy(seat)
                    invalid["recipes"]["grok-build"]["args_template"] = vector
                    doc.ERRORS.clear()
                    doc.check_seat_exec(invalid, provs["providers"], set(provs["providers"]))
                    self.assertTrue(
                        any("exact approved argv" in e for e in doc.ERRORS),
                        doc.ERRORS,
                    )

            shortened = copy.deepcopy(seat)
            shortened["recipes"]["grok-build"]["args_template"][5] = "grok-4"
            doc.ERRORS.clear()
            doc.check_seat_exec(shortened, provs["providers"], set(provs["providers"]))
            self.assertTrue(
                any("exact approved argv" in e and "grok-4.6" in e for e in doc.ERRORS),
                doc.ERRORS,
            )

            wrong_provider_model = copy.deepcopy(provs)
            wrong_provider_model["providers"]["grok-build"]["model"] = "grok-4.6-build"
            doc.ERRORS.clear()
            doc.check_seat_exec(
                seat,
                wrong_provider_model["providers"],
                set(wrong_provider_model["providers"]),
            )
            self.assertTrue(any("must match model-registry route" in e for e in doc.ERRORS), doc.ERRORS)

            derived = copy.deepcopy(provs)
            derived_registry = copy.deepcopy(live())
            derived_seat = copy.deepcopy(seat)
            derived["providers"]["grok-build"]["model"] = "grok-next-test"
            derived_registry["routes"]["grok-4.6-build"]["model"] = "grok-next-test"
            derived_seat["recipes"]["grok-build"]["args_template"][5] = "grok-next-test"
            doc.ERRORS.clear()
            doc.check_seat_exec(
                derived_seat,
                derived["providers"],
                set(derived["providers"]),
                derived_registry,
            )
            self.assertEqual(doc.ERRORS, [])
        finally:
            doc.ERRORS[:] = saved


if __name__ == "__main__":
    unittest.main()
