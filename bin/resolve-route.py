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
  * dispatch codes last — if every worker seat is spent, a concrete live provider on
    the intake subscription implements, and only if that provider is operationally
    allowed to implement (`implement` or `ide`) and has `code` on both the provider
    and its bound live route. Sharing a plan with Luna/Terra/Sol is not enough.
    No such provider → PARK.
  * capability-aware — an implement seat must actually have the needed capability
    (browser/connector/etc., derived from providers.json + connectors.json).
  * MCP volume — --needs-mcp requires an active connector on the MCP volume seat
    AND mcp_bulk on that provider's functions, capabilities, and bound live route.
    Any missing layer PARKS immediately and does not continue to implement.
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
import re
import sys
import time
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mborch  # noqa: E402
import routing  # noqa: E402
import dispatch_evidence  # noqa: E402
try:
    import observe  # noqa: E402
except Exception as _OBS_IMPORT_ERROR:  # observability must not take routing down
    observe = None
else:
    _OBS_IMPORT_ERROR = None


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
    usage_seat = prov.get("usage_seat")
    if usage_seat:
        return sorted([r for r in rows if r.get("seat") == usage_seat], key=routing.route_key)
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


STANDING_REVIEW_AUTHORIZATION_CONSTANTS = {
    "provider_scope": "all-configured-review-providers",
    "artifact_scope": "ordinary_artifacts",
    "per_review_approval_required": False,
    "intake_family_may_review": True,
    "intake_family_review_scope": "artifact-only",
    "intake_family_must_not_be_sole_reviewer": True,
    "separate_physical_invocation_required": True,
}
STANDING_REVIEW_AUTHORIZATION_KEYS = frozenset(
    {*STANDING_REVIEW_AUTHORIZATION_CONSTANTS, "effective_date"}
)
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_standing_effective_date(raw, *, today=None):
    """Return a date for a valid ISO YYYY-MM-DD not in the future, else None."""
    if not isinstance(raw, str) or not _ISO_DATE_RE.fullmatch(raw):
        return None
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        return None
    if parsed > (today or date.today()):
        return None
    return parsed


def standing_review_authorization(policy, *, today=None):
    """Return the standing authorization object, or None if missing/weakened/malformed.

    Semantic fields must match the known constants exactly. effective_date must be a
    valid ISO YYYY-MM-DD that is not in the future. Extra or missing keys fail closed.
    """
    auth = policy.get("standing_review_authorization")
    if not isinstance(auth, dict):
        return None
    if set(auth) != STANDING_REVIEW_AUTHORIZATION_KEYS:
        return None
    if any(auth.get(key) != value for key, value in STANDING_REVIEW_AUTHORIZATION_CONSTANTS.items()):
        return None
    if parse_standing_effective_date(auth.get("effective_date"), today=today) is None:
        return None
    return {**STANDING_REVIEW_AUTHORIZATION_CONSTANTS, "effective_date": auth["effective_date"]}


def evaluate_handoff(policy, artifacts):
    """Classify the run's artifacts before any provider is selected.

    Ordinary configured-provider handoffs are preauthorized only when the exact
    standing review authorization object is present and currently effective.
    Missing, weakened, malformed, future-dated, or extra-field authorization
    parks ordinary artifacts without a permission request.
    Restricted or unknown classes park for their own reasons, also without a
    permission request.
    """
    ordinary = set(policy.get("ordinary_artifacts") or [])
    restricted = set(policy.get("restricted_artifacts") or [])
    requested = list(dict.fromkeys(a for a in artifacts if a))
    bad = [a for a in requested if a in restricted]
    unknown = [a for a in requested if a not in ordinary and a not in restricted]
    auth = standing_review_authorization(policy)
    if bad:
        allowed = False
        reason = f"PARK: restricted artifact(s) cannot transfer automatically: {', '.join(bad)}"
        basis = "fail-closed-restricted"
    elif unknown:
        allowed = False
        reason = f"PARK: unknown artifact class(es) fail closed: {', '.join(unknown)}"
        basis = "fail-closed-unknown"
    elif auth is None:
        allowed = False
        reason = (
            "PARK: standing_review_authorization missing or weakened; "
            "ordinary handoff is not preauthorized"
        )
        basis = "fail-closed-standing-review-authorization"
    else:
        allowed = True
        reason = (
            "ordinary configured-provider handoff is preauthorized by "
            "standing_review_authorization"
        )
        basis = "standing_review_authorization"
    return {
        "allowed": allowed,
        "artifacts": requested,
        "restricted": bad,
        "unknown": unknown,
        "requires_user_permission": False,
        "authorship_changes_authority": False,
        "action": "transfer-minimum-necessary" if allowed else "park",
        "reason": reason,
        "authorization_basis": basis,
        "standing_review_authorization": auth,
    }


