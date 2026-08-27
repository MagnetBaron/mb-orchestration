#!/usr/bin/env python3
"""subscription-calculator — recommend a subscription stack from last month's habits.

A USER-GUIDE helper (best-practices, NOT orchestration runtime — never loaded into
agent context). Give it what you actually did last month; it recommends the plan
stack that fits, with transparent reasons and a rough monthly cost. Deterministic:
same inputs → same recommendation.

Habit inputs (flags, or --from-json a file with the same keys):
  --implement-hours-per-day N   heavy coding/listing volume (Grok)
  --reviews-per-week N          frontier reviews needed (Claude Fable/Opus, Sol)
  --mcp-bulk-per-week N         Google-MCP bulk fetch jobs (Codex Terra / Opus)
  --cross-family                you do money/auth/PII/secrets work (needs 2 review families)
  --storefront-pixels           storefront theme/pixel work (Review D)
  --analytics                   Clarity heatmap/replay analysis (Heat Map)
  --ide-hours-per-day N         time in an IDE agent (Cursor)
  --team-size N                 people sharing the system

Prices are indicative monthly USD for sizing only; verify current pricing before buying.
"""
from __future__ import annotations
import argparse, json, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mborch  # noqa: E402

PRICES = {
    "codex-200": 200, "grok-heavy": 300, "cursor-ultra": 200,
    "claude-max": 200, "claude-team-premium": 125, "claude-pro": 25,
    "fireworks-review-e": 20,
}


