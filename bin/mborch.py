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
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DEFAULT_CONFIG = REPO / "config"


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
