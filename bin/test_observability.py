#!/usr/bin/env python3
"""Observability: schema, privacy, append safety, analysis honesty, no authority."""
from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import copy
import importlib.util
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = HERE.parent


def load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


observe = load_mod("observe", HERE / "observe.py")
rr = load_mod("resolve_route_obs", HERE / "resolve-route.py")
run_brief = load_mod("run_brief_obs", HERE / "run-brief.py")
doc = load_mod("doctor_obs", HERE / "doctor.py")


def _decision(**overrides):
    base = {
        "class": "repo-code",
        "scale": "routine",
        "risk_flags": [],
        "review_depth": "single-frontier",
        "dispatcher": {
            "satisfied": True, "requested": "opus-5", "effective": "opus-5",
            "profile": "default", "fallback_used": False, "family": "anthropic",
            "seat": "claude-pro-a", "tier": "available",
        },
        "handoff": {
            "allowed": True, "action": "transfer-minimum-necessary",
            "artifacts": ["brief", "repo-source", "diff", "test-output"],
            "restricted": [], "unknown": [], "missing_required": [],
            "requires_user_permission": False, "authorship_changes_authority": False,
            "authorization_basis": "standing_review_authorization",
        },
        "review": {
            "satisfied": True,
            "chain": [{
                "provider": "opus-5", "family": "anthropic",
                "independence_group": "anthropic-frontier",
                "review_scope": "artifact-and-dispatch",
                "dispatch_independent": True, "seat": "claude-pro-a", "tier": "available",
            }],
        },
        "authors": ["grok-build"],
        "implement": [{"seat": "grok-build", "available": True, "tier": "available",
                       "on": "grok-heavy"}],
        "implement_requested": True,
        "routing_satisfied": True,
        "park_reason": None,
        "gates": {"landing_lock": True, "tip_bound_green_test": True},
    }
    base.update(overrides)
    return base


class SchemaAndIdempotencyTests(unittest.TestCase):
    def test_v1_required_fields(self):
        ev = observe.make_event(
            "route_decision", run_id="run-1", ts="2026-08-29T00:00:00+00:00",
            actor_id="profile:default", profile_id="default",
        )
        self.assertEqual(ev["schema_version"], 1)
        for key in ("schema_version", "event_id", "run_id", "ts", "kind"):
            self.assertTrue(ev.get(key), key)
        self.assertTrue(ev["event_id"].startswith("obs-v1-"))
        self.assertEqual(observe.validate_event(ev), [])

    def test_unknown_future_fields_are_ignored(self):
        ev = observe.event_from_route_decision(
            _decision(), run_id="run-future", ts="2026-08-29T00:00:00+00:00",
            actor_id="team-a", profile_id="default",
        )
        ev["schema_version"] = 2
        ev["future_metric"] = {"novelty_score": 0.9, "vendor_claim": "ignore-me"}
        self.assertEqual(observe.validate_event(ev), [])
        folded = observe.fold_run([ev])
        self.assertEqual(folded["run_id"], "run-future")
        self.assertEqual(folded["actor_id"], "team-a")
        report = observe.analyze([ev])
        self.assertFalse(report["causal_claim"])
        self.assertEqual(report["runs"], 1)

    def test_unknown_kind_is_tolerated_when_not_strict(self):
        ev = observe.make_event(
            "route_decision", run_id="run-k", ts="2026-08-29T00:00:00+00:00",
        )
        ev["kind"] = "latency_histogram"
        self.assertEqual(observe.validate_event(ev), [])
        self.assertTrue(any("unknown kind" in e for e in observe.validate_event(ev, strict=True)))

    def test_idempotent_event_identifiers(self):
        a = observe.event_from_route_decision(
            _decision(), run_id="run-idemp", ts="2026-08-29T00:00:00+00:00",
            actor_id="team-a", duration_ms=12,
        )
        b = observe.event_from_route_decision(
            _decision(), run_id="run-idemp", ts="2026-08-29T00:00:05+00:00",
            actor_id="team-a", duration_ms=99,
        )
        self.assertEqual(a["event_id"], b["event_id"])
        folded = observe.fold_run([a, b])
        self.assertEqual(folded["event_count"], 1)
        self.assertEqual(folded["event_ids"], [a["event_id"]])

    def test_different_decisions_get_different_ids(self):
        a = observe.event_from_route_decision(
            _decision(), run_id="run-x", ts="2026-08-29T00:00:00+00:00",
        )
        other = _decision(routing_satisfied=False, park_reason="PARK: restricted artifact(s)")
        b = observe.event_from_route_decision(
            other, run_id="run-x", ts="2026-08-29T00:00:00+00:00",
        )
        self.assertNotEqual(a["event_id"], b["event_id"])


