#!/usr/bin/env python3
"""mborch — shared config/data resolution for the orchestration scripts.

The engine is generic: a specific account layout (e.g. the reference 5-Claude
setup in config/) is just ONE example. Any user points MB_CONFIG_DIR at their own
per-user layer (subscriptions / entrypoints / usage-windows / monitoring) and the
shared registry (providers / review-depth / roles / connectors / schema) is
inherited from repo/config as a fallback. This is how the system scales from 1
subscription to many, on any machine, without editing code or prose.

Resolution order for a config file:
  1. $MB_CONFIG_DIR/<name>   (per-user override layer, if set)
  2. <repo>/config/<name>    (shared defaults)

Data (history/observed windows/orchestration events) lives under $MB_DATA_DIR or <repo>/data (gitignored).
"""
from __future__ import annotations
import json
import fcntl
import math
import os
import re
import secrets
import shutil
import stat
import time
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DEFAULT_CONFIG = REPO / "config"
LOCK_OWNER_FILE = "owner.json"
LOCK_STALE_GRACE_SECONDS = 1.0
# Ledger critical sections are millisecond-scale. A live PID attached to a lock
# this old is overwhelmingly a recycled PID after a crash, not a legitimate
# writer. The bound prevents permanent deadlock while preserving fresh owners.
LOCK_LIVE_PID_MAX_AGE_SECONDS = 300.0


# ---- Opus 5 GA classifier (NOT a ban) ----------------------------------------
# Opus 5 (released 2026-07-24) is the operational Anthropic review/judgment seat.
# This matcher still identifies the 5.0 GA line vs later minors so inventory and
# evidence can group them; it does NOT forbid anything. Forbidden models are
# exclusively the explicit map in providers.json `forbidden_models`.
_OPUS5_STEM = re.compile(r"(?:^|[^0-9a-z])opus[-_.]?5(?![0-9])(.*)$", re.IGNORECASE)


def is_opus5_zero(model: str | None) -> bool:
    """True iff `model` names the Opus 5 GA line (bare opus-5, -0/.0, or a 5.0
    build/date stamp). Opus 5.1+ and non-Opus-5 models return False. This is a
    classifier, not a routing ban."""
    if not model:
        return False
    m = _OPUS5_STEM.search(model)
    if not m:
        return False
    tail = m.group(1)
    minor = re.match(r"[-_.]?([0-9]+)", tail)
    if minor is None:
        return True
    digits = minor.group(1)
    if len(digits) >= 5:
        return True
    return int(digits) == 0


def model_is_forbidden(model: str | None, forbidden_map: dict | None) -> bool:
    """A model is forbidden only if it is explicitly listed — by id or alias —
    in providers.json `forbidden_models`. Opus 5 is not auto-forbidden."""
    if not model or not forbidden_map:
        return False
    ids: set[str] = set()
    for fid, meta in forbidden_map.items():
        ids.add(fid)
        ids.update((meta or {}).get("aliases", []))
    return model in ids


def config_dirs() -> list[Path]:
    dirs: list[Path] = []
    env = os.environ.get("MB_CONFIG_DIR")
    if env:
        dirs.append(Path(env).expanduser())
    dirs.append(DEFAULT_CONFIG)
    # de-dupe while preserving order
    seen, out = set(), []
    for d in dirs:
        r = d.resolve()
        if r not in seen:
            seen.add(r)
            out.append(d)
    return out


def find_config(name: str) -> Path:
    for d in config_dirs():
        p = d / name
        if p.exists():
            return p
    return DEFAULT_CONFIG / name  # non-existent path, for clear error messages


def load_config(name: str, required: bool = True) -> dict:
    p = find_config(name)
    if not p.exists():
        if required:
            raise SystemExit(f"mborch: missing config {name} (looked in {[str(d) for d in config_dirs()]})")
        return {}
    try:
        return json.loads(p.read_text())
    except Exception as exc:
        raise SystemExit(f"mborch: cannot parse {p}: {exc}")


def ledger_path() -> Path:
    """Runtime ledger — override-aware so an example/user dir keeps its own."""
    env = os.environ.get("MB_USAGE_LEDGER")
    if env:
        return Path(env).expanduser()
    return find_config("usage-ledger.json")


