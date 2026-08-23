#!/usr/bin/env python3
"""usage-status — durable, script-computed seat reset/limit status for mb-orchestration.

Why this exists
---------------
Reset times must not be hardcoded in policy prose, and remaining quota must not be
guessed by an LLM from token counts. This script is the single reader of:

  * usage-windows.json   — window/cap definitions + reset anchors (the ONLY place a
                           reset time lives). Required, same directory as this file.
  * usage-ledger.json    — live/manual state written by wrappers (on a real 429) or
                           the owner — never a probe/timeout, never an LLM: { "<seat>":
                           {"spent_until": ISO8601,
                           "pct": 0-100, "note": str, "updated": ISO8601 } }. Optional.

It computes the NEXT reset per seat from the anchors and reports each seat's state
from recorded signals. Dispatch/agents run this instead of eyeballing a dashboard.

No network calls. Live per-provider probes plug in by writing usage-ledger.json —
only a real 429/limit writes spent state; a timeout writes nothing.

Usage:
  usage-status.py                 human table
  usage-status.py --json          machine-readable status (for dispatch)
  usage-status.py --earliest-reset   soonest reset among seats currently spent
  usage-status.py --ledger PATH   read an alternate ledger file
"""
from __future__ import annotations

import argparse
import calendar
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - zoneinfo is stdlib on 3.9+
    ZoneInfo = None

HERE = Path(__file__).resolve().parent
CONF_PATH = HERE / "usage-windows.json"
DEFAULT_LEDGER = HERE / "usage-ledger.json"
_WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def _now(tz: str | None) -> datetime:
    if ZoneInfo and tz:
        try:
            return datetime.now(ZoneInfo(tz))
        except Exception:
            pass
    return datetime.now().astimezone()


def _tzinfo(tz: str | None):
    if ZoneInfo and tz:
        try:
            return ZoneInfo(tz)
        except Exception:
            return None
    return None


def next_weekly(weekday, hhmm, tz):
    if not weekday or not hhmm:
        return None
    wd = _WEEKDAYS.get(str(weekday).lower()[:3])
    if wd is None:
        return None
    try:
        hour, minute = (int(x) for x in str(hhmm).split(":"))
    except Exception:
        return None
    now = _now(tz)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    target += timedelta(days=(wd - now.weekday()) % 7)
    if target <= now:
        target += timedelta(days=7)
    return target


def next_monthly(day, tz):
    if not day:
        return None
    now = _now(tz)
    year, month = now.year, now.month

    def build(y, m, d):
        d = min(int(d), calendar.monthrange(y, m)[1])
        return now.replace(year=y, month=m, day=d, hour=0, minute=0,
                           second=0, microsecond=0)

    cand = build(year, month, day)
    if cand <= now:
        month += 1
        if month == 13:
            month, year = 1, year + 1
        cand = build(year, month, day)
    return cand


def reset_for_window(win, default_tz):
    """Return (label, concrete_datetime_or_None) for one window definition."""
    kind = win.get("kind")
    tz = win.get("tz", default_tz)
    if kind == "weekly":
        dt = next_weekly(win.get("weekday"), win.get("time"), tz)
        if dt:
            return f"weekly → {dt:%a %Y-%m-%d %H:%M %Z}", dt
        return "weekly → anchor unset (set weekday/time in usage-windows.json)", None
    if kind == "monthly":
        dt = next_monthly(win.get("day"), tz)
        if dt:
            return f"monthly → {dt:%Y-%m-%d %Z}", dt
        return "monthly → billing day unset (set day in usage-windows.json)", None
    if kind == "rolling":
        hrs = win.get("hours", "?")
        return f"rolling {hrs}h → last window start + {hrs}h (see live_signal)", None
    if kind == "none":
        return "no reset (metered $)", None
    return f"unknown window kind: {kind!r}", None


def parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def to_number(value):
    """Coerce int/float/numeric-string to float; bool and junk → None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def to_aware(dt, tzname="America/Chicago"):
    """Attach a tz to a naive datetime so comparisons/min are by real instant."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    tz = _tzinfo(tzname)
    return dt.replace(tzinfo=tz) if tz else dt.astimezone()


