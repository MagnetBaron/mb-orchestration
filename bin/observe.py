#!/usr/bin/env python3
"""observe — append-only, privacy-safe orchestration decision telemetry.

Records routing quality, usage fallback, review outcomes, and (only when a
provider actually reported them) token/cost figures. It never logs task bodies,
prompts, diffs, credentials, customer data, or absolute user paths, and it
never grants authority or changes a routing decision.

  observe.py append --kind route_decision --run-id R --event-json event.json
  observe.py report [--json] [--path FILE]
  observe.py prune
  observe.py validate-config
  observe.py validate-events [--path FILE]

Runtime log: $MB_DATA_DIR/orchestration-events.jsonl (gitignored).
Synthetic fixtures live under model-evals/fixtures/observability/.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import sys
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mborch  # noqa: E402

EVENT_SCHEMA_VERSION = 1
KINDS = ("route_decision", "run_plan", "review_verdict", "test_verdict",
         "terminal", "tokens", "bootstrap_failure")
SOURCES = ("resolve-route", "run-brief", "observe-cli")
HANDOFF_PARK_CODES = frozenset({
    "restricted_artifact", "unknown_artifact", "missing_required_artifact",
    "unknown_participant", "standing_review_authorization",
})
EVENT_ID_RE = re.compile(r"^obs-v[0-9]+-[a-f0-9]+$")
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
TERMINAL_STATUSES = ("routed", "parked", "planned", "landed")
VERDICTS = ("ship", "fix-list", "blocked")
TEST_VERDICTS = ("pass", "fail", "error", "skip")
CAUSAL_DISCLAIMER = (
    "Observational correlations only. These figures do not prove that a provider, "
    "profile, fallback, or review seat caused an outcome, and they must not be "
    "fed back as authority or used to fabricate missing token or cost data."
)

# Keys that must never persist. Nested dicts/lists are walked.
_FORBIDDEN_KEYS = frozenset({
    "prompt", "prompts", "task_body", "task_bodies", "body", "bodies",
    "diff", "diffs", "patch", "patches", "content", "contents",
    "credential", "credentials", "token", "tokens_secret", "password",
    "secret", "secrets", "api_key", "apikey", "authorization", "cookie",
    "customer", "customer_data", "pii", "email", "emails", "phone",
    "production_export", "export", "raw", "transcript", "messages",
    "text", "prose", "objective_text", "brief_body",
})
# Allowlisted token-telemetry keys (provider-reported usage, not secrets).
_TOKEN_ALLOW = frozenset({"tokens", "token_input", "token_output", "token_total"})

_ABS_PATH_RE = re.compile(
    r"(?i)(?:(?:/Users|/home|/private/var/folders|/var/folders|/root)[^\s\"']+"
    r"|(?:[A-Za-z]:[\\/][^\s\"']+)"
    r"|(?:\\\\[^\s\"']+))"
)
_UNIX_FILE_RE = re.compile(r"(?i)(?:^|[\s\"'=])(/[^\s\"']+\.(?:md|py|json|diff|patch|txt|toml|sh))")
_SECRET_RE = re.compile(
    r"(?i)\b(?:sk-[A-Za-z0-9]{8,}|ghp_[A-Za-z0-9]{8,}|glpat-[A-Za-z0-9\-_]{8,}|"
    r"xox[baprs]-[A-Za-z0-9-]{8,}|Bearer\s+[A-Za-z0-9._\-]+|"
    r"AKIA[0-9A-Z]{8,})"
)
_NOT_USAGE_STARVATION = (
    "model-registry", "no valid live route", "lacks mcp_bulk",
    "not an active connector", "wrong-route", "not dispatch-qualified",
    "unknown dispatcher", "unknown dispatcher profile", "restricted artifact",
    "unknown artifact", "required handoff artifact", "coding-capable",
    "standing_review_authorization", "not preauthorized",
    "implement/ide", "auth_blocked", "unwired", "catalog_verified",
    "required mcp",
)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_ACTOR_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,63}$")
_FINGERPRINT_KEYS = (
    "kind", "run_id", "source", "actor_id", "profile_id",
    "intake", "task", "implementation", "review", "handoff",
    "usage", "terminal", "outcomes", "provider", "verdict", "tokens",
    "integration_session",
)

_IDENTIFIER_KEYS = frozenset({
    "event_id", "run_id", "kind", "source", "actor_id", "profile_id",
    "provider", "providers", "authors", "requested", "effective", "family",
    "independence_group", "review_scope", "seat", "class", "scale",
    "review_depth", "action", "status", "park_reason_code", "fallback_reason",
    "role", "physical", "verdict", "schema_version",
})

_IDENTIFIER_PATHS = frozenset({
    ("integration_session", "runtime"),
    ("integration_session", "canonical_ids", "*"),
})


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_run_id() -> str:
    return str(uuid.uuid4())


# ------------------------------------------------------------------ config --

def observability_config(monitoring=None) -> dict:
    if monitoring is None:
        monitoring = mborch.load_config("monitoring.json", required=False) or {}
    obs = (monitoring or {}).get("observability")
    return obs if isinstance(obs, dict) else {}


def validate_config(obs) -> list[str]:
    """Fail-closed structural checks for the observability config block."""
    if obs is None or obs == {}:
        return []
    if not isinstance(obs, dict):
        return ["observability must be an object"]
    errors = []
    if "enabled" not in obs or not isinstance(obs.get("enabled"), bool):
        errors.append("observability.enabled must be a boolean")
    path = obs.get("events_path")
    if not isinstance(path, str) or not path.strip():
        errors.append("observability.events_path must be a non-empty string")
    else:
        parts = Path(path).parts
        if ".." in parts:
            errors.append("observability.events_path must not contain '..'")
        if path.startswith("~"):
            errors.append("observability.events_path must not expand a home directory")
    rd = obs.get("retention_days")
    if not isinstance(rd, int) or isinstance(rd, bool) or rd < 0:
        errors.append("observability.retention_days must be a non-negative integer")
    for flag in ("emit_on_resolve", "emit_on_run_brief", "require_explicit_actor_id"):
        if flag in obs and not isinstance(obs[flag], bool):
            errors.append(f"observability.{flag} must be a boolean")
    privacy = obs.get("privacy")
    if privacy is None:
        pass
    elif not isinstance(privacy, dict):
        errors.append("observability.privacy must be an object")
    else:
        for key in ("forbid_task_bodies", "forbid_absolute_paths",
                    "forbid_credentials", "pseudonymous_actors_only"):
            if key in privacy and privacy[key] is not True:
                errors.append(
                    f"observability.privacy.{key} must be true "
                    "(the privacy boundary is not optional)"
                )
    return errors


def events_path(monitoring=None, override=None) -> Path:
    if override:
        return Path(override).expanduser()
    return mborch.observability_path(monitoring)


def emit_enabled(obs, *, record=False, no_record=False, emit_key="emit_on_resolve") -> bool:
    """CLI flags outrank the environment toggle; the env toggle outranks config.

    Precedence (highest first):
      1. --no-record / --no-record-observability → never emit
      2. --record / --record-observability → always emit (even if MB_OBSERVABILITY=0)
      3. MB_OBSERVABILITY=0 → disable default/config emit
      4. monitoring.observability.enabled + emit_on_*
    """
    if no_record:
        return False
    if record:
        return True
    if os.environ.get("MB_OBSERVABILITY") == "0":
        return False
    if not obs or not obs.get("enabled"):
        return False
    return bool(obs.get(emit_key, True))


# ------------------------------------------------------------- privacy core --

def looks_like_abs_path(value: str) -> bool:
    if not value:
        return False
    if _ABS_PATH_RE.search(value):
        return True
    if re.match(r"^[A-Za-z]:[\\/]", value):
        return True
    if value.startswith("\\\\"):
        return True
    return False


def looks_like_secret(value: str) -> bool:
    return bool(value and _SECRET_RE.search(value))


def _hash_id(prefix: str, value: str) -> str:
    return f"{prefix}:{hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]}"


def normalize_public_id(raw, *, prefix="id") -> str | None:
    """Keep safe UUIDs/pseudonyms; hash path-like, secret-shaped, or free-text ids."""
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    if looks_like_abs_path(value) or looks_like_secret(value) or "@" in value or " " in value:
        return _hash_id(prefix, value)
    if "/" in value or "\\" in value:
        return _hash_id(prefix, value)
    if not _SAFE_ID_RE.match(value):
        return _hash_id(prefix, value)
    return value


def normalize_actor_id(raw) -> str | None:
    """Accept an explicit pseudonym. Never infer $USER/HOME/git identity."""
    got = normalize_public_id(raw, prefix="actor")
    if got is None:
        return None
    if got.startswith("actor:"):
        return got
    if not _ACTOR_RE.match(got):
        return _hash_id("actor", str(raw).strip())
    return got


def normalize_run_id(raw) -> str:
    got = normalize_public_id(raw, prefix="run")
    if not got:
        raise ValueError("event requires a run_id")
    return got


def default_actor_id(explicit, profile_id) -> str | None:
    """Pseudonym from --actor-id, else profile:<id>. Never os.getlogin()/$USER."""
    got = normalize_actor_id(explicit)
    if got:
        return got
    if profile_id:
        return f"profile:{normalize_actor_id(profile_id) or 'unknown'}"
    return None


def sanitize_text(value: str, *, identifier=False) -> str:
    if not value:
        return value
    if identifier:
        if looks_like_abs_path(value) or looks_like_secret(value):
            return _hash_id("id", value)
        return value
    value = _SECRET_RE.sub("<redacted>", value)
    value = _EMAIL_RE.sub("<redacted-email>", value)
    value = _ABS_PATH_RE.sub("<path>", value)

    def _file(match):
        prefix = match.group(0)[: len(match.group(0)) - len(match.group(1))]
        return prefix + "<path>/" + Path(match.group(1)).name

    value = _UNIX_FILE_RE.sub(_file, value)
    home = os.environ.get("HOME")
    if home:
        value = value.replace(home, "<home>")
        try:
            value = value.replace(str(Path(home).resolve()), "<home>")
        except Exception:
            pass
    return value


def _drop_forbidden_key(key: str) -> bool:
    k = key.lower().replace("-", "_")
    if k in _TOKEN_ALLOW:
        return False
    if k in _FORBIDDEN_KEYS:
        return True
    if k.endswith("_prompt") or k.endswith("_diff") or k.endswith("_secret"):
        return True
    if "credential" in k or "password" in k or "api_key" in k:
        return True
    return False


def sanitize(value, key=None, _path=()):
    """Drop forbidden keys and redact paths/secrets. Pure; does not infer identity."""
    if key is not None and _drop_forbidden_key(str(key)):
        return None
    path = _path + ((str(key),) if key is not None else ())
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if _drop_forbidden_key(str(k)):
                continue
            out[str(k)] = sanitize(v, k, path)
        return out
    if isinstance(value, list):
        return [sanitize(v, _path=path + ("*",)) for v in value]
    identifier = ((str(key) in _IDENTIFIER_KEYS if key is not None else False)
                  or path in _IDENTIFIER_PATHS)
    if isinstance(value, str):
        return sanitize_text(value, identifier=identifier)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return sanitize_text(str(value), identifier=identifier)


def privacy_backstop(value):
    """Final pass: absolute POSIX/Windows paths and secret-shaped values cannot persist."""
    if isinstance(value, dict):
        return {str(k): privacy_backstop(v) for k, v in value.items()
                if not _drop_forbidden_key(str(k)) or str(k) in _TOKEN_ALLOW}
    if isinstance(value, list):
        return [privacy_backstop(v) for v in value]
    if isinstance(value, str):
        if looks_like_secret(value):
            return _SECRET_RE.sub("<redacted>", value)
        if looks_like_abs_path(value):
            return _ABS_PATH_RE.sub("<path>", value)
        return value
    return value


# --------------------------------------------------------------- event core --

def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def event_id_for(payload: dict) -> str:
    """Idempotent id: same run/kind/decision fingerprint → same id (ts excluded)."""
    body = {k: payload.get(k) for k in _FINGERPRINT_KEYS}
    digest = hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()
    version = int(payload.get("schema_version") or EVENT_SCHEMA_VERSION)
    return f"obs-v{version}-{digest[:32]}"


def park_reason_code(reason) -> str | None:
    if not reason:
        return None
    r = str(reason).lower()
    if "standing_review_authorization" in r and (
            "missing" in r or "weakened" in r or "not preauthorized" in r):
        return "standing_review_authorization"
    if "restricted artifact" in r:
        return "restricted_artifact"
    if "unknown artifact" in r:
        return "unknown_artifact"
    if "required handoff artifact" in r:
        return "missing_required_artifact"
    if "handoff participant" in r:
        return "unknown_participant"
    if "not configured" in r and "dispatcher" in r:
        return "unknown_dispatcher"
    if "requested dispatcher" in r and "not configured" in r:
        return "unknown_dispatcher"
    if "not dispatch-qualified" in r:
        return "dispatcher_unqualified"
    if "unknown dispatcher profile" in r:
        return "unknown_profile"
    if "no live fallback" in r or "no live relay" in r:
        return "no_fallback"
    if "unavailable" in r and "dispatcher" in r:
        return "dispatcher_unavailable"
    if "no usable native reviewer" in r or "cross-family unsatisfied" in r:
        return "review_unsatisfied"
    if "independent" in r and "park" in r:
        return "review_unsatisfied"
    if any(s in r for s in _NOT_USAGE_STARVATION):
        return "park"
    if ("spent" in r and ("seat" in r or "usable" in r or "worker" in r or "intake" in r
                          or "quota" in r)) or "quota_spent" in r or "quota spent" in r:
        return "usage_starvation"
    if "no complete usable implementation" in r or "no usable implement" in r:
        return "implement_unsatisfied"
    if str(reason).upper().startswith("PARK"):
        return "park"
    return None


def _review_chain_summary(chain) -> list[dict]:
    out = []
    for entry in chain or []:
        if not isinstance(entry, dict):
            continue
        item = {
            "provider": entry.get("provider") or entry.get("seat"),
            "family": entry.get("family"),
            "independence_group": entry.get("independence_group"),
            "review_scope": entry.get("review_scope"),
            "dispatch_independent": entry.get("dispatch_independent"),
            "physical": list(entry.get("physical") or []) or None,
        }
        out.append({k: v for k, v in item.items() if v is not None})
    return out


def _is_implement_step(step) -> bool:
    if not isinstance(step, dict):
        return False
    if step.get("input_seat"):
        return False
    role = step.get("role")
    if role in ("review-d-input", "review", "review-d", "review-d-input-seat"):
        return False
    return True


def _implementation_summary(implement, authors, requested=None) -> dict:
    if requested is None:
        requested = implement is not None
    if not requested:
        return {
            "requested": False,
            "satisfied": None,
            "providers": [],
            "authors": [],
            "last_resort": False,
        }
    steps = [s for s in (implement or []) if _is_implement_step(s)]
    providers = []
    all_available = bool(steps)
    last_resort = False
    for s in steps:
        seat = s.get("seat")
        available = s.get("available", True)
        if seat in (None, "(none)") or available is False:
            all_available = False
            continue
        providers.append(seat)
        if s.get("last_resort"):
            last_resort = True
    if not steps:
        all_available = False
    return {
        "requested": True,
        "satisfied": all_available,
        "providers": providers,
        "authors": list(authors or []),
        "last_resort": last_resort,
    }


def _usage_starvation(decision) -> bool | None:
    """True only for recorded quota/usage exhaustion — never outage/capability/registry."""
    reason = str(decision.get("park_reason") or (decision.get("transition") or {}).get("park_reason") or "")
    reason_l = reason.lower()
    if any(s in reason_l for s in _NOT_USAGE_STARVATION):
        return False
    impl = decision.get("implement_decision")
    if impl is None:
        impl = decision.get("implement")
    spent_impl = False
    for s in impl or []:
        if not _is_implement_step(s):
            continue
        why = str(s.get("why") or "").lower()
        if s.get("tier") == "spent" or ("spent" in why and "usable" in why):
            spent_impl = True
            break
        if not s.get("available", True) and s.get("tier") == "spent":
            spent_impl = True
            break
    disp = decision.get("dispatcher") or {}
    spent_disp = disp.get("tier") == "spent" and not disp.get("satisfied")
    if spent_impl or spent_disp or park_reason_code(reason) == "usage_starvation":
        return True
    if decision.get("routing_satisfied"):
        return False
    return False


def _usage_summary(decision) -> dict:
    disp = decision.get("dispatcher") or {}
    review = decision.get("review") or {}
    measured = any(k in disp for k in ("tier", "seat", "satisfied"))
    seats = []
    if disp.get("seat"):
        seats.append({"seat": disp.get("seat"), "tier": disp.get("tier"), "role": "dispatcher"})
    for entry in (review.get("chain") or []):
        if isinstance(entry, dict) and entry.get("seat"):
            seats.append({"seat": entry.get("seat"), "tier": entry.get("tier"), "role": "review"})
    return {
        "measured": measured,
        "starvation": _usage_starvation(decision) if measured else None,
        "dispatcher_tier": disp.get("tier"),
        "seats": seats or None,
        "source": "recorded-ledger" if measured else None,
    }


def _tokens_payload(tokens) -> dict:
    """Only persist provider-reported numeric fields. Never invent zeros."""
    if not isinstance(tokens, dict):
        return {"measured": False, "input": None, "output": None, "total": None,
                "cost_usd": None, "source": None}
    measured = tokens.get("measured")
    inp = tokens.get("input")
    out = tokens.get("output")
    total = tokens.get("total")
    cost = tokens.get("cost_usd")
    if measured is not True:
        # Numeric fields without an explicit measured flag stay missing.
        return {"measured": False, "input": None, "output": None, "total": None,
                "cost_usd": None, "source": None}
    payload = {
        "measured": bool(measured),
        "input": inp if isinstance(inp, (int, float)) and not isinstance(inp, bool) else None,
        "output": out if isinstance(out, (int, float)) and not isinstance(out, bool) else None,
        "total": total if isinstance(total, (int, float)) and not isinstance(total, bool) else None,
        "cost_usd": cost if isinstance(cost, (int, float)) and not isinstance(cost, bool) else None,
        "source": tokens.get("source") if isinstance(tokens.get("source"), str) else None,
    }
    if payload["measured"] and payload["total"] is None:
        parts = [v for v in (payload["input"], payload["output"]) if v is not None]
        payload["total"] = sum(parts) if parts else None
    if not payload["measured"]:
        payload.update({"input": None, "output": None, "total": None, "cost_usd": None, "source": None})
    return payload


def make_event(kind, *, run_id, ts, source="observe-cli", actor_id=None, profile_id=None,
               **fields) -> dict:
    if kind not in KINDS:
        raise ValueError(f"unknown event kind {kind!r}; known: {', '.join(KINDS)}")
    run_id = normalize_run_id(run_id)
    if kind == "review_verdict" and fields.get("verdict") not in VERDICTS:
        raise ValueError(f"review_verdict needs verdict in {VERDICTS}")
    if kind == "test_verdict" and fields.get("verdict") not in TEST_VERDICTS:
        raise ValueError(f"test_verdict needs verdict in {TEST_VERDICTS}")
    ev = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "run_id": run_id,
        "ts": ts,
        "kind": kind,
        "source": source if source in SOURCES else "observe-cli",
        "actor_id": normalize_actor_id(actor_id),
        "profile_id": normalize_actor_id(profile_id) if profile_id else None,
        "dry_run": bool(fields.pop("dry_run", True)),
    }
    for key in ("intake", "task", "implementation", "review", "handoff", "usage",
                "timing", "terminal", "outcomes", "tokens", "verdict", "provider",
                "independence_group", "review_scope", "routing_satisfied", "integration_session"):
        if key in fields and fields[key] is not None:
            ev[key] = fields[key]
    extra = {k: v for k, v in fields.items()
             if k not in ev and k not in ("event_id",) and v is not None}
    ev.update(extra)
    if kind in ("route_decision", "run_plan", "tokens") or "tokens" in ev:
        ev["tokens"] = _tokens_payload(ev.get("tokens"))
    ev = privacy_backstop(sanitize(ev))
    ev["event_id"] = event_id_for(ev)
    return ev


def event_from_route_decision(decision, *, run_id, ts, source="resolve-route",
                              actor_id=None, profile_id=None, duration_ms=None,
                              tokens=None, dry_run=True) -> dict:
    """Map a resolve-route / run-brief decision onto the v1 event without reshaping routing."""
    decision = decision if isinstance(decision, dict) else {}
    disp = decision.get("dispatcher") or {}
    handoff = decision.get("handoff") or {}
    review = decision.get("review") or {}
    authors = list(decision.get("authors") or [])
    park = decision.get("park_reason") or (decision.get("transition") or {}).get("park_reason")
    routing_ok = bool(decision.get("routing_satisfied"))
    implement = decision.get("implement_decision")
    if implement is None:
        implement = decision.get("implement")
    implement_requested = decision.get("implement_requested")
    fallback_reason = None
    if disp.get("fallback_used"):
        fallback_reason = "intake_relay" if disp.get("intake_relay") else "recorded_unavailability"
    outcomes = {
        "test_verdict": None,
        "review_verdicts": [],
        "fix_loops": None,
        "retractions": None,
    }
    session_summary = decision.get("integration_session")
    if isinstance(session_summary, dict):
        runtime = session_summary.get("runtime")
        canonical_ids = session_summary.get("canonical_ids")
        session_summary = {
            "runtime": runtime,
            "canonical_ids": sorted({x for x in (canonical_ids or []) if isinstance(x, str) and x}),
        } if isinstance(runtime, str) and runtime else None
    else:
        session_summary = None
    return make_event(
        "run_plan" if source == "run-brief" else "route_decision",
        run_id=run_id, ts=ts, source=source, actor_id=actor_id, profile_id=profile_id,
        dry_run=dry_run,
        intake={
            "requested": disp.get("requested"),
            "effective": disp.get("effective"),
            "profile": disp.get("profile") or profile_id,
            "fallback_used": bool(disp.get("fallback_used")),
            "fallback_reason": fallback_reason,
            "intake_relay": bool(disp.get("intake_relay")),
            "satisfied": bool(disp.get("satisfied")),
            "family": disp.get("family"),
        },
        task={
            "class": decision.get("class"),
            "scale": decision.get("scale"),
            "risk_flags": list(decision.get("risk_flags") or []),
            "review_depth": decision.get("review_depth"),
        },
        implementation=_implementation_summary(implement, authors, requested=implement_requested),
        review={
            "satisfied": bool(review.get("satisfied")),
            "chain": _review_chain_summary(review.get("chain")),
            "author_exclusion": authors,
        },
        handoff={
            "allowed": bool(handoff.get("allowed")),
            "action": handoff.get("action"),
            "artifact_classes": list(handoff.get("artifacts") or []),
            "restricted": list(handoff.get("restricted") or []),
            "unknown": list(handoff.get("unknown") or []),
            "missing_required": list(handoff.get("missing_required") or []),
            "requires_user_permission": False,
            "authorship_changes_authority": False,
            "authorization_basis": handoff.get("authorization_basis"),
        },
        usage=_usage_summary(decision),
        timing={"duration_ms": duration_ms if isinstance(duration_ms, int) else None},
        terminal={
            "status": "routed" if routing_ok else "parked",
            "park_reason_code": park_reason_code(park),
        },
        outcomes=outcomes,
        integration_session=session_summary,
        tokens=tokens,
        routing_satisfied=routing_ok,
        gates={k: bool(v) for k, v in (decision.get("gates") or {}).items()},
    )


def validate_event(ev, *, strict=False) -> list[str]:
    if not isinstance(ev, dict):
        return ["event is not an object"]
    errors = []
    version = ev.get("schema_version")
    if not isinstance(version, int) or version < 1:
        errors.append("schema_version must be a positive integer")
    elif version > EVENT_SCHEMA_VERSION and strict:
        errors.append(f"strict mode rejects future schema_version {version}")
    for key in ("event_id", "run_id", "ts", "kind"):
        if not ev.get(key):
            errors.append(f"missing {key}")
    eid = ev.get("event_id")
    if isinstance(eid, str) and not EVENT_ID_RE.match(eid):
        errors.append("event_id does not match schema pattern")
    rid = ev.get("run_id")
    if isinstance(rid, str) and (looks_like_abs_path(rid) or looks_like_secret(rid)
                                 or not _SAFE_ID_RE.match(rid)):
        errors.append("run_id is not a safe identifier")
    kind = ev.get("kind")
    if kind not in KINDS:
        if strict:
            errors.append(f"unknown kind {kind!r}")
        # non-strict: tolerate future kinds
    if ev.get("actor_id") is not None and not isinstance(ev.get("actor_id"), str):
        errors.append("actor_id must be a string or null")
    elif isinstance(ev.get("actor_id"), str) and looks_like_abs_path(ev["actor_id"]):
        errors.append("actor_id contains an absolute path")
    handoff = ev.get("handoff")
    if isinstance(handoff, dict) and handoff.get("requires_user_permission"):
        errors.append("handoff.requires_user_permission must be false (no permission loop)")
    tokens = ev.get("tokens")
    if isinstance(tokens, dict) and tokens.get("measured") is not True:
        for k in ("input", "output", "total", "cost_usd"):
            if tokens.get(k) not in (None, False):
                # unmeasured runs must not carry invented numbers
                if tokens.get("measured") is False and tokens.get(k) is not None:
                    errors.append(f"tokens.{k} present while measured is false")
    # Privacy: absolute user paths and forbidden keys must not survive.
    blob = _canonical(ev)
    if looks_like_abs_path(blob) or "/Users/" in blob or "/home/" in blob:
        errors.append("event contains an absolute user path")
    for key in ev.keys():
        if _drop_forbidden_key(str(key)) and str(key) not in ("tokens",):
            errors.append(f"forbidden key {key!r} persisted")
    return errors


# -------------------------------------------------------------------- fold --

def _empty_run(run_id) -> dict:
    return {
        "run_id": run_id,
        "actor_id": None,
        "profile_id": None,
        "kinds": [],
        "event_ids": [],
        "intake": {},
        "task": {},
        "implementation": {},
        "review": {},
        "handoff": {},
        "usage": {"measured": False, "starvation": None},
        "timing": {"duration_ms": None},
        "terminal": {"status": None, "park_reason_code": None},
        "routing_satisfied": None,
        "fallback_used": None,
        "fallback_reason": None,
        "review_verdicts": [],
        "test_verdict": None,
        "fix_loops": None,
        "retractions": None,
        "reviewer_disagreement": False,
        "tokens": {"measured": False, "input": None, "output": None, "total": None,
                   "cost_usd": None, "source": None},
        "first_ts": None,
        "last_ts": None,
        "event_count": 0,
    }


def fold_run(events) -> dict:
    """Pure fold of one run_id's events. Missing measured fields stay None."""
    st = _empty_run(None)
    seen_ids = set()
    for ev in events:
        if not isinstance(ev, dict):
            continue
        eid = ev.get("event_id")
        if eid and eid in seen_ids:
            continue  # idempotent: first-wins
        if eid:
            seen_ids.add(eid)
        st["event_count"] += 1
        st["run_id"] = ev.get("run_id", st["run_id"])
        st["event_ids"].append(eid)
        kind = ev.get("kind")
        if kind:
            st["kinds"].append(kind)
        if st["first_ts"] is None:
            st["first_ts"] = ev.get("ts")
        st["last_ts"] = ev.get("ts")
        if ev.get("actor_id") and not st["actor_id"]:
            st["actor_id"] = ev.get("actor_id")
        if ev.get("profile_id") and not st["profile_id"]:
            st["profile_id"] = ev.get("profile_id")
        for section in ("intake", "task", "implementation", "review", "handoff", "usage",
                        "timing", "terminal"):
            incoming = ev.get(section)
            if isinstance(incoming, dict):
                merged = dict(st.get(section) or {})
                incoming = dict(incoming)
                if section == "usage" and merged.get("starvation") is True:
                    incoming["starvation"] = True
                if section == "implementation" and merged.get("satisfied") is False:
                    incoming["satisfied"] = False
                merged.update({k: v for k, v in incoming.items() if v is not None})
                st[section] = merged
        if ev.get("routing_satisfied") is False:
            st["routing_satisfied"] = False
        elif ev.get("routing_satisfied") is not None and st["routing_satisfied"] is not False:
            st["routing_satisfied"] = ev["routing_satisfied"]
        intake = st.get("intake") or {}
        st["fallback_used"] = intake.get("fallback_used")
        st["fallback_reason"] = intake.get("fallback_reason")
        if kind == "review_verdict":
            st["review_verdicts"].append({
                "provider": ev.get("provider"),
                "verdict": ev.get("verdict"),
                "independence_group": ev.get("independence_group"),
                "review_scope": ev.get("review_scope"),
                "ts": ev.get("ts"),
            })
        outcomes = ev.get("outcomes") if isinstance(ev.get("outcomes"), dict) else {}
        if outcomes.get("review_verdicts"):
            for item in outcomes["review_verdicts"]:
                if item not in st["review_verdicts"]:
                    st["review_verdicts"].append(item)
        if outcomes.get("test_verdict"):
            st["test_verdict"] = outcomes["test_verdict"]
        if kind == "test_verdict" and ev.get("verdict"):
            st["test_verdict"] = ev.get("verdict")
        if outcomes.get("fix_loops") is not None:
            st["fix_loops"] = outcomes["fix_loops"]
        if outcomes.get("retractions") is not None:
            st["retractions"] = outcomes["retractions"]
        if ev.get("fix_loops") is not None:
            st["fix_loops"] = ev["fix_loops"]
        if ev.get("retractions") is not None:
            st["retractions"] = ev["retractions"]
        tok = ev.get("tokens")
        if isinstance(tok, dict) and tok.get("measured") is True:
            st["tokens"] = _tokens_payload(tok)
        if kind == "terminal" and isinstance(ev.get("terminal"), dict):
            st["terminal"].update({k: v for k, v in ev["terminal"].items() if v is not None})
    verdicts = {v.get("verdict") for v in st["review_verdicts"] if v.get("verdict")}
    st["reviewer_disagreement"] = len(verdicts) > 1
    if st.get("fix_loops") is None and st["review_verdicts"]:
        st["fix_loops"] = sum(1 for v in st["review_verdicts"] if v.get("verdict") == "fix-list")
    return st