def _pid_is_live(pid: int) -> bool:
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _directory_lock_owner(lock: Path) -> dict | None:
    """Read a lock owner without following attacker/stale symlinks."""
    try:
        lock_stat = lock.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISDIR(lock_stat.st_mode):
        return None
    owner_path = lock / LOCK_OWNER_FILE
    try:
        owner_stat = owner_path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(owner_stat.st_mode):
        return None
    try:
        owner = json.loads(owner_path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(owner, dict) or set(owner) != {"pid", "token", "created"}:
        return None
    if (isinstance(owner.get("pid"), bool)
            or not isinstance(owner.get("pid"), int)
            or owner["pid"] <= 0
            or not isinstance(owner.get("token"), str)
            or not re.fullmatch(r"[0-9a-f]{32}", owner["token"])
            or isinstance(owner.get("created"), bool)
            or not isinstance(owner.get("created"), (int, float))
            or not math.isfinite(owner["created"])):
        return None
    return owner


@contextmanager
def path_lock_guard(path: Path):
    """Serialize generation checks and pathname mutations for a lock.

    The persistent sidecar guard closes the read/check/unlink-or-rename ABA
    window: every cooperating acquirer, reclaimer, and releaser holds the same
    kernel lock while it observes and mutates the public lock pathname.
    """
    guard = path.with_name(f".{path.name}.guard")
    guard.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(guard, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("lock guard is not a regular file")
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _reclaim_stale_directory_lock(
    lock: Path, *, stale_grace_seconds: float = LOCK_STALE_GRACE_SECONDS,
) -> bool:
    """Quarantine a stale lock while the caller holds path_lock_guard(lock)."""
    try:
        lock_stat = lock.lstat()
    except FileNotFoundError:
        return True
    if not stat.S_ISDIR(lock_stat.st_mode):
        return False
    owner = _directory_lock_owner(lock)
    if owner is not None:
        owner_age = time.time() - owner["created"]
        if (_pid_is_live(owner["pid"])
                and owner_age <= LOCK_LIVE_PID_MAX_AGE_SECONDS):
            return False
    elif time.time() - lock_stat.st_mtime < stale_grace_seconds:
        # The winner may be between mkdir and its owner-file write.
        return False
    quarantine = lock.with_name(
        f"{lock.name}.reclaimed.{os.getpid()}.{secrets.token_hex(8)}"
    )
    try:
        os.replace(lock, quarantine)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    try:
        quarantine_stat = quarantine.lstat()
        if stat.S_ISDIR(quarantine_stat.st_mode):
            shutil.rmtree(quarantine)
    except FileNotFoundError:
        pass
    return True


def acquire_directory_lock(
    lock: Path,
    *,
    timeout_seconds: float,
    poll_seconds: float,
    stale_grace_seconds: float = LOCK_STALE_GRACE_SECONDS,
    owner_pid: int | None = None,
) -> str:
    """Acquire a PID-owned mkdir lock and return its unguessable release token."""
    if timeout_seconds <= 0 or poll_seconds <= 0 or stale_grace_seconds < 0:
        raise ValueError("lock timing values are invalid")
    pid = os.getpid() if owner_pid is None else owner_pid
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise ValueError("lock owner PID must be a positive integer")
    token = secrets.token_hex(16)
    deadline = time.monotonic() + timeout_seconds
    while True:
        acquired = False
        with path_lock_guard(lock):
            try:
                os.mkdir(lock, 0o700)
                acquired = True
            except FileExistsError:
                _reclaim_stale_directory_lock(
                    lock, stale_grace_seconds=stale_grace_seconds,
                )
            if acquired:
                owner_path = lock / LOCK_OWNER_FILE
                try:
                    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                    if hasattr(os, "O_NOFOLLOW"):
                        flags |= os.O_NOFOLLOW
                    fd = os.open(owner_path, flags, 0o600)
                    with os.fdopen(fd, "w") as stream:
                        json.dump({"pid": pid, "token": token, "created": time.time()}, stream)
                        stream.write("\n")
                    return token
                except Exception:
                    try:
                        owner_path.unlink(missing_ok=True)
                        lock.rmdir()
                    except OSError:
                        pass
                    raise
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("timed out waiting for the usage-ledger lock")
        time.sleep(min(poll_seconds, remaining))


def release_directory_lock(lock: Path, token: str, *, owner_pid: int | None = None) -> bool:
    """Release only the exact lock generation owned by this PID and token."""
    pid = os.getpid() if owner_pid is None else owner_pid
    with path_lock_guard(lock):
        owner = _directory_lock_owner(lock)
        if owner is None or owner.get("pid") != pid or owner.get("token") != token:
            return False
        try:
            (lock / LOCK_OWNER_FILE).unlink()
            lock.rmdir()
        except FileNotFoundError:
            return False
        except OSError:
            return False
        return True


def data_dir() -> Path:
    env = os.environ.get("MB_DATA_DIR")
    return Path(env).expanduser() if env else (REPO / "data")


def history_path(monitoring: dict | None = None) -> Path:
    if monitoring is None:
        monitoring = load_config("monitoring.json", required=False)
    rel = (monitoring or {}).get("history_path", "usage-history.jsonl")
    p = Path(rel)
    return p if p.is_absolute() else (data_dir() / p.name)


def observability_path(monitoring: dict | None = None) -> Path:
    """Runtime orchestration-event JSONL — override-aware via MB_DATA_DIR.

    Relative names stay inside data_dir (basename only, matching history_path)
    so a configured path cannot escape into the repo or a home directory.
    """
    if monitoring is None:
        monitoring = load_config("monitoring.json", required=False)
    obs = (monitoring or {}).get("observability") or {}
    rel = obs.get("events_path", "orchestration-events.jsonl")
    p = Path(rel)
    return p if p.is_absolute() else (data_dir() / p.name)


def read_history(monitoring: dict | None = None) -> list[dict]:
    """Read the append-only usage-history JSONL (one JSON record per line)."""
    p = history_path(monitoring)
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def observed_windows() -> dict:
    """Learned reset anchors written by usage-record.py --learn-windows (never overrides owner)."""
    p = data_dir() / "observed-windows.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}
