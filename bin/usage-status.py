#!/usr/bin/env python3
"""usage-status — durable, script-computed seat reset/limit status for mb-orchestration.

Reset times are computed from config/usage-windows.json (the ONLY place a reset lives);
live state comes from config/usage-ledger.json (written by wrappers on a real 429, or the
owner — never a probe/timeout, never an LLM). No network calls.

Seat state is a TRI-STATE tier so a self-imposed cap never strands real capacity:
  * available — preferred; drain here first
  * reserve   — over its reserve line (soft cap) OR an intake seat holding headroom;
                still USABLE as a last resort (never park while a reserve seat has quota)
  * spent     — a real 429/limit recorded; genuinely exhausted until reset

Importable: resolve-route.py, drain-plan.py, dashboard.py call compute() for the rows.

Usage:
  usage-status.py                 human table
  usage-status.py --json          machine-readable status
  usage-status.py --earliest-reset   soonest reset among spent/reserve seats
  usage-status.py --seat NAME     one seat
"""
from __future__ import annotations

import argparse
import calendar
import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mborch  # noqa: E402
import teamclaude_status  # noqa: E402

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None

_WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
DEFAULT_TZ = "America/Chicago"


def _now(tz):
    if ZoneInfo and tz:
        try:
            return datetime.now(ZoneInfo(tz))
        except Exception:
            pass
    return datetime.now().astimezone()


def _tzinfo(tz):
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
        return now.replace(year=y, month=m, day=d, hour=0, minute=0, second=0, microsecond=0)

    cand = build(year, month, day)
    if cand <= now:
        month += 1
        if month == 13:
            month, year = 1, year + 1
        cand = build(year, month, day)
    return cand


def reset_for_window(win, default_tz):
    kind = win.get("kind")
    tz = win.get("tz", default_tz)
    if kind == "weekly":
        dt = next_weekly(win.get("weekday"), win.get("time"), tz)
        if dt:
            return f"weekly → {dt:%a %Y-%m-%d %H:%M %Z}", dt
        return "weekly → anchor unset (set weekday/time in usage-windows.json, or learn it via usage-record.py)", None
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
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    try:
        parsed = float(str(value).strip())
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def to_aware(dt, tzname=DEFAULT_TZ):
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    tz = _tzinfo(tzname)
    return dt.replace(tzinfo=tz) if tz else dt.astimezone()


def _apply_observed(windows, observed):
    """Fill NULL anchors from a learned observed-window (never overrides an owner-set anchor)."""
    if not observed:
        return windows, False
    used = False
    out = []
    for w in windows:
        w = dict(w)
        if w.get("kind") == "weekly" and not w.get("weekday") and observed.get("kind") == "weekly" and observed.get("weekday"):
            w["weekday"], w["time"] = observed.get("weekday"), observed.get("time")
            used = True
        elif w.get("kind") == "monthly" and not w.get("day") and observed.get("kind") == "monthly" and observed.get("day"):
            w["day"] = observed.get("day")
            used = True
        out.append(w)
    return out, used