class AppendSafetyTests(unittest.TestCase):
    def test_concurrent_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"

            def write(i):
                ev = observe.make_event(
                    "route_decision", run_id=f"run-{i}", ts="2026-08-29T00:00:00+00:00",
                    actor_id=f"actor-{i}",
                )
                observe.append(ev, path=str(path))
                return ev["event_id"]

            n = 24
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                ids = list(pool.map(write, range(n)))
            events = observe.read(path)
            self.assertEqual(len(events), n)
            self.assertEqual(sorted(e["event_id"] for e in events), sorted(ids))
            self.assertEqual(len({e["run_id"] for e in events}), n)

    def test_truncated_and_corrupt_tail_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            first = observe.make_event(
                "route_decision", run_id="run-ok", ts="2026-08-29T00:00:00+00:00",
                actor_id="team-a",
            )
            observe.append(first, path=str(path))
            with path.open("a", encoding="utf-8") as fh:
                fh.write('{"schema_version":1,"event_id":"obs-v1-truncated"')  # no newline, truncated
            recovered = observe.make_event(
                "route_decision", run_id="run-after", ts="2026-08-29T00:00:01+00:00",
                actor_id="team-a",
            )
            observe.append(recovered, path=str(path))
            with path.open("a", encoding="utf-8") as fh:
                fh.write("{not json}\n")
            third = observe.make_event(
                "route_decision", run_id="run-third", ts="2026-08-29T00:00:02+00:00",
                actor_id="team-b",
            )
            observe.append(third, path=str(path))
            events = observe.read(path)
            run_ids = [e["run_id"] for e in events]
            self.assertEqual(run_ids, ["run-ok", "run-after", "run-third"])
            self.assertTrue(all(observe.validate_event(e) == [] for e in events))

    def test_retention_prune_keeps_recent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            old = observe.make_event(
                "route_decision", run_id="old", ts="2020-01-01T00:00:00+00:00",
            )
            new = observe.make_event(
                "route_decision", run_id="new", ts="2026-08-29T00:00:00+00:00",
            )
            observe.append(old, path=str(path))
            observe.append(new, path=str(path))
            dropped = observe.prune(
                {"observability": {"enabled": True, "events_path": "events.jsonl",
                                   "retention_days": 30}},
                path=str(path),
                now=datetime(2026, 8, 29, tzinfo=timezone.utc),
            )
            events = observe.read(path)
            self.assertEqual(dropped, 1)
            self.assertEqual([e["run_id"] for e in events], ["new"])


class PrivacyTests(unittest.TestCase):
    def test_redaction_strips_prompts_diffs_and_secrets(self):
        ev = observe.make_event(
            "route_decision", run_id="run-redact", ts="2026-08-29T00:00:00+00:00",
            prompt="do the secret task",
            task_body="full brief text",
            diff="--- a/x\n+++ b/x",
            credentials="sk-live-secret",
            customer_data="Acme Corp invoice",
            note="token sk-abcdefghijklmnopqrstuvwxyz and Bearer abc.def",
        )
        self.assertNotIn("prompt", ev)
        self.assertNotIn("task_body", ev)
        self.assertNotIn("diff", ev)
        self.assertNotIn("credentials", ev)
        self.assertNotIn("customer_data", ev)
        blob = json.dumps(ev)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz", blob)
        self.assertNotIn("Bearer abc.def", blob)
        self.assertNotIn("full brief text", blob)

    def test_path_sanitization_removes_absolute_user_paths(self):
        ev = observe.make_event(
            "route_decision", run_id="run-path", ts="2026-08-29T00:00:00+00:00",
            park_reason=f"PARK: cannot read {Path.home()}/git/secret-brief.md",
        )
        blob = json.dumps(ev)
        self.assertNotIn(str(Path.home()), blob)
        self.assertNotIn("/Users/", blob)
        self.assertNotIn("/home/", blob)
        self.assertEqual(observe.validate_event(ev), [])

    def test_never_infers_user_identity(self):
        with mock.patch.dict(os.environ, {"USER": "constantine", "LOGNAME": "constantine",
                                          "HOME": str(Path.home())}):
            self.assertIsNone(observe.default_actor_id(None, None))
            self.assertEqual(observe.default_actor_id(None, "default"), "profile:default")
            hashed = observe.normalize_actor_id("constantine@example.com")
            self.assertTrue(hashed.startswith("actor:"))
            self.assertNotIn("constantine", hashed)
            ev = observe.make_event(
                "route_decision", run_id="run-id", ts="2026-08-29T00:00:00+00:00",
                actor_id=None, profile_id=None,
            )
            self.assertIsNone(ev["actor_id"])
            blob = json.dumps(ev)
            self.assertNotIn("constantine", blob)

    def test_multi_user_separation(self):
        a = observe.event_from_route_decision(
            _decision(), run_id="run-a", ts="2026-08-29T00:00:00+00:00", actor_id="team-a",
        )
        parked = _decision(routing_satisfied=False, park_reason="PARK: no usable implement seat")
        parked["dispatcher"] = dict(parked["dispatcher"], requested="opus-5", effective=None,
                                    satisfied=False)
        b = observe.event_from_route_decision(
            parked, run_id="run-b", ts="2026-08-29T00:00:00+00:00", actor_id="team-b",
        )
        report = observe.analyze([a, b])
        self.assertEqual(report["by_actor"]["team-a"]["routing_success"], 1)
        self.assertEqual(report["by_actor"]["team-a"]["parked"], 0)
        self.assertEqual(report["by_actor"]["team-b"]["routing_success"], 0)
        self.assertEqual(report["by_actor"]["team-b"]["parked"], 1)
        self.assertEqual(report["by_actor"]["team-a"]["runs"], 1)
        self.assertEqual(report["by_actor"]["team-b"]["runs"], 1)