def run_ids(events) -> list:
    seen = []
    for ev in events:
        rid = ev.get("run_id") if isinstance(ev, dict) else None
        if rid is not None and rid not in seen:
            seen.append(rid)
    return seen


def fold_all(events) -> list[dict]:
    by = defaultdict(list)
    order = []
    for ev in events:
        if not isinstance(ev, dict) or not ev.get("run_id"):
            continue
        rid = ev["run_id"]
        if rid not in by:
            order.append(rid)
        by[rid].append(ev)
    return [fold_run(by[rid]) for rid in order]


# ---------------------------------------------------------------- analysis --

def _rate(n, d):
    return (n / d) if d else None


def analyze(events) -> dict:
    """Coverage, rates, and per-role/provider outcomes. Never fabricates tokens."""
    runs = fold_all(events)
    n = len(runs)
    routing_ok = sum(1 for r in runs if r.get("routing_satisfied") is True)
    parked = sum(1 for r in runs if (r.get("terminal") or {}).get("status") == "parked"
                 or r.get("routing_satisfied") is False)
    fallback = sum(1 for r in runs if r.get("fallback_used") is True)
    tokens_measured = [r for r in runs if (r.get("tokens") or {}).get("measured")]
    usage_measured = [r for r in runs if (r.get("usage") or {}).get("measured")]
    starved = [r for r in runs if (r.get("usage") or {}).get("starvation") is True]
    def _handoff_policy_park(r):
        code = (r.get("terminal") or {}).get("park_reason_code")
        hp = r.get("handoff") or {}
        return (code in HANDOFF_PARK_CODES
                or bool(hp.get("restricted")) or bool(hp.get("unknown"))
                or bool(hp.get("missing_required")))
    handoff_parked = [r for r in runs if _handoff_policy_park(r)]
    restricted = sum(1 for r in handoff_parked
                     if (r.get("terminal") or {}).get("park_reason_code") == "restricted_artifact"
                     or (r.get("handoff") or {}).get("restricted"))
    unknown_art = sum(1 for r in handoff_parked
                      if (r.get("terminal") or {}).get("park_reason_code") == "unknown_artifact"
                      or (r.get("handoff") or {}).get("unknown"))
    reviewed = [r for r in runs if r.get("review_verdicts")]
    disagreed = [r for r in reviewed if r.get("reviewer_disagreement")]
    looped = [r for r in runs if (r.get("fix_loops") or 0) > 0]
    retracted = [r for r in runs if (r.get("retractions") or 0) > 0]
    successes_measured = [r for r in tokens_measured if r.get("routing_satisfied") is True]
    token_sum = 0
    token_n = 0
    cost_sum = 0.0
    cost_n = 0
    for r in successes_measured:
        tok = r["tokens"]
        total = tok.get("total")
        if total is None:
            parts = [v for v in (tok.get("input"), tok.get("output")) if isinstance(v, (int, float))]
            total = sum(parts) if parts else None
        if isinstance(total, (int, float)):
            token_sum += total
            token_n += 1
        cost = tok.get("cost_usd")
        if isinstance(cost, (int, float)):
            cost_sum += cost
            cost_n += 1

    missing = {
        "actor_id": sum(1 for r in runs if not r.get("actor_id")),
        "tokens": n - len(tokens_measured),
        "usage": n - len(usage_measured),
        "review_verdict": n - len(reviewed),
        "test_verdict": sum(1 for r in runs if not r.get("test_verdict")),
        "fix_loops": sum(1 for r in runs if r.get("fix_loops") is None),
        "retractions": sum(1 for r in runs if r.get("retractions") is None),
        "duration_ms": sum(1 for r in runs if (r.get("timing") or {}).get("duration_ms") is None),
    }

    by_provider = defaultdict(lambda: {"runs": 0, "routing_success": 0, "parked": 0, "fallback_from": 0})
    by_role = defaultdict(lambda: {"runs": 0, "routing_success": 0, "parked": 0})
    by_actor = defaultdict(lambda: {"runs": 0, "routing_success": 0, "parked": 0, "fallback": 0})
    fallback_from = defaultdict(int)
    fallback_to = defaultdict(int)

    for r in runs:
        intake = r.get("intake") or {}
        impl = r.get("implementation") or {}
        review = r.get("review") or {}
        ok = r.get("routing_satisfied") is True
        park = (r.get("terminal") or {}).get("status") == "parked" or r.get("routing_satisfied") is False
        actor = r.get("actor_id") or "unknown"
        by_actor[actor]["runs"] += 1
        by_actor[actor]["routing_success"] += int(ok)
        by_actor[actor]["parked"] += int(park)
        by_actor[actor]["fallback"] += int(bool(r.get("fallback_used")))
        roles = []
        if intake.get("effective"):
            roles.append(("dispatch", intake["effective"]))
        for pid in impl.get("providers") or []:
            roles.append(("implement", pid))
        for entry in review.get("chain") or []:
            if isinstance(entry, dict) and entry.get("provider"):
                roles.append(("review", entry["provider"]))
        seen_p = set()
        for role, pid in roles:
            by_role[role]["runs"] += 1
            by_role[role]["routing_success"] += int(ok)
            by_role[role]["parked"] += int(park)
            if pid not in seen_p:
                by_provider[pid]["runs"] += 1
                by_provider[pid]["routing_success"] += int(ok)
                by_provider[pid]["parked"] += int(park)
                seen_p.add(pid)
        if r.get("fallback_used"):
            src = intake.get("requested")
            dst = intake.get("effective")
            if src:
                fallback_from[src] += 1
                by_provider[src]["fallback_from"] += 1
            if dst:
                fallback_to[dst] += 1

    return {
        "causal_claim": False,
        "disclaimer": CAUSAL_DISCLAIMER,
        "schema_version": EVENT_SCHEMA_VERSION,
        "runs": n,
        "events": len(events),
        "coverage": {
            "tokens_measured_pct": _rate(len(tokens_measured), n),
            "usage_measured_pct": _rate(len(usage_measured), n),
            "review_verdict_pct": _rate(len(reviewed), n),
            "actor_id_pct": _rate(n - missing["actor_id"], n),
            "missing_fields": missing,
        },
        "outcomes": {
            "routing_success": routing_ok,
            "routing_success_rate": _rate(routing_ok, n),
            "parked": parked,
            "park_rate": _rate(parked, n),
            "fallback": fallback,
            "fallback_rate": _rate(fallback, n),
        },
        "tokens": {
            "measured_runs": len(tokens_measured),
            "measured_routing_successes": token_n,
            "token_per_success": (token_sum / token_n) if token_n else None,
            "cost_per_success_usd": (cost_sum / cost_n) if cost_n else None,
            "unmeasured_note": None if token_n else (
                "unmeasured — no provider-reported token fields present; "
                "token-per-success is not fabricated"
            ),
        },
        "usage_starvation": {
            "count": len(starved),
            "rate": _rate(len(starved), n),
        },
        "handoff_parks": {
            "count": len(handoff_parked),
            "restricted": restricted,
            "unknown_artifact": unknown_art,
            "missing_required": sum(
                1 for r in handoff_parked
                if (r.get("terminal") or {}).get("park_reason_code") == "missing_required_artifact"
                or (r.get("handoff") or {}).get("missing_required")
            ),
            "standing_review_authorization": sum(
                1 for r in handoff_parked
                if (r.get("terminal") or {}).get("park_reason_code") == "standing_review_authorization"
                or (r.get("handoff") or {}).get("authorization_basis")
                == "fail-closed-standing-review-authorization"
            ),
            "requires_user_permission_true": sum(
                1 for r in runs if (r.get("handoff") or {}).get("requires_user_permission")
            ),
        },
        "reviewer_disagreement": {
            "reviewed_runs": len(reviewed),
            "count": len(disagreed),
            "rate_among_reviewed": _rate(len(disagreed), len(reviewed)),
        },
        "fix_loops": {
            "runs_with_loops": len(looped),
            "rate": _rate(len(looped), n),
            "mean_among_those": (
                sum(r["fix_loops"] for r in looped) / len(looped) if looped else None
            ),
        },
        "retractions": {
            "runs_with_retractions": len(retracted),
            "rate": _rate(len(retracted), n),
        },
        "fallback_attribution": {
            "from": dict(fallback_from),
            "to": dict(fallback_to),
            "note": "Attribution is the recorded requested→effective pair, not a causal claim.",
        },
        "by_provider": dict(by_provider),
        "by_role": dict(by_role),
        "by_actor": dict(by_actor),
    }


