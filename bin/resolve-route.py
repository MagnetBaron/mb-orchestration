#!/usr/bin/env python3
"""resolve-route — the deterministic router for mb-orchestration.

Turns a task class + live seat state into an exact routing decision:
  * the review DEPTH (from config/review-depth.json + risk flags), and
  * the concrete REVIEW CHAIN (which live seats, in order, satisfy that depth), and
  * the IMPLEMENT seat, and
  * the FALLBACK order / park reason when seats are spent.

It reads ONLY config + recorded usage signals (config/usage-ledger.json via
usage-status). It never guesses quota from token counts and never treats an
outage as exhaustion. Same inputs + same recorded state => same decision: this
is where the system's non-determinism is squeezed out of prose and into code.

Every routing rule it applies is stated in AGENTS.md / DOCTRINE.md; this script
is the executable form, not a new policy.

Examples:
  resolve-route.py --class money-data --scale elevated
  resolve-route.py --class repo-code --risk auth,secrets --implement
  resolve-route.py --class storefront-theme --pixels --json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE.parent / "config"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_json(path):
    if not path.exists():
        sys.exit(f"resolve-route: missing config {path}")
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        sys.exit(f"resolve-route: cannot parse {path}: {exc}")


usage_status = _load_module("usage_status", HERE / "usage-status.py")

LEVEL_RANK = {"none": 0, "self-check": 1, "single-frontier": 2, "cross-family": 3}


def max_level(a, b):
    return a if LEVEL_RANK[a] >= LEVEL_RANK[b] else b


def compute_depth(depth_conf, klass, scale, risk_flags):
    classes = depth_conf["classes"]
    if klass not in classes:
        sys.exit(f"resolve-route: unknown class {klass!r}; known: {', '.join(sorted(classes))}")
    spec = classes[klass]
    level = spec.get(scale)
    if level is None:
        sys.exit(f"resolve-route: class {klass!r} has no scale {scale!r}")
    reasons = [f"class {klass} @ {scale} floor = {level}"]
    if risk_flags:
        level = max_level(level, spec["risk"])
        reasons.append(f"risk flag(s) {','.join(risk_flags)} → raise to class risk column ({spec['risk']})")
        if set(risk_flags) & set(depth_conf["cross_family_risk_flags"]):
            hit = sorted(set(risk_flags) & set(depth_conf["cross_family_risk_flags"]))
            level = max_level(level, "cross-family")
            reasons.append(f"cross-family risk flag(s) {','.join(hit)} → force cross-family")
    extra = {k: spec[k] for k in ("review_d", "owner", "human") if spec.get(k)}
    return level, reasons, extra


def live_reviewers(providers, rows, ledger):
    """Return concrete, live frontier/sole reviewers in review_order, each as
    {provider, family, seat, note}. Fable availability is a subscription grant
    re-checked against downgrade markers; Opus/Sol from live seat state."""
    by_name = {r["seat"]: r for r in rows}
    prov = providers["providers"]

    fable_seats = [r for r in rows if r.get("fable") and r["available"]]
    downgraded = {k.split(":", 1)[1] for k in (ledger or {}) if str(k).startswith("fable-downgrade:")}
    fable_seats = [r for r in fable_seats if r["seat"] not in downgraded]
    opus_seats = [r for r in rows if r.get("family") == "anthropic" and r["available"]]
    # Prefer a non-Fable (Pro) seat for Opus-only work so Fable seats are preserved.
    opus_pref = sorted(opus_seats, key=lambda r: (bool(r.get("fable")),))

    out = []
    for pid in providers["review_order"]:
        p = prov.get(pid, {})
        if not p.get("review_eligible"):
            continue
        fam = p.get("family")
        if pid == "fable-5":
            if fable_seats:
                out.append({"provider": pid, "family": fam, "seat": fable_seats[0]["seat"], "note": "Fable-capable seat live"})
        elif pid == "opus-4.8":
            if opus_pref:
                out.append({"provider": pid, "family": fam, "seat": opus_pref[0]["seat"], "note": "Claude seat live (Pro preferred to spare Fable seats)"})
        elif pid == "codex-sol":
            r = by_name.get("codex-sol")
            if r and r["available"]:
                out.append({"provider": pid, "family": fam, "seat": "codex-sol", "note": "Sol under soft cap"})
        elif pid == "review-e":
            if p.get("wired"):
                r = by_name.get("review-e")
                if not r or r["available"]:
                    out.append({"provider": pid, "family": fam, "seat": "review-e", "note": "independent-family fallback (wired)"})
        else:
            r = by_name.get(pid)
            if r and r["available"]:
                out.append({"provider": pid, "family": fam, "seat": pid, "note": "live"})
    return out


def pick_review(level, reviewers, review_e_wired):
    """Given a depth level and the live reviewer list, return the decision."""
    if level in ("none", "self-check"):
        return {
            "satisfied": True,
            "chain": [],
            "explanation": f"{level}: no second-model review (implementer's own tests bound to done_when). "
                           "Landing lock, tip-bound green test, Review D pixels, and owner gates still apply.",
        }
    if not reviewers:
        return {"satisfied": False, "chain": [],
                "explanation": "PARK: no live native reviewer. Park to earliest reset "
                               "(usage-status --earliest-reset); a rested native seat beats an unwired fallback."}
    if level == "single-frontier":
        first = reviewers[0]
        return {"satisfied": True, "chain": [first],
                "explanation": f"single-frontier: first live seat = {first['provider']} on {first['seat']} [{first['family']}]. "
                               f"Fallback order if it 429s mid-flight: {', '.join(r['provider'] for r in reviewers[1:]) or '(none — then park)'}"}
    # cross-family: one pass each from two DIFFERENT families
    first = reviewers[0]
    second = next((r for r in reviewers[1:] if r["family"] != first["family"]), None)
    if second:
        return {"satisfied": True, "chain": [first, second],
                "explanation": f"cross-family: {first['provider']} [{first['family']}] + {second['provider']} [{second['family']}] "
                               "— one pass each, sequential, one machine reviewer at a time. blocked wins on disagreement."}
    # only one family available
    families = {r["family"] for r in reviewers}
    msg = (f"cross-family UNSATISFIED: only family {sorted(families)} is live. ")
    if review_e_wired and "open-weight" not in families:
        msg += "Review E is wired and open-weight → it may fill the second family slot IF the remaining native family is QUOTA-spent (not merely down). Confirm with usage-status before engaging."
    else:
        msg += "One native family quota-spent and no independent second family available → PARK the gate to earliest reset. Owner may land a risk item explicitly."
    return {"satisfied": False, "chain": [first], "explanation": "PARK: " + msg}


def pick_implement(providers, rows, klass, needs_mcp, pixels):
    by_name = {r["seat"]: r for r in rows}
    prov = providers["providers"]

    def avail(pid):
        # CLI seats map to a usage seat by backed_by/meter; approximate by family/meter presence.
        # grok-build -> grok-heavy, codex-terra -> codex-plan.
        seat = {"grok-build": "grok-heavy", "codex-terra": "codex-plan"}.get(pid)
        r = by_name.get(seat) if seat else None
        return (r is None) or r["available"]

    steps = []
    if needs_mcp:
        steps.append({"seat": "codex-terra", "why": f"Google-MCP bulk ({needs_mcp}) → output_path snapshot",
                      "available": avail("codex-terra")})
        steps.append({"seat": "grok-build", "why": "implement against the frozen snapshot (must_read)",
                      "available": avail("grok-build")})
    else:
        steps.append({"seat": "grok-build", "why": "default implementer (1 worktree/branch/named scope)",
                      "available": avail("grok-build")})
    if pixels or klass == "storefront-theme":
        steps.append({"seat": "grok-bot-review-d", "why": "Review D pixel walk once a visitor preview URL exists (Slack #visual-qa)",
                      "available": True, "input_seat": True})
    return steps


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deterministic router: task class + live state → seat + review chain.")
    ap.add_argument("--class", dest="klass", required=True, help="task class id (see config/review-depth.json)")
    ap.add_argument("--scale", default="routine", choices=["routine", "elevated"],
                    help="routine=single reversible item; elevated=bulk>=50 / new logic / site-wide")
    ap.add_argument("--risk", default="", help="comma list of risk-gate flags that fired (auth,money,PII,prod,irreversible,multi-service,grok-conflict,flaky-tests,secrets,untrusted-shell)")
    ap.add_argument("--implement", action="store_true", help="also emit the implement-seat plan")
    ap.add_argument("--needs-mcp", default="", help="google connector this brief needs (gsc/drive/dataforseo) → routes bulk to Terra first")
    ap.add_argument("--pixels", action="store_true", help="storefront pixels change → add Review D")
    ap.add_argument("--user-said-ship", action="store_true", help="owner said ship = land, not spend a frontier (does not lower the floor's gates)")
    ap.add_argument("--ledger", default=None, help="alternate usage-ledger.json")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    depth_conf = load_json(CONFIG / "review-depth.json")
    providers = load_json(CONFIG / "providers.json")
    risk_flags = [f.strip() for f in args.risk.split(",") if f.strip()]

    updated, rows = usage_status.compute(args.ledger)
    ledger = usage_status.load(Path(args.ledger) if args.ledger else usage_status.DEFAULT_LEDGER, required=False)

    level, reasons, extra = compute_depth(depth_conf, args.klass, args.scale, risk_flags)
    reviewers = live_reviewers(providers, rows, ledger)
    review_e_wired = bool(providers["providers"].get("review-e", {}).get("wired"))
    review = pick_review(level, reviewers, review_e_wired)

    implement = pick_implement(providers, rows, args.klass, args.needs_mcp.strip(), args.pixels) if args.implement else None

    decision = {
        "class": args.klass,
        "scale": args.scale,
        "risk_flags": risk_flags,
        "review_depth": level,
        "depth_reasons": reasons,
        "review": review,
        "live_reviewers": reviewers,
        "gates": {
            "review_d_pixels": bool(extra.get("review_d") or args.pixels or args.klass == "storefront-theme"),
            "owner_gate": bool(extra.get("owner")),
            "human_gate": bool(extra.get("human")),
            "landing_lock": True,
            "tip_bound_green_test": True,
        },
        "user_said_ship": args.user_said_ship,
        "implement": implement,
        "usage_updated": updated,
    }

    if args.json:
        print(json.dumps(decision, indent=2))
        return 0

    print(f"ROUTE  class={args.klass} scale={args.scale} risk={risk_flags or '-'}")
    print("-" * 72)
    print(f"review depth: {level}")
    for r in reasons:
        print(f"  · {r}")
    print(f"review: {'SATISFIED' if review['satisfied'] else 'NOT SATISFIED'}")
    print(f"  {review['explanation']}")
    if review["chain"]:
        for i, c in enumerate(review["chain"], 1):
            print(f"  pass {i}: {c['provider']} on seat {c['seat']} [{c['family']}] — {c['note']}")
    g = decision["gates"]
    active = [k for k, v in g.items() if v]
    print(f"gates: {', '.join(active)}")
    if args.user_said_ship:
        print("  note: user said ship = LAND, not spend a frontier — the floor's landing lock / green test / pixel / owner gates still apply.")
    if implement:
        print("implement:")
        for s in implement:
            tag = " (input seat)" if s.get("input_seat") else ""
            av = "" if s.get("available", True) else "  [SEAT SPENT/DOWN — see EDGE-CASES]"
            print(f"  → {s['seat']}{tag}: {s['why']}{av}")
    print("-" * 72)
    print("deterministic: same class + same recorded seat state → same decision. Rules live in AGENTS.md/DOCTRINE.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