def seat_state(name, seat, ledger, default_tz="America/Chicago"):
    windows = seat.get("windows", [])
    resets = [reset_for_window(w, default_tz) for w in windows]
    concrete = [dt for _, dt in resets if dt is not None]
    next_reset_dt = min(concrete) if concrete else None

    entry = ledger.get(name) if isinstance(ledger, dict) else None
    if not isinstance(entry, dict):  # null / string / malformed entry → treat as no signal
        entry = {}
    now_ref = to_aware(_now(default_tz), default_tz)
    spent_until = to_aware(parse_iso(entry.get("spent_until")), default_tz)
    pct = to_number(entry.get("pct"))
    cap = seat.get("soft_cap_pct")

    # A spent_until only counts while it is in the FUTURE; a past one must NOT shadow a
    # still-over-cap pct (a wrapper 429 expires, but the weekly % can still be capped).
    su_future = spent_until if (spent_until is not None and spent_until > now_ref) else None
    if su_future is not None:
        state = "SPENT"
    elif pct is not None and cap is not None and pct >= cap:
        state = f"SOFT-CAPPED ({pct:g}%≥{cap}%)"
    elif pct is not None:
        state = f"available ({pct:g}%)"
    else:
        state = "available (no signal recorded)"

    # Effective reset: a spent seat recovers at its recorded spent_until (that instant
    # IS the reset, and works even for rolling windows with no computed anchor);
    # otherwise fall back to the computed window reset.
    reset_effective = su_future if su_future is not None else next_reset_dt

    return {
        "seat": name,
        "meter": seat.get("meter"),
        "soft_cap_pct": cap,
        "state": state,
        "windows": [label for label, _ in resets],
        "next_reset": next_reset_dt.isoformat() if next_reset_dt else None,
        "reset_effective": reset_effective.isoformat() if reset_effective else None,
        "live_signal": seat.get("live_signal"),
        "ledger": entry or None,
    }


def load(path, required):
    if not path.exists():
        if required:
            sys.exit(f"usage-status: missing required config {path}")
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # pragma: no cover
        sys.exit(f"usage-status: cannot parse {path}: {exc}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Script-computed seat reset/limit status.")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--earliest-reset", action="store_true",
                    help="print the soonest reset among currently-spent seats")
    ap.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER,
                    help="path to a usage-ledger.json (default: alongside config)")
    args = ap.parse_args(argv)

    conf = load(CONF_PATH, required=True)
    ledger = load(args.ledger, required=False)
    seats = conf.get("seats", {})
    rows = [seat_state(name, seat, ledger) for name, seat in seats.items()]

    if args.earliest_reset:
        def constrained(r):
            return r["state"].startswith("SPENT") or "SOFT-CAPPED" in r["state"]
        cand = []
        for r in rows:
            if not constrained(r):
                continue
            inst = to_aware(parse_iso(r["reset_effective"]))
            if inst is not None:
                cand.append((r, inst))  # compare real instants, not ISO strings
        stuck = [r["seat"] for r in rows
                 if constrained(r) and to_aware(parse_iso(r["reset_effective"])) is None]
        if not cand and not stuck:
            print("no seat is currently marked spent or capped")
            return 0
        if cand:
            soonest, inst = min(cand, key=lambda ri: ri[1])
            print(f"{soonest['seat']}  next reset {inst.isoformat()}")
        if stuck:
            print("spent/capped but reset unknown (rolling/unset): " + ", ".join(stuck))
        return 0

    if args.json:
        print(json.dumps({"updated": conf.get("updated"), "seats": rows}, indent=2))
        return 0

    print(f"usage-status  (windows: usage-windows.json, updated {conf.get('updated')})")
    print(f"ledger: {args.ledger if args.ledger.exists() else '(none — no live signal recorded)'}")
    print("-" * 72)
    for r in rows:
        print(f"{r['seat']:<20} {r['state']}")
        if r["reset_effective"]:
            print(f"  next reset: {r['reset_effective']}")
        for w in r["windows"]:
            print(f"  window: {w}")
    print("-" * 72)
    print("limits come from recorded 429/ledger signals + computed windows above, "
          "never from LLM token estimation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