# --------------------------------------------------------------------- I/O --

def _lockfile(path: Path) -> Path:
    return path.with_name(path.name + ".lock")


@contextmanager
def log_lock(path: Path):
    """One exclusive lock for append, prune-read, rewrite, and replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = _lockfile(path).open("a+")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


def _append_unlocked(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as fh:
        fh.seek(0, os.SEEK_END)
        if fh.tell() > 0:
            fh.seek(fh.tell() - 1)
            if fh.read(1) != "\n":
                fh.write("\n")  # isolate a truncated tail before appending
        fh.write(line)
        if not line.endswith("\n"):
            fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())


def iter_log_lines(path) -> list[tuple[int, dict | None, str | None]]:
    """Physical line numbers. Corrupt/truncated lines are returned as errors, not dropped silently from numbering."""
    p = Path(path)
    if not p.exists():
        return []
    try:
        raw = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    out = []
    for lineno, line in enumerate(raw.splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except Exception:
            out.append((lineno, None, "corrupt"))
            continue
        if isinstance(obj, dict):
            out.append((lineno, obj, None))
        else:
            out.append((lineno, None, "not-object"))
    return out


def _prepare_payload(event) -> dict:
    payload = privacy_backstop(sanitize(event if isinstance(event, dict) else {}))
    if isinstance(payload.get("run_id"), str):
        try:
            payload["run_id"] = normalize_run_id(payload["run_id"])
        except ValueError:
            pass
    if payload.get("actor_id"):
        payload["actor_id"] = normalize_actor_id(payload["actor_id"])
    if "event_id" not in payload:
        payload["event_id"] = event_id_for(payload)
    return payload


def append(event, path=None, monitoring=None) -> Path:
    """Append one sanitized JSON line. Never rewrites existing lines."""
    p = events_path(monitoring, path)
    payload = _prepare_payload(event)
    line = json.dumps(payload, separators=(",", ":"), default=str)
    with log_lock(p):
        _append_unlocked(p, line)
    return p


def read(path=None, monitoring=None) -> list[dict]:
    """Read events; skip blank, truncated, and corrupt lines. Never rewrite."""
    p = path if isinstance(path, Path) else events_path(monitoring, path)
    return [obj for _, obj, err in iter_log_lines(p) if obj is not None and err is None]


def prune(monitoring=None, path=None, now=None) -> int:
    obs = observability_config(monitoring)
    days = int(obs.get("retention_days", (monitoring or {}).get("retention_days", 365)) or 0)
    if days <= 0:
        return 0
    p = events_path(monitoring, path)
    if not p.exists():
        return 0
    cutoff = (now or datetime.now(timezone.utc)).timestamp() - days * 86400
    with log_lock(p):
        kept, dropped = [], 0
        for _, ev, err in iter_log_lines(p):
            if ev is None or err is not None:
                continue
            ts = ev.get("ts")
            try:
                t = datetime.fromisoformat(ts).timestamp() if ts else None
            except Exception:
                t = None
            if t is None or t >= cutoff:
                kept.append(ev)
            else:
                dropped += 1
        tmp = p.with_name(p.name + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for ev in kept:
                fh.write(json.dumps(ev, separators=(",", ":"), default=str) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, p)
    return dropped


# ----------------------------------------------------------- runtime emit --

def try_emit_route_decision(decision, *, source, record=False, no_record=False,
                            run_id=None, actor_id=None, profile_id=None,
                            duration_ms=None, tokens=None, path=None,
                            emit_key="emit_on_resolve") -> dict:
    """Best-effort emit. Never raises into the router; never flips routing_satisfied."""
    meta = {"recorded": False, "event_id": None, "run_id": run_id, "write_error": None}
    routing_ok = bool((decision or {}).get("routing_satisfied"))
    try:
        monitoring = mborch.load_config("monitoring.json", required=False) or {}
        obs = observability_config(monitoring)
        cfg_errors = validate_config(obs) if obs else []
        if cfg_errors:
            meta["write_error"] = "malformed observability config: " + "; ".join(cfg_errors)
            meta["routing_satisfied_unchanged"] = routing_ok
            return meta
        if not emit_enabled(obs, record=record, no_record=no_record, emit_key=emit_key):
            meta["reason"] = "disabled"
            meta["routing_satisfied_unchanged"] = routing_ok
            return meta
        rid = run_id or new_run_id()
        profile = profile_id or (decision.get("dispatcher") or {}).get("profile")
        actor = default_actor_id(actor_id, profile)
        if obs.get("require_explicit_actor_id") and not normalize_actor_id(actor_id):
            actor = None
        event = event_from_route_decision(
            decision, run_id=rid, ts=now_iso(), source=source,
            actor_id=actor, profile_id=profile, duration_ms=duration_ms,
            tokens=tokens, dry_run=True,
        )
        append(event, path=path, monitoring=monitoring)
        meta.update({
            "recorded": True, "event_id": event["event_id"], "run_id": rid,
            "kind": event["kind"],
        })
    except Exception as exc:
        meta["write_error"] = f"{type(exc).__name__}: {exc}"
    meta["routing_satisfied_unchanged"] = routing_ok
    return meta


def try_emit_bootstrap_failure(*, reason_code, message, source="resolve-route",
                               record=False, no_record=False, run_id=None,
                               actor_id=None, profile_id=None, duration_ms=None,
                               path=None) -> dict:
    """Bounded pre-decision failure event. Never raises; never claims routing success."""
    meta = {"recorded": False, "event_id": None, "run_id": run_id, "write_error": None,
            "routing_satisfied_unchanged": False}
    try:
        monitoring = mborch.load_config("monitoring.json", required=False) or {}
        obs = observability_config(monitoring)
        cfg_errors = validate_config(obs) if obs else []
        if cfg_errors:
            meta["write_error"] = "malformed observability config: " + "; ".join(cfg_errors)
            return meta
        emit_key = "emit_on_run_brief" if source == "run-brief" else "emit_on_resolve"
        if not emit_enabled(obs, record=record, no_record=no_record, emit_key=emit_key):
            meta["reason"] = "disabled"
            return meta
        rid = run_id or new_run_id()
        event = make_event(
            "bootstrap_failure",
            run_id=rid, ts=now_iso(), source=source,
            actor_id=default_actor_id(actor_id, profile_id),
            profile_id=profile_id,
            dry_run=True,
            routing_satisfied=False,
            terminal={"status": "parked", "park_reason_code": reason_code},
            bootstrap={"reason_code": reason_code, "stage": "pre-decision"},
            note=sanitize_text(str(message)[:240]),
            timing={"duration_ms": duration_ms if isinstance(duration_ms, int) else None},
        )
        append(event, path=path, monitoring=monitoring)
        meta.update({"recorded": True, "event_id": event["event_id"], "run_id": rid,
                     "kind": event["kind"]})
    except Exception as exc:
        meta["write_error"] = f"{type(exc).__name__}: {exc}"
    return meta


# ----------------------------------------------------------------------- CLI ---

def _print_report(report):
    print("orchestration observability report")
    print("=" * 72)
    print(report["disclaimer"])
    print(f"causal_claim: {report['causal_claim']}")
    print(f"runs: {report['runs']}  events: {report['events']}")
    o = report["outcomes"]
    print(f"routing success: {o['routing_success']}  rate={o['routing_success_rate']}")
    print(f"parked: {o['parked']}  rate={o['park_rate']}")
    print(f"fallback: {o['fallback']}  rate={o['fallback_rate']}")
    t = report["tokens"]
    print(f"token-per-success: {t['token_per_success']}  "
          f"(measured successes={t['measured_routing_successes']})")
    if t.get("unmeasured_note"):
        print(f"  {t['unmeasured_note']}")
    print(f"usage starvation: {report['usage_starvation']['count']}  "
          f"rate={report['usage_starvation']['rate']}")
    print(f"handoff parks: {report['handoff_parks']['count']}  "
          f"restricted={report['handoff_parks']['restricted']}  "
          f"unknown={report['handoff_parks']['unknown_artifact']}")
    print(f"reviewer disagreement: {report['reviewer_disagreement']['count']} / "
          f"{report['reviewer_disagreement']['reviewed_runs']} reviewed")
    print(f"fix-loop runs: {report['fix_loops']['runs_with_loops']}  "
          f"retraction runs: {report['retractions']['runs_with_retractions']}")
    cov = report["coverage"]
    print(f"coverage: tokens={cov['tokens_measured_pct']} usage={cov['usage_measured_pct']} "
          f"review={cov['review_verdict_pct']} actor={cov['actor_id_pct']}")
    print("missing fields:", json.dumps(cov["missing_fields"]))
    print("by role:", json.dumps(report["by_role"]))
    print("by provider:", json.dumps(report["by_provider"]))
    print("by actor:", json.dumps(report["by_actor"]))
    print("=" * 72)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Append-only orchestration observability log + analysis.")
    ap.add_argument("--path", default=None, help="events JSONL (default data_dir/orchestration-events.jsonl)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("append", help="append one event")
    a.add_argument("--kind", required=True, choices=list(KINDS))
    a.add_argument("--run-id", required=True)
    a.add_argument("--ts", default=None)
    a.add_argument("--source", default="observe-cli", choices=list(SOURCES))
    a.add_argument("--actor-id", default=None)
    a.add_argument("--profile", default=None)
    a.add_argument("--event-json", default=None, help="path to a JSON object (or - for stdin)")
    a.add_argument("--set", action="append", default=[], metavar="k=v")
    a.add_argument("--json", action="store_true")

    r = sub.add_parser("report", help="fold events and print observational analysis")
    r.add_argument("--json", action="store_true")

    p = sub.add_parser("prune", help="apply observability retention_days")
    p.add_argument("--json", action="store_true")

    c = sub.add_parser("validate-config", help="fail closed on malformed observability config")
    c.add_argument("--json", action="store_true")

    v = sub.add_parser("validate-events", help="validate events in a JSONL file")
    v.add_argument("--strict", action="store_true")
    v.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)
    monitoring = mborch.load_config("monitoring.json", required=False) or {}

    if args.cmd == "validate-config":
        obs = observability_config(monitoring)
        errors = validate_config(obs) if obs else []
        if not obs:
            errors.append("monitoring.json is missing the observability block")
        payload = {"ok": not errors, "errors": errors}
        print(json.dumps(payload, indent=2) if args.json else (
            "observability config ok" if not errors else "observability config errors:\n  - " + "\n  - ".join(errors)
        ))
        return 0 if not errors else 1

    if args.cmd == "append":
        fields = {}
        if args.event_json:
            blob = sys.stdin.read() if args.event_json == "-" else Path(args.event_json).read_text()
            loaded = json.loads(blob)
            if not isinstance(loaded, dict):
                raise SystemExit("observe append: --event-json must be an object")
            fields.update(loaded)
        for pair in args.set:
            if "=" not in pair:
                raise SystemExit(f"observe append: --set expects k=v, got {pair!r}")
            k, val = pair.split("=", 1)
            try:
                fields[k] = json.loads(val)
            except Exception:
                fields[k] = val
        try:
            ev = make_event(
                args.kind, run_id=args.run_id, ts=args.ts or now_iso(),
                source=args.source, actor_id=args.actor_id, profile_id=args.profile,
                **fields,
            )
        except ValueError as exc:
            raise SystemExit(f"observe: {exc}")
        pth = append(ev, path=args.path, monitoring=monitoring)
        print(json.dumps(ev, indent=2) if args.json else f"appended {ev['kind']} {ev['event_id']} → {pth}")
        return 0

    if args.cmd == "report":
        events = read(args.path, monitoring)
        report = analyze(events)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            _print_report(report)
        return 0

    if args.cmd == "prune":
        dropped = prune(monitoring, path=args.path)
        msg = {"dropped": dropped, "path": str(events_path(monitoring, args.path))}
        print(json.dumps(msg, indent=2) if args.json else f"pruned {dropped} events → {msg['path']}")
        return 0

    if args.cmd == "validate-events":
        p = Path(args.path) if args.path else events_path(monitoring)
        rows = iter_log_lines(p)
        problems = []
        valid = 0
        for lineno, ev, err in rows:
            if err or ev is None:
                problems.append({"line": lineno, "event_id": None, "errors": [err or "corrupt"]})
                continue
            valid += 1
            errs = validate_event(ev, strict=args.strict)
            if errs:
                problems.append({"line": lineno, "event_id": ev.get("event_id"), "errors": errs})
        payload = {"ok": not problems, "events": valid, "problems": problems}
        print(json.dumps(payload, indent=2) if args.json else (
            f"events ok ({len(events)})" if not problems
            else f"{len(problems)} invalid events:\n" + "\n".join(
                f"  line {p['line']}: {'; '.join(p['errors'])}" for p in problems
            )
        ))
        return 0 if not problems else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
