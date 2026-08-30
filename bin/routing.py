#!/usr/bin/env python3
"""routing — shared drain/allocation scoring for resolve-route.py and drain-plan.py.

Encodes the economics the owner asked for, as legible deterministic rules:
  * minimize API $   — `included` (subscription) seats before `metered` ($) seats, always.
  * never strand     — a `reserve`/intake seat is still USABLE; it only sorts LAST, so a
                       self-imposed cap never halts work while real quota exists.
  * use-before-lost  — among equal seats, drain the one whose quota resets soonest with
                       capacity unused (weekly/monthly near reset) first, to maximize value.
  * preserve intake  — non-intake drain-full seats before the intake/dispatch seat, so
                       dispatch keeps headroom — until nothing else is left, then it codes.
  * no mid-turn swap — a seat whose window resets before the task finishes is flagged.

`capabilities_of(provider, connectors)` unions coarse capabilities with only connectors inside
the `available_on` ceiling that also have fresh runtime/session callable proof, so "who has
Clarity/Chrome/GSC" is observed rather than assumed.
Connector IDs and aliases are always connector-derived — even when they equal a coarse
word such as `browser` — and are granted only through an explicitly active connector
whose `available_on` includes the provider. A coarse exception applies only to connector
`class` labels, and only when that class is declared in the capability catalog
(`COARSE_CAPABILITIES`). Doctor rejects ID/alias collisions with that vocabulary.
"""
from __future__ import annotations

import integrations


# Enumerated non-connector capability vocabulary. Must match providers.json
# `capability_catalog` keys (except `_note`). Connector IDs and aliases never join
# this set; a class label may match a catalog key and stay coarse.
COARSE_CAPABILITIES = frozenset({
    "code", "review", "architecture", "dispatch", "mcp_bulk", "mcp_judgment",
    "browser", "visual_qa", "analytics", "marketplace_intelligence", "ide",
})

# Current Google-MCP volume seat. `--needs-mcp` requires this provider in available_on.
MCP_VOLUME_PROVIDER = "codex-terra"


def expiry_urgency(row):
    """Higher = more quota will be LOST at the next reset if unused. Metered never expires."""
    kinds = row.get("window_kinds") or []
    if "none" in kinds:
        return 0.0  # metered $ — no reset, nothing lost by waiting
    runway = row.get("runway_seconds")
    if "weekly" in kinds or "monthly" in kinds:
        if runway is None:
            return 1.0  # anchor unset — treat as mildly urgent
        days = runway / 86400.0
        return 3.0 / (days + 0.5)  # soon reset → large urgency
    return 0.5  # rolling — refills continuously, low waste urgency


def usable(row):
    return row.get("tier") != "spent"


def connector_is_active(meta):
    """A connector is live-eligible ONLY when its explicit status is 'active'.

    Missing or unknown status is inert — never active. primed (bundled/declared, not wired)
    and ready (validated, awaiting owner activation) are also inert scaffolding and are never
    granted to a seat. Only an owner/admin setting status to 'active' makes a connector
    eligible within the policy ceiling. ``connector_is_effective`` adds the mandatory
    observed runtime/session proof used by routing, role/MCP generation, and skill gates.
    """
    return (meta or {}).get("status") == "active"


def connector_is_effective(provider_id, connector_id, meta, inventory=None, session=None,
                           require_callable=True):
    """Central observed-effective predicate for a provider connector grant.

    ``available_on`` and ``status=active`` are only the vetted ceiling. Fresh
    Runtime/session evidence must additionally prove that the connector is
    enabled, configured, and healthy. Runtime grants keep the default
    ``require_callable=True``; static role validation may explicitly request
    configured-manifest evidence without changing runtime routing.
    """
    return integrations.connector_effective(
        provider_id, connector_id, meta, inv=inventory, overlay=session,
        require_callable=require_callable,
    )


def route_key(row):
    """Sort key for routing ONE task: preferred seat first.
    included→metered, available→reserve, non-intake→intake, then drain the more-urgent first."""
    billing_rank = 0 if row.get("billing") == "included" else 1
    tier_rank = {"available": 0, "reserve": 1, "spent": 2}.get(row.get("tier"), 2)
    intake_rank = 1 if row.get("intake") else 0
    return (billing_rank, tier_rank, intake_rank, -expiry_urgency(row))


def drain_key(row):
    """Sort key for the DRAIN PLAN (use-before-lost): among included seats, expiry urgency
    leads so soon-to-reset weekly/monthly quota is spent first; metered stays last."""
    billing_rank = 0 if row.get("billing") == "included" else 1
    return (billing_rank, -expiry_urgency(row), 1 if row.get("intake") else 0,
            {"available": 0, "reserve": 1, "spent": 2}.get(row.get("tier"), 2))


