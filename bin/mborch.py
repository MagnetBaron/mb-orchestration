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
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DEFAULT_CONFIG = REPO / "config"


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