def provider_dispatch_configured(provider_id, provider, registry):
    """Static dispatch claim: evidence + provider and bound-route capabilities agree."""
    if not isinstance(provider, dict) or provider.get("enabled", True) is False:
        return False
    if provider.get("dispatch_eligible") is not True:
        return False
    evidence = provider.get("dispatch_evidence") or {}
    trials = evidence.get("trials")
    if (evidence.get("status") != "passed" or not isinstance(trials, int) or trials < 1
            or evidence.get("completed") != trials or evidence.get("reversals") != 0):
        return False
    receipt_ok, _ = dispatch_evidence.validate(provider_id, provider)
    if not receipt_ok:
        return False
    if "dispatch" not in (provider.get("functions") or []):
        return False
    if "dispatch" not in (provider.get("capabilities") or []):
        return False
    route = (registry.get("routes") or {}).get(provider.get("route") or "") or {}
    return "dispatch" in (route.get("capabilities") or [])


def provider_can_dispatch(provider_id, provider, registry):
    """Configured dispatch claim whose bound catalog route is currently live."""
    return (provider_dispatch_configured(provider_id, provider, registry)
            and modelreg.provider_route_is_live(registry, provider))


def dispatch_statuses(providers, rows, registry, entrypoints, ledger=None):
    """Return capability/availability status for every configured provider."""
    provs = providers.get("providers") or {}
    fallback = (entrypoints.get("dispatcher") or {}).get("fallback_order") or []
    order = {pid: i for i, pid in enumerate(fallback)}
    downgraded = {k.split(":", 1)[1] for k in (ledger or {}) if str(k).startswith("fable-downgrade:")}
    statuses = {}
    for pid, p in provs.items():
        configured = provider_dispatch_configured(pid, p, registry)
        qualified = provider_can_dispatch(pid, p, registry)
        seats = [s for s in provider_seats(pid, providers, rows) if routing.usable(s)] if qualified else []
        if pid == "fable-5":
            seats = [s for s in seats if s.get("seat") not in downgraded]
        if qualified and not seats and p.get("kind") == "api":
            seats = [{"seat": pid, "tier": "available", "billing": p.get("billing"),
                      "family": p.get("family"), "intake": False, "window_kinds": ["none"]}]
        seat = seats[0] if seats else None
        statuses[pid] = {
            "provider": pid,
            "configured": configured,
            "qualified": qualified,
            "usable": seat is not None,
            "seat": seat,
            "family": p.get("family"),
            "prowess": (p.get("prowess") or {}).get("dispatch", 0),
            "fallback_order": order.get(pid, 999),
        }
    return statuses


