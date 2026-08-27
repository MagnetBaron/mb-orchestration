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


def main(argv=None):
    ap = argparse.ArgumentParser(description="Recommend a subscription stack from last month's habits.")
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