def seat_state(name, seat, ledger, default_tz=DEFAULT_TZ, observed=None):
    windows, learned = _apply_observed(seat.get("windows", []), observed)
    resets = [reset_for_window(w, default_tz) for w in windows]
    concrete = [dt for _, dt in resets if dt is not None]
    next_reset_dt = min(concrete) if concrete else None

    entry = ledger.get(name) if isinstance(ledger, dict) else None
    if not isinstance(entry, dict):
        entry = {}
    now_ref = to_aware(_now(default_tz), default_tz)
    spent_until = to_aware(parse_iso(entry.get("spent_until")), default_tz)
    spent_without_reset = entry.get("spent") is True and spent_until is None
    pct = to_number(entry.get("pct"))
    # reserve line: reserve_pct (new) or legacy soft_cap_pct
    reserve_pct = seat.get("reserve_pct", seat.get("soft_cap_pct"))
    drain = seat.get("drain", "full")
    intake = bool(seat.get("intake"))
    billing = seat.get("billing", "included")
    monthly_cap_usd = to_number(seat.get("monthly_cap_usd"))
    monthly_spend_usd = to_number(entry.get("monthly_spend_usd"))
    spend_period = entry.get("monthly_spend_period")
    spend_updated = to_aware(parse_iso(entry.get("updated")), default_tz)
    current_period = now_ref.strftime("%Y-%m")
    period_start = now_ref.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    spend_evidence_valid = (
        monthly_spend_usd is not None
        and monthly_spend_usd >= 0
        and spend_period == current_period
        and spend_updated is not None
        and period_start <= spend_updated <= now_ref + timedelta(minutes=5)
    )

    su_future = spent_until if (spent_until is not None and spent_until > now_ref) else None
    over_reserve = (pct is not None and reserve_pct is not None and pct >= reserve_pct)
    # A drain:reserve seat holds headroom by policy even without a pct signal. `intake` is
    # just a label (used for reserve sizing) — it does NOT demote a seat on its own, so a
    # solo user's single (intake) seat stays 'available' and codes normally.
    holds_reserve = (drain == "reserve")
    # A configured metered ceiling is executable state, not prose. Unknown
    # month-to-date spend fails closed because routing cannot prove another call
    # stays below the owner's cap; an at/over-cap row is positively spent.
    metered_spend_unknown = monthly_cap_usd is not None and not spend_evidence_valid
    over_monthly_cap = (
        monthly_cap_usd is not None
        and spend_evidence_valid
        and monthly_spend_usd >= monthly_cap_usd
    )

    if su_future is not None or spent_without_reset or metered_spend_unknown or over_monthly_cap:
        tier = "spent"
    elif over_reserve or holds_reserve:
        tier = "reserve"
    else:
        tier = "available"

    if tier == "spent":
        if metered_spend_unknown:
            state = "SPENT (metered monthly spend unknown, malformed, or stale)"
        elif over_monthly_cap:
            state = f"SPENT (${monthly_spend_usd:g}≥${monthly_cap_usd:g} monthly cap)"
        else:
            state = "SPENT" if su_future is not None else "SPENT (reset unknown)"
    elif tier == "reserve":
        why = f"{pct:g}%≥{reserve_pct}%" if over_reserve else "reserve policy"
        state = f"RESERVE ({why}) — usable as last resort"
    elif pct is not None:
        state = f"available ({pct:g}%)"
    else:
        state = "available (no signal recorded)"

    # A hard exhaustion signal with no provider reset remains parked until live
    # recovery is verified.  The configured/learned schedule may still be useful
    # context in `next_reset`, but it is not evidence that clears this ledger row
    # and therefore must not drive `--earliest-reset` or runway calculations.
    reset_effective = (
        None if spent_without_reset
        else su_future if su_future is not None
        else next_reset_dt
    )
    runway_seconds = None
    if reset_effective is not None:
        runway_seconds = max(0, int((to_aware(reset_effective, default_tz) - now_ref).total_seconds()))

    return {
        "seat": name,
        "meter": seat.get("meter"),
        "family": seat.get("family"),
        "fable": seat.get("fable"),
        "subscription": seat.get("subscription"),
        "reserve_pct": reserve_pct,
        "drain": drain,
        "intake": intake,
        "billing": billing,
        "monthly_cap_usd": monthly_cap_usd,
        "monthly_spend_usd": monthly_spend_usd,
        "monthly_spend_period": spend_period,
        "monthly_spend_fresh": spend_evidence_valid,
        "tier": tier,
        "usable": tier != "spent",
        "available": tier == "available",
        "state": state,
        "pct": pct,
        "windows": [label for label, _ in resets],
        "window_kinds": [w.get("kind") for w in windows],
        "windows_learned": learned,
        "next_reset": next_reset_dt.isoformat() if next_reset_dt else None,
        "reset_effective": reset_effective.isoformat() if reset_effective else None,
        "runway_seconds": runway_seconds,
        "live_signal": seat.get("live_signal"),
        "ledger": entry or None,
    }


