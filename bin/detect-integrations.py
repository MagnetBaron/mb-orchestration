#!/usr/bin/env python3
"""Refresh/check the safe per-runtime integration inventory."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import integrations  # noqa: E402
import mborch  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Detect configured integrations without retaining secrets.")
    ap.add_argument("--json", action="store_true", help="print normalized safe metadata")
    ap.add_argument("--refresh", action="store_true", help="force a fresh allowlisted-manifest scan")
    ap.add_argument("--check", action="store_true", help="return 2 when registered access is not effective")
    ap.add_argument("--session", metavar="FILE|-", help="merge one runtime-bound JSON overlay for this process only")
    args = ap.parse_args(argv)
    try:
        inv = integrations.refresh(force=args.refresh)
        overlay = integrations.load_session(args.session) if args.session else None
        records = integrations.merged_records(inv, overlay)
    except (integrations.InventoryError, OSError) as exc:
        print(f"detect-integrations: {exc}", file=sys.stderr)
        return 1
    effective = []
    for rec in records:
        cid = rec.get("canonical_id")
        if not cid:
            continue
        ok, _ = integrations.effective(rec["runtime"], rec["kind"], cid,
                                       require_callable=rec["kind"] in {"mcp", "app", "connector", "capability"},
                                       inv=inv, overlay=overlay)
        if ok:
            effective.append(f"{rec['runtime']}:{rec['kind']}:{cid}")
    unregistered = [f"{r['runtime']}:{r['kind']}:{r['observed_id']}" for r in records if not r.get("registered")]
    connectors = mborch.load_config("connectors.json", required=False) or {}
    parked = []
    for cid, meta in (connectors.get("mcp_connectors") or {}).items():
        if meta.get("status") != "active":
            continue
        for provider_id in (meta.get("available_on") or []):
            ok, reason = integrations.connector_effective(
                provider_id, cid, meta, inv=inv, overlay=overlay
            )
            if not ok:
                parked.append({"provider": provider_id, "connector": cid, "reason": reason})
    if parked:
        integrations._observe("integration_park", f"count={len(parked)}")
    result = {
        "schema_version": inv.get("schema_version"),
        "generated_at": inv.get("generated_at"),
        "refresh_reason": inv.get("refresh_reason"),
        "session_runtime": overlay.get("runtime") if overlay else None,
        "session_persisted": False,
        "cache_mode_0600": integrations.cache_mode_ok(),
        "records": records,
        "effective": sorted(set(effective)),
        "unregistered": sorted(unregistered),
        "parked": parked,
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("integration inventory")
        print(f"  refreshed: {result['generated_at']} ({result['refresh_reason']})")
        print(f"  observed: {len(records)}  effective now: {len(result['effective'])}  "
              f"unregistered: {len(unregistered)}  parked grants: {len(parked)}")
        for runtime in sorted({r.get("runtime") for r in records}):
            rows = [r for r in records if r.get("runtime") == runtime]
            print(f"  {runtime}: " + ", ".join(
                f"{r['kind']}:{r.get('canonical_id') or r['observed_id']}"
                f" [{'callable' if r.get('callable') else 'configured' if r.get('configured') else 'blocked'}"
                f"{'/unregistered' if not r.get('registered') else ''}]" for r in rows))
    return 2 if args.check and not result["effective"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