class MissingAndFallbackTests(unittest.TestCase):
    def test_missing_usage_and_token_fields_are_not_fabricated(self):
        ev = observe.event_from_route_decision(
            _decision(), run_id="run-miss", ts="2026-08-29T00:00:00+00:00",
            tokens=None,
        )
        self.assertFalse(ev["tokens"]["measured"])
        self.assertIsNone(ev["tokens"]["input"])
        self.assertIsNone(ev["tokens"]["cost_usd"])
        report = observe.analyze([ev])
        self.assertIsNone(report["tokens"]["token_per_success"])
        self.assertIsNone(report["tokens"]["cost_per_success_usd"])
        self.assertIn("not fabricated", report["tokens"]["unmeasured_note"])
        self.assertEqual(report["coverage"]["missing_fields"]["tokens"], 1)

    def test_token_per_success_only_uses_measured_successes(self):
        ok = observe.event_from_route_decision(
            _decision(), run_id="run-tok", ts="2026-08-29T00:00:00+00:00",
            tokens={"measured": True, "input": 100, "output": 50, "cost_usd": 0.02,
                    "source": "provider-report"},
        )
        other = observe.event_from_route_decision(
            _decision(), run_id="run-notok", ts="2026-08-29T00:00:00+00:00",
        )
        report = observe.analyze([ok, other])
        self.assertEqual(report["tokens"]["measured_runs"], 1)
        self.assertEqual(report["tokens"]["token_per_success"], 150)
        self.assertEqual(report["tokens"]["cost_per_success_usd"], 0.02)
        self.assertIsNone(report["tokens"]["unmeasured_note"])

    def test_fallback_attribution(self):
        d = _decision()
        d["dispatcher"] = {
            "satisfied": True, "requested": "grok-build", "effective": "codex-terra",
            "fallback_used": True, "intake_relay": False, "family": "openai",
            "seat": "codex-plan", "tier": "reserve",
        }
        ev = observe.event_from_route_decision(
            d, run_id="run-fb", ts="2026-08-29T00:00:00+00:00", actor_id="team-a",
        )
        self.assertTrue(ev["intake"]["fallback_used"])
        self.assertEqual(ev["intake"]["fallback_reason"], "recorded_unavailability")
        report = observe.analyze([ev])
        self.assertEqual(report["fallback_attribution"]["from"]["grok-build"], 1)
        self.assertEqual(report["fallback_attribution"]["to"]["codex-terra"], 1)
        self.assertIn("not a causal claim", report["fallback_attribution"]["note"])
        self.assertEqual(report["outcomes"]["fallback"], 1)

    def test_usage_starvation_and_handoff_parks(self):
        starve = _decision(routing_satisfied=False,
                           park_reason="PARK: no usable implement seat — intake spent")
        starve["dispatcher"]["tier"] = "spent"
        starve["implement"] = [{"seat": "(none)", "available": False, "why": "PARK"}]
        handoff = _decision(
            routing_satisfied=False,
            park_reason="PARK: restricted artifact(s) cannot transfer automatically: credentials",
            handoff={
                "allowed": False, "action": "park", "artifacts": ["brief", "credentials"],
                "restricted": ["credentials"], "unknown": [], "missing_required": [],
                "requires_user_permission": False, "authorship_changes_authority": False,
            },
        )
        report = observe.analyze([
            observe.event_from_route_decision(starve, run_id="s", ts="2026-08-29T00:00:00+00:00"),
            observe.event_from_route_decision(handoff, run_id="h", ts="2026-08-29T00:00:00+00:00"),
        ])
        self.assertGreaterEqual(report["usage_starvation"]["count"], 1)
        self.assertEqual(report["handoff_parks"]["count"], 1)
        self.assertGreaterEqual(report["handoff_parks"]["restricted"], 1)
        self.assertEqual(report["handoff_parks"]["requires_user_permission_true"], 0)
        self.assertEqual(report["handoff_parks"]["standing_review_authorization"], 0)

    def test_no_permission_loop_on_restricted_handoff(self):
        policy = json.loads((REPO / "config" / "handoff-policy.json").read_text())
        got = rr.evaluate_handoff(policy, ["brief", "credentials"])
        self.assertFalse(got["allowed"])
        self.assertFalse(got["requires_user_permission"])
        ev = observe.event_from_route_decision(
            _decision(routing_satisfied=False, park_reason=got["reason"], handoff=got),
            run_id="run-perm", ts="2026-08-29T00:00:00+00:00",
        )
        self.assertFalse(ev["handoff"]["requires_user_permission"])
        self.assertFalse(ev["handoff"]["authorship_changes_authority"])
        self.assertEqual(ev["handoff"]["authorization_basis"], "fail-closed-restricted")
        self.assertEqual(observe.validate_event(ev), [])

    def test_standing_authorization_park_is_observability_first_class(self):
        policy = json.loads((REPO / "config" / "handoff-policy.json").read_text())
        del policy["standing_review_authorization"]
        got = rr.evaluate_handoff(policy, ["brief", "repo-source"])
        self.assertEqual(got["authorization_basis"],
                         "fail-closed-standing-review-authorization")
        self.assertFalse(got["requires_user_permission"])
        code = observe.park_reason_code(got["reason"])
        self.assertEqual(code, "standing_review_authorization")
        self.assertIn(code, observe.HANDOFF_PARK_CODES)
        ev = observe.event_from_route_decision(
            _decision(routing_satisfied=False, park_reason=got["reason"], handoff=got),
            run_id="run-auth-park", ts="2026-08-30T00:00:00+00:00",
        )
        self.assertEqual(ev["terminal"]["park_reason_code"], "standing_review_authorization")
        self.assertEqual(ev["handoff"]["authorization_basis"],
                         "fail-closed-standing-review-authorization")
        self.assertFalse(ev["usage"]["starvation"])
        report = observe.analyze([ev])
        self.assertEqual(report["handoff_parks"]["count"], 1)
        self.assertEqual(report["handoff_parks"]["standing_review_authorization"], 1)
        self.assertEqual(report["usage_starvation"]["count"], 0)

    def test_separate_invocation_note_follows_review_scope(self):
        recipes = json.loads((REPO / "config" / "seat-exec.json").read_text())["recipes"]
        self.assertTrue(recipes["codex-sol"]["separate_invocation_when_dispatcher"])
        ctx = {"brief_path": "b", "worktree": "w", "branch": "br", "repo": ".",
               "output_path": "o", "preview_url": "u"}
        same = run_brief.plan_for_seat(
            "codex-sol", recipes, ctx, "review", dispatcher="codex-sol",
            review_scope="artifact-only",
        )
        self.assertIn("separate physical invocation", same["note"])
        family = run_brief.plan_for_seat(
            "opus-5", recipes, ctx, "review", dispatcher="opus-4.8",
            review_scope="artifact-only",
        )
        self.assertIn("separate physical invocation", family["note"])
        independent = run_brief.plan_for_seat(
            "opus-5", recipes, ctx, "review", dispatcher="codex-sol",
            review_scope="artifact-and-dispatch",
        )
        self.assertNotIn("note", independent)

    def test_reviewer_disagreement_and_fix_loop_retraction(self):
        route = observe.event_from_route_decision(
            _decision(), run_id="run-rev", ts="2026-08-29T00:00:00+00:00",
        )
        v1 = observe.make_event(
            "review_verdict", run_id="run-rev", ts="2026-08-29T00:01:00+00:00",
            provider="opus-5", verdict="ship", independence_group="anthropic",
            review_scope="artifact-and-dispatch",
        )
        v2 = observe.make_event(
            "review_verdict", run_id="run-rev", ts="2026-08-29T00:02:00+00:00",
            provider="codex-sol", verdict="blocked", independence_group="openai",
            review_scope="artifact-and-dispatch",
        )
        loops = observe.make_event(
            "terminal", run_id="run-rev", ts="2026-08-29T00:03:00+00:00",
            fix_loops=2, retractions=1,
            terminal={"status": "parked", "park_reason_code": "park"},
        )
        folded = observe.fold_run([route, v1, v2, loops])
        self.assertTrue(folded["reviewer_disagreement"])
        self.assertEqual(folded["fix_loops"], 2)
        self.assertEqual(folded["retractions"], 1)
        report = observe.analyze([route, v1, v2, loops])
        self.assertEqual(report["reviewer_disagreement"]["count"], 1)
        self.assertEqual(report["fix_loops"]["runs_with_loops"], 1)
        self.assertEqual(report["retractions"]["runs_with_retractions"], 1)
        self.assertFalse(report["causal_claim"])
        self.assertIn("Observational", report["disclaimer"])


