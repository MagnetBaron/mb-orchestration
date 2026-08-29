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
        self.assertEqual(by_route["fable-5-teamclaude"]["rank"], 2)
        self.assertEqual(by_route["fable-5-teamclaude"]["confidence"], "low")
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
        self.assertIn("spoof-openai-opus", decision["rejected_same_family"])
        families = [r["family"] for r in decision["routes"]]
        self.assertNotEqual(set(families), {"anthropic", "openai"})


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

    def test_live_entrypoints_have_exactly_one_dispatcher(self):
        entry = json.loads((REPO / "config" / "entrypoints.json").read_text())
        self.assertEqual(self._check(entry), [])

    def test_multiple_dispatchers_fail(self):
        entry = self._entry()
        entry["entry_surfaces"]["codex-cli"]["can_dispatch"] = True
        errors = self._check(entry)
        self.assertTrue(any("exactly one can_dispatch:true" in e for e in errors), errors)

    def test_zero_dispatchers_fail(self):
        entry = self._entry()
        entry["entry_surfaces"]["claude-code"]["can_dispatch"] = False
        errors = self._check(entry)
        self.assertTrue(any("exactly one can_dispatch:true" in e and "found 0" in e for e in errors), errors)

    def test_provider_mismatch_fails(self):
        entry = self._entry()
        entry["entry_surfaces"]["claude-code"]["provider"] = "codex-terra"
        errors = self._check(entry)
        self.assertTrue(any("!= dispatcher.provider" in e for e in errors), errors)

    def test_level_mismatch_fails(self):
        entry = json.loads((REPO / "config" / "entrypoints.json").read_text())
        entry["dispatcher"]["level"] = "terra"
        errors = self._check(entry)
        self.assertTrue(any("dispatcher.level" in e and "terra" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
