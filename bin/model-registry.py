#!/usr/bin/env python3
"""model-registry — canonical catalog of models, routes, and per-role rankings.

Providers.json is the runtime seat/host registry (billing, detect, capability
level). This file is the model/route catalog: identity, family/lab, public
lifecycle, route state, harness/invocation id, evidence, and per-role quality
vs selection. Rank never grants tools, credentials, write access, publish
authority, or data access.

Only routes in state `live_verified` may resolve for active dispatch. A catalog
entry or announcement is not a usable route. Unknown availability fails closed.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mborch  # noqa: E402

SCHEMA_VERSION = 1
ROUTE_STATES = (
    "live_verified",
    "catalog_verified",
    "unwired",
    "auth_blocked",
    "quota_spent",
    "disabled",
)
ACTIVE_RESOLVE_STATES = frozenset({"live_verified"})
LIFECYCLES = ("preview", "stable", "superseded", "restricted", "retired")
ROUTABLE_LIFECYCLES = frozenset({"preview", "stable", "superseded", "restricted"})
EVIDENCE_STRENGTHS = (
    "local_smoke",
    "cli_listing",
    "independent_benchmark",
    "vendor_self_reported",
    "owner_eval",
    "none",
)
REQUIRED_RANKING_KINDS = ("quality", "selection")
OPTIONAL_RANKING_KINDS = ("efficiency",)
DATA_BOUNDARIES = ("subscription", "metered_third_party", "local", "unknown")
AUTHORITY_KEYS = frozenset({
    "tools_granted", "credentials", "write_access", "publish_authority",
    "data_access", "can_dispatch", "mcp_granted",
})
REQUIRED_ROLES = (
    "dispatch",
    "context_scouting",
    "research_synthesis",
    "implementation",
    "architecture_spec_critique",
    "code_review",
    "mcp_volume",
    "mcp_judgment",
    "visual_qa",
    "evidence_audit",
    "model_evaluation_admin",
)


class RegistryError(ValueError):
    """Invalid catalog or unsatisfiable resolve request."""


def load(path: Path | None = None) -> dict:
    if path is None:
        return mborch.load_config("model-registry.json")
    try:
        return json.loads(Path(path).read_text())
    except Exception as exc:
        raise RegistryError(f"cannot parse {path}: {exc}") from exc


def _as_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def _sorted_items(mapping: dict) -> list[tuple[str, dict]]:
    return sorted((mapping or {}).items(), key=lambda kv: kv[0])


def validate(registry: dict, as_of: date | None = None, providers: dict | None = None) -> list[str]:
    """Return ERROR strings. Empty list = valid. Stale or contradictory evidence fails."""
    errors: list[str] = []
    if not isinstance(registry, dict):
        return ["model-registry: root must be an object"]
    if registry.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"model-registry: schema_version must be {SCHEMA_VERSION}")
    as_of = as_of or _as_date(registry.get("as_of")) or date.today()
    freshness_days = registry.get("freshness_days", 90)
    if not isinstance(freshness_days, int) or freshness_days < 1:
        errors.append("model-registry: freshness_days must be a positive integer")
        freshness_days = 90

    families = registry.get("families")
    if not isinstance(families, dict) or not families:
        errors.append("model-registry: families must be a non-empty object")
        families = {}
    models = registry.get("models")
    if not isinstance(models, dict) or not models:
        errors.append("model-registry: models must be a non-empty object")
        models = {}
    routes = registry.get("routes")
    if not isinstance(routes, dict) or not routes:
        errors.append("model-registry: routes must be a non-empty object")
        routes = {}
    roles = registry.get("roles")
    if not isinstance(roles, dict):
        errors.append("model-registry: roles must be an object")
        roles = {}
    rankings = registry.get("rankings")
    if not isinstance(rankings, dict):
        errors.append("model-registry: rankings must be an object")
        rankings = {}

    for rid in REQUIRED_ROLES:
        if rid not in roles:
            errors.append(f"model-registry: missing required ranking role {rid!r}")
        if rid not in rankings:
            errors.append(f"model-registry: missing rankings for role {rid!r}")

    for mid, model in models.items():
        if not isinstance(model, dict):
            errors.append(f"model {mid}: must be an object")
            continue
        if model.get("family") not in families:
            errors.append(f"model {mid}: family {model.get('family')!r} is not declared")
        if model.get("lifecycle") not in LIFECYCLES:
            errors.append(f"model {mid}: lifecycle {model.get('lifecycle')!r} not in {LIFECYCLES}")
        ids = model.get("official_ids")
        if not isinstance(ids, list) or not ids or any(not isinstance(x, str) or not x for x in ids):
            errors.append(f"model {mid}: official_ids must be a non-empty list of strings")
        if AUTHORITY_KEYS.intersection(model):
            errors.append(f"model {mid}: rank/catalog must not grant {sorted(AUTHORITY_KEYS.intersection(model))}")

    seen_invocations: dict[tuple, list[str]] = {}
    for rid, route in routes.items():
        if not isinstance(route, dict):
            errors.append(f"route {rid}: must be an object")
            continue
        mid = route.get("model")
        if mid not in models:
            errors.append(f"route {rid}: model {mid!r} is not in models")
            model = {}
        else:
            model = models[mid]
        state = route.get("route_state")
        if state not in ROUTE_STATES:
            errors.append(f"route {rid}: route_state {state!r} not in {ROUTE_STATES}")
        if route.get("lifecycle_override") not in (None, *LIFECYCLES):
            errors.append(f"route {rid}: lifecycle_override {route.get('lifecycle_override')!r} invalid")
        evidence_date = _as_date(route.get("evidence_date"))
        if evidence_date is None:
            errors.append(f"route {rid}: evidence_date is required (YYYY-MM-DD)")
        elif state == "live_verified" and (as_of - evidence_date).days > freshness_days:
            errors.append(
                f"route {rid}: live_verified evidence_date {evidence_date.isoformat()} is stale "
                f"(>{freshness_days} days before {as_of.isoformat()})"
            )
        strength = route.get("evidence_strength")
        if strength not in EVIDENCE_STRENGTHS:
            errors.append(f"route {rid}: evidence_strength {strength!r} not in {EVIDENCE_STRENGTHS}")
        if route.get("data_boundary") not in DATA_BOUNDARIES:
            errors.append(f"route {rid}: data_boundary {route.get('data_boundary')!r} not in {DATA_BOUNDARIES}")
        if not route.get("host") or not route.get("harness") or not route.get("invocation_id"):
            errors.append(f"route {rid}: host, harness, and invocation_id are required")
        if state == "live_verified" and route.get("host") in ("none", "unknown"):
            errors.append(f"route {rid}: host {route.get('host')!r} cannot be live_verified")
        if not isinstance(route.get("capabilities"), list):
            errors.append(f"route {rid}: capabilities must be a list")
        if AUTHORITY_KEYS.intersection(route):
            errors.append(f"route {rid}: must not grant {sorted(AUTHORITY_KEYS.intersection(route))}")
        if state == "live_verified" and (model.get("lifecycle") == "retired"):
            errors.append(f"route {rid}: retired model {mid} cannot be live_verified")
        if state == "live_verified" and route.get("incubation"):
            errors.append(f"route {rid}: incubation routes cannot be live_verified")
        records = route.get("evidence") or []
        if not isinstance(records, list):
            errors.append(f"route {rid}: evidence must be a list")
        else:
            dated = []
            for i, rec in enumerate(records):
                if not isinstance(rec, dict):
                    errors.append(f"route {rid}: evidence[{i}] must be an object")
                    continue
                d = _as_date(rec.get("date"))
                if d is None:
                    errors.append(f"route {rid}: evidence[{i}] missing date")
                    continue
                dated.append((d, rec))
            dated.sort(key=lambda x: x[0])
            last_state = None
            last_date = None
            for d, rec in dated:
                st = rec.get("route_state", state)
                if last_state is not None and st != last_state and d == last_date:
                    errors.append(
                        f"route {rid}: contradictory evidence on {d.isoformat()} "
                        f"({last_state!r} vs {st!r})"
                    )
                last_state, last_date = st, d
            if dated:
                latest_state = dated[-1][1].get("route_state", state)
                if latest_state != state:
                    errors.append(
                        f"route {rid}: route_state {state!r} contradicts latest evidence "
                        f"{latest_state!r} dated {dated[-1][0].isoformat()}"
                    )
        key = (route.get("host"), route.get("harness"), route.get("invocation_id"))
        seen_invocations.setdefault(key, []).append(rid)

    for rid, rnk in rankings.items():
        if rid not in roles:
            errors.append(f"rankings {rid}: role is not declared in roles")
        if not isinstance(rnk, dict):
            errors.append(f"rankings {rid}: must be an object")
            continue
        if AUTHORITY_KEYS.intersection(rnk):
            errors.append(f"rankings {rid}: must not grant {sorted(AUTHORITY_KEYS.intersection(rnk))}")
        for kind in REQUIRED_RANKING_KINDS + OPTIONAL_RANKING_KINDS:
            rows = rnk.get(kind)
            if kind in OPTIONAL_RANKING_KINDS and not rows:
                continue
            if not isinstance(rows, list) or not rows:
                errors.append(f"rankings.{rid}.{kind} must be a non-empty list")
                continue
            ranks = []
            for i, row in enumerate(rows):
                if not isinstance(row, dict) or row.get("route") not in routes:
                    errors.append(f"rankings.{rid}.{kind}[{i}]: route must name a cataloged route")
                    continue
                n = row.get("rank") if kind != "selection" else row.get("priority")
                if not isinstance(n, int) or n < 1:
                    errors.append(f"rankings.{rid}.{kind}[{i}]: rank/priority must be a positive integer")
                else:
                    ranks.append(n)
                if row.get("confidence") not in (None, "high", "medium", "low"):
                    errors.append(f"rankings.{rid}.{kind}[{i}]: confidence must be high|medium|low")
            if len(ranks) != len(set(ranks)):
                errors.append(f"rankings.{rid}.{kind}: rank/priority values must be unique")

    if providers:
        provs = providers.get("providers") or {}
        for pid, p in provs.items():
            if not isinstance(p, dict) or p.get("enabled", True) is False:
                continue
            route_id = p.get("route")
            if not route_id:
                continue
            if route_id not in routes:
                errors.append(f"provider {pid}: route {route_id!r} is not in model-registry.json")
                continue
            route = routes[route_id]
            if route.get("provider") not in (None, pid):
                errors.append(
                    f"provider {pid}: bound route {route_id} names provider {route.get('provider')!r}"
                )
            model = models.get(route.get("model"), {})
            inv = p.get("model")
            official = set(model.get("official_ids") or [])
            if inv and inv not in official and inv != route.get("invocation_id"):
                errors.append(
                    f"provider {pid}: model {inv!r} is not an official id of catalog model "
                    f"{route.get('model')!r} and does not match route invocation_id"
                )
            pf = p.get("family")
            mf = model.get("family")
            harness_families = {"cursor-pool"}
            if pf and mf and pf != mf and pf not in harness_families:
                errors.append(
                    f"provider {pid}: family {pf!r} != catalog family {mf!r}"
                )
        order = providers.get("review_order") or []
        for pid in order:
            p = provs.get(pid) or {}
            route_id = p.get("route")
            if not route_id:
                continue
            route = routes.get(route_id)
            if route and route.get("route_state") not in ACTIVE_RESOLVE_STATES | {"unwired", "quota_spent"}:
                errors.append(
                    f"review_order provider {pid}: bound route {route_id} is "
                    f"{route.get('route_state')!r} (auth_blocked/disabled cannot sit in the gate order)"
                )

    intake = registry.get("intake") or {}
    if not isinstance(intake, dict) or not intake.get("promote_requires"):
        errors.append("model-registry: intake.promote_requires is required (two-phase new-model intake)")

    census = registry.get("census") or {}
    if census:
        if not census.get("as_of") or not census.get("scope"):
            errors.append("model-registry: census.as_of and census.scope are required when census is present")
        for mid in census.get("required_model_ids") or []:
            if mid not in models:
                errors.append(f"census: required model {mid!r} is missing")
                continue
            if not any(r.get("model") == mid for r in routes.values()):
                errors.append(f"census: required model {mid!r} has no route")
        for mid in census.get("ambiguous_ids_forbidden") or []:
            if mid in models:
                errors.append(f"census: ambiguous model id {mid!r} is forbidden")

    return errors


def assert_valid(registry: dict, **kw) -> dict:
    errors = validate(registry, **kw)
    if errors:
        raise RegistryError("model-registry invalid:\n  - " + "\n  - ".join(errors))
    return registry


def _lifecycle(route: dict, model: dict) -> str:
    return route.get("lifecycle_override") or model.get("lifecycle")


def _route_row(rid: str, route: dict, model: dict) -> dict:
    return {
        "route": rid,
        "model": route.get("model"),
        "label": model.get("label") or route.get("model"),
        "family": model.get("family"),
        "lab": model.get("lab"),
        "lifecycle": _lifecycle(route, model),
        "route_state": route.get("route_state"),
        "host": route.get("host"),
        "harness": route.get("harness"),
        "invocation_id": route.get("invocation_id"),
        "provider": route.get("provider"),
        "capabilities": list(route.get("capabilities") or []),
        "tools": list(route.get("tools") or []),
        "connectors": list(route.get("connectors") or []),
        "data_boundary": route.get("data_boundary"),
        "quota_bucket": route.get("quota_bucket"),
        "evidence_date": route.get("evidence_date"),
        "evidence_strength": route.get("evidence_strength"),
        "incubation": bool(route.get("incubation")),
        "compatibility_fallback": bool(route.get("compatibility_fallback")),
        "fallback_until": route.get("fallback_until"),
        "notes": route.get("notes") or model.get("notes") or "",
    }


def inventory(registry: dict) -> list[dict]:
    models = registry.get("models") or {}
    out = []
    for rid, route in _sorted_items(registry.get("routes") or {}):
        model = models.get(route.get("model"), {})
        out.append(_route_row(rid, route, model))
    return out


def _matches(row: dict, *, required_capabilities=None, required_tools=None,
             data_boundary=None, exclude_models=None, exclude_families=None,
             exclude_routes=None, hosts=None, quota_spent=None) -> bool:
    if row["route_state"] not in ACTIVE_RESOLVE_STATES:
        return False
    if row.get("incubation"):
        return False
    if row["lifecycle"] not in ROUTABLE_LIFECYCLES:
        return False
    if row["lifecycle"] == "retired":
        return False
    caps = set(row.get("capabilities") or [])
    tools = set(row.get("tools") or [])
    if required_capabilities and not set(required_capabilities).issubset(caps):
        return False
    if required_tools and not set(required_tools).issubset(tools | caps):
        return False
    if data_boundary and row.get("data_boundary") != data_boundary:
        return False
    if exclude_models and row.get("model") in set(exclude_models):
        return False
    if exclude_families and row.get("family") in set(exclude_families):
        return False
    if exclude_routes and row.get("route") in set(exclude_routes):
        return False
    if hosts and row.get("host") not in set(hosts):
        return False
    spent = set(quota_spent or [])
    if row.get("quota_bucket") in spent or row.get("provider") in spent or row.get("route") in spent:
        return False
    return True


def resolve(registry: dict, role: str, *, n: int = 1, family_diversity: int | None = None,
            required_capabilities=None, required_tools=None, data_boundary=None,
            exclude_models=None, exclude_families=None, exclude_routes=None,
            hosts=None, quota_spent=None, use_quality: bool = False) -> dict:
    """Fail-closed resolver. Only live_verified routes. Rank does not grant authority.

    family_diversity=2 rejects two routes from the same family (cross-family).
    """
    roles = registry.get("roles") or {}
    rankings = registry.get("rankings") or {}
    if role not in roles or role not in rankings:
        return {"ok": False, "role": role, "routes": [], "reason": f"unknown role {role!r}"}
    spec = roles[role]
    req_caps = list(required_capabilities or spec.get("required_capabilities") or [])
    models = registry.get("models") or {}
    routes = registry.get("routes") or {}
    kind = "quality" if use_quality else "selection"
    order_key = "rank" if use_quality else "priority"
    ranked = sorted(
        rankings[role].get(kind) or [],
        key=lambda row: (row.get(order_key, 99), row.get("route") or ""),
    )
    candidates = []
    seen = set()
    for entry in ranked:
        rid = entry.get("route")
        if rid in seen or rid not in routes:
            continue
        seen.add(rid)
        row = _route_row(rid, routes[rid], models.get(routes[rid].get("model"), {}))
        row["quality_rank"] = next(
            (x.get("rank") for x in (rankings[role].get("quality") or []) if x.get("route") == rid),
            None,
        )
        row["selection_priority"] = next(
            (x.get("priority") for x in (rankings[role].get("selection") or []) if x.get("route") == rid),
            None,
        )
        row["confidence"] = entry.get("confidence")
        row["rationale"] = entry.get("rationale")
        if _matches(
            row,
            required_capabilities=req_caps,
            required_tools=required_tools,
            data_boundary=data_boundary,
            exclude_models=exclude_models,
            exclude_families=exclude_families,
            exclude_routes=exclude_routes,
            hosts=hosts,
            quota_spent=quota_spent,
        ):
            candidates.append(row)

    want = family_diversity if family_diversity else n
    picked = []
    used_families = set()
    rejected_same_family = []
    for row in candidates:
        fam = row.get("family")
        if family_diversity and fam in used_families:
            rejected_same_family.append(row["route"])
            continue
        picked.append(row)
        used_families.add(fam)
        if len(picked) >= want:
            break

    result = {
        "ok": False,
        "role": role,
        "routes": picked,
        "rejected_same_family": rejected_same_family,
        "authority_grants": False,
        "reason": "",
    }
    if family_diversity and family_diversity >= 2 and len(picked) < family_diversity:
        fams = sorted(used_families)
        result["reason"] = (
            f"fail-closed: cross-family needs {family_diversity} distinct families; "
            f"only {fams or 'none'} resolved from live_verified routes"
        )
        return result
    if not picked:
        result["reason"] = (
            f"fail-closed: no live_verified route for role {role!r} after filters "
            f"(lifecycle, capabilities, data boundary, exclusions, quota)"
        )
        return result
    if n > 1 and not family_diversity and len(picked) < n:
        result["reason"] = f"fail-closed: needed {n} routes, resolved {len(picked)}"
        return result
    result["ok"] = True
    result["reason"] = "resolved from live_verified routes; rank did not grant tools or data"
    if not family_diversity:
        result["routes"] = picked[:n]
    return result


def rankings_for(registry: dict, role: str) -> dict:
    rnk = (registry.get("rankings") or {}).get(role)
    if not rnk:
        raise RegistryError(f"unknown role {role!r}")
    blob = {
        "role": role,
        "quality": rnk.get("quality") or [],
        "selection": rnk.get("selection") or [],
        "note": (
            "quality_rank and selection_priority are independent; neither grants authority. "
            "Descending ranks are evidence-bounded and role/harness-specific, not a universal ordering. "
            "Cost/token efficiency is selection or an explicit efficiency field, not quality."
        ),
        "authority_grants": False,
    }
    if rnk.get("efficiency"):
        blob["efficiency"] = rnk.get("efficiency")
    return blob


def live_review_providers(registry: dict, providers: dict) -> list[str]:
    """review_order filtered to providers whose bound route is live_verified (or unwired Review E)."""
    routes = registry.get("routes") or {}
    provs = providers.get("providers") or {}
    out = []
    for pid in providers.get("review_order") or []:
        p = provs.get(pid) or {}
        if not p.get("review_eligible"):
            continue
        rid = p.get("route")
        if not rid:
            # Review E historically has no live route; keep the slot only when wired.
            if p.get("wired"):
                out.append(pid)
            continue
        route = routes.get(rid) or {}
        if route.get("route_state") in ACTIVE_RESOLVE_STATES:
            out.append(pid)
        elif pid == "review-e" and p.get("wired") and route.get("route_state") != "disabled":
            out.append(pid)
    return out


def render_matrix(registry: dict) -> str:
    """Byte-idempotent markdown audit surface. Stable key order, trailing newline."""
    lines = [
        "# Model matrix",
        "",
        f"Generated from `config/model-registry.json` as of {registry.get('as_of')}.",
        "Deterministic. Do not hand-edit; run `python3 bin/model-registry.py write-matrix`.",
        "",
        "A catalog entry is not a usable route. Only `live_verified` routes resolve.",
        "Quality rank is not selection priority. Rank never grants tools or data.",
        "Descending ranks are evidence-bounded and role/harness-specific, not a universal ordering.",
        "",
    ]
    census = registry.get("census") or {}
    if census:
        lines += [
            "## Census scope",
            "",
            f"- as_of: {census.get('as_of', '')}",
            f"- cutoff: {census.get('cutoff') or census.get('as_of', '')}",
            f"- scope: {census.get('scope', '')}",
            "",
        ]
    lines += [
        "## Models",
        "",
        "| id | family | lab | lifecycle | official ids | excluded |",
        "|---|---|---|---|---|---|",
    ]
    for mid, model in _sorted_items(registry.get("models") or {}):
        ids = ", ".join(model.get("official_ids") or [])
        excl = "yes" if model.get("excluded") else "no"
        lines.append(
            f"| `{mid}` | {model.get('family','')} | {model.get('lab','')} | "
            f"{model.get('lifecycle','')} | {ids} | {excl} |"
        )
    lines += [
        "",
        "## Routes",
        "",
        "| route | model | state | lifecycle | host | harness | invocation | evidence | provider |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    models = registry.get("models") or {}
    for rid, route in _sorted_items(registry.get("routes") or {}):
        model = models.get(route.get("model"), {})
        lines.append(
            f"| `{rid}` | `{route.get('model')}` | {route.get('route_state')} | "
            f"{_lifecycle(route, model)} | {route.get('host')} | {route.get('harness')} | "
            f"`{route.get('invocation_id')}` | {route.get('evidence_date')} "
            f"{route.get('evidence_strength')} | {route.get('provider') or '—'} |"
        )
    lines += ["", "## Per-role rankings (selection vs quality)", ""]
    for role in REQUIRED_ROLES:
        rnk = (registry.get("rankings") or {}).get(role) or {}
        lines.append(f"### `{role}`")
        lines.append("")
        desc = ((registry.get("roles") or {}).get(role) or {}).get("description") or ""
        if desc:
            lines.append(desc)
            lines.append("")
        lines.append("| kind | n | route | confidence |")
        lines.append("|---|---:|---|---|")
        for kind, key in (("quality", "rank"), ("selection", "priority"), ("efficiency", "rank")):
            for row in rnk.get(kind) or []:
                lines.append(
                    f"| {kind} | {row.get(key)} | `{row.get('route')}` | {row.get('confidence') or ''} |"
                )
        lines.append("")
    lines.append("## Invariants")
    lines.append("")
    inv = registry.get("invariants") or {}
    for k in sorted(inv):
        v = inv[k]
        if isinstance(v, bool):
            v = "true" if v else "false"
        lines.append(f"- `{k}`: {v}")
    lines.append("")
    return "\n".join(lines)


def matrix_path() -> Path:
    return mborch.REPO / "generated" / "model-matrix.md"


def write_matrix(registry: dict, path: Path | None = None, check: bool = False) -> Path:
    path = path or matrix_path()
    text = render_matrix(registry)
    if check:
        if not path.exists():
            raise RegistryError(f"missing generated matrix {path}")
        existing = path.read_text()
        if existing != text:
            raise RegistryError(
                f"{path} is stale or hand-edited — run `python3 bin/model-registry.py write-matrix`"
            )
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Validate and query the model registry.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_val = sub.add_parser("validate", help="schema + freshness + contradiction checks")
    p_val.add_argument("--json", action="store_true")

    p_inv = sub.add_parser("inventory", help="list every cataloged route")
    p_inv.add_argument("--json", action="store_true")
    p_inv.add_argument("--state", default="")

    p_res = sub.add_parser("resolve", help="fail-closed role resolution")
    p_res.add_argument("--role", required=True)
    p_res.add_argument("--n", type=int, default=1)
    p_res.add_argument("--family-diversity", type=int, default=0)
    p_res.add_argument("--require-cap", default="", help="comma-separated capabilities")
    p_res.add_argument("--exclude-family", default="")
    p_res.add_argument("--exclude-model", default="")
    p_res.add_argument("--data-boundary", default="")
    p_res.add_argument("--quota-spent", default="")
    p_res.add_argument("--quality", action="store_true", help="order by quality rank instead of selection")
    p_res.add_argument("--json", action="store_true")

    p_rnk = sub.add_parser("rankings", help="quality vs selection for one role")
    p_rnk.add_argument("--role", required=True)
    p_rnk.add_argument("--json", action="store_true")

    p_mat = sub.add_parser("write-matrix", help="write generated/model-matrix.md")
    p_mat.add_argument("--check", action="store_true")

    args = ap.parse_args(argv)
    registry = load()
    providers = mborch.load_config("providers.json", required=False) or None

    if args.cmd == "validate":
        errors = validate(registry, providers=providers)
        if args.json:
            print(json.dumps({"ok": not errors, "errors": errors}, indent=2))
        else:
            if errors:
                print("model-registry INVALID")
                for e in errors:
                    print(f"  ✗ {e}")
            else:
                print("model-registry OK")
        return 1 if errors else 0

    assert_valid(registry, providers=providers)

    if args.cmd == "inventory":
        rows = inventory(registry)
        if args.state:
            rows = [r for r in rows if r["route_state"] == args.state]
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            print(f"{len(rows)} routes")
            for r in rows:
                print(f"  {r['route_state']:16} {r['route']:28} {r['family']:12} {r['invocation_id']}")
        return 0

    if args.cmd == "resolve":
        def split(s):
            return [x.strip() for x in s.split(",") if x.strip()]
        decision = resolve(
            registry,
            args.role,
            n=args.n,
            family_diversity=args.family_diversity or None,
            required_capabilities=split(args.require_cap) or None,
            exclude_families=split(args.exclude_family) or None,
            exclude_models=split(args.exclude_model) or None,
            data_boundary=args.data_boundary or None,
            quota_spent=split(args.quota_spent) or None,
            use_quality=args.quality,
        )
        if args.json:
            print(json.dumps(decision, indent=2))
        else:
            print(f"{'OK' if decision['ok'] else 'FAIL'}  {decision['reason']}")
            for i, r in enumerate(decision["routes"], 1):
                print(f"  {i}. {r['route']} [{r['family']}] {r['route_state']} sel={r.get('selection_priority')} q={r.get('quality_rank')}")
        return 0 if decision["ok"] else 1

    if args.cmd == "rankings":
        blob = rankings_for(registry, args.role)
        if args.json:
            print(json.dumps(blob, indent=2))
        else:
            print(f"role {args.role} (authority_grants={blob['authority_grants']})")
            print("selection:")
            for row in blob["selection"]:
                print(f"  {row['priority']}. {row['route']} ({row.get('confidence')})")
            print("quality:")
            for row in blob["quality"]:
                print(f"  {row['rank']}. {row['route']} ({row.get('confidence')})")
        return 0

    if args.cmd == "write-matrix":
        path = write_matrix(registry, check=args.check)
        print(("checked " if args.check else "wrote ") + str(path.relative_to(mborch.REPO)))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
