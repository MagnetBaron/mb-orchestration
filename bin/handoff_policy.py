"""Immutable safety floor for agent-to-agent artifact handoffs.

The configurable restricted list may add organization-specific classes, but it
cannot weaken this minimum. Runtime routing imports this module directly so a
class copied into ``ordinary_artifacts`` remains restricted. Doctor imports the
same constant to reject drift before landing.
"""
from __future__ import annotations


IMMUTABLE_MINIMUM_RESTRICTED_ARTIFACTS = frozenset({
    "credentials",
    "customer-data",
    "production-data",
    "production-export",
    "restricted-data",
    "restricted-pii",
    "secrets",
    "tokens",
})


def configured_classes(policy: dict, key: str) -> set[str]:
    """Return only non-empty string classes from a policy list.

    Malformed values never become transferable classes. Schema and doctor report
    the configuration defect; runtime routing remains fail closed meanwhile.
    """
    raw = policy.get(key)
    if not isinstance(raw, list):
        return set()
    return {value for value in raw if isinstance(value, str) and value}


def effective_restricted_artifacts(policy: dict) -> set[str]:
    """Configured restrictions plus the non-removable safety minimum."""
    return configured_classes(policy, "restricted_artifacts") | set(
        IMMUTABLE_MINIMUM_RESTRICTED_ARTIFACTS
    )
