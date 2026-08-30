"""Code-owned input bindings for the standing Grok CLI roles.

These bindings are deliberately not configuration.  Both route resolution and
the launcher import this table so a registry or integration attestation cannot
advertise a role that the launcher still has no concrete input path to execute.
"""
from __future__ import annotations


# All normal standing-role execution is parked until each source has a
# code-owned deposit/manifest boundary.  A prompt-declared path, source, class,
# or digest is not transfer authorization and must never become a binding.
EXECUTION_INPUT_BINDINGS: dict[str, str | None] = {
    "grok-bot-review-d": None,
    "grok-bot-heat-map": None,
    "grok-bot-marketplace-intelligence": None,
}
