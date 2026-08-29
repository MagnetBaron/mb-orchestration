#!/usr/bin/env python3
"""Fail-closed validator for provider dispatch-stability receipts."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECEIPTS = (ROOT / "model-evals" / "receipts").resolve()


def validate(provider_id, provider, as_of=None):
    """Return (valid, reason) for a provider's structured dispatch receipt."""
    evidence = (provider or {}).get("dispatch_evidence") or {}
    try:
        evidence_date = date.fromisoformat(evidence.get("date", ""))
    except (TypeError, ValueError):
        return False, "date must be ISO YYYY-MM-DD"
    if evidence_date > (as_of or date.today()):
        return False, "date is in the future"

    source = evidence.get("source")
    if not isinstance(source, str) or not source:
        return False, "source is missing"
    try:
        source_path = (ROOT / source).resolve()
        source_path.relative_to(RECEIPTS)
    except (OSError, ValueError):
        return False, "source must be inside model-evals/receipts"
    if source_path.suffix != ".json" or not source_path.is_file():
        return False, "source must be an existing structured JSON receipt"
    try:
        receipt = json.loads(source_path.read_text())
    except (OSError, json.JSONDecodeError):
        return False, "source receipt is unreadable or invalid JSON"
    if receipt.get("receipt_type") != "dispatch_stability_v1":
        return False, "source receipt has the wrong type"
    if receipt.get("date") != evidence.get("date"):
        return False, "source receipt date does not match provider evidence"

    record = (receipt.get("providers") or {}).get(provider_id)
    if not isinstance(record, dict):
        return False, "source receipt does not bind this provider"
    trials = record.get("trials")
    expected = evidence.get("trials")
    if (record.get("route") != provider.get("route")
            or record.get("status") != evidence.get("status")
            or not isinstance(trials, list) or len(trials) != expected
            or record.get("completed") != evidence.get("completed")
            or record.get("reversals") != evidence.get("reversals")):
        return False, "source receipt summary does not match provider evidence"
    if any(t.get("terminal_reason") != "completed" or t.get("reversals") != 0
           for t in trials if isinstance(t, dict)) or not all(isinstance(t, dict) for t in trials):
        return False, "source receipt contains an incomplete or retracting trial"
    return True, "structured receipt verified"
