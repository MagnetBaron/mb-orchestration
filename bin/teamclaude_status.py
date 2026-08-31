#!/usr/bin/env python3
"""Schema-bound, privacy-safe TeamClaude rotation status adapter.

TeamClaude's native status document contains account names.  Orca must not copy
those identities into logs, receipts, or dispatch output, so this adapter keeps
the native document process-local and emits aggregate counts only.  A model is
eligible on an account only when every quota dimension that governs it has a
fresh numeric value and remains below hard exhaustion:

  shared 5-hour AND shared weekly AND model-family weekly.

TeamClaude's switch threshold is a proactive rotation preference, not proof that
the remaining quota is gone.  Its native per-route eligibility remains an
additional account-selection gate, while this adapter treats only an exact
`rejected` verdict or full numeric utilization as quota exhaustion.  For Opus,
the family bucket is the shared weekly bucket.  Fable and Sonnet have their own
additional weekly buckets.  Declared inventory is a policy ceiling:
a smaller live subset is usable (and reported as degraded), but undeclared
accounts or model capability fail closed.  Missing or malformed live state also
fails closed, while a missing TeamClaude binary remains a graceful portable/CI
mode.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import math
import os
import re
import selectors
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mborch  # noqa: E402


DEFAULT_TIMEOUT_SECONDS = 8.0
MAX_OUTPUT_BYTES = 256 * 1024
MAX_PROBE_INTERVAL_SECONDS = 900.0
MAX_PROBE_AGE_SECONDS = 1800.0
FULL_UTILIZATION = 1.0
SUPPORTED_FAMILIES = ("opus", "fable", "sonnet")
MODEL_FOR_FAMILY = {
    "opus": "claude-opus-5",
    "fable": "claude-fable-5",
    "sonnet": "claude-sonnet-4-6",
}
DEFAULT_MODELS = (
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-fable-5",
)
FAMILY_BUCKET = {
    "opus": "unified7d",
    "fable": "unified7dFable",
    "sonnet": "unified7dSonnet",
}


class TeamClaudeStatusError(RuntimeError):
    """Base class for bounded command and schema failures."""


class OutputLimitError(TeamClaudeStatusError):
    pass


class StatusTimeoutError(TeamClaudeStatusError):
    pass


class StatusSchemaError(TeamClaudeStatusError):
    pass


class CommandResult(NamedTuple):
    returncode: int
    stdout: str
    stderr: str


def _stop_process(proc: subprocess.Popen) -> None:
    """Stop the status process group so a timed-out child cannot linger."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass


