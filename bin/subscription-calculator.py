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
  --no-codex                    Codex is unavailable or intentionally excluded
  --third-party-safe-review     record sanitized eligibility for a future Review E route
  --storefront-pixels           storefront theme/pixel work (records future Review D need)
  --analytics                   Clarity heatmap/replay need (records future Heat Map need)
  --ide-hours-per-day N         time in an IDE agent (Cursor)
  --team-size N                 people sharing the system

Prices are indicative monthly USD for sizing only; verify current pricing before buying.
"""
from __future__ import annotations
import argparse, json, math, sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mborch  # noqa: E402

PRICES = {
    "codex-200": 200, "grok-heavy": 300, "cursor-ultra": 200,
    "claude-max": 200, "claude-team-premium": 125, "claude-pro": 25,
    "fireworks-review-e": 20,
}

HABIT_KEYS = {
    "implement_hours_per_day",
    "reviews_per_week",
    "mcp_bulk_per_week",
    "cross_family",
    "codex_available",
    "third_party_safe_review",
    "storefront_pixels",
    "analytics",
    "ide_hours_per_day",
    "team_size",
}
HISTORY_ANALYSIS_DAYS = 30
DOWNGRADE_MIN_DISTINCT_DAYS = 21
DOWNGRADE_MIN_SPAN_DAYS = 28


def validate_habits(h):
    if not isinstance(h, dict) or set(h) != HABIT_KEYS:
        raise ValueError("habit input must contain exactly the documented keys")
    for key in (
        "cross_family",
        "codex_available",
        "third_party_safe_review",
        "storefront_pixels",
        "analytics",
    ):
        if type(h[key]) is not bool:
            raise ValueError(f"{key} must be an exact JSON boolean")
    for key in ("implement_hours_per_day", "ide_hours_per_day"):
        value = h[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError(f"{key} must be a finite non-negative number")
    for key in ("reviews_per_week", "mcp_bulk_per_week"):
        if type(h[key]) is not int or h[key] < 0:
            raise ValueError(f"{key} must be a non-negative integer")
    if type(h["team_size"]) is not int or h["team_size"] < 1:
        raise ValueError("team_size must be a positive integer")
    return h


def recommend(h):
    validate_habits(h)
    stack = {}
    reasons = []

    # Implement volume → Grok Heavy (abundant volume family)
    if h["implement_hours_per_day"] >= 1:
        stack["grok-heavy"] = 1
        reasons.append("Grok SuperGrok Heavy: abundant Grok Build implementation volume.")
    if h["storefront_pixels"] or h["analytics"]:
        requested = []
        if h["storefront_pixels"]:
            requested.append("Review D pixels")
        if h["analytics"]:
            requested.append("Heat Map analytics")
        reasons.append(
            f"{', '.join(requested)}: recorded as future needs only and do not add a plan. "
            "Both named CLI roles remain hard-parked before inputs until their code-owned "
            "bindings and live gates pass."
        )

    # Frontier review → Claude seats. Fable-capable Max is the anchor.
    reviews = h["reviews_per_week"]
    if reviews > 0 or h["cross_family"]:
        stack["claude-max"] = 1
        reasons.append("1× Claude Max: the Fable + Opus 5 anchor for frontier review/architecture.")
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
        reasons.append("2× Claude Pro: cheap Opus 5 overflow + teamclaude rotation headroom (no Fable).")

    # MCP bulk + the OpenAI review family → Codex $200, unless the caller
    # explicitly says that Codex is unavailable or excluded.
    codex_available = bool(h.get("codex_available", True))
    if codex_available and (h["mcp_bulk_per_week"] > 0 or h["cross_family"]):
        stack["codex-200"] = 1
        reasons.append("Codex $200: GPT Terra runs Google-MCP bulk, and Sol gives the OpenAI review family — "
                       "the second family a cross-family gate needs alongside Anthropic.")

    # Review E is intentionally unwired in the reference configuration. Sanitized
    # artifacts are a necessary future eligibility condition, not evidence that a
    # provider, model, execution recipe, or live route exists today.
    if h["cross_family"] and not codex_available:
        if h.get("third_party_safe_review", False):
            reasons.append(
                "Cross-family review remains unserved: Codex was explicitly excluded. "
                "Sanitized/third-party-safe artifacts make Review E a future setup candidate "
                "only; the reference provider, named model, executable recipe, and live route "
                "are currently unwired, so Review E is neither recommended nor priced."
            )
        else:
            reasons.append(
                "Cross-family review remains unserved: Codex was explicitly excluded and "
                "Review E is forbidden unless the review artifacts are separately declared "
                "sanitized/third-party-safe. Secrets and PII stay parked."
            )
    if h["mcp_bulk_per_week"] > 0 and not codex_available:
        reasons.append(
            "Google-MCP bulk remains unserved because Codex was explicitly excluded; "
            "Review E is a review fallback, not a Terra/MCP substitute."
        )

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
        with open(args.from_json) as handle:
            h = json.load(handle)
        if not isinstance(h, dict):
            raise ValueError("--from-json must contain one JSON object")
        allowed_input_keys = HABIT_KEYS | {"no_codex"}
        unknown = set(h) - allowed_input_keys
        if unknown:
            raise ValueError(f"--from-json contains unknown keys: {sorted(unknown)!r}")
    else:
        h = {}
    def g(key, val):
        return h.get(key, val)
    if "codex_available" in h:
        codex_available = h["codex_available"]
        if type(codex_available) is not bool:
            raise ValueError("codex_available must be an exact JSON boolean")
    else:
        no_codex = h.get("no_codex", args.no_codex)
        if type(no_codex) is not bool:
            raise ValueError("no_codex must be an exact JSON boolean")
        codex_available = not no_codex
    if "no_codex" in h:
        if type(h["no_codex"]) is not bool:
            raise ValueError("no_codex must be an exact JSON boolean")
        if codex_available == h["no_codex"]:
            raise ValueError("codex_available conflicts with no_codex")
    result = {
        "implement_hours_per_day": g("implement_hours_per_day", args.implement_hours_per_day),
        "reviews_per_week": g("reviews_per_week", args.reviews_per_week),
        "mcp_bulk_per_week": g("mcp_bulk_per_week", args.mcp_bulk_per_week),
        "cross_family": g("cross_family", args.cross_family),
        "codex_available": codex_available,
        "third_party_safe_review": g(
            "third_party_safe_review", args.third_party_safe_review
        ),
        "storefront_pixels": g("storefront_pixels", args.storefront_pixels),
        "analytics": g("analytics", args.analytics),
        "ide_hours_per_day": g("ide_hours_per_day", args.ide_hours_per_day),
        "team_size": g("team_size", args.team_size),
    }
    return validate_habits(result)


def from_history(now=None):
    """Compare paid plans with complete, timestamped evidence from the last 30 days."""
    monitoring = mborch.load_config("monitoring.json", required=False)
    retained_history = mborch.read_history(monitoring)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("history analysis clock must be timezone-aware")
    now = now.astimezone(timezone.utc)
    cutoff = now - timedelta(days=HISTORY_ANALYSIS_DAYS)
    timestamped_history = []
    for row in retained_history:
        if not isinstance(row, dict) or not isinstance(row.get("ts"), str):
            continue
        try:
            observed_at = datetime.fromisoformat(row["ts"])
        except (TypeError, ValueError, OverflowError):
            continue
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            continue
        observed_at = observed_at.astimezone(timezone.utc)
        if observed_at <= now:
            normalized = dict(row)
            normalized["_observed_at"] = observed_at
            timestamped_history.append(normalized)
    subs = mborch.load_config("subscriptions.json", required=False).get("subscriptions", {})
    windows = mborch.load_config("usage-windows.json", required=False).get("seats", {})
    # seat → subscription
    seat_sub = {seat: w.get("subscription") for seat, w in windows.items()}
    subscription_seats = defaultdict(set)
    for seat, subscription in seat_sub.items():
        if subscription:
            subscription_seats[subscription].add(seat)
    history = []
    baseline_tiers = {}
    baseline_times = {}
    allowed_tiers = {"available", "reserve", "spent"}
    allowed_billing = {"included", "metered"}
    for row in timestamped_history:
        seat = row.get("seat")
        if not isinstance(seat, str) or seat not in seat_sub:
            continue
        pct = row.get("pct")
        if pct is not None and (
            isinstance(pct, bool)
            or not isinstance(pct, (int, float))
            or not math.isfinite(pct)
            or not 0 <= pct <= 100
        ):
            continue
        tier = row.get("tier")
        if tier is not None and tier not in allowed_tiers:
            continue
        billing = row.get("billing")
        if billing is not None and billing not in allowed_billing:
            continue
        observed_at = row["_observed_at"]
        if observed_at < cutoff:
            if tier is not None and observed_at > baseline_times.get(
                seat, datetime.min.replace(tzinfo=timezone.utc)
            ):
                baseline_tiers[seat] = tier
                baseline_times[seat] = observed_at
            continue
        history.append(row)
    stats = defaultdict(
        lambda: {
            "samples": 0, "sum": 0.0, "max": 0.0,
            "spent_events": 0, "billing": "included", "sample_days": set(),
            "first_sample": None, "last_sample": None,
        }
    )
    timed_tiers = defaultdict(list)
    for h in history:
        seat = h.get("seat")
        pct = h.get("pct")
        if seat is None:
            continue
        st = stats[seat]
        st["billing"] = h.get("billing") or windows[seat].get("billing", st["billing"])
        if pct is not None:
            st["samples"] += 1
            st["sum"] += pct
            st["max"] = max(st["max"], pct)
            observed_at = h["_observed_at"]
            st["sample_days"].add(observed_at.date())
            st["first_sample"] = min(st["first_sample"] or observed_at, observed_at)
            st["last_sample"] = max(st["last_sample"] or observed_at, observed_at)
        ts = h.get("ts")
        if isinstance(ts, str) and isinstance(h.get("tier"), str):
            try:
                parsed_ts = datetime.fromisoformat(ts).timestamp()
            except (TypeError, ValueError, OverflowError):
                pass
            else:
                timed_tiers[seat].append((parsed_ts, h["tier"]))
    # Snapshots are periodic observations. Count one cap event per transition into
    # `spent`, never one event per retained spent sample.
    for seat, tiers in timed_tiers.items():
        in_spent = baseline_tiers.get(seat) == "spent"
        for _ts, tier in sorted(tiers):
            if tier == "spent":
                if not in_spent:
                    stats[seat]["spent_events"] += 1
                in_spent = True
            else:
                in_spent = False
    recs, util = [], []
    # per-subscription utilization
    sub_used = defaultdict(
        lambda: {
            "avg": 0.0, "max": 0.0, "spent": 0, "seats": 0,
            "samples": 0, "sampled_seats": set(), "coverage": {},
        }
    )
    for seat, st in stats.items():
        sub = seat_sub.get(seat)
        avg = (st["sum"] / st["samples"]) if st["samples"] else 0.0
        util.append({"seat": seat, "subscription": sub, "avg_pct": round(avg, 1), "max_pct": round(st["max"], 1),
                     "times_spent": st["spent_events"], "billing": st["billing"]})
        if sub:
            u = sub_used[sub]
            u["avg"] = max(u["avg"], avg)
            u["max"] = max(u["max"], st["max"])
            u["spent"] += st["spent_events"]
            u["seats"] += 1
            u["samples"] += st["samples"]
            if st["samples"]:
                u["sampled_seats"].add(seat)
                span_days = (
                    (st["last_sample"] - st["first_sample"]).total_seconds() / 86400
                    if st["first_sample"] is not None and st["last_sample"] is not None
                    else 0
                )
                u["coverage"][seat] = {
                    "distinct_days": len(st["sample_days"]),
                    "span_days": span_days,
                }
    for sid, s in subs.items():
        cost = s.get("monthly_usd") or 0
        u = sub_used.get(
            sid, {
                "avg": 0.0, "max": 0.0, "spent": 0, "seats": 0,
                "samples": 0, "sampled_seats": set(), "coverage": {},
            }
        )
        if not history:
            continue
        if u["spent"] >= 3:
            recs.append(
                f"ADD capacity near {sid} ({s.get('product')}): its seats entered the "
                f"spent state {u['spent']}x in the last {HISTORY_ANALYSIS_DAYS} days — "
                "observed exhaustion is losing throughput; add a seat/plan of the same family."
            )
            continue
        if u["samples"] < 1:
            continue
        full_coverage = (
            bool(subscription_seats.get(sid))
            and u["sampled_seats"] == subscription_seats[sid]
        )
        longitudinal_coverage = full_coverage and all(
            u["coverage"].get(seat, {}).get("distinct_days", 0)
                >= DOWNGRADE_MIN_DISTINCT_DAYS
            and u["coverage"].get(seat, {}).get("span_days", 0)
                >= DOWNGRADE_MIN_SPAN_DAYS
            for seat in subscription_seats[sid]
        )
        if u["max"] < 20 and cost >= 100 and longitudinal_coverage:
            recs.append(f"DOWNGRADE candidate: {sid} ({s.get('product')}, ${cost}/mo) peaked at {u['max']:.0f}% — under-used; a smaller plan may suffice.")
        elif u["max"] < 20 and cost >= 100:
            weakest_days = min(
                (u["coverage"].get(seat, {}).get("distinct_days", 0)
                 for seat in subscription_seats.get(sid, set())),
                default=0,
            )
            weakest_span = min(
                (u["coverage"].get(seat, {}).get("span_days", 0)
                 for seat in subscription_seats.get(sid, set())),
                default=0,
            )
            recs.append(
                f"INSUFFICIENT downgrade evidence for {sid}: lowest-covered seat has "
                f"{weakest_days} distinct observed day(s) spanning {weakest_span:.0f} day(s); "
                f"need every configured seat on at least {DOWNGRADE_MIN_DISTINCT_DAYS} "
                f"distinct days spanning {DOWNGRADE_MIN_SPAN_DAYS} days. No downgrade "
                "recommendation was made."
            )
        elif u["max"] >= 95:
            recs.append(
                f"REVIEW capacity near {sid} ({s.get('product')}): observed utilization "
                f"peaked at {u['max']:.0f}% in the last {HISTORY_ANALYSIS_DAYS} days. "
                "This is near-cap evidence, not a recorded exhaustion event; verify reset "
                "headroom before adding capacity."
            )
    metered_used = [x for x in util if x["billing"] == "metered" and x["max_pct"] > 0]
    if metered_used:
        recs.append(
            f"Metered use observed ({', '.join(x['seat'] for x in metered_used)}). "
            "This history does not prove that a capability-equivalent included plan exists; "
            "compare an explicitly validated equivalent before changing spend."
        )
    if not history:
        recs.append(
            f"No usable timestamped usage history exists in the last "
            f"{HISTORY_ANALYSIS_DAYS} days — schedule bin/usage-record.py --snapshot "
            "(e.g. hourly) so this can compare paid vs used."
        )
    return {
        "analysis_window_days": HISTORY_ANALYSIS_DAYS,
        "retained_records": len(retained_history),
        "analyzed_records": len(history),
        "utilization": sorted(util, key=lambda x: -x["avg_pct"]),
        "recommendations": recs,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Recommend a subscription stack from last month's habits.")
    ap.add_argument(
        "--from-history", action="store_true",
        help="30-day timestamped utilization advice from data/usage-history.jsonl",
    )
    ap.add_argument("--implement-hours-per-day", type=float, default=0)
    ap.add_argument("--reviews-per-week", type=int, default=0)
    ap.add_argument("--mcp-bulk-per-week", type=int, default=0)
    ap.add_argument("--cross-family", action="store_true")
    ap.add_argument(
        "--no-codex",
        action="store_true",
        help="exclude Codex; cross-family and Terra/MCP work stay unserved in the reference setup",
    )
    ap.add_argument(
        "--third-party-safe-review",
        action="store_true",
        help="record sanitized eligibility for a future Review E route; does not activate or price it",
    )
    ap.add_argument("--storefront-pixels", action="store_true")
    ap.add_argument("--analytics", action="store_true")
    ap.add_argument("--ide-hours-per-day", type=float, default=0)
    ap.add_argument("--team-size", type=int, default=1)
    ap.add_argument("--from-json", help="load habits from a JSON file (keys = long flag names with underscores)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    explicit_habit_flags = (
        args.implement_hours_per_day != 0
        or args.reviews_per_week != 0
        or args.mcp_bulk_per_week != 0
        or args.cross_family
        or args.no_codex
        or args.third_party_safe_review
        or args.storefront_pixels
        or args.analytics
        or args.ide_hours_per_day != 0
        or args.team_size != 1
    )
    if args.from_json and explicit_habit_flags:
        print(
            "ERROR: --from-json cannot be mixed with habit/safety flags; put the complete "
            "typed input in one JSON object",
            file=sys.stderr,
        )
        return 2
    if args.from_history and (args.from_json or explicit_habit_flags):
        print(
            "ERROR: --from-history cannot be mixed with habit or --from-json inputs",
            file=sys.stderr,
        )
        return 2

    if args.from_history:
        result = from_history()
        if args.json:
            print(json.dumps(result, indent=2))
            return 0
        print("subscription-calculator — last-30-day utilization (paid vs used)")
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

    try:
        h = parse_habits(args)
        stack, reasons, monthly = recommend(h)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: invalid habit input: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({"habits": h, "recommended_stack": stack,
                          "monthly_usd_indicative": monthly, "reasons": reasons}, indent=2))
        return 0

    print("subscription-calculator — recommendation from last month's habits")
    print("=" * 72)
    print("habits:", ", ".join(f"{k}={v}" for k, v in h.items()))
    print("-" * 72)
    if not stack:
        print("No paid stack is indicated by the supplied habits.")
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
