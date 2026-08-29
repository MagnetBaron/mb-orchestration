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

`capabilities_of(provider, connectors)` unions the provider's coarse capabilities with the
connectors it appears in (`available_on`), so "who has Clarity/Chrome/GSC" is data-derived.
"""
from __future__ import annotations


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
    routable. This is the single lifecycle predicate used by routing, role/MCP generation,
    doctor, and skill gates.
    """
    return (meta or {}).get("status") == "active"


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


def capabilities_of(provider_id, provider, connectors):
    """Union of coarse capabilities (providers.json) and connector access (connectors.json)."""
    caps = set(provider.get("capabilities", []))
    for cname, meta in (connectors or {}).get("mcp_connectors", {}).items():
        if not connector_is_active(meta):
            continue  # primed/ready connectors are inert scaffolding — never routed/granted
        if provider_id in (meta.get("available_on") or []):
            caps.add(cname)
            caps.add(meta.get("class", "connector"))
    return caps