def resets_before(row, task_seconds):
    """True if this seat's window would reset before a task of task_seconds finishes
    (a mid-turn swap risk). Rolling/metered/unknown → False (no scheduled cutover)."""
    if not task_seconds:
        return False
    kinds = row.get("window_kinds") or []
    if "weekly" not in kinds and "monthly" not in kinds:
        return False
    rw = row.get("runway_seconds")
    return rw is not None and rw < task_seconds


def connector_ids(connectors):
    """Known connector IDs and aliases (not classes). Always connector-derived."""
    names = set()
    for cname, meta in (connectors or {}).get("mcp_connectors", {}).items():
        names.add(cname)
        alias = (meta or {}).get("alias")
        if alias:
            names.add(alias)
    return names


def connector_derived_labels(connectors, catalog=None):
    """IDs, aliases, and non-catalog class labels.

    IDs and aliases are always connector-derived and are never subtracted because
    they collide with `COARSE_CAPABILITIES`. A class label is connector-derived
    unless it is explicitly declared in the capability catalog (the coarse
    exception is class-only).
    """
    catalog = COARSE_CAPABILITIES if catalog is None else catalog
    labels = connector_ids(connectors)
    for _cname, meta in (connectors or {}).get("mcp_connectors", {}).items():
        if not isinstance(meta, dict):
            continue
        cls = meta.get("class")
        if cls and cls not in catalog:
            labels.add(cls)
    return labels


def lookup_connector(name, connectors):
    """Resolve a connector by id or alias. Returns (canonical_id, meta) or (None, None)."""
    if not name:
        return None, None
    mcp = (connectors or {}).get("mcp_connectors") or {}
    if name in mcp:
        return name, mcp[name]
    for cname, meta in mcp.items():
        if isinstance(meta, dict) and meta.get("alias") == name:
            return cname, meta
    return None, None


def connectors_for_label(name, connectors):
    """Matching connectors for an ID, explicit alias, or non-catalog class.

    ID/alias always resolves to exactly one connector, even if the name equals a
    coarse word. A class label matches every connector that declares that class,
    except when the class is declared in the capability catalog (class-only
    coarse exception).
    """
    cid, meta = lookup_connector(name, connectors)
    if cid is not None:
        return [(cid, meta)]
    if not name or name in COARSE_CAPABILITIES:
        return []
    out = []
    for cname, meta in ((connectors or {}).get("mcp_connectors") or {}).items():
        if isinstance(meta, dict) and meta.get("class") == name:
            out.append((cname, meta))
    return out


def mcp_volume_matches(name, connectors, provider_id=None, inventory=None, session=None):
    """Active connectors matching `name` that list the MCP volume provider in available_on.

    Returns (matches, reason). Empty matches = fail closed (unknown/missing/primed/
    inactive/wrong-seat/unobserved/not-callable). ``connector_is_effective`` is the grant predicate.
    """
    provider_id = provider_id or MCP_VOLUME_PROVIDER
    if not name:
        return [], "missing connector requirement"
    matches = connectors_for_label(name, connectors)
    if not matches:
        return [], "unknown connector (not an id, alias, or class)"
    live = []
    reasons = []
    for cid, meta in matches:
        ok, reason = connector_is_effective(provider_id, cid, meta, inventory, session)
        if not ok:
            reasons.append(f"{cid}: {reason}")
            continue
        live.append((cid, meta))
    if live:
        return live, "ok"
    return [], "; ".join(reasons) or "no active matching connector on the MCP volume seat"


def capabilities_of(provider_id, provider, connectors, inventory=None, session=None,
                    require_callable=True):
    """Union of coarse capabilities (providers.json) and connector access (connectors.json).

    Connector IDs and aliases are stripped from the raw capability list even when they
    equal a coarse word. A class is stripped only when it is not in the capability
    catalog. A derived label is granted only when at least one matching connector is
    active, its lifecycle predicate passes, `available_on` includes this provider, and fresh
    runtime/session evidence proves it callable (the default). Static role
    validation may explicitly set ``require_callable=False``; runtime callers
    must retain the default.
    """
    derived = connector_derived_labels(connectors)
    caps = {c for c in (provider.get("capabilities") or []) if c not in derived}
    for cname, meta in (connectors or {}).get("mcp_connectors", {}).items():
        ok, _reason = connector_is_effective(
            provider_id, cname, meta, inventory, session, require_callable=require_callable
        )
        if not ok:
            continue
        caps.add(cname)
        alias = (meta or {}).get("alias")
        if alias:
            caps.add(alias)
        cls = (meta or {}).get("class")
        if cls and cls not in COARSE_CAPABILITIES:
            caps.add(cls)
    return caps
