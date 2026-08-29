#!/usr/bin/env python3
"""resolve-route — the deterministic router for mb-orchestration.

Turns a task class + live seat state into an exact routing decision: the review
DEPTH, the concrete REVIEW CHAIN, the IMPLEMENT seat, and the fallback — reading
ONLY config + recorded usage signals. Same inputs + same recorded state => same
decision.

It enforces the owner's economics (bin/routing.py):
  * never strand — a reserve/intake seat is usable as a last resort; the system
    never parks for a SELF-IMPOSED cap while real quota exists. It parks only for a
    genuine exhaustion (429) or an unsatisfiable SAFETY gate (cross-family needs two
    live families).
  * minimize API $ — included seats before metered.
  * use-before-lost — drain soon-to-reset weekly/monthly quota first.
  * dispatch codes last — if every worker seat is spent, the intake/dispatch seat
    implements (a 2-subscription setup routes coding to dispatch by design).
  * capability-aware — an implement seat must actually have the needed capability
    (browser/connector/etc., derived from providers.json + connectors.json).
  * no mid-turn swaps — --task-seconds flags a seat that would reset mid-task.

Examples:
  resolve-route.py --class money-data --scale elevated
  resolve-route.py --class repo-code --risk auth,secrets --implement --task-seconds 1800
  resolve-route.py --class storefront-theme --pixels --needs-connector clarity-magnetbaron
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mborch  # noqa: E402
import routing  # noqa: E402


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


usage_status = _load_module("usage_status", HERE / "usage-status.py")
modelreg = _load_module("model_registry", HERE / "model-registry.py")

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
        reasons.append(f"risk {','.join(risk_flags)} → class risk column ({spec['risk']})")
        if set(risk_flags) & set(depth_conf["cross_family_risk_flags"]):
            hit = sorted(set(risk_flags) & set(depth_conf["cross_family_risk_flags"]))
            level = max_level(level, "cross-family")
            reasons.append(f"cross-family risk flag(s) {','.join(hit)} → force cross-family")
    extra = {k: spec[k] for k in ("review_d", "owner", "human") if spec.get(k)}
    return level, reasons, extra


def provider_seats(pid, providers, rows):
    """Live usage rows backing a provider, best (route_key) first."""
    prov = providers["providers"].get(pid, {})
    sub = prov.get("backed_by")
    special = {"fireworks-api": ["review-e"]}
    if sub in special:
        want = special[sub]
        seats = [r for r in rows if r["seat"] in want]
    elif sub in ("claude-any-seat",):
        seats = [r for r in rows if r.get("family") == "anthropic"]
    elif sub in ("claude-fable-capable-seats",):
        seats = [r for r in rows if r.get("fable")]
    else:
        seats = [r for r in rows if r.get("subscription") == sub]
    return sorted(seats, key=routing.route_key)


def live_reviewers(providers, rows, ledger, registry):
    """Reviewers whose bound catalog route is live. Registry is required; unknown state fails closed."""
    if not registry:
        return []
    by_name = {r["seat"]: r for r in rows}
    prov = providers["providers"]
    order_index = {pid: i for i, pid in enumerate(providers["review_order"])}
    live_ids = set(modelreg.live_review_providers(registry, providers))

    downgraded = {k.split(":", 1)[1] for k in (ledger or {}) if str(k).startswith("fable-downgrade:")}
    fable_seats = [r for r in rows if r.get("fable") and routing.usable(r) and r["seat"] not in downgraded]
    anthropic_seats = [r for r in rows if r.get("family") == "anthropic" and routing.usable(r)]

    out = []
    for pid in providers["review_order"]:
        p = prov.get(pid, {})
        if not p.get("review_eligible"):
            continue
        if pid not in live_ids:
            continue
        fam = p.get("family")
        group = modelreg.independence_group_of(registry, fam)
        route = (registry.get("routes") or {}).get(p.get("route") or "") or {}
        phys = modelreg.physical_invocation(route)
        seat = None
        if pid == "fable-5":
            cand = sorted(fable_seats, key=routing.route_key)
            seat = cand[0] if cand else None
        elif fam == "anthropic":
            # prefer a non-Fable (Pro) seat to spare Fable seats; then by route_key
            cand = sorted(anthropic_seats, key=lambda r: (bool(r.get("fable")), *routing.route_key(r)))
            seat = cand[0] if cand else None
        else:
            r = by_name.get(pid)
            if r and routing.usable(r):
                seat = r
            elif r is None and p.get("kind") == "api":
                # Live API route with no usage-window seat: treat as available. Still requires
                # a live_verified catalog route (live_ids filter above); wired=true is not enough.
                seat = {"seat": pid, "tier": "available", "billing": p.get("billing"),
                        "family": fam, "intake": False, "window_kinds": ["none"]}
        if seat is not None:
            out.append({"provider": pid, "family": fam, "independence_group": group,
                        "physical": phys, "seat": seat["seat"], "tier": seat["tier"],
                        "billing": seat.get("billing"), "row": seat, "order": order_index.get(pid, 99)})
    # preferred first: included/available/non-intake by route_key, then prowess order
    out.sort(key=lambda e: (routing.route_key(e["row"]), e["order"]))
    return out


def note_for(entry):
    t = entry["tier"]
    tag = "" if t == "available" else " (reserve released — never strand)"
    return f"{entry['provider']} on {entry['seat']} [{entry['family']}]{tag}"


def pick_review(level, reviewers, review_e_wired, task_seconds):
    if level in ("none", "self-check"):
        return {"satisfied": True, "chain": [],
                "explanation": f"{level}: no second-model review. Landing lock, tip-bound green test, "
                               "Review D pixels, and owner gates still apply."}
    if not reviewers:
        return {"satisfied": False, "chain": [],
                "explanation": "PARK: no USABLE native reviewer (all spent). Park to earliest reset "
                               "(usage-status --earliest-reset)."}
    swap = [r for r in reviewers if routing.resets_before(r["row"], task_seconds)]
    warn = f" ⚠ resets mid-task: {', '.join(r['seat'] for r in swap)} — bring in at the next boundary" if swap else ""
    if level == "single-frontier":
        first = reviewers[0]
        rest = ", ".join(r["provider"] for r in reviewers[1:]) or "(none — then park)"
        return {"satisfied": True, "chain": [first],
                "explanation": f"single-frontier: {note_for(first)}. Fallback: {rest}.{warn}"}
    # cross-family: two DIFFERENT independence groups AND unique physical invocations
    first = reviewers[0]
    first_group = first.get("independence_group") or first["family"]
    first_phys = tuple(first.get("physical") or ())
    second = next(
        (r for r in reviewers[1:]
         if (r.get("independence_group") or r["family"]) != first_group
         and tuple(r.get("physical") or ()) != first_phys),
        None,
    )
    if second:
        return {"satisfied": True, "chain": [first, second],
                "explanation": f"cross-family: {note_for(first)} + {note_for(second)} — one pass each, "
                               f"sequential. blocked wins on disagreement.{warn}"}
    families = sorted({r["family"] for r in reviewers})
    msg = f"cross-family UNSATISFIED: only family {families} has a USABLE seat. "
    if review_e_wired and "open-weight" not in families:
        msg += "Review E is wired (open-weight) → it may fill the second family IF the missing native family is QUOTA-spent. "
    else:
        msg += "No independent second family available → PARK the gate (genuine exhaustion, not a self-imposed cap). Owner may land a risk item explicitly."
    return {"satisfied": False, "chain": [first], "explanation": "PARK: " + msg}


def pick_implement(providers, connectors, rows, klass, needs_connector, needs_mcp, pixels,
                   task_seconds, registry):
    prov = providers["providers"]
    steps = []
    if not registry:
        steps.append({"seat": "(none)", "why": "model-registry required for runtime routing — fail closed",
                      "available": False, "tier": "spent"})
        return steps

    def live_ok(pid):
        return modelreg.provider_route_is_live(registry, prov.get(pid) or {})

    def cap_ok(pid):
        if not needs_connector:
            return True
        return needs_connector in routing.capabilities_of(pid, prov.get(pid, {}), connectors)

    # candidate implement providers: live catalog route + implement/ide + needed capability
    impl_ids = [pid for pid, p in prov.items()
                if ("implement" in p.get("functions", []) or "ide" in p.get("functions", []))
                and p.get("enabled", True) and live_ok(pid) and cap_ok(pid)]

    def best_seat(pid):
        seats = [s for s in provider_seats(pid, providers, rows) if routing.usable(s)]
        return seats[0] if seats else None

    # worker candidates (non-intake) usable, ordered by route_key of their seat
    workers = []
    for pid in impl_ids:
        s = best_seat(pid)
        if s and not s.get("intake"):
            workers.append((pid, s))
    workers.sort(key=lambda ps: routing.route_key(ps[1]))

    if needs_mcp:
        # MCP bulk to Terra first (capability), then implement against the snapshot
        terra = best_seat("codex-terra") if live_ok("codex-terra") else None
        steps.append({"seat": "codex-terra", "why": f"Google-MCP bulk ({needs_mcp}) → output_path snapshot",
                      "available": bool(terra), "tier": terra["tier"] if terra else "spent"})

    if workers:
        pid, s = workers[0]
        steps.append({"seat": pid, "on": s["seat"], "why": "implement (drain-ordered: included→metered, available→reserve, use-before-lost)",
                      "available": True, "tier": s["tier"], "billing": s.get("billing"),
                      "resets_mid_task": routing.resets_before(s, task_seconds)})
    else:
        # never strand: no usable worker → the intake/dispatch seat codes (2-sub setups land here)
        # last-resort still requires some provider on that subscription to have a live catalog route
        def sub_has_live(sub):
            return any(
                p.get("backed_by") == sub and modelreg.provider_route_is_live(registry, p)
                for p in prov.values() if isinstance(p, dict)
            )
        last_dollar = [pid for pid, p in prov.items()
                       if "last_dollar" in (p.get("functions") or [])
                       and p.get("enabled", True) and live_ok(pid)]
        intake = sorted(
            [r for r in rows if r.get("intake") and routing.usable(r) and sub_has_live(r.get("subscription"))],
            key=routing.route_key,
        )
        if intake:
            steps.append({"seat": "dispatch/intake", "on": intake[0]["seat"],
                          "why": "ALL worker seats spent → intake/dispatch codes as last resort (never strand; releases reserve)",
                          "available": True, "tier": intake[0]["tier"], "last_resort": True})
        elif last_dollar:
            pid = last_dollar[0]
            s = best_seat(pid)
            if s:
                steps.append({"seat": pid, "on": s["seat"],
                              "why": "last-resort metered provider (live catalog route required)",
                              "available": True, "tier": s["tier"], "last_resort": True, "billing": s.get("billing")})
            else:
                steps.append({"seat": "(none)", "why": "no usable implement seat anywhere — genuine full exhaustion → PARK",
                              "available": False, "tier": "spent"})
        else:
            steps.append({"seat": "(none)", "why": "no usable implement seat anywhere — genuine full exhaustion → PARK",
                          "available": False, "tier": "spent"})

    if pixels or klass == "storefront-theme":
        steps.append({"seat": "grok-bot-review-d", "why": "Review D pixel walk once a visitor preview URL exists (Slack #visual-qa)",
                      "available": True, "input_seat": True})
    return steps


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deterministic router.")
    ap.add_argument("--class", dest="klass", required=True)
    ap.add_argument("--scale", default="routine", choices=["routine", "elevated"])
    ap.add_argument("--risk", default="")
    ap.add_argument("--implement", action="store_true")
    ap.add_argument("--needs-mcp", default="", help="google connector this brief needs (routes bulk to Terra)")
    ap.add_argument("--needs-connector", default="", help="capability/connector the implement seat must have (e.g. clarity-magnetbaron, browser)")
    ap.add_argument("--pixels", action="store_true")
    ap.add_argument("--task-seconds", type=int, default=0, help="est. task length; flags seats that reset before it finishes (no mid-turn swaps)")
    ap.add_argument("--user-said-ship", action="store_true")
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    depth_conf = mborch.load_config("review-depth.json")
    providers = mborch.load_config("providers.json")
    connectors = mborch.load_config("connectors.json", required=False) or {}
    registry = mborch.load_config("model-registry.json")
    if not registry:
        sys.exit("resolve-route: model-registry.json is required (unknown registry state fails closed)")
    reg_errors = modelreg.validate(registry, providers=providers)
    if reg_errors:
        sys.exit("resolve-route: model-registry invalid (fail closed):\n  - " + "\n  - ".join(reg_errors))
    risk_flags = [f.strip() for f in args.risk.split(",") if f.strip()]

    updated, rows = usage_status.compute(args.ledger)
    lp = Path(args.ledger) if args.ledger else mborch.ledger_path()
    ledger = json.loads(lp.read_text()) if lp.exists() else {}

    level, reasons, extra = compute_depth(depth_conf, args.klass, args.scale, risk_flags)
    reviewers = live_reviewers(providers, rows, ledger, registry)
    review_e = providers["providers"].get("review-e") or {}
    review_e_wired = modelreg.provider_route_is_live(registry, review_e)
    review = pick_review(level, reviewers, review_e_wired, args.task_seconds)
    implement = pick_implement(providers, connectors, rows, args.klass, args.needs_connector.strip(),
                               args.needs_mcp.strip(), args.pixels, args.task_seconds,
                               registry) if args.implement else None

    decision = {
        "class": args.klass, "scale": args.scale, "risk_flags": risk_flags,
        "review_depth": level, "depth_reasons": reasons, "review": review,
        "live_reviewers": [{k: e[k] for k in ("provider", "family", "seat", "tier", "billing")} for e in reviewers],
        "gates": {
            "review_d_pixels": bool(extra.get("review_d") or args.pixels or args.klass == "storefront-theme"),
            "owner_gate": bool(extra.get("owner")), "human_gate": bool(extra.get("human")),
            "landing_lock": True, "tip_bound_green_test": True,
        },
        "user_said_ship": args.user_said_ship, "implement": implement, "usage_updated": updated,
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
    for i, c in enumerate(review["chain"], 1):
        print(f"  pass {i}: {note_for(c)}")
    g = decision["gates"]
    print(f"gates: {', '.join(k for k, v in g.items() if v)}")
    if args.user_said_ship:
        print("  note: user said ship = LAND; the floor's landing lock / green test / pixel / owner gates still apply.")
    if implement:
        print("implement:")
        for s in implement:
            tag = " (input seat)" if s.get("input_seat") else ""
            lr = " [LAST RESORT]" if s.get("last_resort") else ""
            sw = " ⚠resets-mid-task" if s.get("resets_mid_task") else ""
            on = f" on {s['on']}" if s.get("on") else ""
            av = "" if s.get("available", True) else "  [SPENT/DOWN]"
            print(f"  → {s['seat']}{on}{tag}{lr}{sw}: {s['why']}{av}")
    print("-" * 72)
    print("deterministic: same class + recorded state → same decision. Reserves yield (never strand); metered $ last.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
