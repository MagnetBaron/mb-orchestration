#!/usr/bin/env python3
"""Privacy-safe, fail-closed runtime integration inventory.

The inventory is observation, never authorization. ``connectors.json`` remains the
maximum vetted scope; an MCP grant additionally needs fresh runtime/session proof.
Only allowlisted manifests are parsed and only names plus boolean/status metadata are
retained. Session overlays are challenge-bound, short-lived, process-scoped, and never
written to the cache. Explicit negative runtime evidence is monotonic: an overlay cannot
turn a blocked, disabled, unconfigured, or uninstalled integration into an effective one.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
import tempfile
import time
import tomllib
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import mborch

CACHE_NAME = "integration-inventory.json"
EVENTS_NAME = "integration-inventory-events.jsonl"
HEALTH = frozenset({"verified", "unknown", "needs_auth", "blocked", "unavailable"})
KINDS = frozenset({"mcp", "plugin", "app", "connector", "capability"})
LOCK_RECYCLED_PID_MAX_AGE_SECONDS = 3600.0
SESSION_SCHEMA_VERSION = 1
SESSION_SOURCE = "dispatcher-runtime-v1"
SESSION_MAX_AGE_SECONDS = 60.0
SESSION_MAX_TTL_SECONDS = 120.0
SESSION_FUTURE_SKEW_SECONDS = 5.0
SESSION_MAX_BYTES = 262_144
_SAFE_SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,199}$")
_SESSION_BOOL_KEYS = frozenset({"enabled", "configured", "blocked", "callable"})
_SESSION_RECORD_KEYS = frozenset({
    "runtime", "kind", "id", "observed_id", "installed", *_SESSION_BOOL_KEYS, "health",
})
_PROCESS_INVENTORY = None
_PROCESS_SESSION = None
_CONSUMED_SESSION_DIGESTS: dict[str, datetime] = {}


class InventoryError(ValueError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def cache_path() -> Path:
    return mborch.data_dir() / CACHE_NAME


def events_path() -> Path:
    return mborch.data_dir() / EVENTS_NAME


def load_adapters() -> dict:
    data = mborch.load_config("integration-adapters.json", required=True)
    if data.get("schema_version") != 1 or data.get("inventory_schema_version") != 1:
        raise InventoryError("integration-adapters schema must be version 1")
    if not isinstance(data.get("provider_runtimes"), dict):
        raise InventoryError("integration-adapters provider_runtimes must be an object")
    if not isinstance(data.get("session_only_aliases"), dict):
        raise InventoryError("integration-adapters session_only_aliases must be an object")
    if not isinstance(data.get("sources"), list):
        raise InventoryError("integration-adapters sources must be a list")
    for src in data["sources"]:
        if not isinstance(src, dict) or not all(src.get(k) for k in ("id", "runtime", "kind", "path", "format", "key")):
            raise InventoryError("every integration source needs id/runtime/kind/path/format/key")
        if src["kind"] not in KINDS:
            raise InventoryError(f"integration source {src['id']}: unknown kind")
        evidence = src.get("evidence", "observation")
        if evidence not in {"observation", "policy-only"}:
            raise InventoryError(f"integration source {src['id']}: unknown evidence class")
        if evidence == "policy-only" and (src["runtime"], src["kind"]) != ("codex", "plugin"):
            raise InventoryError(f"integration source {src['id']}: policy-only is restricted to Codex plugin config")
        raw = str(src["path"])
        if "*" in raw or "?" in raw or any(x in raw.lower() for x in ("backup", "cache", "marketplace", "log")):
            raise InventoryError(f"integration source {src['id']}: non-canonical path is forbidden")
    return data


def _path(src: dict) -> Path:
    override = os.environ.get("MB_INTEGRATION_SOURCE_ROOT")
    raw = str(src["path"])
    if override:
        # Portable fixtures mirror paths below a synthetic home.
        rel = raw[2:] if raw.startswith("~/") else raw.lstrip("/")
        return Path(override) / rel
    return Path(raw).expanduser()


def _fingerprint(path: Path) -> dict:
    if not path.is_file():
        return {"exists": False}
    blob = path.read_bytes()
    st = path.stat()
    return {
        "exists": True,
        "size": st.st_size,
        "mtime_ns": st.st_mtime_ns,
        "sha256": hashlib.sha256(blob).hexdigest(),
    }


def source_fingerprints(config: dict) -> dict:
    adapter_digest = hashlib.sha256(
        json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    fixture = os.environ.get("MB_INTEGRATION_FIXTURE")
    if fixture:
        return {"adapter_config": {"sha256": adapter_digest},
                "fixture": _fingerprint(Path(fixture).expanduser())}
    by_path = {}
    out = {}
    for src in config["sources"]:
        path = _path(src)
        key = str(path)
        if key not in by_path:
            by_path[key] = _fingerprint(path)
        out[src["id"]] = by_path[key]
    out["adapter_config"] = {"sha256": adapter_digest}
    return out


def _nested(data, dotted: str):
    cur = data
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _safe_names(src: dict, parsed_cache: dict | None = None) -> list[tuple[str, bool]]:
    path = _path(src)
    if not path.is_file():
        return []
    parsed_cache = {} if parsed_cache is None else parsed_cache
    cache_key = (str(path), "json" if src["format"].startswith("json-") else "toml")
    try:
        if cache_key in parsed_cache:
            data = parsed_cache[cache_key]
        else:
            if src["format"].startswith("json-"):
                data = json.loads(path.read_text())
            elif src["format"].startswith("toml-"):
                data = tomllib.loads(path.read_text())
            else:
                raise InventoryError(f"source {src['id']}: unsupported parser")
            parsed_cache[cache_key] = data
    except Exception as exc:
        raise InventoryError(f"source {src['id']}: malformed canonical manifest ({type(exc).__name__})") from None
    value = _nested(data, src["key"])
    object_values = value if isinstance(value, dict) else {}
    if src["format"].endswith("object-keys"):
        names = list(value) if isinstance(value, dict) else []
    elif src["format"].endswith("list"):
        names = value if isinstance(value, list) else []
    else:
        names = []
    disabled_names = set()
    if src.get("disabled_key"):
        disabled = _nested(data, src["disabled_key"])
        if isinstance(disabled, list):
            disabled_names = {str(x) for x in disabled}
        elif isinstance(disabled, dict):
            disabled_names = {str(k) for k, v in disabled.items() if v}
    out = []
    for name in names:
        if not isinstance(name, str) or not name or len(name) > 200:
            continue
        meta = object_values.get(name)
        disabled = (bool(src.get("disabled")) or name in disabled_names
                    or (isinstance(meta, dict) and meta.get("enabled") is False))
        out.append((name, disabled))
    return out


def _canonical(config: dict, runtime: str, kind: str, observed_id: str, *, session=False) -> str | None:
    aliases = dict((((config.get("aliases") or {}).get(runtime) or {}).get(kind) or {}))
    if session:
        aliases.update(
            (((config.get("session_only_aliases") or {}).get(runtime) or {}).get(kind) or {})
        )
    return aliases.get(observed_id) or (observed_id if observed_id in set(aliases.values()) else None)


def _record(config: dict, runtime: str, kind: str, observed_id: str, *, disabled=False,
            source="manifest", callable_value=False, health="unknown", suggested=False) -> dict:
    canonical = _canonical(config, runtime, kind, observed_id)
    # An installed-plugin manifest proves installation. An MCP/app config proves
    # configuration but not that its package/auth/transport is currently usable.
    installed = (not suggested) if kind == "plugin" else None
    return {
        "runtime": runtime,
        "kind": kind,
        "observed_id": observed_id,
        "canonical_id": canonical,
        "registered": canonical is not None,
        "suggested": bool(suggested),
        "installed": installed,
        "enabled": not disabled and not suggested,
        "configured": not disabled and not suggested,
        "blocked": bool(disabled),
        "health": "blocked" if disabled else health,
        "callable": bool(callable_value),
        "source": source,
    }


def _validate_record(rec: dict, *, session=False) -> dict:
    if not isinstance(rec, dict):
        raise InventoryError("integration record must be an object")
    runtime, kind, observed = rec.get("runtime"), rec.get("kind"), rec.get("observed_id") or rec.get("id")
    if not all(isinstance(x, str) and x for x in (runtime, kind, observed)) or kind not in KINDS:
        raise InventoryError("integration record needs safe runtime/kind/id")
    health = rec.get("health", "unknown")
    if health not in HEALTH:
        raise InventoryError(f"integration record {observed}: invalid health")
    clean = {"runtime": runtime, "kind": kind, "observed_id": observed}
    for key in ("registered", "suggested", "enabled", "configured", "blocked", "callable"):
        clean[key] = bool(rec.get(key, False))
    # Installed is tri-state only for MCP/app manifest evidence: None means the
    # field is not applicable/observable, while explicit False is a denial.
    installed = rec.get("installed", False)
    clean["installed"] = None if installed is None and kind in {"mcp", "app"} else bool(installed)
    clean["health"] = health
    clean["source"] = "session" if session else "fixture"
    return clean


def _fixture_records(config: dict, path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text())
    except Exception as exc:
        raise InventoryError(f"fixture malformed ({type(exc).__name__})") from None
    records = data.get("records") if isinstance(data, dict) else None
    if not isinstance(records, list):
        raise InventoryError("fixture needs a records list")
    out = []
    for raw in records:
        rec = _validate_record(raw)
        rec["canonical_id"] = _canonical(config, rec["runtime"], rec["kind"], rec["observed_id"])
        rec["registered"] = bool(rec.get("canonical_id"))
        out.append(rec)
    return out


def discover(config: dict) -> tuple[list[dict], list[str]]:
    fixture = os.environ.get("MB_INTEGRATION_FIXTURE")
    if fixture:
        return _fixture_records(config, Path(fixture).expanduser()), ["fixture_refresh"]
    records, events, parsed_cache = [], [], {}
    for src in config["sources"]:
        try:
            names = _safe_names(src, parsed_cache)
            if src.get("evidence") == "policy-only":
                # Codex `plugins` config is an MCP allowlist/policy layer. It is
                # not the Plugins tab or `/plugins` installation inventory.
                continue
            for name, disabled in names:
                records.append(_record(config, src["runtime"], src["kind"], name,
                                       disabled=disabled, source=src["id"]))
        except InventoryError:
            # Malformed source fails that adapter closed without retaining content.
            events.append(f"source_unavailable:{src['id']}")
    records.sort(key=lambda r: (r["runtime"], r["kind"], r["observed_id"]))
    return records, events


def fixture_inventory(path: Path) -> dict:
    """Load a portable synthetic inventory without touching the runtime cache."""
    config = load_adapters()
    return {
        "schema_version": config["inventory_schema_version"],
        "generated_at": now_iso(),
        "ttl_seconds": config["ttl_seconds"],
        "source_fingerprints": {"fixture": _fingerprint(path)},
        "refresh_reason": "explicit_fixture",
        "events": [],
        "records": _fixture_records(config, path),
    }


def _read_cache(path: Path, config: dict, fingerprints: dict) -> tuple[dict | None, str]:
    if not path.exists():
        return None, "missing_cache"
    try:
        data = json.loads(path.read_text())
        if data.get("schema_version") != config["inventory_schema_version"]:
            return None, "schema_old"
        generated = datetime.fromisoformat(data["generated_at"])
        age = (datetime.now(timezone.utc) - generated).total_seconds()
        if age < 0 or age > int(config["ttl_seconds"]):
            return None, "ttl_expired"
        if data.get("source_fingerprints") != fingerprints:
            return None, "fingerprint_changed"
        if not isinstance(data.get("records"), list):
            return None, "corrupt_cache"
        return data, "cache_hit"
    except Exception:
        return None, "corrupt_cache"


def _pid_alive(pid: int) -> bool:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _lock_owner(path: Path) -> dict | None:
    try:
        owner = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(owner, dict):
        return None
    if not isinstance(owner.get("pid"), int) or not isinstance(owner.get("owner"), str):
        return None
    return owner


def _lock(path: Path, timeout: float) -> str:
    owner_token = uuid.uuid4().hex
    payload = json.dumps({"pid": os.getpid(), "owner": owner_token, "created_at": now_iso()}) + "\n"
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            try:
                os.write(fd, payload.encode("utf-8"))
                os.fsync(fd)
            finally:
                os.close(fd)
            return owner_token
        except FileExistsError:
            try:
                owner = _lock_owner(path)
                age = time.time() - path.stat().st_mtime
                dead_owner = owner is not None and not _pid_alive(owner["pid"])
                malformed_stale = owner is None and age > max(30.0, timeout * 4)
                recycled_pid_stale = owner is not None and age > LOCK_RECYCLED_PID_MAX_AGE_SECONDS
                if dead_owner or malformed_stale or recycled_pid_stale:
                    path.unlink()
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() >= deadline:
                raise InventoryError("integration inventory lock timeout")
            time.sleep(0.02)


def _unlock(path: Path, owner_token: str) -> None:
    owner = _lock_owner(path)
    if owner is not None and owner.get("owner") == owner_token:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _observe(event: str, detail: str = "") -> None:
    path = events_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": now_iso(), "event": event, "detail": detail[:200]}
    # No task content, paths, values, stdout/stderr, or identity are recorded.
    with path.open("a") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")
    os.chmod(path, 0o600)


def refresh(force: bool = False) -> dict:
    global _PROCESS_INVENTORY
    config = load_adapters()
    path = cache_path()
    fps = source_fingerprints(config)
    if not force:
        cached, reason = _read_cache(path, config, fps)
        if cached is not None:
            _PROCESS_INVENTORY = cached
            return cached
    else:
        reason = "force_refresh"
    lock = Path(str(path) + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    owner_token = _lock(lock, float(config["lock_timeout_seconds"]))
    try:
        if not force:
            cached, second_reason = _read_cache(path, config, fps)
            if cached is not None:
                _PROCESS_INVENTORY = cached
                return cached
            reason = second_reason
        records, events = discover(config)
        data = {
            "schema_version": config["inventory_schema_version"],
            "generated_at": now_iso(),
            "ttl_seconds": config["ttl_seconds"],
            "source_fingerprints": fps,
            "refresh_reason": reason,
            "events": events,
            "records": records,
        }
        _atomic_write(path, data)
        _observe("inventory_refresh", reason)
        if reason in {"missing_cache", "schema_old", "corrupt_cache"}:
            _observe("inventory_recovery", reason)
        _PROCESS_INVENTORY = data
        return data
    finally:
        _unlock(lock, owner_token)


def reset_process_cache() -> None:
    global _PROCESS_INVENTORY, _PROCESS_SESSION
    _PROCESS_INVENTORY = None
    _PROCESS_SESSION = None


def inventory() -> dict:
    global _PROCESS_INVENTORY
    if _PROCESS_INVENTORY is None:
        _PROCESS_INVENTORY = refresh()
    return _PROCESS_INVENTORY


def _session_iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InventoryError("session attestation timestamps must include a timezone")
    return value.astimezone(timezone.utc).isoformat()


def _session_unsigned(data: dict) -> dict:
    attestation = data.get("attestation") or {}
    return {
        "schema_version": data.get("schema_version"),
        "runtime": data.get("runtime"),
        "records": data.get("records"),
        "attestation": {
            "source": attestation.get("source"),
            "observed_at": attestation.get("observed_at"),
            "expires_at": attestation.get("expires_at"),
            "nonce_digest": attestation.get("nonce_digest"),
        },
    }


def _session_digest(data: dict, nonce: str) -> str:
    encoded = json.dumps(_session_unsigned(data), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hmac.new(nonce.encode("utf-8"), encoded, hashlib.sha256).hexdigest()


def build_session_document(runtime: str, records: list[dict], nonce: str, *,
                           observed_at: datetime | None = None,
                           expires_at: datetime | None = None) -> dict:
    """Build the strict value-free v1 envelope a trusted runtime dispatcher emits."""
    if not isinstance(nonce, str) or not 32 <= len(nonce) <= 512:
        raise InventoryError("session attestation nonce must contain 32 to 512 characters")
    observed_at = observed_at or datetime.now(timezone.utc)
    expires_at = expires_at or (observed_at + timedelta(seconds=60))
    doc = {
        "schema_version": SESSION_SCHEMA_VERSION,
        "runtime": runtime,
        "records": records,
        "attestation": {
            "source": SESSION_SOURCE,
            "observed_at": _session_iso(observed_at),
            "expires_at": _session_iso(expires_at),
            "nonce_digest": "sha256:" + hashlib.sha256(str(nonce).encode("utf-8")).hexdigest(),
        },
    }
    doc["attestation"]["digest"] = _session_digest(doc, nonce)
    return doc


def _parse_session_time(value, field: str) -> datetime:
    if not isinstance(value, str):
        raise InventoryError(f"session attestation {field} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise InventoryError(f"session attestation {field} is malformed") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InventoryError(f"session attestation {field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _read_session_source(source: str | None) -> str | None:
    from_env = source is None
    if source is None:
        source = os.environ.get("MB_INTEGRATION_SESSION")
    if not source:
        return None
    if not isinstance(source, str):
        raise InventoryError("session source must be a file path or '-' for explicit stdin")
    if source.lstrip().startswith(("{", "[")):
        raise InventoryError("inline session JSON is forbidden; use a mode-0600 file or explicit stdin")
    if source == "-":
        if from_env:
            raise InventoryError("MB_INTEGRATION_SESSION may not request stdin")
        import sys
        raw = sys.stdin.read(SESSION_MAX_BYTES + 1)
    else:
        path = Path(source).expanduser()
        if path.is_symlink() or not path.is_file():
            raise InventoryError("session overlay file must be a regular non-symlink file")
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            raise InventoryError("session overlay file must be owner-only (mode 0600)")
        if path.stat().st_size > SESSION_MAX_BYTES:
            raise InventoryError("session overlay exceeds the bounded size limit")
        raw = path.read_text()
    if len(raw.encode("utf-8")) > SESSION_MAX_BYTES:
        raise InventoryError("session overlay exceeds the bounded size limit")
    return raw


def _validate_session_envelope(data: dict, now: datetime | None = None) -> tuple[datetime, datetime, str]:
    if set(data) != {"schema_version", "runtime", "records", "attestation"}:
        raise InventoryError("session overlay has unknown or missing top-level fields")
    if data.get("schema_version") != SESSION_SCHEMA_VERSION:
        raise InventoryError(f"session overlay schema_version must be {SESSION_SCHEMA_VERSION}")
    runtime = data.get("runtime")
    records = data.get("records")
    if not isinstance(runtime, str) or not _SAFE_SESSION_ID.fullmatch(runtime):
        raise InventoryError("session overlay needs one safe runtime id")
    if not isinstance(records, list) or len(records) > 500:
        raise InventoryError("session overlay records must be a bounded list")
    attestation = data.get("attestation")
    expected_attestation = {"source", "observed_at", "expires_at", "nonce_digest", "digest"}
    if not isinstance(attestation, dict) or set(attestation) != expected_attestation:
        raise InventoryError("session attestation has unknown or missing fields")
    if attestation.get("source") != SESSION_SOURCE:
        raise InventoryError("session attestation source is not runtime-trusted")
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    observed_at = _parse_session_time(attestation.get("observed_at"), "observed_at")
    expires_at = _parse_session_time(attestation.get("expires_at"), "expires_at")
    if observed_at > now + timedelta(seconds=SESSION_FUTURE_SKEW_SECONDS):
        raise InventoryError("session attestation is from the future")
    if (now - observed_at).total_seconds() > SESSION_MAX_AGE_SECONDS:
        raise InventoryError("session attestation is stale")
    lifetime = (expires_at - observed_at).total_seconds()
    if lifetime <= 0 or lifetime > SESSION_MAX_TTL_SECONDS or expires_at <= now:
        raise InventoryError("session attestation expiry is invalid or stale")
    nonce = os.environ.get("MB_INTEGRATION_SESSION_NONCE")
    if not isinstance(nonce, str) or not 32 <= len(nonce) <= 512:
        raise InventoryError("fresh MB_INTEGRATION_SESSION_NONCE is required")
    expected_nonce = "sha256:" + hashlib.sha256(nonce.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(str(attestation.get("nonce_digest")), expected_nonce):
        raise InventoryError("session attestation is not bound to this process challenge")
    claimed_digest = attestation.get("digest")
    if not isinstance(claimed_digest, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", claimed_digest):
        raise InventoryError("session attestation digest is malformed")
    expected_digest = _session_digest(data, nonce)
    if not hmac.compare_digest(claimed_digest, expected_digest):
        raise InventoryError("session attestation digest mismatch")
    for old_digest, old_expiry in list(_CONSUMED_SESSION_DIGESTS.items()):
        if old_expiry <= now:
            del _CONSUMED_SESSION_DIGESTS[old_digest]
    if claimed_digest in _CONSUMED_SESSION_DIGESTS:
        raise InventoryError("session attestation was already consumed in this process")
    return observed_at, expires_at, claimed_digest


def load_session(source: str | None = None) -> dict | None:
    global _PROCESS_SESSION
    raw = _read_session_source(source)
    if raw is None:
        return None
    _PROCESS_SESSION = None
    try:
        data = json.loads(raw)
    except Exception:
        raise InventoryError("session overlay is malformed JSON") from None
    if not isinstance(data, dict):
        raise InventoryError("session overlay must be a JSON object")
    observed_at, expires_at, digest = _validate_session_envelope(data)
    runtime = data["runtime"]
    records = data["records"]
    clean = []
    for raw_rec in records:
        if not isinstance(raw_rec, dict) or not set(raw_rec).issubset(_SESSION_RECORD_KEYS):
            raise InventoryError("session record has unknown fields")
        merged = dict(raw_rec) if isinstance(raw_rec, dict) else raw_rec
        if isinstance(merged, dict):
            if merged.get("runtime") not in (None, runtime):
                raise InventoryError("session records may not cross runtime boundaries")
            merged["runtime"] = runtime
            observed_id = merged.get("observed_id") or merged.get("id")
            if not isinstance(observed_id, str) or not _SAFE_SESSION_ID.fullmatch(observed_id):
                raise InventoryError("session record id is malformed")
            for key in _SESSION_BOOL_KEYS:
                if key in merged and not isinstance(merged[key], bool):
                    raise InventoryError(f"session record {observed_id}: {key} must be boolean")
            if "installed" in merged and merged["installed"] is not None and not isinstance(merged["installed"], bool):
                raise InventoryError(f"session record {observed_id}: installed must be boolean or null")
        rec = _validate_record(merged, session=True)
        canonical = _canonical(load_adapters(), runtime, rec["kind"], rec["observed_id"], session=True)
        rec["canonical_id"] = canonical
        rec["registered"] = canonical is not None
        clean.append(rec)
    _CONSUMED_SESSION_DIGESTS[digest] = expires_at
    _PROCESS_SESSION = {
        "runtime": runtime,
        "process_scope": True,
        "records": clean,
        "attestation": {
            "source": data["attestation"]["source"],
            "observed_at": _session_iso(observed_at),
            "expires_at": _session_iso(expires_at),
            "digest": digest,
        },
    }
    return _PROCESS_SESSION


def session() -> dict | None:
    global _PROCESS_SESSION
    if _PROCESS_SESSION is None and os.environ.get("MB_INTEGRATION_SESSION"):
        return load_session()
    return _PROCESS_SESSION


def session_provenance(overlay: dict | None = None) -> dict | None:
    """Return a value-free summary when an overlay was supplied, including zero proof."""
    overlay = session() if overlay is None else overlay
    if not overlay or not isinstance(overlay.get("runtime"), str):
        return None
    runtime = overlay["runtime"]
    empty = {"records": []}
    canonical_ids = sorted({
        rec["canonical_id"]
        for rec in overlay.get("records", [])
        if isinstance(rec, dict) and isinstance(rec.get("canonical_id"), str)
        and effective(runtime, rec.get("kind"), rec["canonical_id"], require_callable=True,
                      inv=empty, overlay=overlay)[0]
    })
    attestation = overlay.get("attestation") or {}
    return {
        "runtime": runtime,
        "canonical_ids": canonical_ids,
        "attestation": {
            "source": attestation.get("source"),
            "observed_at": attestation.get("observed_at"),
            "expires_at": attestation.get("expires_at"),
            "digest": attestation.get("digest"),
        },
    }


def _overlay_is_fresh(overlay: dict | None) -> bool:
    if not overlay:
        return False
    try:
        expiry = _parse_session_time((overlay.get("attestation") or {}).get("expires_at"), "expires_at")
    except InventoryError:
        return False
    return expiry > datetime.now(timezone.utc)


def _explicit_negative(rec: dict) -> bool:
    return bool(
        rec.get("blocked") is True
        or rec.get("enabled") is False
        or rec.get("configured") is False
        or rec.get("installed") is False
        or rec.get("health") in {"needs_auth", "blocked", "unavailable"}
    )


def merged_records(inv: dict | None = None, overlay: dict | None = None) -> list[dict]:
    inv = inventory() if inv is None else inv
    overlay = session() if overlay is None else overlay
    by_key = {}
    for r in inv.get("records", []):
        if not isinstance(r, dict):
            continue
        key = (r.get("runtime"), r.get("kind"), r.get("canonical_id") or r.get("observed_id"))
        # Preserve a negative observation even when a duplicate positive base record
        # follows it. This keeps the merged diagnostic view aligned with effective().
        if key not in by_key or _explicit_negative(r):
            by_key[key] = dict(r)
    if _overlay_is_fresh(overlay):
        for r in overlay.get("records", []):
            key = (r.get("runtime"), r.get("kind"), r.get("canonical_id") or r.get("observed_id"))
            if key in by_key and _explicit_negative(by_key[key]):
                continue
            by_key[key] = dict(r)
    return sorted(by_key.values(), key=lambda r: (str(r.get("runtime")), str(r.get("kind")), str(r.get("observed_id"))))


def provider_runtime(provider_id: str, config: dict | None = None) -> str | None:
    config = config or load_adapters()
    return (config.get("provider_runtimes") or {}).get(provider_id)


def effective(runtime: str, kind: str, canonical_id: str, *, require_callable: bool,
              inv: dict | None = None, overlay: dict | None = None) -> tuple[bool, str]:
    inv = inventory() if inv is None else inv
    overlay = session() if overlay is None else overlay
    base_hits = [r for r in inv.get("records", []) if isinstance(r, dict)
                 and r.get("runtime") == runtime and r.get("kind") == kind
                 and r.get("canonical_id") == canonical_id]
    if any(_explicit_negative(rec) for rec in base_hits):
        return False, f"{runtime}:{kind}:{canonical_id} is explicitly denied by observed runtime state"
    overlay_hits = []
    if _overlay_is_fresh(overlay) and overlay.get("runtime") == runtime:
        overlay_hits = [r for r in overlay.get("records", []) if isinstance(r, dict)
                        and r.get("runtime") == runtime and r.get("kind") == kind
                        and r.get("canonical_id") == canonical_id]
    hits = base_hits + overlay_hits
    if not hits:
        return False, f"{runtime}:{kind}:{canonical_id} is not freshly observed"
    for rec in hits:
        if rec.get("suggested") and not rec.get("installed"):
            continue
        if not rec.get("enabled") or not rec.get("configured") or rec.get("blocked"):
            continue
        # A canonical MCP/app manifest proves configured presence, but not that a
        # package, auth, or transport is callable. Plugin manifests additionally
        # prove installation. Runtime routes always request callable proof below.
        if kind in {"mcp", "app"}:
            if "installed" not in rec or rec.get("installed") is False:
                continue
        elif not rec.get("installed"):
            continue
        if rec.get("health") in {"needs_auth", "blocked", "unavailable"}:
            continue
        if require_callable and (not rec.get("installed") or not rec.get("callable")
                                 or rec.get("health") != "verified"):
            continue
        return True, "observed effective"
    suffix = " and callable in this process" if require_callable else ""
    return False, f"{runtime}:{kind}:{canonical_id} is not installed, enabled, configured, healthy{suffix}"


def connector_effective(provider_id: str, connector_id: str, meta: dict,
                        *, inv: dict | None = None, overlay: dict | None = None,
                        require_callable: bool = True) -> tuple[bool, str]:
    if (meta or {}).get("status") != "active":
        return False, f"{connector_id} lifecycle is not active"
    if provider_id not in ((meta or {}).get("available_on") or []):
        return False, f"{connector_id} does not authorize {provider_id}"
    runtime = provider_runtime(provider_id)
    if not runtime:
        return False, f"{provider_id} has no explicit runtime mapping"
    ok, reason = effective(runtime, "mcp", connector_id, require_callable=require_callable,
                           inv=inv, overlay=overlay)
    return ok, reason


def plugin_effective(runtime: str, plugin_id: str, *, inv: dict | None = None,
                     overlay: dict | None = None) -> tuple[bool, str]:
    return effective(runtime, "plugin", plugin_id, require_callable=False, inv=inv, overlay=overlay)


def cache_mode_ok(path: Path | None = None) -> bool:
    path = path or cache_path()
    return path.is_file() and stat.S_IMODE(path.stat().st_mode) == 0o600
