#!/usr/bin/env python3
"""Regression tests for exact Grok exhaustion -> Cursor Grok overflow.

This suite is intentionally separate from the broad doctor/model-registry tests:
the boundary is a provider error classifier plus one exact implementation recipe.
No provider process is invoked.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import stat
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock
from datetime import date
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RECORD = HERE / "record-429.sh"
WINDOWS = ROOT / "config" / "usage-windows.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


doctor = load_module("doctor_grok_cursor_overflow", HERE / "doctor.py")
model_registry = load_module("model_registry_grok_cursor_overflow", HERE / "model-registry.py")
resolve = load_module("resolve_route_grok_cursor_overflow", HERE / "resolve-route.py")
usage_status = load_module("usage_status_grok_cursor_overflow", HERE / "usage-status.py")
detect_capability = load_module(
    "detect_capability_grok_cursor_overflow", HERE / "detect-capability.py"
)
usage_record = load_module("usage_record_grok_cursor_overflow", HERE / "usage-record.py")


class RecordGrokExhaustionTests(unittest.TestCase):
    RESET = "2099-01-01T00:00:00Z"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = self.root / "usage-ledger.json"

    def tearDown(self):
        self.tmp.cleanup()

    def run_record(
        self, seat: str, message: str, *, reset: str | None = RESET,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update({
            "MB_USAGE_LEDGER": str(self.ledger),
            "MB_USAGE_WINDOWS": str(WINDOWS),
        })
        if reset is None:
            env.pop("MB_429_RESET", None)
        else:
            env["MB_429_RESET"] = reset
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            ["bash", str(RECORD), seat, message],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_only_exact_whole_grok_402_transport_errors_are_recorded(self):
        accepted = (
            "402 Payment Required: Grok Build usage balance exhausted",
            "HTTP 402: Grok Build usage balance exhausted",
            "Error: 402 Payment Required: Grok Build usage balance exhausted",
        )
        for message in accepted:
            with self.subTest(message=message):
                self.ledger.unlink(missing_ok=True)
                got = self.run_record("grok-heavy", message)
                self.assertEqual(got.returncode, 0, got.stderr)
                entry = json.loads(self.ledger.read_text())["grok-heavy"]
                self.assertIs(entry["spent"], True)
                self.assertEqual(entry["spent_until"], self.RESET)
                self.assertEqual(
                    entry["note"],
                    "Grok Build 402 usage-balance-exhausted recorded by wrapper",
                )
                self.assertEqual(stat.S_IMODE(self.ledger.stat().st_mode), 0o600)

    def test_grok_exhaustion_without_reset_stays_spent_with_reset_unknown(self):
        got = self.run_record(
            "grok-heavy",
            "402 Payment Required: Grok Build usage balance exhausted",
            reset=None,
        )
        self.assertEqual(got.returncode, 0, got.stderr)
        entry = json.loads(self.ledger.read_text())["grok-heavy"]
        self.assertIs(entry["spent"], True)
        self.assertIsNone(entry["spent_until"])

        status = subprocess.run(
            ["python3", str(HERE / "usage-status.py"), "--json", "--ledger", str(self.ledger)],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(status.returncode, 0, status.stderr)
        row = next(item for item in json.loads(status.stdout)["seats"]
                   if item["seat"] == "grok-heavy")
        self.assertEqual(row["tier"], "spent")
        self.assertEqual(row["state"], "SPENT (reset unknown)")
        self.assertIsNone(row["reset_effective"])

    def test_unknown_reset_does_not_inherit_an_anchored_schedule(self):
        row = usage_status.seat_state(
            "anchored-weekly",
            {
                "meter": "anchored weekly test",
                "family": "xai",
                "drain": "full",
                "billing": "included",
                "windows": [{
                    "kind": "weekly",
                    "weekday": "Sun",
                    "time": "22:00",
                    "tz": "America/Chicago",
                }],
            },
            {"anchored-weekly": {"spent": True, "spent_until": None}},
        )
        self.assertEqual(row["tier"], "spent")
        self.assertEqual(row["state"], "SPENT (reset unknown)")
        self.assertIsNotNone(row["next_reset"])
        self.assertIsNone(row["reset_effective"])
        self.assertIsNone(row["runway_seconds"])

    def test_python_ledger_writers_time_out_instead_of_spinning_forever(self):
        cases = (
            (
                detect_capability,
                lambda: detect_capability.write_ledger(
                    lambda data: data.__setitem__("test", {"spent": True})
                ),
            ),
            (
                usage_record,
                lambda: usage_record.write_ledger_pct("codex-plan", 50),
            ),
        )
        for module, call in cases:
            with self.subTest(module=module.__name__):
                ledger = self.root / f"{module.__name__}.json"
                lock = Path(f"{ledger}.lock")
                lock.mkdir()
                with mock.patch.object(module.mborch, "ledger_path", return_value=ledger), \
                        mock.patch.object(module, "LEDGER_LOCK_TIMEOUT_SECONDS", 0.01), \
                        mock.patch.object(module, "LEDGER_LOCK_POLL_SECONDS", 0.001), \
                        self.assertRaisesRegex(TimeoutError, "timed out waiting"):
                    call()
                self.assertFalse(ledger.exists())
                self.assertTrue(lock.is_dir())

    def test_all_ledger_writers_reclaim_a_dead_pid_lock(self):
        dead_pid = 2_147_483_647
        cases = (
            (
                detect_capability,
                lambda: detect_capability.write_ledger(
                    lambda data: data.__setitem__("test", {"spent": True})
                ),
            ),
            (
                usage_record,
                lambda: usage_record.write_ledger_pct("codex-plan", 50),
            ),
        )
        for module, call in cases:
            with self.subTest(module=module.__name__):
                ledger = self.root / f"dead-{module.__name__}.json"
                lock = Path(f"{ledger}.lock")
                lock.mkdir()
                (lock / "owner.json").write_text(json.dumps({
                    "pid": dead_pid,
                    "token": "a" * 32,
                    "created": 1.0,
                }))
                with mock.patch.object(module.mborch, "ledger_path", return_value=ledger):
                    call()
                self.assertTrue(ledger.exists())
                self.assertFalse(lock.exists())

        shell_lock = Path(f"{self.ledger}.lock")
        shell_lock.mkdir()
        (shell_lock / "owner.json").write_text(json.dumps({
            "pid": dead_pid,
            "token": "b" * 32,
            "created": 1.0,
        }))
        got = self.run_record("codex-plan", "HTTP 429 rate limit exceeded")
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertFalse(shell_lock.exists())

    def test_all_ledger_writers_never_steal_a_live_pid_lock(self):
        cases = (
            (
                detect_capability,
                lambda: detect_capability.write_ledger(
                    lambda data: data.__setitem__("test", {"spent": True})
                ),
            ),
            (
                usage_record,
                lambda: usage_record.write_ledger_pct("codex-plan", 50),
            ),
        )
        for module, call in cases:
            with self.subTest(module=module.__name__):
                ledger = self.root / f"live-{module.__name__}.json"
                lock = Path(f"{ledger}.lock")
                token = module.mborch.acquire_directory_lock(
                    lock, timeout_seconds=1, poll_seconds=0.001,
                )
                try:
                    with mock.patch.object(module.mborch, "ledger_path", return_value=ledger), \
                            mock.patch.object(module, "LEDGER_LOCK_TIMEOUT_SECONDS", 0.01), \
                            mock.patch.object(module, "LEDGER_LOCK_POLL_SECONDS", 0.001), \
                            self.assertRaisesRegex(TimeoutError, "timed out waiting"):
                        call()
                    self.assertFalse(ledger.exists())
                    self.assertTrue(lock.is_dir())
                finally:
                    self.assertTrue(module.mborch.release_directory_lock(lock, token))

        shell_lock = Path(f"{self.ledger}.lock")
        token = detect_capability.mborch.acquire_directory_lock(
            shell_lock, timeout_seconds=1, poll_seconds=0.001,
        )
        try:
            got = self.run_record(
                "codex-plan", "HTTP 429 rate limit exceeded",
                extra_env={"MB_LEDGER_LOCK_TIMEOUT": "0.03"},
            )
            self.assertNotEqual(got.returncode, 0)
            self.assertIn("timed out waiting", got.stderr)
            self.assertFalse(self.ledger.exists())
            self.assertTrue(shell_lock.is_dir())
        finally:
            self.assertTrue(
                detect_capability.mborch.release_directory_lock(shell_lock, token)
            )

    def test_recycled_live_pid_owner_does_not_wedge_shared_ledger_lock(self):
        lock = Path(f"{self.ledger}.lock")
        lock.mkdir()
        (lock / "owner.json").write_text(json.dumps({
            "pid": os.getpid(),
            "token": "c" * 32,
            "created": 1.0,
        }))
        token = detect_capability.mborch.acquire_directory_lock(
            lock, timeout_seconds=0.1, poll_seconds=0.001,
        )
        try:
            owner = json.loads((lock / "owner.json").read_text())
            self.assertEqual(owner["pid"], os.getpid())
            self.assertNotEqual(owner["token"], "c" * 32)
        finally:
            self.assertTrue(
                detect_capability.mborch.release_directory_lock(lock, token)
            )

    def test_directory_lock_release_is_serialized_with_generation_checks(self):
        lock = Path(f"{self.ledger}.lock")
        token = detect_capability.mborch.acquire_directory_lock(
            lock, timeout_seconds=1, poll_seconds=0.001,
        )
        started = threading.Event()
        finished = threading.Event()
        result = []

        def release():
            started.set()
            result.append(detect_capability.mborch.release_directory_lock(lock, token))
            finished.set()

        with detect_capability.mborch.path_lock_guard(lock):
            thread = threading.Thread(target=release)
            thread.start()
            self.assertTrue(started.wait(1))
            time.sleep(0.03)
            self.assertFalse(finished.is_set(),
                             "release cannot pass the generation guard mid-check")
        thread.join(1)
        self.assertEqual(result, [True])
        self.assertFalse(lock.exists())

    def test_metered_monthly_cap_is_fail_closed_and_executable(self):
        seat = {
            "meter": "metered review",
            "family": "open-weight",
            "drain": "full",
            "billing": "metered",
            "monthly_cap_usd": 20,
            "windows": [{"kind": "none"}],
        }
        unknown = usage_status.seat_state("review-e", seat, {})
        self.assertEqual(unknown["tier"], "spent")
        self.assertIn("spend unknown", unknown["state"])
        now = usage_status._now(usage_status.DEFAULT_TZ)
        fresh = {
            "monthly_spend_period": now.strftime("%Y-%m"),
            "updated": now.isoformat(),
        }
        below = usage_status.seat_state(
            "review-e", seat,
            {"review-e": {**fresh, "monthly_spend_usd": 19.99}},
        )
        self.assertTrue(below["usable"])
        self.assertTrue(below["monthly_spend_fresh"])
        capped = usage_status.seat_state(
            "review-e", seat, {"review-e": {**fresh, "monthly_spend_usd": 20}},
        )
        self.assertEqual(capped["tier"], "spent")
        self.assertIn("monthly cap", capped["state"])

        invalid_rows = (
            {**fresh, "monthly_spend_usd": float("nan")},
            {**fresh, "monthly_spend_usd": float("inf")},
            {**fresh, "monthly_spend_usd": -1},
            {"monthly_spend_usd": 1, "monthly_spend_period": "2020-01",
             "updated": "2020-01-15T00:00:00+00:00"},
            {"monthly_spend_usd": 1, "monthly_spend_period": now.strftime("%Y-%m"),
             "updated": "2020-01-15T00:00:00+00:00"},
        )
        for row in invalid_rows:
            with self.subTest(row=row):
                state = usage_status.seat_state("review-e", seat, {"review-e": row})
                self.assertEqual(state["tier"], "spent")
                self.assertFalse(state["usable"])
                self.assertFalse(state["monthly_spend_fresh"])

    def test_invalid_or_past_explicit_reset_fails_without_write(self):
        for reset in ("not-a-date", "2000-01-01T00:00:00Z"):
            with self.subTest(reset=reset):
                self.ledger.unlink(missing_ok=True)
                got = self.run_record(
                    "grok-heavy", "HTTP 429 rate limit exceeded", reset=reset
                )
                self.assertNotEqual(got.returncode, 0)
                self.assertIn("future UTC ISO", got.stderr)
                self.assertFalse(self.ledger.exists())

    def test_generic_402_auth_payment_and_completion_text_write_nothing(self):
        rejected = (
            "402 Payment Required",
            "HTTP 402: payment required",
            "Grok Build usage balance exhausted",
            "HTTP 402: usage balance exhausted",
            "401 Unauthorized: Grok Build usage balance exhausted",
            "A completion says: 402 Payment Required: Grok Build usage balance exhausted",
            "A completion says:\n402 Payment Required: Grok Build usage balance exhausted",
            "402 Payment Required: Grok Build usage balance exhausted.",
            "402 payment Required: Grok Build usage balance exhausted",
            "402 Payment Required: grok Build usage balance exhausted",
            "HTTP 402: Grok Build Usage balance exhausted",
        )
        for message in rejected:
            with self.subTest(message=message):
                self.ledger.unlink(missing_ok=True)
                got = self.run_record("grok-heavy", message)
                self.assertEqual(got.returncode, 0, got.stderr)
                self.assertFalse(self.ledger.exists())

        got = self.run_record(
            "codex-plan", "402 Payment Required: Grok Build usage balance exhausted"
        )
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertFalse(self.ledger.exists())

    def test_registered_429_still_records_and_unknown_seat_fails_before_write(self):
        got = self.run_record("codex-plan", "HTTP 429 rate limit exceeded")
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertIn("codex-plan", json.loads(self.ledger.read_text()))

        before = self.ledger.read_bytes()
        got = self.run_record("invented-seat", "HTTP 429 rate limit exceeded")
        self.assertNotEqual(got.returncode, 0)
        self.assertIn("unknown seat", got.stderr)
        self.assertEqual(self.ledger.read_bytes(), before)

    def test_no_reset_is_invented_for_weekly_monthly_or_mixed_window_seats(self):
        for seat in ("grok-heavy", "cursor-models", "codex-plan"):
            with self.subTest(seat=seat):
                self.ledger.unlink(missing_ok=True)
                got = self.run_record(
                    seat, "HTTP 429 rate limit exceeded", reset=None,
                )
                self.assertEqual(got.returncode, 0, got.stderr)
                entry = json.loads(self.ledger.read_text())[seat]
                self.assertIs(entry["spent"], True)
                self.assertIsNone(entry["spent_until"])

    def test_no_reset_defaults_to_five_hours_only_for_rolling_five_hour_seat(self):
        got = self.run_record(
            "claude-max", "HTTP 429 rate limit exceeded", reset=None,
        )
        self.assertEqual(got.returncode, 0, got.stderr)
        entry = json.loads(self.ledger.read_text())["claude-max"]
        self.assertIs(entry["spent"], True)
        self.assertIsInstance(entry["spent_until"], str)

    def test_rolling_default_rejects_missing_or_non_numeric_hours(self):
        for hours in (None, "5", "five"):
            with self.subTest(hours=hours):
                self.ledger.unlink(missing_ok=True)
                window = {"kind": "rolling"}
                if hours is not None:
                    window["hours"] = hours
                windows = self.root / f"windows-{str(hours)}.json"
                windows.write_text(json.dumps({
                    "seats": {"test-seat": {"windows": [window]}},
                }))
                got = self.run_record(
                    "test-seat", "HTTP 429 rate limit exceeded", reset=None,
                    extra_env={"MB_USAGE_WINDOWS": str(windows)},
                )
                self.assertEqual(got.returncode, 0, got.stderr)
                entry = json.loads(self.ledger.read_text())["test-seat"]
                self.assertIs(entry["spent"], True)
                self.assertIsNone(entry["spent_until"])

    def test_malformed_ledger_is_preserved_and_temp_lock_are_cleaned(self):
        before = b"not-json\n"
        self.ledger.write_bytes(before)
        got = self.run_record("grok-heavy", "HTTP 429 rate limit exceeded")
        self.assertNotEqual(got.returncode, 0)
        self.assertEqual(self.ledger.read_bytes(), before)
        self.assertFalse(Path(f"{self.ledger}.lock").exists())
        self.assertEqual(list(self.root.glob("usage-ledger.json.tmp.*")), [])

    def test_concurrent_registered_writes_are_serialized_without_lost_update(self):
        env = os.environ.copy()
        env.update({
            "MB_USAGE_LEDGER": str(self.ledger),
            "MB_USAGE_WINDOWS": str(WINDOWS),
            "MB_429_RESET": self.RESET,
        })
        procs = [
            subprocess.Popen(
                ["bash", str(RECORD), seat, "HTTP 429 rate limit exceeded"],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            for seat in ("codex-plan", "grok-heavy")
        ]
        for proc in procs:
            _out, err = proc.communicate(timeout=10)
            self.assertEqual(proc.returncode, 0, err)
        self.assertEqual(
            set(json.loads(self.ledger.read_text())), {"codex-plan", "grok-heavy"}
        )

    def test_confirmed_grok_exhaustion_parks_until_cursor_inference_is_live(self):
        healthy = self.root / "healthy.json"
        healthy.write_text("{}\n")

        def resolve(ledger: Path) -> dict:
            got = subprocess.run(
                [
                    "python3", str(HERE / "resolve-route.py"),
                    "--class", "repo-code", "--scale", "routine", "--implement",
                    "--ledger", str(ledger), "--no-record", "--json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(got.returncode, 0, got.stderr)
            return json.loads(got.stdout)

        healthy_step = next(
            row for row in resolve(healthy)["implement"] if not row.get("input_seat")
        )
        self.assertEqual(healthy_step["seat"], "grok-build")

        got = self.run_record(
            "grok-heavy", "402 Payment Required: Grok Build usage balance exhausted"
        )
        self.assertEqual(got.returncode, 0, got.stderr)
        decision = resolve(self.ledger)
        overflow_step = next(
            row for row in decision["implement"] if not row.get("input_seat")
        )
        self.assertEqual(overflow_step["seat"], "(none)")
        self.assertFalse(overflow_step["available"])
        self.assertFalse(decision["routing_satisfied"])


class CursorOverflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.providers_root = json.loads((ROOT / "config" / "providers.json").read_text())
        cls.providers = cls.providers_root["providers"]
        cls.seat_exec = json.loads((ROOT / "config" / "seat-exec.json").read_text())
        cls.registry = json.loads((ROOT / "config" / "model-registry.json").read_text())

    def setUp(self):
        self.saved_errors = doctor.ERRORS[:]
        self.saved_warnings = doctor.WARNINGS[:]
        doctor.ERRORS.clear()
        doctor.WARNINGS.clear()

    def tearDown(self):
        doctor.ERRORS[:] = self.saved_errors
        doctor.WARNINGS[:] = self.saved_warnings

    def check(self, seat_exec=None, providers=None, registry=None) -> list[str]:
        doctor.ERRORS.clear()
        provs = providers or self.providers
        doctor.check_seat_exec(
            seat_exec or self.seat_exec,
            provs,
            set(provs),
            registry or self.registry,
        )
        return list(doctor.ERRORS)

    def test_exact_cursor_agent_recipe_and_honest_listing_evidence(self):
        provider = self.providers["cursor-grok"]
        route = self.registry["routes"][provider["route"]]
        recipe = self.seat_exec["recipes"]["cursor-grok"]
        self.assertEqual(provider["detect"], {"method": "command", "cmd": "cursor-agent"})
        self.assertEqual(provider["functions"], ["ide"])
        self.assertIs(provider["review_eligible"], False)
        self.assertIsNot(provider.get("dispatch_eligible"), True)
        self.assertFalse({"review", "dispatch"} & set(provider["capabilities"]))
        self.assertEqual(route["invocation_id"], "cursor-grok-4.6-xhigh")
        self.assertEqual(route["route_state"], "catalog_verified")
        self.assertEqual(route["evidence_strength"], "cli_listing")
        self.assertEqual(route["attestations"]["local_access_smoke"]["state"], "missing")
        matrix_row = next(
            line for line in model_registry.render_matrix(self.registry).splitlines()
            if line.startswith("| `grok-4.6-cursor`")
        )
        self.assertIn("| catalog_verified |", matrix_row)
        self.assertIn("| — | cursor-grok |", matrix_row)
        listing = [e for e in route["evidence"] if e.get("kind") == "cli_listing"][-1]
        self.assertIn("cursor-agent --list-models", listing["source"])
        self.assertIn("no inference", listing["source"].lower())
        self.assertNotIn("signal", listing)
        self.assertEqual(
            recipe["args_template"],
            [
                "--trust", "--print", "--workspace", "{worktree}", "--model",
                "cursor-grok-4.6-xhigh",
                "Read the scoped brief at {brief_path}. Implement only the authorized file "
                "scope in that brief inside this workspace; preserve unrelated changes and "
                "stop on any conflict.",
            ],
        )
        for cursor_recipe in (
            self.seat_exec["recipes"]["cursor-grok"],
            self.seat_exec["recipes"]["cursor-other-400"],
        ):
            self.assertFalse(
                {"--workdir", "--brief", "--yolo"}
                & set(cursor_recipe["args_template"])
            )
        errors = self.check()
        self.assertFalse(
            [error for error in errors if "cursor" in error.lower()],
            errors,
        )

    def test_cursor_overflow_requires_ledger_backed_grok_exhaustion(self):
        self.assertEqual(
            self.providers["cursor-grok"]["overflow_after_provider"],
            "grok-build",
        )
        self.assertEqual(self.providers["grok-build"]["usage_seat"], "grok-heavy")
        healthy = [{
            "seat": "grok-heavy", "tier": "available", "ledger": None,
        }]
        synthetic = [{
            "seat": "grok-heavy", "tier": "spent", "ledger": None,
        }]
        confirmed = [{
            "seat": "grok-heavy", "tier": "spent",
            "ledger": {
                "spent": True,
                "note": "429/usage-limit recorded by wrapper",
            },
        }]
        self.assertFalse(resolve.implementation_overflow_dependency_satisfied(
            "cursor-grok", self.providers, healthy,
        ))
        self.assertFalse(resolve.implementation_overflow_dependency_satisfied(
            "cursor-grok", self.providers, synthetic,
        ))
        self.assertTrue(resolve.implementation_overflow_dependency_satisfied(
            "cursor-grok", self.providers, confirmed,
        ))
        self.assertTrue(resolve.implementation_overflow_dependency_satisfied(
            "grok-build", self.providers, healthy,
        ))

    def test_cursor_overflow_accepts_only_live_legacy_wrapper_exhaustion(self):
        def row(ledger):
            return [{"seat": "grok-heavy", "tier": "spent", "ledger": ledger}]

        legacy = {
            "spent_until": "2099-01-01T00:00:00+00:00",
            "note": "429/usage-limit recorded by wrapper",
        }
        self.assertTrue(resolve.implementation_overflow_dependency_satisfied(
            "cursor-grok", self.providers, row(legacy),
        ))
        for rejected in (
            {"spent_until": "2020-01-01T00:00:00+00:00",
             "note": "429/usage-limit recorded by wrapper"},
            {"spent_until": "2099-01-01T00:00:00+00:00",
             "note": "manual tier-only claim"},
            {"spent": False, "spent_until": "2099-01-01T00:00:00+00:00",
             "note": "429/usage-limit recorded by wrapper"},
            {"spent": True, "note": "manual tier-only claim"},
        ):
            with self.subTest(rejected=rejected):
                self.assertFalse(resolve.implementation_overflow_dependency_satisfied(
                    "cursor-grok", self.providers, row(rejected),
                ))

    def test_cursor_overflow_dependency_uses_renamed_config_ids(self):
        providers = copy.deepcopy(self.providers)
        build = providers.pop("grok-build")
        cursor = providers.pop("cursor-grok")
        build["usage_seat"] = "renamed-build-seat"
        cursor["overflow_after_provider"] = "renamed-build"
        providers["renamed-build"] = build
        providers["renamed-cursor"] = cursor
        rows = [{
            "seat": "renamed-build-seat",
            "tier": "spent",
            "ledger": {
                "spent": True,
                "note": "429/usage-limit recorded by wrapper",
            },
        }]
        self.assertTrue(resolve.implementation_overflow_dependency_satisfied(
            "renamed-cursor", providers, rows,
        ))
        cursor["overflow_after_provider"] = "missing-build"
        self.assertFalse(resolve.implementation_overflow_dependency_satisfied(
            "renamed-cursor", providers, rows,
        ))

    def test_live_cursor_remains_inert_until_grok_is_confirmed_spent(self):
        providers = copy.deepcopy(self.providers_root)
        connectors = {"mcp_connectors": {}}
        base_rows = [
            {
                "seat": "grok-heavy", "subscription": "grok-heavy",
                "family": "xai", "tier": "available", "billing": "included",
                "intake": False, "window_kinds": ["weekly"],
                "runway_seconds": None, "ledger": None,
            },
            {
                "seat": "cursor-models", "subscription": "cursor-ultra",
                "family": "cursor-pool", "tier": "available", "billing": "included",
                "intake": False, "window_kinds": ["monthly"],
                "runway_seconds": None, "ledger": None,
            },
        ]
        # This test exercises selection after both routes are live.  The current
        # catalog deliberately keeps Cursor non-live until it gains a real smoke.
        with mock.patch.object(resolve.modelreg, "provider_route_is_live", return_value=True):
            healthy = resolve.pick_implement(
                providers, connectors, copy.deepcopy(base_rows), "repo-code",
                "", "", False, 0, self.registry,
            )
            healthy_step = next(row for row in healthy if not row.get("input_seat"))
            self.assertEqual(healthy_step["seat"], "grok-build")

            spent_rows = copy.deepcopy(base_rows)
            spent_rows[0].update({
                "tier": "spent",
                "ledger": {
                    "spent": True,
                    "note": "429/usage-limit recorded by wrapper",
                },
            })
            overflow = resolve.pick_implement(
                providers, connectors, spent_rows, "repo-code",
                "", "", False, 0, self.registry,
            )
            overflow_step = next(row for row in overflow if not row.get("input_seat"))
            self.assertEqual(overflow_step["seat"], "cursor-grok")

    def test_cursor_intake_cannot_bypass_exhaustion_gate_as_last_resort(self):
        providers = copy.deepcopy(self.providers_root)
        rows = [
            {
                "seat": "grok-heavy", "subscription": "grok-heavy",
                "family": "xai", "tier": "spent", "billing": "included",
                "intake": False, "window_kinds": ["weekly"],
                "runway_seconds": None, "ledger": None,
            },
            {
                "seat": "cursor-models", "subscription": "cursor-ultra",
                "family": "cursor-pool", "tier": "available", "billing": "included",
                "intake": True, "window_kinds": ["monthly"],
                "runway_seconds": None, "ledger": None,
            },
        ]
        with mock.patch.object(resolve.modelreg, "provider_route_is_live", return_value=True):
            decision = resolve.pick_implement(
                providers, {"mcp_connectors": {}}, rows, "repo-code",
                "", "", False, 0, self.registry,
            )
        self.assertFalse(any(
            step.get("seat") == "cursor-grok" and step.get("available", True)
            for step in decision
        ), decision)

    def test_doctor_rejects_cursor_contract_drift(self):
        mutations = []

        bad_recipe = copy.deepcopy(self.seat_exec)
        bad_recipe["recipes"]["cursor-grok"]["args_template"] = [
            "--workdir", "{worktree}", "--brief", "{brief_path}", "--yolo",
        ]
        mutations.append((bad_recipe, self.providers, self.registry, "exact approved argv"))

        bad_detect = copy.deepcopy(self.providers)
        bad_detect["cursor-grok"]["detect"]["cmd"] = "cursor"
        mutations.append((self.seat_exec, bad_detect, self.registry, "detect must be exact"))

        bad_route = copy.deepcopy(self.registry)
        bad_route["routes"]["grok-4.6-cursor"]["invocation_id"] = "grok-4.6"
        mutations.append((self.seat_exec, self.providers, bad_route, "invocation_id must be"))

        false_smoke = copy.deepcopy(self.registry)
        listing = [
            e for e in false_smoke["routes"]["grok-4.6-cursor"]["evidence"]
            if e.get("kind") == "cli_listing"
        ][0]
        listing["signal"] = "direct_invocation"
        mutations.append((self.seat_exec, self.providers, false_smoke, "must not masquerade"))

        false_live = copy.deepcopy(self.registry)
        false_live["routes"]["grok-4.6-cursor"]["route_state"] = "live_verified"
        mutations.append((self.seat_exec, self.providers, false_live, "terminal inference receipt"))

        bad_authority = copy.deepcopy(self.providers)
        bad_authority["cursor-grok"]["functions"].append("review")
        bad_authority["cursor-grok"]["review_eligible"] = True
        mutations.append((self.seat_exec, bad_authority, self.registry, "implementation-only"))

        for seats, providers, registry, needle in mutations:
            with self.subTest(needle=needle):
                errors = self.check(seats, providers, registry)
                self.assertTrue(any(needle in error for error in errors), errors)

    def test_doctor_permits_only_exact_receipt_attested_cursor_promotion(self):
        promoted = copy.deepcopy(self.registry)
        route = promoted["routes"]["grok-4.6-cursor"]
        route["route_state"] = "live_verified"
        route["evidence_strength"] = "local_smoke"
        route["attestations"]["local_access_smoke"] = {
            "state": "attested",
            "date": "2026-08-30",
            "source": "Recorded exact Cursor Agent terminal inference receipt.",
            "evidence_kind": "direct_invocation",
            "signal": "direct_invocation",
        }
        route["evidence"].append({
            "date": "2026-08-30",
            "route_state": "live_verified",
            "kind": "terminal_inference_receipt",
            "source": "Recorded exact Cursor Agent terminal inference receipt.",
            "signal": "direct_invocation",
            "terminal_receipt": {
                "harness": "cursor-agent",
                "invocation_id": "cursor-grok-4.6-xhigh",
                "exit_code": 0,
                "completed": True,
            },
        })
        # Isolate this Doctor contract from the generic six-attestation gate. A
        # real promotion must pass both; the corrected identity intentionally
        # cannot inherit the frozen old-invocation waivers.
        with mock.patch.object(doctor.model_registry, "route_is_live", return_value=True):
            errors = self.check(registry=promoted)
        self.assertFalse(
            [error for error in errors if "provider 'cursor-grok'" in error],
            errors,
        )

        malformed = copy.deepcopy(promoted)
        malformed["routes"]["grok-4.6-cursor"]["evidence"][-1] \
            ["terminal_receipt"]["invocation_id"] = "grok-4.6"
        with mock.patch.object(doctor.model_registry, "route_is_live", return_value=True):
            errors = self.check(registry=malformed)
        self.assertTrue(any("exact successful terminal inference receipt" in e for e in errors), errors)

        with mock.patch.object(doctor.model_registry, "route_is_live", return_value=False):
            errors = self.check(registry=promoted)
        self.assertTrue(any("frozen legacy waiver" in e for e in errors), errors)

    def test_specialized_grokbots_remain_explicitly_parked(self):
        for pid in (
            "grok-bot-review-d",
            "grok-bot-heat-map",
            "grok-bot-marketplace-intelligence",
        ):
            with self.subTest(pid=pid):
                provider = self.providers[pid]
                route = self.registry["routes"][provider["route"]]
                self.assertIs(provider["wired"], False)
                self.assertEqual(route["route_state"], "unwired")

        bad = copy.deepcopy(self.providers)
        bad["grok-bot-review-d"]["wired"] = True
        errors = self.check(providers=bad)
        self.assertTrue(any("grok-bot-review-d" in e and "parked" in e for e in errors), errors)

    def test_model_registry_frozen_identity_and_validation_match_exact_cursor_id(self):
        frozen = model_registry.LEGACY_WAIVER_IDENTITIES["grok-4.6-cursor"]
        self.assertEqual(frozen[4], "grok-4.6")
        errors = model_registry.validate(
            self.registry,
            providers=self.providers_root,
            as_of=date(2026, 8, 30),
        )
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
