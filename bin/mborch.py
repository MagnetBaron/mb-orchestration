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

Data (history/observed windows) lives under $MB_DATA_DIR or <repo>/data (gitignored).
"""
from __future__ import annotations
import json
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DEFAULT_CONFIG = REPO / "config"


# ---- Forbidden-model matcher: the ONE hard invariant of this system ----------
# Policy: Opus 5.0 must NEVER run (default or reviewer). Opus 5.1 and every later
# minor are NOT blocked — they enter through the normal capability+prowess slot-in
# (providers.json `model_slot_in`). So we match the Opus-5.0 version token EXACTLY;
# this is deliberately NOT a wildcard over the whole "opus-5" series.
#
# Read what follows the "opus5" stem:
#   (nothing)                    "opus-5"            -> 5.0        -> BLOCK
#   -0  / .0                     "opus-5-0"/"5.0"    -> 5.0        -> BLOCK
#   -<>=5-digit build/date>      "opus-5-20260401"   -> 5.0 GA     -> BLOCK
#   non-numeric build tag        "opus-5-preview"    -> unversioned 5.0 -> BLOCK
#   -<n> / .<n>, n >= 1 (short)  "opus-5-1"/"5.2"    -> later minor -> ALLOW
# A short integer (<=4 digits) after opus5 is a MINOR version (0 blocks, >=1 allows);
# a long run (>=5 digits) is a build/date stamp on 5.0. Anything that is not Opus-5
# at all (opus-4-8, sonnet-5, fable-5, haiku-4-5-*) never matches here.
_OPUS5_STEM = re.compile(r"(?:^|[^0-9a-z])opus[-_.]?5(?![0-9])(.*)$", re.IGNORECASE)


def is_opus5_zero(model: str | None) -> bool:
    """True iff `model` names Opus 5.0 in any form (bare, -0/.0, a 5.0 build/date
    stamp, or an unversioned opus-5 build). Opus 5.1+ (minor >= 1) and every model
    that is not Opus-5 return False — those are allowed to slot in normally."""
    if not model:
        return False
    m = _OPUS5_STEM.search(model)
    if not m:
        return False
    tail = m.group(1)
    minor = re.match(r"[-_.]?([0-9]+)", tail)
    if minor is None:
        return True                       # bare / non-numeric opus-5 == 5.0
    digits = minor.group(1)
    if len(digits) >= 5:
        return True                       # build/date stamp on 5.0 (e.g. 8-digit GA date)
    return int(digits) == 0               # 5.0 only; 5.1, 5.2, ... allowed


def model_is_forbidden(model: str | None, forbidden_map: dict | None) -> bool:
    """A model is forbidden if it is Opus 5.0 (the hard invariant) OR is explicitly
    listed — by id or alias — in providers.json `forbidden_models` (extensible data).
    Everything else, including Opus 5.1+, is allowed."""
    if is_opus5_zero(model):
        return True
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