class ConfigAndAuthorityTests(unittest.TestCase):
    def test_malformed_observability_config_fails_closed(self):
        errors = observe.validate_config({"enabled": "yes", "events_path": "../secret.jsonl",
                                          "retention_days": -1})
        self.assertTrue(any("enabled" in e for e in errors), errors)
        self.assertTrue(any(".." in e for e in errors), errors)
        self.assertTrue(any("retention_days" in e for e in errors), errors)
        privacy = observe.validate_config({
            "enabled": True, "events_path": "events.jsonl", "retention_days": 1,
            "privacy": {"forbid_task_bodies": False},
        })
        self.assertTrue(any("forbid_task_bodies" in e for e in privacy), privacy)
        doc.ERRORS.clear()
        doc.WARNINGS.clear()
        doc.check_observability({"observability": {
            "enabled": True, "events_path": "~/events.jsonl", "retention_days": 1,
        }})
        self.assertTrue(any("home directory" in e for e in doc.ERRORS), doc.ERRORS)

    def test_live_monitoring_config_is_valid(self):
        monitoring = json.loads((REPO / "config" / "monitoring.json").read_text())
        self.assertEqual(observe.validate_config(monitoring["observability"]), [])

    def test_telemetry_write_failure_does_not_flip_park_to_success(self):
        decision = _decision(
            routing_satisfied=False,
            park_reason="PARK: restricted artifact(s) cannot transfer automatically: credentials",
        )
        original = copy.deepcopy(decision)

        def boom(*_a, **_k):
            raise OSError("disk full")

        with mock.patch.object(observe, "append", boom):
            meta = observe.try_emit_route_decision(
                decision, source="resolve-route", record=True, actor_id="team-a",
            )
        self.assertFalse(meta["recorded"])
        self.assertIsNotNone(meta["write_error"])
        self.assertFalse(meta["routing_satisfied_unchanged"])
        self.assertEqual(decision["routing_satisfied"], False)
        self.assertEqual(decision, original)

    def test_malformed_config_does_not_change_routing(self):
        decision = _decision(routing_satisfied=False, park_reason="PARK: x")
        with mock.patch.object(observe, "observability_config",
                               return_value={"enabled": "nope"}):
            meta = observe.try_emit_route_decision(
                decision, source="resolve-route", record=True,
            )
        self.assertFalse(meta["recorded"])
        self.assertIn("malformed", meta["write_error"])
        self.assertFalse(decision["routing_satisfied"])


