#!/usr/bin/env python3
"""Privacy-safe, fail-closed runtime integration inventory.

The inventory is observation, never authorization. ``connectors.json`` remains the
maximum vetted scope; an MCP grant additionally needs fresh runtime/session proof.
Only allowlisted manifests are parsed and only names plus boolean/status metadata are
retained. Session overlays are process-scoped and are never written to the cache.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

import mborch

CACHE_NAME = "integration-inventory.json"
EVENTS_NAME = "integration-inventory-events.jsonl"
HEALTH = frozenset({"verified", "unknown", "needs_auth", "blocked", "unavailable"})
KINDS = frozenset({"mcp", "plugin", "app", "connector", "capability"})
_PROCESS_INVENTORY = None
_PROCESS_SESSION = None


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
    if not isinstance(data.get("sources"), list):
        raise InventoryError("integration-adapters sources must be a list")
    for src in data["sources"]:
        if not isinstance(src, dict) or not all(src.get(k) for k in ("id", "runtime", "kind", "path", "format", "key")):
            raise InventoryError("every integration source needs id/runtime/kind/path/format/key")
        if src["kind"] not in KINDS:
            raise InventoryError(f"integration source {src['id']}: unknown kind")
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
    fixture = os.environ.get("MB_INTEGRATION_FIXTURE")
    if fixture:
        return {"fixture": _fingerprint(Path(fixture).expanduser())}
    by_path = {}
    out = {}
    for src in config["sources"]:
        path = _path(src)
        key = str(path)
        if key not in by_path:
            by_path[key] = _fingerprint(path)
        out[src["id"]] = by_path[key]
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


def _canonical(config: dict, runtime: str, kind: str, observed_id: str) -> str | None:
    aliases = (((config.get("aliases") or {}).get(runtime) or {}).get(kind) or {})
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
    for key in ("registered", "suggested", "installed", "enabled", "configured", "blocked", "callable"):
        clean[key] = bool(rec.get(key, False))
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
            for name, disabled in _safe_names(src, parsed_cache):
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


def _lock(path: Path, timeout: float):
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            return
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > max(30.0, timeout * 4):
                    path.unlink()
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() >= deadline:
                raise InventoryError("integration inventory lock timeout")
            time.sleep(0.02)


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
    _lock(lock, float(config["lock_timeout_seconds"]))
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
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def reset_process_cache() -> None:
    global _PROCESS_INVENTORY, _PROCESS_SESSION
    _PROCESS_INVENTORY = None
    _PROCESS_SESSION = None


def inventory() -> dict:
    global _PROCESS_INVENTORY
    if _PROCESS_INVENTORY is None:
        _PROCESS_INVENTORY = refresh()
    return _PROCESS_INVENTORY


def load_session(source: str | None = None) -> dict | None:
    global _PROCESS_SESSION
    if source is None:
        source = os.environ.get("MB_INTEGRATION_SESSION")
    if not source:
        return None
    if source == "-":
        import sys
        raw = sys.stdin.read()
    else:
        raw = Path(source).expanduser().read_text()
    try:
        data = json.loads(raw)
    except Exception:
        raise InventoryError("session overlay is malformed JSON") from None
    runtime = data.get("runtime") if isinstance(data, dict) else None
    records = data.get("records") if isinstance(data, dict) else None
    if not isinstance(runtime, str) or not runtime or not isinstance(records, list):
        raise InventoryError("session overlay needs one runtime and a records list")
    clean = []
    for raw_rec in records:
        merged = dict(raw_rec) if isinstance(raw_rec, dict) else raw_rec
        if isinstance(merged, dict):
            if merged.get("runtime") not in (None, runtime):
                raise InventoryError("session records may not cross runtime boundaries")
            merged["runtime"] = runtime
        rec = _validate_record(merged, session=True)
        canonical = _canonical(load_adapters(), runtime, rec["kind"], rec["observed_id"])
        rec["canonical_id"] = canonical
        rec["registered"] = canonical is not None
        clean.append(rec)
    _PROCESS_SESSION = {"runtime": runtime, "process_scope": True, "records": clean}
    return _PROCESS_SESSION


def session() -> dict | None:
    global _PROCESS_SESSION
    if _PROCESS_SESSION is None and os.environ.get("MB_INTEGRATION_SESSION"):
        return load_session()
    return _PROCESS_SESSION


def merged_records(inv: dict | None = None, overlay: dict | None = None) -> list[dict]:
    inv = inventory() if inv is None else inv
    overlay = session() if overlay is None else overlay
    by_key = {(r.get("runtime"), r.get("kind"), r.get("canonical_id") or r.get("observed_id")): dict(r)
              for r in inv.get("records", []) if isinstance(r, dict)}
    if overlay:
        for r in overlay.get("records", []):
            key = (r.get("runtime"), r.get("kind"), r.get("canonical_id") or r.get("observed_id"))
            by_key[key] = dict(r)
    return sorted(by_key.values(), key=lambda r: (str(r.get("runtime")), str(r.get("kind")), str(r.get("observed_id"))))


def provider_runtime(provider_id: str, config: dict | None = None) -> str | None:
    config = config or load_adapters()
    return (config.get("provider_runtimes") or {}).get(provider_id)


def effective(runtime: str, kind: str, canonical_id: str, *, require_callable: bool,
              inv: dict | None = None, overlay: dict | None = None) -> tuple[bool, str]:
    hits = [r for r in merged_records(inv, overlay)
            if r.get("runtime") == runtime and r.get("kind") == kind and r.get("canonical_id") == canonical_id]
    if not hits:
        return False, f"{runtime}:{kind}:{canonical_id} is not freshly observed"
    for rec in hits:
        if rec.get("suggested") and not rec.get("installed"):
            continue
        if not rec.get("installed") or not rec.get("enabled") or not rec.get("configured") or rec.get("blocked"):
            continue
        if rec.get("health") in {"needs_auth", "blocked", "unavailable"}:
            continue
        if require_callable and (not rec.get("callable") or rec.get("health") != "verified"):
            continue
        return True, "observed effective"
    suffix = " and callable in this process" if require_callable else ""
    return False, f"{runtime}:{kind}:{canonical_id} is not installed, enabled, configured, healthy{suffix}"


def connector_effective(provider_id: str, connector_id: str, meta: dict,
                        *, inv: dict | None = None, overlay: dict | None = None) -> tuple[bool, str]:
    if (meta or {}).get("status") != "active":
        return False, f"{connector_id} lifecycle is not active"
    if provider_id not in ((meta or {}).get("available_on") or []):
        return False, f"{connector_id} does not authorize {provider_id}"
    runtime = provider_runtime(provider_id)
    if not runtime:
        return False, f"{provider_id} has no explicit runtime mapping"
    ok, reason = effective(runtime, "mcp", connector_id, require_callable=True, inv=inv, overlay=overlay)
    return ok, reason


def plugin_effective(runtime: str, plugin_id: str, *, inv: dict | None = None,
                     overlay: dict | None = None) -> tuple[bool, str]:
    return effective(runtime, "plugin", plugin_id, require_callable=False, inv=inv, overlay=overlay)


def cache_mode_ok(path: Path | None = None) -> bool:
    path = path or cache_path()
    return path.is_file() and stat.S_IMODE(path.stat().st_mode) == 0o600