def select_dispatcher(entrypoints, providers, rows, registry, requested=None, profile="default", ledger=None):
    """Select exactly one dispatcher per run; explicit valid intake choice wins."""
    profiles = entrypoints.get("profiles") or {}
    if requested is None and profile not in profiles:
        return {"satisfied": False, "requested": requested, "effective": None,
                "profile": profile, "fallback_used": False,
                "explanation": f"PARK: unknown dispatcher profile {profile!r}"}
    disp = entrypoints.get("dispatcher") or {}
    preferred = requested or (profiles.get(profile) or {}).get("preferred_dispatcher") or disp.get("default_provider")
    statuses = dispatch_statuses(providers, rows, registry, entrypoints, ledger=ledger)
    status = statuses.get(preferred)
    if status is None:
        return {"satisfied": False, "requested": preferred, "effective": None,
                "profile": profile, "fallback_used": False,
                "explanation": f"PARK: requested dispatcher {preferred!r} is not configured"}
    if not status["configured"]:
        p = (providers.get("providers") or {}).get(preferred) or {}
        relay_ids = {
            pid
            for surface in (entrypoints.get("entry_surfaces") or {}).values()
            if not surface.get("can_dispatch")
            for pid in (surface.get("providers") or [])
        }
        # A known non-dispatch entry surface may relay an ordinary brief without gaining
        # dispatch authority. A provider claiming dispatch eligibility but failing its
        # evidence/capability/live-route conjunction is misconfigured and fails closed.
        if (p.get("dispatch_eligible") or preferred not in relay_ids
                or not disp.get("relay_known_unqualified_intake")):
            return {"satisfied": False, "requested": preferred, "effective": None,
                    "profile": profile, "fallback_used": False,
                    "explanation": f"PARK: requested dispatcher {preferred!r} is not dispatch-qualified on a live route"}
        candidates = [s for pid, s in statuses.items()
                      if pid != preferred and s["fallback_order"] < 999 and s["qualified"] and s["usable"]]
        candidates.sort(key=lambda s: (s["fallback_order"], routing.route_key(s["seat"]),
                                       -s["prowess"], s["provider"]))
        if not candidates:
            return {"satisfied": False, "requested": preferred, "effective": None,
                    "profile": profile, "fallback_used": False, "intake_relay": True,
                    "explanation": f"PARK: intake provider {preferred!r} cannot dispatch and no live relay target remains"}
        chosen = candidates[0]
        s = chosen["seat"]
        return {"satisfied": True, "requested": preferred, "effective": chosen["provider"],
                "profile": profile, "fallback_used": True, "intake_relay": True,
                "seat": s["seat"], "tier": s["tier"], "family": chosen["family"],
                "explanation": (f"known intake provider {preferred} is not dispatch-qualified; "
                                f"relayed ordinary brief to {chosen['provider']} on {s['seat']}")}
    if status["usable"]:
        s = status["seat"]
        return {"satisfied": True, "requested": preferred, "effective": preferred,
                "profile": profile, "fallback_used": False, "seat": s["seat"],
                "tier": s["tier"], "family": status["family"],
                "explanation": f"requested intake provider {preferred} is live and usable"}
    if not disp.get("fallback_on_recorded_unavailability"):
        return {"satisfied": False, "requested": preferred, "effective": None,
                "profile": profile, "fallback_used": False,
                "explanation": f"PARK: requested dispatcher {preferred} is unavailable and fallback is disabled"}
    candidates = [s for pid, s in statuses.items()
                  if pid != preferred and s["fallback_order"] < 999 and s["qualified"] and s["usable"]]
    candidates.sort(key=lambda s: (s["fallback_order"], routing.route_key(s["seat"]),
                                   -s["prowess"], s["provider"]))
    if not candidates:
        return {"satisfied": False, "requested": preferred, "effective": None,
                "profile": profile, "fallback_used": False,
                "explanation": f"PARK: requested dispatcher {preferred} is unavailable and no live fallback remains"}
    chosen = candidates[0]
    s = chosen["seat"]
    return {"satisfied": True, "requested": preferred, "effective": chosen["provider"],
            "profile": profile, "fallback_used": True, "seat": s["seat"], "tier": s["tier"],
            "family": chosen["family"],
            "explanation": (f"{preferred} unavailable by recorded usage/route state; "
                            f"fell back to {chosen['provider']} on {s['seat']}")}