def run_bounded(
    argv: list[str],
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_output_bytes: int = MAX_OUTPUT_BYTES,
) -> CommandResult:
    """Run a local status command with wall-clock and combined-output bounds."""
    if timeout <= 0 or max_output_bytes <= 0:
        raise ValueError("timeout and max_output_bytes must be positive")
    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as exc:
        raise TeamClaudeStatusError("status process could not start") from exc

    if proc.stdout is None or proc.stderr is None:  # pragma: no cover - Popen contract
        _stop_process(proc)
        raise TeamClaudeStatusError("status process did not expose output pipes")

    selector = selectors.DefaultSelector()
    stdout_fd = proc.stdout.fileno()
    stderr_fd = proc.stderr.fileno()
    streams = {stdout_fd: bytearray(), stderr_fd: bytearray()}
    selector.register(proc.stdout, selectors.EVENT_READ)
    selector.register(proc.stderr, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout
    total = 0
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _stop_process(proc)
                raise StatusTimeoutError("status command timed out")
            events = selector.select(min(remaining, 0.25))
            if not events:
                continue
            for key, _ in events:
                chunk = os.read(key.fd, min(65536, max_output_bytes + 1))
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                total += len(chunk)
                if total > max_output_bytes:
                    _stop_process(proc)
                    raise OutputLimitError("status command exceeded output bound")
                streams[key.fd].extend(chunk)
        try:
            returncode = proc.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired as exc:
            _stop_process(proc)
            raise StatusTimeoutError("status command timed out") from exc
    except (StatusTimeoutError, OutputLimitError):
        raise
    except Exception:
        _stop_process(proc)
        raise
    finally:
        selector.close()
        proc.stdout.close()
        proc.stderr.close()

    try:
        stdout = bytes(streams[stdout_fd]).decode("utf-8", errors="strict")
        stderr = bytes(streams[stderr_fd]).decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise TeamClaudeStatusError("status command returned non-UTF-8 output") from exc
    return CommandResult(returncode=returncode, stdout=stdout, stderr=stderr)


def _family(value: str) -> str:
    lower = str(value or "").lower()
    for family in SUPPORTED_FAMILIES:
        if family in lower:
            return family
    raise ValueError(f"unsupported Claude model family: {value!r}")


def _number(value, field: str, *, required: bool = False) -> float | None:
    if value is None and not required:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StatusSchemaError(f"{field} must be a number")
    out = float(value)
    if not math.isfinite(out) or out < 0:
        raise StatusSchemaError(f"{field} must be finite and non-negative")
    return out


def _timestamp(value, field: str) -> datetime:
    if not isinstance(value, str):
        raise StatusSchemaError(f"{field} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise StatusSchemaError(f"{field} must be an ISO timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise StatusSchemaError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _validate_status(document) -> dict:
    if not isinstance(document, dict):
        raise StatusSchemaError("status root must be an object")
    threshold = _number(document.get("switchThreshold"), "switchThreshold", required=True)
    if threshold is None or not 0 < threshold <= 1:
        raise StatusSchemaError("switchThreshold must be greater than zero and at most one")
    accounts = document.get("accounts")
    if not isinstance(accounts, list):
        raise StatusSchemaError("accounts must be an array")

    seen_names = set()
    for index, account in enumerate(accounts):
        where = f"accounts[{index}]"
        if not isinstance(account, dict):
            raise StatusSchemaError(f"{where} must be an object")
        name = account.get("name")
        if not isinstance(name, str) or not name or name in seen_names:
            raise StatusSchemaError(f"{where}.name must be a unique non-empty string")
        seen_names.add(name)
        if account.get("type") not in {"oauth", "apikey"}:
            raise StatusSchemaError(f"{where}.type is not recognized")
        if not isinstance(account.get("disabled"), bool):
            raise StatusSchemaError(f"{where}.disabled must be a boolean")
        if account.get("status") not in {"active", "throttled", "exhausted", "error"}:
            raise StatusSchemaError(f"{where}.status is not recognized")
        for field in ("rateLimitedUntil", "pausedUntil"):
            if account.get(field) is not None:
                _timestamp(account[field], f"{where}.{field}")
        quota = account.get("quota")
        if not isinstance(quota, dict):
            raise StatusSchemaError(f"{where}.quota must be an object")
        for key in ("unified5h", "unified7d", "unified7dFable", "unified7dSonnet"):
            _number(quota.get(key), f"{where}.quota.{key}")
        for key in (
            "unifiedStatus",
            "unified5hStatus",
            "unified7dStatus",
            "unified7dFableStatus",
            "unified7dSonnetStatus",
        ):
            if quota.get(key) not in {None, "allowed", "allowed_warning", "rejected"}:
                raise StatusSchemaError(f"{where}.quota.{key} is not recognized")
        if quota.get("fableCapability") not in {
            None, "unknown", "supported", "unsupported",
        }:
            raise StatusSchemaError(
                f"{where}.quota.fableCapability is not recognized"
            )

    blocked = document.get("blockedModels", [])
    if not isinstance(blocked, list) or any(not isinstance(item, str) for item in blocked):
        raise StatusSchemaError("blockedModels must be an array of strings")
    routes = document.get("routes", [])
    if not isinstance(routes, list):
        raise StatusSchemaError("routes must be an array")
    for index, route in enumerate(routes):
        where = f"routes[{index}]"
        if not isinstance(route, dict):
            raise StatusSchemaError(f"{where} must be an object")
        matches = route.get("match")
        if not isinstance(matches, list) or any(not isinstance(item, str) for item in matches):
            raise StatusSchemaError(f"{where}.match must be an array of strings")
        route_accounts = route.get("accounts")
        if not isinstance(route_accounts, list):
            raise StatusSchemaError(f"{where}.accounts must be an array")
        for account_index, item in enumerate(route_accounts):
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                raise StatusSchemaError(
                    f"{where}.accounts[{account_index}] must contain a string name"
                )
            if not isinstance(item.get("eligible"), bool):
                raise StatusSchemaError(
                    f"{where}.accounts[{account_index}].eligible must be a boolean"
                )
    probe = document.get("probe")
    if not isinstance(probe, dict):
        raise StatusSchemaError("probe must be an object")
    if not isinstance(probe.get("enabled"), bool):
        raise StatusSchemaError("probe.enabled must be a boolean")
    interval = _number(probe.get("intervalSeconds"), "probe.intervalSeconds", required=True)
    if interval is None or interval < 0:
        raise StatusSchemaError("probe.intervalSeconds must be non-negative")
    probe_accounts = probe.get("accounts")
    if not isinstance(probe_accounts, list) or len(probe_accounts) != len(accounts):
        raise StatusSchemaError("probe.accounts must match the account fleet")
    probe_names = set()
    for index, item in enumerate(probe_accounts):
        where = f"probe.accounts[{index}]"
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise StatusSchemaError(f"{where} must contain a string name")
        if item["name"] in probe_names:
            raise StatusSchemaError("probe account names must be unique")
        probe_names.add(item["name"])
        if item.get("status") not in {
            "ok", "error", "timeout", "never", "running", "not-applicable",
        }:
            raise StatusSchemaError(f"{where}.status is not recognized")
        if item.get("lastProbedAt") is not None:
            _timestamp(item["lastProbedAt"], f"{where}.lastProbedAt")
    if probe_names != seen_names:
        raise StatusSchemaError("probe account identities do not match the account fleet")
    persistence = document.get("persistence")
    if persistence is not None:
        if not isinstance(persistence, dict):
            raise StatusSchemaError("persistence must be an object")
        if persistence.get("healthy") not in {True, False, None}:
            raise StatusSchemaError("persistence.healthy must be a boolean or null")
        for field in ("lastSuccessAt", "lastErrorAt"):
            if persistence.get(field) is not None:
                _timestamp(persistence[field], f"persistence.{field}")
        error_code = persistence.get("errorCode")
        if error_code is not None and (
            not isinstance(error_code, str)
            or re.fullmatch(r"[A-Z0-9_]{1,64}", error_code) is None
        ):
            raise StatusSchemaError("persistence.errorCode is malformed")
    return document


def _fresh_probe_accounts(
    document: dict,
    now: datetime | None = None,
) -> tuple[set[str], list[str], list[str]]:
    """Return fresh OAuth identities plus fleet problems and anonymous warnings.

    A bad fleet-wide probe configuration is unreconciled.  A stale or failed
    account probe is instead isolated to that account: it contributes no live
    eligibility, while fresh peers continue to rotate.  Only aggregate counts
    leave this process so account identities remain private.
    """
    probe = document["probe"]
    if probe.get("enabled") is not True:
        return set(), ["quota probe is disabled; live bucket freshness is not proven"], []
    interval = float(probe["intervalSeconds"])
    if interval < 30:
        return set(), ["quota probe interval is below the supported safety floor"], []
    if interval > MAX_PROBE_INTERVAL_SECONDS:
        return set(), ["quota probe interval exceeds the supported freshness ceiling"], []
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    max_age = min(MAX_PROBE_AGE_SECONDS, max(180.0, interval * 2 + 60.0))
    by_name = {item["name"]: item for item in probe["accounts"]}
    fresh = set()
    excluded = 0
    for account in document["accounts"]:
        if account["disabled"] or account["type"] != "oauth":
            continue
        state = by_name[account["name"]]
        if state.get("status") != "ok" or state.get("lastProbedAt") is None:
            excluded += 1
            continue
        age = (now - _timestamp(state["lastProbedAt"], "probe lastProbedAt")).total_seconds()
        if age < -30 or age > max_age:
            excluded += 1
            continue
        fresh.add(account["name"])
    warnings = []
    if excluded:
        warnings.append(
            "one or more enabled OAuth accounts were excluded because quota probes "
            f"were stale or unsuccessful ({excluded} excluded)"
        )
    return fresh, [], warnings


def declared_inventory(subscriptions: dict | None = None) -> dict:
    """Return declaration counts only; never expose configured seat identifiers."""
    source = subscriptions
    downgrade_markers: set[str] = set()
    if source is None:
        source = mborch.load_config("subscriptions.json", required=False)
        ledger_path = mborch.ledger_path()
        if ledger_path.exists():
            ledger = json.loads(ledger_path.read_text())
            if not isinstance(ledger, dict):
                raise StatusSchemaError("usage ledger root must be an object")
            downgrade_markers = {
                key.split(":", 1)[1]
                for key, value in ledger.items()
                if isinstance(key, str)
                and key.startswith("fable-downgrade:")
                and isinstance(value, dict)
                and value.get("grant_lost") == "fable"
            }
    rows = source.get("subscriptions", {}) if isinstance(source, dict) else {}
    if not isinstance(rows, dict):
        rows = {}
    account_count = 0
    family_counts = {family: 0 for family in SUPPORTED_FAMILIES}
    for subscription in rows.values():
        if not isinstance(subscription, dict):
            continue
        if str(subscription.get("vendor", "")).lower() != "anthropic":
            continue
        account_count += 1
        grants = subscription.get("grants")
        if not isinstance(grants, dict):
            grants = {}
        for family in SUPPORTED_FAMILIES:
            seat_id = subscription.get("seat_id")
            downgraded = (
                family == "fable"
                and isinstance(seat_id, str)
                and seat_id in downgrade_markers
            )
            if grants.get(family) is True and not downgraded:
                family_counts[family] += 1
    return {
        "account_count": account_count,
        "family_seat_counts": family_counts,
        "fable_downgrade_marker_count": len(downgrade_markers),
    }


def _matches(pattern: str, model: str) -> bool:
    return fnmatch.fnmatchcase(model.lower(), pattern.lower())


def _route_account_names(document: dict, model: str) -> set[str] | None:
    """Return names allowed by the first matching status route, or None for all."""
    for route in document.get("routes", []):
        if any(_matches(pattern, model) for pattern in route["match"]):
            return {item["name"] for item in route["accounts"]}
    return None


def _route_account_eligibility(document: dict, model: str) -> dict[str, bool] | None:
    """Return TeamClaude's native eligibility decision for a matching route."""
    for route in document.get("routes", []):
        if any(_matches(pattern, model) for pattern in route["match"]):
            return {item["name"]: item["eligible"] for item in route["accounts"]}
    return None


def _model_blocked(document: dict, model: str) -> bool:
    return any(_matches(pattern, model) for pattern in document.get("blockedModels", []))


def _future_hold(account: dict, now: datetime) -> bool:
    """Whether TeamClaude says this account is temporarily unavailable now."""
    for field in ("rateLimitedUntil", "pausedUntil"):
        value = account.get(field)
        if value is not None and _timestamp(value, field) > now:
            return True
    return False


def _account_capable(account: dict, family: str, allowed: set[str] | None) -> bool:
    if account["type"] != "oauth":
        return False
    if allowed is not None and account["name"] not in allowed:
        return False
    quota = account["quota"]
    if family == "fable" and quota.get("fableCapability") is not None:
        return quota["fableCapability"] == "supported"
    family_key = FAMILY_BUCKET[family]
    if _number(quota.get(family_key), "family bucket") is not None:
        return True
    # Compatibility with a native status producer that reports an exact bucket
    # verdict before it reports utilization.  In particular, a Fable-specific
    # `rejected` is both positive capability evidence and quota-exhaustion
    # evidence; treating it as an unknown/outage would suppress valid fallback.
    return quota.get(f"{family_key}Status") in {
        "allowed", "allowed_warning", "rejected",
    }


def _account_eligible(
    account: dict,
    family: str,
    threshold: float,
    allowed: set[str] | None,
    fresh_probe_accounts: set[str],
    native_route_eligibility: dict[str, bool] | None,
    now: datetime,
) -> bool:
    """Evaluate all quota gates independently; unknown state is ineligible."""
    if account["type"] == "oauth" and account["name"] not in fresh_probe_accounts:
        return False
    if (native_route_eligibility is not None
            and native_route_eligibility.get(account["name"]) is not True):
        return False
    if not _account_capable(account, family, allowed):
        return False
    if account["disabled"] or _future_hold(account, now):
        return False
    status = account["status"]
    if status == "throttled":
        # TeamClaude can leave the label in place until the next selection pass.
        # Only an explicitly expired hold is enough to treat that label as
        # recoverable; absent/future timing remains fail-closed.
        limited_until = account.get("rateLimitedUntil")
        if limited_until is None or _timestamp(limited_until, "rateLimitedUntil") > now:
            return False
    elif status != "active":
        return False
    quota = account["quota"]
    if quota.get("unifiedStatus") == "rejected":
        return False
    if quota.get("unified5hStatus") == "rejected":
        return False
    if quota.get("unified7dStatus") == "rejected":
        return False
    family_status = f"{FAMILY_BUCKET[family]}Status"
    if family_status != "unified7dStatus" and quota.get(family_status) == "rejected":
        return False
    shared_5h = _number(quota.get("unified5h"), "shared 5-hour bucket")
    shared_weekly = _number(quota.get("unified7d"), "shared weekly bucket")
    family_weekly = _number(quota.get(FAMILY_BUCKET[family]), "family weekly bucket")
    # `threshold` controls TeamClaude's preferred rotation point.  It cannot be
    # reused as an exhaustion boundary here: when all accounts reach (for
    # example) 98%, the final allowance must remain usable until the native
    # route rejects it or a bucket is actually full.
    del threshold
    return all(
        value is not None and value < FULL_UTILIZATION
        for value in (shared_5h, shared_weekly, family_weekly)
    )


def _account_quota_exhausted(account: dict, family: str, threshold: float) -> bool:
    """Positive proof that at least one applicable quota bucket is spent."""
    del threshold
    quota = account["quota"]
    keys = ["unified5h", "unified7d"]
    family_key = FAMILY_BUCKET[family]
    if family_key != "unified7d":
        keys.append(family_key)
    for key in keys:
        if quota.get(f"{key}Status") == "rejected":
            return True
        value = _number(quota.get(key), f"{key} quota")
        if value is not None and value >= FULL_UTILIZATION:
            return True
    return False


def summarize_status(
    document: dict,
    *,
    subscriptions: dict | None = None,
    models: tuple[str, ...] = DEFAULT_MODELS,
    now: datetime | None = None,
) -> dict:
    """Validate native status and return an identity-free aggregate."""
    document = _validate_status(document)
    declared = declared_inventory(subscriptions)
    accounts = document["accounts"]
    threshold = float(document["switchThreshold"])
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    oauth_accounts = [account for account in accounts if account["type"] == "oauth"]
    observed = {
        "account_count": len(oauth_accounts),
        "enabled_account_count": sum(
            not account["disabled"] for account in oauth_accounts
        ),
        "status_account_count": len(accounts),
        "excluded_non_oauth_account_count": len(accounts) - len(oauth_accounts),
    }
    problems = []
    warnings = []
    fresh_probe_accounts, probe_problems, probe_warnings = _fresh_probe_accounts(
        document, now=now,
    )
    problems.extend(probe_problems)
    warnings.extend(probe_warnings)
    if observed["account_count"] > declared["account_count"]:
        problems.append(
            "live account count exceeds the declared Anthropic subscription ceiling "
            f"({observed['account_count']} > {declared['account_count']})"
        )
    elif observed["account_count"] < declared["account_count"]:
        warnings.append(
            "live account fleet is a degraded subset of declared Anthropic subscriptions "
            f"({observed['account_count']} < {declared['account_count']})"
        )
    if observed["enabled_account_count"] < observed["account_count"]:
        warnings.append(
            "one or more observed TeamClaude accounts are disabled "
            f"({observed['enabled_account_count']} enabled of {observed['account_count']})"
        )
    if observed["excluded_non_oauth_account_count"]:
        warnings.append(
            "non-OAuth TeamClaude accounts are excluded from included Anthropic capacity "
            f"({observed['excluded_non_oauth_account_count']} excluded)"
        )
    if declared.get("fable_downgrade_marker_count", 0):
        warnings.append(
            "declared Fable ceiling includes operator-recorded downgrade markers "
            f"({declared['fable_downgrade_marker_count']} marker(s))"
        )
    native_persistence = document.get("persistence")
    if native_persistence is None:
        persistence = {
            "reported": False,
            "healthy": None,
            "error_code": None,
        }
        warnings.append(
            "TeamClaude does not report atomic quota-state persistence health; upgrade required"
        )
    else:
        persistence = {
            "reported": True,
            "healthy": native_persistence.get("healthy"),
            "error_code": native_persistence.get("errorCode"),
        }
        if persistence["healthy"] is not True:
            warnings.append(
                "TeamClaude quota-state persistence is degraded; live in-memory rotation remains usable"
            )

    model_routes = {}
    family_rows = {}
    for requested in dict.fromkeys(models):
        family = _family(requested)
        model = MODEL_FOR_FAMILY[family] if requested == family else requested
        allowed = _route_account_names(document, model)
        native_route_eligibility = _route_account_eligibility(document, model)
        blocked = _model_blocked(document, model)
        capable_accounts = [] if blocked else [
            account for account in accounts
            if _account_capable(account, family, allowed)
        ]
        capable = len(capable_accounts)
        eligible = 0 if blocked else sum(
            _account_eligible(
                account, family, threshold, allowed, fresh_probe_accounts,
                native_route_eligibility, now,
            )
            for account in accounts
        )
        temporarily_unavailable = sum(
            not account["disabled"]
            and account["status"] != "error"
            and account["name"] in fresh_probe_accounts
            and _future_hold(account, now)
            for account in capable_accounts
        )
        all_capable_quota_exhausted = bool(capable_accounts) and all(
            not account["disabled"]
            and account["status"] in {"active", "throttled", "exhausted"}
            and account["name"] in fresh_probe_accounts
            and not _future_hold(account, now)
            and _account_quota_exhausted(account, family, threshold)
            for account in capable_accounts
        )
        declared_count = declared["family_seat_counts"].get(family, 0)
        capability_ceiling_exceeded = capable > declared_count
        if capability_ceiling_exceeded:
            warnings.append(
                f"live {family} capability exceeds the declared policy ceiling "
                f"({capable} > {declared_count}); that family is blocked"
            )
            eligible = 0
            temporarily_unavailable = 0
            all_capable_quota_exhausted = False
        elif capable < declared_count:
            warnings.append(
                f"live {family} capability is a degraded subset of declarations "
                f"({capable} < {declared_count})"
            )
        row = {
            "model": model,
            "declared_seat_count": declared_count,
            "capable_account_count": capable,
            "eligible_account_count": eligible,
            "temporarily_unavailable_account_count": temporarily_unavailable,
            "all_capable_quota_exhausted": all_capable_quota_exhausted,
            "blocked_by_policy": blocked or capability_ceiling_exceeded,
            "capability_ceiling_exceeded": capability_ceiling_exceeded,
        }
        model_routes[model] = row
        if family not in family_rows or model == MODEL_FOR_FAMILY[family]:
            family_rows[family] = row

    reconciled = not problems
    requested_ready = bool(model_routes) and all(
        row["eligible_account_count"] > 0 for row in model_routes.values()
    )
    available = reconciled and requested_ready
    temporarily_unavailable = bool(model_routes) and not available and reconciled and all(
        row["eligible_account_count"] > 0
        or (
            row["temporarily_unavailable_account_count"] > 0
            and row["all_capable_quota_exhausted"] is False
            and row["blocked_by_policy"] is False
        )
        for row in model_routes.values()
    )
    return {
        "tool": "teamclaude",
        "transport_present": True,
        "service_reachable": True,
        "schema_valid": True,
        "available": available,
        "readiness": (
            "ready" if available
            else "temporarily_unavailable" if temporarily_unavailable
            else "blocked"
        ),
        "reconciled": reconciled,
        "switch_threshold": threshold,
        "declared": declared,
        "observed": observed,
        "persistence": persistence,
        "models": family_rows,
        "model_routes": model_routes,
        "problems": problems,
        "warnings": warnings,
        "status": (
            "live rotation ready; using the fresh anonymous fleet"
            + (" with degraded warnings" if warnings else "")
            if available
            else "live rotation temporarily unavailable; wait for the reported hold to expire"
            if temporarily_unavailable
            else "live rotation blocked; inspect aggregate problems and model eligibility"
        ),
    }


def _unavailable(
    *,
    transport_present: bool,
    service_reachable: bool | None,
    error_code: str,
    status: str,
    evaluated: bool = True,
) -> dict:
    return {
        "tool": "teamclaude",
        "transport_present": transport_present,
        "service_reachable": service_reachable,
        "schema_valid": None if service_reachable is not True else False,
        "available": False if evaluated else None,
        "readiness": "blocked" if evaluated else "not evaluated",
        "reconciled": False,
        "models": {},
        "model_routes": {},
        "persistence": {"reported": False, "healthy": None, "error_code": None},
        "problems": [status],
        "warnings": [],
        "error_code": error_code,
        "status": status,
    }


def inspect_status(
    *,
    subscriptions: dict | None = None,
    models: tuple[str, ...] = DEFAULT_MODELS,
    executable: str | None = None,
    runner=run_bounded,
) -> dict:
    """Run and aggregate `teamclaude status --json` without leaking identities."""
    path = executable or os.environ.get("TEAMCLAUDE_STATUS_BIN") or shutil.which("teamclaude")
    if not path:
        return _unavailable(
            transport_present=False,
            service_reachable=None,
            error_code="transport_absent",
            status=(
                "TeamClaude transport absent; Anthropic routing is parked because "
                "no verified direct-account route exists on this host"
            ),
        )
    try:
        result = runner([path, "status", "--json"])
    except (StatusTimeoutError, OutputLimitError):
        return _unavailable(
            transport_present=True,
            service_reachable=None,
            error_code="status_bounded_failure",
            status="TeamClaude status exceeded a safety bound; rotation is blocked",
        )
    except TeamClaudeStatusError:
        # A resolver can be mocked independently of the filesystem in tests and
        # inventory tools.  If it resolves to an unstartable path, presence is
        # known but the service was never evaluated; never promote this to ready.
        return _unavailable(
            transport_present=True,
            service_reachable=None,
            error_code="status_start_failed",
            status="transport present; live rotation status was not evaluated",
            evaluated=False,
        )
    except Exception:
        return _unavailable(
            transport_present=True,
            service_reachable=None,
            error_code="status_start_failed",
            status="transport present; live rotation status was not evaluated",
            evaluated=False,
        )
    if result.returncode != 0:
        return _unavailable(
            transport_present=True,
            service_reachable=False,
            error_code="service_unreachable",
            status="transport present but the TeamClaude status service is unreachable",
        )
    try:
        native = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError):
        return _unavailable(
            transport_present=True,
            service_reachable=True,
            error_code="invalid_json",
            status="TeamClaude status returned invalid JSON; rotation is blocked",
        )
    try:
        return summarize_status(native, subscriptions=subscriptions, models=models)
    except (StatusSchemaError, ValueError):
        return _unavailable(
            transport_present=True,
            service_reachable=True,
            error_code="schema_mismatch",
            status="TeamClaude status schema does not match the supported contract; rotation is blocked",
        )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Privacy-safe aggregate of live TeamClaude rotation readiness."
    )
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        help="Claude model/family to evaluate (repeatable; default: Opus and Fable)",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    models = tuple(args.model) if args.model else DEFAULT_MODELS
    report = inspect_status(models=models)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"TeamClaude: {report['status']}")
        for model, row in report.get("model_routes", {}).items():
            print(
                f"  {model}: eligible {row['eligible_account_count']} / "
                f"capable {row['capable_account_count']} / "
                f"declared {row['declared_seat_count']}"
            )
        for problem in report.get("problems", []):
            print(f"  - {problem}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