class RuntimeEmitTests(unittest.TestCase):
    def _route_json(self, extra, env):
        buf = io.StringIO()
        argv = ["--class", "internal-notes", "--json", *extra]
        with contextlib.redirect_stdout(buf):
            with mock.patch.dict(os.environ, env, clear=False):
                rc = rr.main(argv)
        self.assertEqual(rc, 0)
        return json.loads(buf.getvalue())

    def test_resolve_route_emit_does_not_change_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"MB_DATA_DIR": tmp, "MB_OBSERVABILITY": "1"}
            silent = self._route_json(["--no-record"], env)
            recorded = self._route_json(
                ["--record", "--run-id", "run-emit-1", "--actor-id", "team-a"], env,
            )
            keys = ("class", "scale", "review_depth", "routing_satisfied", "park_reason",
                    "authors", "dispatcher", "handoff", "review", "gates", "risk_flags")
            self.assertEqual({k: silent[k] for k in keys}, {k: recorded[k] for k in keys})
            self.assertTrue(recorded["observability"]["recorded"])
            events = observe.read(Path(tmp) / "orchestration-events.jsonl")
            self.assertTrue(events)
            self.assertEqual(events[-1]["actor_id"], "team-a")
            self.assertNotIn("prompt", events[-1])
            blob = json.dumps(events[-1])
            self.assertNotIn("/Users/", blob)

    def test_resolve_route_park_stays_park_when_record_fails(self):
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            env = {"MB_DATA_DIR": tmp}
            with contextlib.redirect_stdout(buf):
                with mock.patch.dict(os.environ, env, clear=False):
                    with mock.patch.object(rr.observe, "append", side_effect=OSError("nope")):
                        rc = rr.main(["--class", "internal-notes",
                                      "--intake-provider", "not-a-provider",
                                      "--record", "--json"])
            got = json.loads(buf.getvalue())
        self.assertEqual(rc, 0)
        self.assertFalse(got["routing_satisfied"])
        self.assertEqual(got["handoff"]["action"], "park")
        self.assertFalse(got["handoff"]["requires_user_permission"])
        self.assertFalse(got["observability"]["recorded"])
        self.assertIsNotNone(got["observability"]["write_error"])

    def test_run_brief_dry_run_can_emit(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"MB_DATA_DIR": tmp}
            buf = io.StringIO()
            argv = ["--dry-run", "--class", "repo-code", "--scale", "routine", "--json",
                    "--record-observability", "--run-id", "run-brief-1", "--actor-id", "team-a"]
            with contextlib.redirect_stdout(buf):
                with mock.patch.dict(os.environ, env, clear=False):
                    rc = run_brief.main(argv)
            self.assertEqual(rc, 0)
            plan = json.loads(buf.getvalue())
            self.assertTrue(plan["dry_run"])
            self.assertTrue(plan["observability"]["recorded"])
            self.assertEqual(plan["observability"]["run_id"], "run-brief-1")
            events = observe.read(Path(tmp) / "orchestration-events.jsonl")
            kinds = {e["kind"] for e in events}
            self.assertTrue(kinds & {"run_plan", "route_decision"})
            self.assertTrue(all(e.get("dry_run") for e in events))
            self.assertFalse(any(e.get("handoff", {}).get("requires_user_permission")
                                 for e in events if e.get("handoff")))