def rotation_status():
    """Return schema-bound live rotation state without exposing account identities."""
    return teamclaude_status.inspect_status()


def attach_rotation(rows, rotation=None):
    """Attach one value-free live fleet receipt to Anthropic rows for routing."""
    rotation = rotation_status() if rotation is None else rotation
    out = []
    for row in rows:
        copy = dict(row)
        if copy.get("family") == "anthropic":
            copy["teamclaude_rotation"] = rotation
        out.append(copy)
    return out


def compute(ledger_path=None):
    """Importable: return (updated, rows). No printing, no exit."""
    conf = mborch.load_config("usage-windows.json", required=True)
    lp = Path(ledger_path) if ledger_path else mborch.ledger_path()
    ledger = json.loads(lp.read_text()) if lp.exists() else {}
    observed = mborch.observed_windows()
    seats = conf.get("seats", {})
    rows = attach_rotation([
        seat_state(name, seat, ledger, observed=observed.get(name))
        for name, seat in seats.items()
    ])
    return conf.get("updated"), rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="Script-computed seat reset/limit status.")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--earliest-reset", action="store_true",
                    help="soonest reset among currently spent/reserve seats")
    ap.add_argument("--seat", help="show only this seat")
    ap.add_argument("--ledger", type=Path, default=None)
    args = ap.parse_args(argv)

    conf = mborch.load_config("usage-windows.json", required=True)
    lp = args.ledger if args.ledger else mborch.ledger_path()
    ledger = json.loads(Path(lp).read_text()) if Path(lp).exists() else {}
    observed = mborch.observed_windows()
    seats = conf.get("seats", {})
    rotation = rotation_status()
    rows = attach_rotation([
        seat_state(name, seat, ledger, observed=observed.get(name))
        for name, seat in seats.items()
    ], rotation)
    if args.seat:
        rows = [r for r in rows if r["seat"] == args.seat]
        if not rows:
            sys.exit(f"usage-status: no such seat {args.seat!r}")

    if args.earliest_reset:
        def constrained(r):
            return r["tier"] in ("spent", "reserve")
        cand = []
        for r in rows:
            if not constrained(r):
                continue
            inst = to_aware(parse_iso(r["reset_effective"]))
            if inst is not None:
                cand.append((r, inst))
        stuck = [r["seat"] for r in rows
                 if constrained(r) and to_aware(parse_iso(r["reset_effective"])) is None]
        if not cand and not stuck:
            print("no seat is currently marked spent or reserve")
            return 0
        if cand:
            soonest, inst = min(cand, key=lambda ri: ri[1])
            print(f"{soonest['seat']}  next reset {inst.isoformat()}")
        if stuck:
            print("spent/reserve but reset unknown (rolling/unset): " + ", ".join(stuck))
        return 0

    if args.json:
        print(json.dumps({"updated": conf.get("updated"), "seats": rows,
                          "rotation": rotation}, indent=2))
        return 0

    print(f"usage-status  (windows: config/usage-windows.json, updated {conf.get('updated')})")
    print(f"ledger: {lp if Path(lp).exists() else '(none — no live signal recorded)'}")
    print("-" * 72)
    for r in rows:
        fable = " ·fable" if r.get("fable") else ""
        fam = f" [{r['family']}]" if r.get("family") else ""
        bill = " $metered" if r.get("billing") == "metered" else ""
        print(f"{r['seat']:<18}{fam}{fable}{bill}  {r['state']}")
        if r["reset_effective"]:
            print(f"  next reset: {r['reset_effective']}")
    print("-" * 72)
    print(f"rotation: {rotation['status']}")
    print("tiers: available → reserve (usable last resort) → spent. limits from recorded "
          "429/ledger + computed windows, never LLM token estimation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
