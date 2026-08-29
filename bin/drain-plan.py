#!/usr/bin/env python3
"""drain-plan — maximize subscription value: use quota before it is lost.

Answers "what should I drain next, and how much do I reserve?" from live seat
state + policy, deterministically:

  * DRAIN ORDER — rank USABLE seats so that soon-to-reset weekly/monthly quota with
    capacity unused is spent FIRST (before it resets to waste), included seats before
    metered $, reserves/intake last. This is DOCTRINE §Reset-aware placement, executable.
  * RESERVE — recommend an intake/dispatch reserve_pct from observed dispatch
    consumption × margin (config/monitoring.json), floored at the default. A reserve
    only lowers priority; it NEVER blocks coding (never-strand).
  * WASTE RISK — flag weekly/monthly seats resetting soon with lots unused.

  drain-plan.py               human plan
  drain-plan.py --json
  drain-plan.py --reserve     just the reserve recommendation(s)
  drain-plan.py --task-seconds 1800   flag seats that would reset mid-task
"""
from __future__ import annotations
import argparse, importlib.util, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mborch  # noqa: E402
import routing  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


usage_status = _load("usage_status", HERE / "usage-status.py")


def recommend_reserve(intake_seat, history, defaults):
    margin = defaults.get("margin_factor", 1.5)
    floor = defaults.get("intake_reserve_pct", 15)
    samples = [h.get("pct") for h in history if h.get("seat") == intake_seat and isinstance(h.get("pct"), (int, float))]
    if samples:
        observed = max(samples[-30:])  # recent observed dispatch consumption
        rec = min(95, max(floor, round(observed * margin)))
        basis = f"observed recent max {observed:g}% × {margin} margin (floor {floor}%)"
    else:
        rec = floor
        basis = f"no history yet — default floor {floor}% (margin {margin} applies once history exists)"
    return rec, basis


def main(argv=None):
    ap = argparse.ArgumentParser(description="Use-it-or-lose-it drain plan + reserve sizing.")
    ap.add_argument("--reserve", action="store_true", help="only the reserve recommendation")
    ap.add_argument("--task-seconds", type=int, default=0)
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    monitoring = mborch.load_config("monitoring.json", required=False)
    defaults = monitoring.get("reserve_defaults", {"intake_reserve_pct": 15, "margin_factor": 1.5})
    history = mborch.read_history(monitoring)
    _, rows = usage_status.compute(args.ledger)

    # Recommend a reserve only for seats configured to reserve (drain:reserve). A solo
    # drain:full seat is the worker and needs no reserve.
    intake_rows = [r for r in rows if r.get("drain") == "reserve"]
    reserve_recs = []
    for r in intake_rows:
        rec, basis = recommend_reserve(r["seat"], history, defaults)
        reserve_recs.append({"seat": r["seat"], "current_reserve_pct": r.get("reserve_pct"),
                             "recommended_reserve_pct": rec, "basis": basis})

    if args.reserve:
        if args.json:
            print(json.dumps({"reserve_recommendations": reserve_recs}, indent=2))
        else:
            print("reserve recommendation (never blocks coding — only lowers priority):")
            for x in reserve_recs:
                print(f"  {x['seat']}: current={x['current_reserve_pct']} → recommend {x['recommended_reserve_pct']}%  ({x['basis']})")
        return 0

    usable = [r for r in rows if routing.usable(r)]
    ordered = sorted(usable, key=routing.drain_key)

    def waste_risk(r):
        u = routing.expiry_urgency(r)
        kinds = r.get("window_kinds") or []
        return u >= 1.5 and ("weekly" in kinds or "monthly" in kinds)

    plan = []
    for r in ordered:
        plan.append({
            "seat": r["seat"], "billing": r.get("billing"), "tier": r["tier"],
            "intake": r.get("intake"), "window_kinds": r.get("window_kinds"),
            "runway_seconds": r.get("runway_seconds"),
            "urgency": round(routing.expiry_urgency(r), 2),
            "waste_risk": waste_risk(r),
            "resets_mid_task": routing.resets_before(r, args.task_seconds),
        })

    if args.json:
        print(json.dumps({"drain_order": plan, "reserve_recommendations": reserve_recs}, indent=2))
        return 0

    print("drain-plan — use quota before it is lost (maximize subscription value)")
    print("=" * 72)
    print("DRAIN ORDER (send work here first → last):")
    for i, p in enumerate(plan, 1):
        bill = "$metered" if p["billing"] == "metered" else "included"
        tags = []
        if p["intake"]:
            tags.append("intake-reserve")
        if p["waste_risk"]:
            tags.append("⚠WASTE-RISK (resets soon, unused)")
        if p["resets_mid_task"]:
            tags.append("⚠resets-mid-task")
        tag = ("  " + ", ".join(tags)) if tags else ""
        print(f"  {i:>2}. {p['seat']:<18} {bill:<9} {p['tier']:<9} urgency={p['urgency']}{tag}")
    print("-" * 72)
    print("reserve (intake/dispatch headroom — never blocks coding):")
    for x in reserve_recs:
        print(f"  {x['seat']}: current={x['current_reserve_pct']} → recommend {x['recommended_reserve_pct']}%  ({x['basis']})")
    print("=" * 72)
    print("rule: included before metered $ (minimize API cost); soon-to-reset weekly/monthly before rolling")
    print("(use before lost); reserves/intake last but USABLE (never strand).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