class AnalysisCliTests(unittest.TestCase):
    def test_report_cli_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            ev = observe.event_from_route_decision(
                _decision(), run_id="run-cli", ts="2026-08-29T00:00:00+00:00",
                actor_id="team-a",
            )
            observe.append(ev, path=str(path))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = observe.main(["--path", str(path), "report", "--json"])
            self.assertEqual(rc, 0)
            report = json.loads(buf.getvalue())
            self.assertFalse(report["causal_claim"])
            self.assertEqual(report["runs"], 1)
            self.assertIn("by_role", report)
            self.assertIn("by_provider", report)

    def test_committed_fixture_analyzes(self):
        fixture = REPO / "model-evals" / "fixtures" / "observability" / "v1-correlated-runs.jsonl"
        events = observe.read(fixture)
        self.assertGreaterEqual(len(events), 4)
        report = observe.analyze(events)
        self.assertFalse(report["causal_claim"])
        self.assertGreaterEqual(report["runs"], 2)
        self.assertIn("team-a", report["by_actor"])
        self.assertIn("team-b", report["by_actor"])
        if report["tokens"]["measured_runs"] == 0:
            self.assertIsNone(report["tokens"]["token_per_success"])
            self.assertIsNone(report["tokens"]["cost_per_success_usd"])
        else:
            self.assertIsInstance(report["tokens"]["token_per_success"], (int, float))