def recommend(h):
    stack = {}
    reasons = []

    # Implement volume → Grok Heavy (abundant volume family)
    if h["implement_hours_per_day"] >= 1 or h["storefront_pixels"] or h["analytics"]:
        stack["grok-heavy"] = 1
        reasons.append("Grok SuperGrok Heavy: abundant implement volume + the two Grok Bot identities "
                       "(Review D pixels, Heat Map analytics) ride this one plan.")

    # Frontier review → Claude seats. Fable-capable Max is the anchor.
    reviews = h["reviews_per_week"]
    if reviews > 0 or h["cross_family"]:
        stack["claude-max"] = 1
        reasons.append("1× Claude Max: the Fable + Opus 4.8 anchor for frontier review/architecture.")
    # More review volume → add Team premium seats (Fable) for teamclaude rotation.
    extra_team = 0
    if reviews > 10:
        extra_team = min(3, (reviews - 10 + 14) // 15)  # ~1 seat per 15 reviews/wk over 10
    if extra_team:
        stack["claude-team-premium"] = extra_team
        reasons.append(f"{extra_team}× Claude Team premium (Fable): teamclaude rotates review load across 5h windows "
                       "so no single account caps mid-week.")
    # Overflow / cheap Opus capacity if sustained but not review-heavy
    if h["implement_hours_per_day"] >= 3 and reviews <= 10:
        stack["claude-pro"] = 2
        reasons.append("2× Claude Pro: cheap Opus 4.8 overflow + teamclaude rotation headroom (no Fable).")

    # MCP bulk + the OpenAI review family → Codex $200
    if h["mcp_bulk_per_week"] > 0 or h["cross_family"]:
        stack["codex-200"] = 1
        reasons.append("Codex $200: GPT Terra runs Google-MCP bulk, and Sol gives the OpenAI review family — "
                       "the second family a cross-family gate needs alongside Anthropic.")

    # Cross-family without Codex → Fireworks fills the independent family
    if h["cross_family"] and "codex-200" not in stack:
        stack["fireworks-review-e"] = 1
        reasons.append("Fireworks Review E (~$20/mo metered): without Codex you have no OpenAI family, so an "
                       "open-weight family is required to satisfy a cross-family gate. See USER-GUIDE §Fable.")

    # IDE time → Cursor Ultra
    if h["ide_hours_per_day"] >= 1:
        stack["cursor-ultra"] = 1
        reasons.append("Cursor Ultra: first-party Grok pool for IDE work + $400 Other-Models as the last-resort bucket.")

    # Team scaling note
    if h["team_size"] > 1:
        reasons.append(f"Team of {h['team_size']}: give each person an entry surface (entrypoints.json), keep ONE dispatcher. "
                       "Add Claude Team seats rather than more Max plans.")

    monthly = sum(PRICES.get(k, 0) * n for k, n in stack.items())
    return stack, reasons, monthly


def parse_habits(args):
    if args.from_json:
        h = json.loads(open(args.from_json).read())
    else:
        h = {}
    def g(key, val):
        return h.get(key, val)
    return {
        "implement_hours_per_day": g("implement_hours_per_day", args.implement_hours_per_day),
        "reviews_per_week": g("reviews_per_week", args.reviews_per_week),
        "mcp_bulk_per_week": g("mcp_bulk_per_week", args.mcp_bulk_per_week),
        "cross_family": g("cross_family", args.cross_family),
        "storefront_pixels": g("storefront_pixels", args.storefront_pixels),
        "analytics": g("analytics", args.analytics),
        "ide_hours_per_day": g("ide_hours_per_day", args.ide_hours_per_day),
        "team_size": g("team_size", args.team_size),
    }


def from_history():
    """Utilization-based advice: compare what you PAY for against what you USED last period."""
    monitoring = mborch.load_config("monitoring.json", required=False)
    history = mborch.read_history(monitoring)
    subs = mborch.load_config("subscriptions.json", required=False).get("subscriptions", {})
    windows = mborch.load_config("usage-windows.json", required=False).get("seats", {})
    # seat → subscription
    seat_sub = {seat: w.get("subscription") for seat, w in windows.items()}
    stats = defaultdict(lambda: {"samples": 0, "sum": 0.0, "max": 0.0, "spent": 0, "billing": "included"})
    for h in history:
        seat = h.get("seat")
        pct = h.get("pct")
        if seat is None:
            continue
        st = stats[seat]
        st["billing"] = h.get("billing", st["billing"])
        if isinstance(pct, (int, float)):
            st["samples"] += 1
            st["sum"] += pct
            st["max"] = max(st["max"], pct)
        if h.get("tier") == "spent":
            st["spent"] += 1
    recs, util = [], []
    # per-subscription utilization
    sub_used = defaultdict(lambda: {"avg": 0.0, "max": 0.0, "spent": 0, "seats": 0})
    for seat, st in stats.items():
        sub = seat_sub.get(seat)
        avg = (st["sum"] / st["samples"]) if st["samples"] else 0.0
        util.append({"seat": seat, "subscription": sub, "avg_pct": round(avg, 1), "max_pct": round(st["max"], 1),
                     "times_spent": st["spent"], "billing": st["billing"]})
        if sub:
            u = sub_used[sub]
            u["avg"] = max(u["avg"], avg)
            u["max"] = max(u["max"], st["max"])
            u["spent"] += st["spent"]
            u["seats"] += 1
    for sid, s in subs.items():
        cost = s.get("monthly_usd") or 0
        u = sub_used.get(sid, {"avg": 0.0, "max": 0.0, "spent": 0})
        if not history:
            continue
        if u["max"] < 20 and cost >= 100:
            recs.append(f"DOWNGRADE candidate: {sid} ({s.get('product')}, ${cost}/mo) peaked at {u['max']:.0f}% — under-used; a smaller plan may suffice.")
        elif u["spent"] >= 3 or u["max"] >= 95:
            recs.append(f"ADD capacity near {sid} ({s.get('product')}): its seats hit the cap {u['spent']}x — you are losing throughput; add a seat/plan of the same family.")
    metered_used = [x for x in util if x["billing"] == "metered" and x["max_pct"] > 0]
    if metered_used:
        recs.append(f"Metered $ in use ({', '.join(x['seat'] for x in metered_used)}) — a matching INCLUDED subscription would cut API billing.")
    if not history:
        recs.append("No usage history yet — schedule bin/usage-record.py --snapshot (e.g. hourly) so this can compare paid vs used.")
    return {"utilization": sorted(util, key=lambda x: -x["avg_pct"]), "recommendations": recs}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Recommend a subscription stack from last month's habits.")
    ap.add_argument("--from-history", action="store_true", help="utilization-based advice from data/usage-history.jsonl")
    ap.add_argument("--implement-hours-per-day", type=float, default=0)
    ap.add_argument("--reviews-per-week", type=int, default=0)
    ap.add_argument("--mcp-bulk-per-week", type=int, default=0)
    ap.add_argument("--cross-family", action="store_true")
    ap.add_argument("--storefront-pixels", action="store_true")
    ap.add_argument("--analytics", action="store_true")
    ap.add_argument("--ide-hours-per-day", type=float, default=0)
    ap.add_argument("--team-size", type=int, default=1)
    ap.add_argument("--from-json", help="load habits from a JSON file (keys = long flag names with underscores)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.from_history:
        result = from_history()
        if args.json:
            print(json.dumps(result, indent=2))
            return 0
        print("subscription-calculator — utilization from usage history (paid vs used)")
        print("=" * 72)
        print(f"{'seat':<18}{'avg%':>7}{'max%':>7}{'spent':>7}  billing")
        for x in result["utilization"]:
            print(f"{x['seat']:<18}{x['avg_pct']:>7}{x['max_pct']:>7}{x['times_spent']:>7}  {x['billing']}")
        print("-" * 72)
        print("recommendations:")
        for r in result["recommendations"]:
            print(f"  · {r}")
        print("=" * 72)
        print("Indicative — verify current pricing/tiers before changing plans.")
        return 0

    h = parse_habits(args)
    stack, reasons, monthly = recommend(h)

    if args.json:
        print(json.dumps({"habits": h, "recommended_stack": stack,
                          "monthly_usd_indicative": monthly, "reasons": reasons}, indent=2))
        return 0

    print("subscription-calculator — recommendation from last month's habits")
    print("=" * 72)
    print("habits:", ", ".join(f"{k}={v}" for k, v in h.items()))
    print("-" * 72)
    if not stack:
        print("No paid stack indicated — a single Claude Pro ($25) covers light solo use.")
    else:
        print("recommended stack:")
        for k, n in stack.items():
            print(f"  {n}× {k:<22} ~${PRICES.get(k,0)*n}/mo")
    print(f"  {'indicative total':<26} ~${monthly}/mo")
    print("-" * 72)
    print("why:")
    for r in reasons:
        print(f"  · {r}")
    print("=" * 72)
    print("Indicative sizing only — verify current pricing/tiers before buying. See USER-GUIDE.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