def live_reviewers(providers, rows, ledger, registry, dispatcher=None, authors=()):
    """Reviewers whose bound catalog route is live. Registry is required; unknown state fails closed."""
    if not registry:
        return []
    by_name = {r["seat"]: r for r in rows}
    prov = providers["providers"]
    review_ids = list(dict.fromkeys((providers.get("review_order") or []) +
                                    (providers.get("review_fallbacks") or [])))
    order_index = {pid: i for i, pid in enumerate(review_ids)}
    live_ids = {pid for pid in review_ids
                if modelreg.provider_route_is_live(registry, prov.get(pid) or {})}
    author_ids = set(authors or ())
    # Family independence follows the *effective* dispatcher. A requested intake
    # that fell back is not a review participant unless that provider was selected.
    dispatcher_family = (prov.get(dispatcher) or {}).get("family")
    dispatcher_group = modelreg.independence_group_of(registry, dispatcher_family)

    downgraded = {k.split(":", 1)[1] for k in (ledger or {}) if str(k).startswith("fable-downgrade:")}
    fable_seats = [r for r in rows if r.get("fable") and routing.usable(r) and r["seat"] not in downgraded]
    anthropic_seats = [r for r in rows if r.get("family") == "anthropic" and routing.usable(r)]

    out = []
    for pid in review_ids:
        p = prov.get(pid, {})
        if not p.get("review_eligible"):
            continue
        if pid in author_ids:
            continue
        if pid not in live_ids:
            continue
        fam = p.get("family")
        group = modelreg.independence_group_of(registry, fam)
        if not group:
            continue
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
            dispatch_independent = not dispatcher_group or group != dispatcher_group
            out.append({"provider": pid, "family": fam, "independence_group": group,
                        "physical": phys, "seat": seat["seat"], "tier": seat["tier"],
                        "billing": seat.get("billing"), "row": seat, "order": order_index.get(pid, 99),
                        "dispatch_independent": dispatch_independent,
                        "review_scope": "artifact-and-dispatch" if dispatch_independent else "artifact-only"})
    # Independent dispatch first, then different family, then billing and availability
    # tier. Among the same independence/billing/tier, configured review_order precedes
    # expiry/intake tie-breaks so drain-window edits cannot invert the gate.
    out.sort(key=lambda e: (not e["dispatch_independent"],
                            bool(dispatcher_family and e["family"] == dispatcher_family),
                            0 if e.get("billing") == "included" else 1,
                            {"available": 0, "reserve": 1, "spent": 2}.get(e.get("tier"), 2),
                            e["order"],
                            1 if e["row"].get("intake") else 0,
                            -routing.expiry_urgency(e["row"])))
    return out


def note_for(entry):
    t = entry["tier"]
    tag = "" if t == "available" else " (reserve released — never strand)"
    scope = f", {entry.get('review_scope')}" if entry.get("review_scope") else ""
    return f"{entry['provider']} on {entry['seat']} [{entry['family']}{scope}]{tag}"


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
        if not first.get("dispatch_independent", True):
            return {"satisfied": False, "chain": [first],
                    "explanation": "PARK: only the dispatcher can review; dispatch intent/risk lacks an independent check."}
        rest = ", ".join(r["provider"] for r in reviewers[1:]) or "(none — then park)"
        return {"satisfied": True, "chain": [first],
                "explanation": f"single-frontier: {note_for(first)}. Fallback: {rest}.{warn}"}
    # cross-family: two DIFFERENT declared independence groups AND unique physical invocations
    first = reviewers[0]
    first_group = first.get("independence_group")
    first_phys = tuple(first.get("physical") or ())
    if not first_group:
        return {"satisfied": False, "chain": [first],
                "explanation": "PARK: first reviewer has no declared independence group."}
    second = next(
        (r for r in reviewers[1:]
         if r.get("independence_group")
         and r.get("independence_group") != first_group
         and tuple(r.get("physical") or ()) != first_phys),
        None,
    )
    if second:
        if not any(r.get("dispatch_independent", True) for r in (first, second)):
            return {"satisfied": False, "chain": [first, second],
                    "explanation": "PARK: review chain lacks an independent dispatch intent/risk check."}
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


IMPLEMENT_FNS = frozenset({"implement", "ide"})


def provider_can_code(provider, registry):
    """True iff this provider may implement: implement/ide function, `code` on the provider
    AND on its bound live catalog route. Live-route predicate is shared (route_is_live)."""
    if not isinstance(provider, dict) or provider.get("enabled", True) is False:
        return False
    fns = set(provider.get("functions") or [])
    if not (fns & IMPLEMENT_FNS):
        return False
    if "code" not in (provider.get("capabilities") or []):
        return False
    if not modelreg.provider_route_is_live(registry, provider):
        return False
    route = (registry.get("routes") or {}).get(provider.get("route") or "") or {}
    return "code" in (route.get("capabilities") or [])


def provider_can_mcp_bulk(provider, registry):
    """True iff this provider may run MCP volume: mcp_bulk function, mcp_bulk on the
    provider AND on its bound live catalog route. Live-route predicate is shared."""
    if not isinstance(provider, dict) or provider.get("enabled", True) is False:
        return False
    if "mcp_bulk" not in (provider.get("functions") or []):
        return False
    if "mcp_bulk" not in (provider.get("capabilities") or []):
        return False
    if not modelreg.provider_route_is_live(registry, provider):
        return False
    route = (registry.get("routes") or {}).get(provider.get("route") or "") or {}
    return "mcp_bulk" in (route.get("capabilities") or [])