class CompletenessFixTests(unittest.TestCase):
    def test_run_plan_matches_route_decision_and_excludes_review_d(self):
        route_dec = _decision(implement=[
            {"seat": "grok-build", "available": True, "tier": "available"},
            {"seat": "grok-bot-review-d", "available": True, "input_seat": True,
             "why": "Review D pixel walk"},
        ])
        parked = _decision(
            routing_satisfied=False,
            park_reason="PARK: no usable implement seat — quota spent",
            implement=[{"seat": "(none)", "available": False, "tier": "spent",
                        "why": "ALL worker seats spent"}],
            implement_requested=True, authors=[],
        )
        plan_ok = dict(route_dec)
        plan_ok["implement"] = [
            {"seat": "grok-build", "role": "implement", "available": True},
            {"seat": "grok-bot-review-d", "role": "review-d-input", "available": True},
        ]
        plan_ok["implement_decision"] = route_dec["implement"]
        plan_park = dict(parked)
        plan_park["implement"] = [{"seat": "(none)", "role": "implement"}]  # available omitted
        plan_park["implement_decision"] = parked["implement"]
        route_ev = observe.event_from_route_decision(
            route_dec, run_id="parity-ok", ts="2026-08-29T00:00:00+00:00", source="resolve-route")
        plan_ev = observe.event_from_route_decision(
            plan_ok, run_id="parity-ok", ts="2026-08-29T00:00:01+00:00", source="run-brief")
        self.assertEqual(route_ev["implementation"]["providers"], ["grok-build"])
        self.assertEqual(plan_ev["implementation"]["providers"], ["grok-build"])
        self.assertNotIn("grok-bot-review-d", plan_ev["implementation"]["providers"])
        self.assertTrue(plan_ev["implementation"]["requested"])
        folded = observe.fold_run([route_ev, plan_ev])
        self.assertEqual(folded["implementation"]["providers"], ["grok-build"])
        self.assertTrue(folded["routing_satisfied"])
        p_route = observe.event_from_route_decision(
            parked, run_id="parity-park", ts="2026-08-29T00:00:00+00:00", source="resolve-route")
        p_plan = observe.event_from_route_decision(
            plan_park, run_id="parity-park", ts="2026-08-29T00:00:01+00:00", source="run-brief")
        self.assertFalse(p_route["implementation"]["satisfied"])
        self.assertFalse(p_plan["implementation"]["satisfied"])
        self.assertTrue(p_route["usage"]["starvation"])
        self.assertTrue(p_plan["usage"]["starvation"])
        folded_p = observe.fold_run([p_route, p_plan])
        self.assertFalse(folded_p["routing_satisfied"])
        self.assertTrue(folded_p["usage"]["starvation"])

    def test_emit_on_run_brief_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"MB_DATA_DIR": tmp, "MB_OBSERVABILITY": "0"}
            buf = io.StringIO()
            argv = ["--dry-run", "--class", "repo-code", "--scale", "routine", "--json",
                    "--record-observability", "--run-id", "only-plan", "--actor-id", "team-a"]
            with contextlib.redirect_stdout(buf):
                with mock.patch.dict(os.environ, env, clear=False):
                    rc = run_brief.main(argv)
            self.assertEqual(rc, 0)
            plan = json.loads(buf.getvalue())
            self.assertTrue(plan["observability"]["recorded"])
            events = observe.read(Path(tmp) / "orchestration-events.jsonl")
            self.assertEqual({e["kind"] for e in events}, {"run_plan"})
            self.assertTrue(all(e.get("implementation", {}).get("requested") for e in events))
            self.assertNotIn("grok-bot-review-d", events[0]["implementation"]["providers"])

    def test_record_flag_beats_env_disable(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"MB_DATA_DIR": tmp, "MB_OBSERVABILITY": "0"}
            silent = io.StringIO()
            with contextlib.redirect_stdout(silent):
                with mock.patch.dict(os.environ, env, clear=False):
                    rr.main(["--class", "internal-notes", "--json", "--run-id", "env-off",
                             "--actor-id", "team-a"])
            self.assertFalse(observe.read(Path(tmp) / "orchestration-events.jsonl"))
            recorded = io.StringIO()
            with contextlib.redirect_stdout(recorded):
                with mock.patch.dict(os.environ, env, clear=False):
                    rc = rr.main(["--class", "internal-notes", "--json", "--record",
                                  "--run-id", "cli-wins", "--actor-id", "team-a"])
            self.assertEqual(rc, 0)
            events = observe.read(Path(tmp) / "orchestration-events.jsonl")
            self.assertTrue(events)
            self.assertEqual(events[-1]["run_id"], "cli-wins")

    def test_prune_vs_append_loses_no_accepted_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text('{"schema_version":1,"event_id":"obs-v1-truncated"')  # no newline
            accepted = []
            monitoring = {"observability": {"enabled": True, "events_path": "events.jsonl",
                                            "retention_days": 365}}

            def writer(i):
                ev = observe.make_event(
                    "route_decision", run_id=f"keep-{i}", ts="2026-08-29T00:00:00+00:00",
                    actor_id="team-a",
                )
                observe.append(ev, path=str(path), monitoring=monitoring)
                accepted.append(ev["event_id"])

            def pruner():
                observe.prune(monitoring, path=str(path),
                              now=datetime(2026, 8, 29, tzinfo=timezone.utc))

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                futs = [pool.submit(writer, i) for i in range(16)] + [pool.submit(pruner) for _ in range(4)]
                for f in futs:
                    f.result()
            left = {e["event_id"] for e in observe.read(path)}
            self.assertTrue(set(accepted) <= left, f"lost {set(accepted) - left}")

    def test_windows_and_secret_ids_cannot_bypass_backstop(self):
        ev = observe.make_event(
            "route_decision",
            run_id=r"C:\Users\neo\secret-brief.md",
            ts="2026-08-29T00:00:00+00:00",
            actor_id=r"C:\Users\neo\id",
            note=r"failed at C:\Users\neo\repo\diff.patch token sk-abcdefghijklmnopqrstuvwxyz",
        )
        blob = json.dumps(ev)
        self.assertNotIn(r"C:\Users", blob)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz", blob)
        self.assertTrue(ev["run_id"].startswith("run:"))
        self.assertTrue(ev["actor_id"].startswith("actor:"))
        self.assertEqual(observe.validate_event(ev), [])
        uid = "550e8400-e29b-41d4-a716-446655440000"
        ok = observe.make_event(
            "route_decision", run_id=uid, ts="2026-08-29T00:00:00+00:00",
            actor_id="team-a",
        )
        self.assertEqual(ok["run_id"], uid)
        self.assertEqual(ok["actor_id"], "team-a")

    def test_starvation_excludes_capability_and_handoff_is_policy_only(self):
        cap = _decision(
            routing_satisfied=False,
            park_reason="PARK: no usable implement seat — intake has no live coding-capable provider",
            implement=[{"seat": "(none)", "available": False, "why": "PARK coding-capable"}],
        )
        conn = _decision(
            routing_satisfied=False,
            park_reason="PARK: --needs-mcp 'github' is not an active connector on codex-terra",
            implement=[{"seat": "(none)", "available": False}],
        )
        disp = _decision(
            routing_satisfied=False,
            park_reason="PARK: requested dispatcher 'not-a-provider' is not configured",
            handoff={"allowed": False, "action": "park", "artifacts": ["brief"],
                     "restricted": [], "unknown": [], "missing_required": [],
                     "requires_user_permission": False, "authorship_changes_authority": False},
        )
        report = observe.analyze([
            observe.event_from_route_decision(cap, run_id="cap", ts="2026-08-29T00:00:00+00:00"),
            observe.event_from_route_decision(conn, run_id="conn", ts="2026-08-29T00:00:00+00:00"),
            observe.event_from_route_decision(disp, run_id="disp", ts="2026-08-29T00:00:00+00:00"),
        ])
        self.assertEqual(report["usage_starvation"]["count"], 0)
        self.assertEqual(report["handoff_parks"]["count"], 0)

    def test_implement_not_requested_distinct_from_unsatisfied(self):
        none = observe.event_from_route_decision(
            _decision(implement=None, implement_requested=False, authors=[], routing_satisfied=True),
            run_id="no-impl", ts="2026-08-29T00:00:00+00:00",
        )
        unsat = observe.event_from_route_decision(
            _decision(implement=[{"seat": "(none)", "available": False}],
                      implement_requested=True, authors=[], routing_satisfied=False,
                      park_reason="PARK: no complete usable implementation path"),
            run_id="unsat", ts="2026-08-29T00:00:00+00:00",
        )
        self.assertFalse(none["implementation"]["requested"])
        self.assertIsNone(none["implementation"]["satisfied"])
        self.assertTrue(unsat["implementation"]["requested"])
        self.assertFalse(unsat["implementation"]["satisfied"])

    def test_numeric_tokens_without_measured_flag_stay_missing(self):
        ev = observe.event_from_route_decision(
            _decision(), run_id="tok-flag", ts="2026-08-29T00:00:00+00:00",
            tokens={"input": 99, "output": 3, "cost_usd": 1.25},
        )
        self.assertFalse(ev["tokens"]["measured"])
        self.assertIsNone(ev["tokens"]["input"])
        self.assertIsNone(ev["tokens"]["cost_usd"])
        report = observe.analyze([ev])
        self.assertIsNone(report["tokens"]["token_per_success"])

    def test_bootstrap_failure_records_unknown_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"MB_DATA_DIR": tmp}
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                with mock.patch.dict(os.environ, env, clear=False):
                    with self.assertRaises(SystemExit):
                        rr.main(["--class", "not-a-real-class", "--record",
                                 "--run-id", "boot-1", "--actor-id", "team-a", "--json"])
            events = observe.read(Path(tmp) / "orchestration-events.jsonl")
            self.assertTrue(events)
            self.assertEqual(events[-1]["kind"], "bootstrap_failure")
            self.assertFalse(events[-1]["routing_satisfied"])
            self.assertEqual(events[-1]["bootstrap"]["stage"], "pre-decision")

    def test_observe_import_failure_does_not_change_park(self):
        ns = argparse.Namespace(record=True, no_record=False, run_id="x", actor_id="team-a",
                                profile="default")
        decision = _decision(routing_satisfied=False, park_reason="PARK: x")
        with mock.patch.object(rr, "observe", None):
            with mock.patch.object(rr, "_OBS_IMPORT_ERROR", RuntimeError("boom"), create=True):
                meta = rr._emit_decision(decision, ns, 1)
        self.assertFalse(meta["recorded"])
        self.assertFalse(meta["routing_satisfied_unchanged"])
        self.assertFalse(decision["routing_satisfied"])

    def test_validate_events_reports_physical_line_after_corrupt(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            good = observe.make_event(
                "route_decision", run_id="ok-line", ts="2026-08-29T00:00:00+00:00",
                actor_id="team-a",
            )
            path.write_text(json.dumps(good) + "\n{not json}\n" + json.dumps(good) + "\n")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = observe.main(["--path", str(path), "validate-events", "--json"])
            self.assertNotEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            lines = [p["line"] for p in payload["problems"]]
            self.assertIn(2, lines)

    def test_event_id_pattern_enforced(self):
        ev = observe.make_event(
            "route_decision", run_id="pat", ts="2026-08-29T00:00:00+00:00",
        )
        ev["event_id"] = "not-a-valid-id"
        self.assertTrue(any("event_id" in e for e in observe.validate_event(ev)))


if __name__ == "__main__":
    unittest.main()