def last_resort_coder(prov, registry, subscription, cap_ok):
    """Concrete live coding-capable provider on this subscription, or None.

    Fail closed: a live provider that merely shares the intake plan (Luna/Terra/Sol) is
    not a coder. Prefer `implement` over `ide`, then stable pid order.
    """
    if not subscription:
        return None
    ranked = []
    for pid, p in prov.items():
        if not isinstance(p, dict) or p.get("backed_by") != subscription:
            continue
        if not provider_can_code(p, registry):
            continue
        if not cap_ok(pid):
            continue
        fns = set(p.get("functions") or [])
        ranked.append((0 if "implement" in fns else 1, pid))
    ranked.sort()
    return ranked[0][1] if ranked else None


def pick_implement(providers, connectors, rows, klass, needs_connector, needs_mcp, pixels,
                   task_seconds, registry, avoid_provider=None):
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

    # candidate implement providers: live catalog route + implement/ide + code + needed capability
    impl_ids = [pid for pid, p in prov.items()
                if provider_can_code(p, registry) and cap_ok(pid)]

    def best_seat(pid):
        seats = [s for s in provider_seats(pid, providers, rows) if routing.usable(s)]
        return seats[0] if seats else None

    # worker candidates (non-intake) usable, ordered by route_key of their seat
    workers = []
    for pid in impl_ids:
        s = best_seat(pid)
        if s and not s.get("intake"):
            workers.append((pid, s))
    # Preserve dispatcher context/quota when another equally eligible worker is live.
    # This is a preference, not an absolute: the dispatcher remains a last usable worker.
    def worker_key(pair):
        pid, seat = pair
        economic = routing.route_key(seat)
        # Included always beats metered. Within a billing class, keep dispatch out
        # of implementation while any other usable coder remains, even if reserve.
        return (economic[0], pid == avoid_provider, *economic[1:])

    workers.sort(key=worker_key)

    if needs_mcp:
        # MCP bulk to Terra first. Any failed prerequisite PARKS the whole pipeline —
        # do not snapshot then continue to Grok. Connector match, live Terra route,
        # mcp_bulk on functions + provider capabilities + bound live-route
        # capabilities, and a currently usable Terra seat are all required.
        matches, why = routing.mcp_volume_matches(needs_mcp, connectors, routing.MCP_VOLUME_PROVIDER)
        if not matches:
            steps.append({
                "seat": "(none)",
                "why": (f"PARK: --needs-mcp {needs_mcp!r} is not an active connector "
                        f"(id/alias/class) on {routing.MCP_VOLUME_PROVIDER} ({why})"),
                "available": False, "tier": "spent",
            })
            return steps
        terra_pid = routing.MCP_VOLUME_PROVIDER
        terra_prov = prov.get(terra_pid)
        if not isinstance(terra_prov, dict):
            steps.append({
                "seat": "(none)",
                "why": (f"PARK: --needs-mcp {needs_mcp!r} resolved, but {terra_pid} "
                        "is missing — required MCP work cannot continue to implement"),
                "available": False, "tier": "spent",
            })
            return steps
        terra_route_id = terra_prov.get("route")
        terra_route = (registry.get("routes") or {}).get(terra_route_id) or {}
        if not live_ok(terra_pid):
            steps.append({
                "seat": "(none)",
                "why": (f"PARK: --needs-mcp {needs_mcp!r} resolved, but {terra_pid} "
                        f"has no valid live route ({terra_route_id!r}) — required MCP "
                        "work cannot continue to implement"),
                "available": False, "tier": "spent",
            })
            return steps
        if terra_route.get("provider") not in (None, terra_pid):
            steps.append({
                "seat": "(none)",
                "why": (f"PARK: --needs-mcp {needs_mcp!r} resolved, but {terra_pid} "
                        f"is bound to wrong-route {terra_route_id!r} "
                        f"(provider {terra_route.get('provider')!r}) — required MCP "
                        "work cannot continue to implement"),
                "available": False, "tier": "spent",
            })
            return steps
        if not provider_can_mcp_bulk(terra_prov, registry):
            steps.append({
                "seat": "(none)",
                "why": (f"PARK: --needs-mcp {needs_mcp!r} resolved, but {terra_pid} "
                        "lacks mcp_bulk on provider functions, provider capabilities, "
                        "and bound live-route capabilities — required MCP work "
                        "cannot continue to implement"),
                "available": False, "tier": "spent",
            })
            return steps
        terra = best_seat(terra_pid)
        if not terra:
            steps.append({
                "seat": "(none)",
                "why": (f"PARK: --needs-mcp {needs_mcp!r} resolved, but {terra_pid} "
                        "has no currently usable seat — required MCP work cannot "
                        "continue to implement"),
                "available": False, "tier": "spent",
            })
            return steps
        steps.append({"seat": terra_pid,
                      "why": f"Google-MCP bulk ({needs_mcp}) → output_path snapshot",
                      "available": True, "tier": terra["tier"]})

    if workers:
        pid, s = workers[0]
        steps.append({"seat": pid, "on": s["seat"], "why": "implement (drain-ordered: included→metered, available→reserve, use-before-lost)",
                      "available": True, "tier": s["tier"], "billing": s.get("billing"),
                      "resets_mid_task": routing.resets_before(s, task_seconds)})
    else:
        # never strand: no usable worker → a concrete live coding-capable provider on the
        # intake subscription implements. Luna/Terra/Sol sharing the plan is not enough.
        last_dollar = [pid for pid, p in prov.items()
                       if "last_dollar" in (p.get("functions") or [])
                       and provider_can_code(p, registry) and cap_ok(pid)]
        intake = sorted(
            [r for r in rows if r.get("intake") and routing.usable(r)],
            key=routing.route_key,
        )
        coder = None
        on_row = None
        for row in intake:
            pid = last_resort_coder(prov, registry, row.get("subscription"), cap_ok)
            if pid:
                coder, on_row = pid, row
                break
        if coder and on_row is not None:
            steps.append({
                "seat": coder, "on": on_row["seat"],
                "why": (f"ALL worker seats spent → {coder} on intake codes as last resort "
                        "(never strand; releases reserve; live implement/ide + code on "
                        "provider and bound route)"),
                "available": True, "tier": on_row["tier"], "last_resort": True,
            })
        elif last_dollar:
            pid = last_dollar[0]
            s = best_seat(pid)
            if s:
                steps.append({"seat": pid, "on": s["seat"],
                              "why": "last-resort metered provider (live implement/ide + code on provider and bound route)",
                              "available": True, "tier": s["tier"], "last_resort": True, "billing": s.get("billing")})
            else:
                steps.append({"seat": "(none)",
                              "why": "no usable implement seat — intake has no live coding-capable provider → PARK",
                              "available": False, "tier": "spent"})
        else:
            steps.append({"seat": "(none)",
                          "why": "no usable implement seat — intake has no live coding-capable provider "
                                 "(implement/ide + code on provider and bound live route) → PARK",
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
    ap.add_argument("--needs-mcp", default="",
                    help="connector id, alias, or class this brief needs (routes bulk to Terra; unknown/inert/unusable-Terra PARK)")
    ap.add_argument("--needs-connector", default="", help="capability/connector the implement seat must have (e.g. clarity-magnetbaron, browser)")
    ap.add_argument("--pixels", action="store_true")
    ap.add_argument("--task-seconds", type=int, default=0, help="est. task length; flags seats that reset before it finishes (no mid-turn swaps)")
    ap.add_argument("--user-said-ship", action="store_true")
    ap.add_argument("--intake-provider", default="",
                    help="user-selected dispatcher provider for this run; valid usable choice wins")
    ap.add_argument("--profile", default="default",
                    help="entrypoints profile used when --intake-provider is omitted")
    ap.add_argument("--artifacts", default="",
                    help="comma-separated handoff classes; restricted/unknown classes PARK without asking permission")
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--run-id", default="",
                    help="correlates observability events for this run (generated if omitted)")
    ap.add_argument("--actor-id", default="",
                    help="explicit pseudonymous actor/profile id; never inferred from USER/HOME/git")
    rec = ap.add_mutually_exclusive_group()
    rec.add_argument("--record", action="store_true",
                     help="force-emit an observability event even if emit_on_resolve is false")
    rec.add_argument("--no-record", action="store_true",
                     help="suppress observability emit (routing is unchanged either way)")
    args = ap.parse_args(argv)
    started = time.perf_counter()

    depth_conf = mborch.load_config("review-depth.json")
    providers = mborch.load_config("providers.json")
    entrypoints = mborch.load_config("entrypoints.json")
    handoff_policy = mborch.load_config("handoff-policy.json")
    connectors = mborch.load_config("connectors.json", required=False) or {}
    registry = mborch.load_config("model-registry.json")
    if not registry:
        _emit_bootstrap(args, "missing_registry",
                        "model-registry.json is required (unknown registry state fails closed)", started)
        sys.exit("resolve-route: model-registry.json is required (unknown registry state fails closed)")
    reg_errors = modelreg.validate(registry, providers=providers)
    if reg_errors:
        _emit_bootstrap(args, "invalid_registry", "model-registry invalid (fail closed)", started)
        sys.exit("resolve-route: model-registry invalid (fail closed):\n  - " + "\n  - ".join(reg_errors))
    risk_flags = [f.strip() for f in args.risk.split(",") if f.strip()]

    updated, rows = usage_status.compute(args.ledger)
    lp = Path(args.ledger) if args.ledger else mborch.ledger_path()
    ledger = json.loads(lp.read_text()) if lp.exists() else {}

    try:
        level, reasons, extra = compute_depth(depth_conf, args.klass, args.scale, risk_flags)
    except SystemExit as exc:
        _emit_bootstrap(args, "invalid_class_or_scale", str(exc), started)
        raise
    artifacts = [a.strip() for a in args.artifacts.split(",") if a.strip()]
    required_artifacts = {"brief"}
    if level not in ("none", "self-check"):
        required_artifacts.add("diff")
    if args.implement:
        required_artifacts.update(("repo-source", "diff", "test-output"))
    if not artifacts:
        artifacts = sorted(required_artifacts)
    handoff = evaluate_handoff(handoff_policy, artifacts)
    missing_artifacts = sorted(required_artifacts - set(artifacts))
    handoff["missing_required"] = missing_artifacts
    if missing_artifacts and handoff["allowed"]:
        handoff.update({
            "allowed": False,
            "action": "park",
            "reason": f"PARK: required handoff artifact class(es) not declared: {', '.join(missing_artifacts)}",
        })
    dispatcher = select_dispatcher(entrypoints, providers, rows, registry,
                                   requested=args.intake_provider.strip() or None,
                                   profile=args.profile, ledger=ledger)
    if not dispatcher.get("satisfied") and handoff["allowed"]:
        handoff.update({"allowed": False, "action": "park", "reason": dispatcher["explanation"]})
    effective_dispatcher = dispatcher.get("effective") if dispatcher.get("satisfied") else None
    implement = None
    if args.implement and handoff["allowed"] and dispatcher.get("satisfied"):
        implement = pick_implement(
            providers, connectors, rows, args.klass, args.needs_connector.strip(),
            args.needs_mcp.strip(), args.pixels, args.task_seconds, registry,
            avoid_provider=effective_dispatcher,
        )
    authors = [s.get("seat") for s in (implement or [])
               if s.get("available", True) and not s.get("input_seat") and s.get("seat") not in (None, "(none)")]
    reviewers = live_reviewers(providers, rows, ledger, registry,
                               dispatcher=effective_dispatcher, authors=authors)
    review_e = providers["providers"].get("review-e") or {}
    review_e_wired = modelreg.provider_route_is_live(registry, review_e)
    if not handoff["allowed"]:
        review = {"satisfied": False, "chain": [], "explanation": handoff["reason"]}
    elif not dispatcher.get("satisfied"):
        review = {"satisfied": False, "chain": [], "explanation": dispatcher["explanation"]}
    else:
        review = pick_review(level, reviewers, review_e_wired, args.task_seconds)
    configured_provider_ids = set(providers.get("providers") or {})
    intake_identity = dispatcher.get("requested") if dispatcher.get("requested") in configured_provider_ids else None
    participants = ([intake_identity] if intake_identity else []) + ([effective_dispatcher] if effective_dispatcher else []) + authors + [r["provider"] for r in review["chain"]]
    handoff["participants"] = list(dict.fromkeys(p for p in participants if p))
    unknown_participants = [p for p in handoff["participants"] if p not in configured_provider_ids]
    handoff["unknown_participants"] = unknown_participants
    if unknown_participants:
        handoff.update({
            "allowed": False,
            "action": "park",
            "reason": f"PARK: handoff participant(s) are not configured: {', '.join(unknown_participants)}",
        })
    impl_required_steps = [s for s in (implement or []) if not s.get("input_seat")]
    implementation_satisfied = (not args.implement or
                                (bool(impl_required_steps) and all(s.get("available", True) for s in impl_required_steps)))
    routing_satisfied = bool(handoff["allowed"] and dispatcher.get("satisfied") and
                             review.get("satisfied") and implementation_satisfied)
    if not handoff["allowed"]:
        park_reason = handoff["reason"]
    elif not dispatcher.get("satisfied"):
        park_reason = dispatcher["explanation"]
    elif not review.get("satisfied"):
        park_reason = review["explanation"]
    elif not implementation_satisfied:
        park_reason = "PARK: no complete usable implementation path"
    else:
        park_reason = None

    decision = {
        "class": args.klass, "scale": args.scale, "risk_flags": risk_flags,
        "review_depth": level, "depth_reasons": reasons, "review": review,
        "dispatcher": dispatcher, "handoff": handoff, "authors": authors,
        "routing_satisfied": routing_satisfied, "park_reason": park_reason,
        "live_reviewers": [{k: e[k] for k in ("provider", "family", "seat", "tier", "billing",
                                                "dispatch_independent", "review_scope")} for e in reviewers],
        "gates": {
            "review_d_pixels": bool(extra.get("review_d") or args.pixels or args.klass == "storefront-theme"),
            "owner_gate": bool(extra.get("owner")), "human_gate": bool(extra.get("human")),
            "landing_lock": True, "tip_bound_green_test": True,
        },
        "user_said_ship": args.user_said_ship, "implement": implement, "usage_updated": updated,
        "implement_requested": bool(args.implement),
    }

    duration_ms = int((time.perf_counter() - started) * 1000)
    obs_meta = _emit_decision(decision, args, duration_ms)
    # Metadata only. routing_satisfied / park_reason / seats are already frozen.
    decision["observability"] = obs_meta
    if obs_meta.get("write_error") and not args.json:
        print(f"observability write failed (routing unchanged): {obs_meta['write_error']}",
              file=sys.stderr)

    if args.json:
        print(json.dumps(decision, indent=2))
        return 0

    print(f"ROUTE  class={args.klass} scale={args.scale} risk={risk_flags or '-'}")
    print("-" * 72)
    print(f"review depth: {level}")
    for r in reasons:
        print(f"  · {r}")
    print(f"dispatcher: {'SATISFIED' if dispatcher['satisfied'] else 'NOT SATISFIED'} — {dispatcher['explanation']}")
    print(f"handoff: {'ALLOWED' if handoff['allowed'] else 'PARK'} — {handoff['reason']} (permission prompt: no; basis={handoff.get('authorization_basis')})")
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


def _emit_decision(decision, args, duration_ms):
    routing_ok = bool((decision or {}).get("routing_satisfied"))
    meta = {"recorded": False, "event_id": None, "run_id": args.run_id.strip() or None,
            "write_error": None, "routing_satisfied_unchanged": routing_ok}
    if observe is None:
        meta["write_error"] = f"observe import failed: {_OBS_IMPORT_ERROR}"
        return meta
    try:
        return observe.try_emit_route_decision(
            decision, source="resolve-route", record=args.record, no_record=args.no_record,
            run_id=args.run_id.strip() or None, actor_id=args.actor_id.strip() or None,
            profile_id=args.profile, duration_ms=duration_ms, emit_key="emit_on_resolve",
        )
    except Exception as exc:
        meta["write_error"] = f"{type(exc).__name__}: {exc}"
        return meta


def _emit_bootstrap(args, reason_code, message, started):
    if observe is None:
        return
    try:
        observe.try_emit_bootstrap_failure(
            reason_code=reason_code, message=message, source="resolve-route",
            record=getattr(args, "record", False), no_record=getattr(args, "no_record", False),
            run_id=(getattr(args, "run_id", "") or "").strip() or None,
            actor_id=(getattr(args, "actor_id", "") or "").strip() or None,
            profile_id=getattr(args, "profile", None),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
    except Exception:
        return


if __name__ == "__main__":
    raise SystemExit(main())
