#!/usr/bin/env python3
"""detect-capability — bidirectional (downgrade + upgrade) capability detection.

Capabilities like Fable can silently vanish (plan downgrade) OR silently appear
(plan upgrade / new grant). Either way the system should re-route without a prose
edit. This script:

  1. DOWNGRADE: a declared capability (e.g. Fable on a seat) no longer served →
     record `fable-downgrade:<seat>`; resolve-route drops it from the capable set.
  2. UPGRADE: a seat regains a capability (or gains one config didn't declare) →
     surface it so the owner clears the marker / updates config and the system
     adopts the stronger seat.
  3. MODELS: surface providers that declare `supersedes` (a newer model waiting to
     replace an incumbent) so a clean slot-in (Opus 5.1, Fable 5.1, …) is adopted.

Verification is best-effort via teamclaude (per-seat Claude caps); on a portable
box without it, it trusts declared grants and says so. Prints the verified
disable-auto-downgrade levers.

Exit 0 normally; 2 if a declared/observed conflict is detected in --check.
"""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mborch  # noqa: E402

DOWNGRADE_GUIDANCE = """\
Disable automatic model downgrades (verified against code.claude.com/docs/en/model-config):
  · availableModels allowlist — the practical lever. Include 'opus-4.8' (and 'fable-5' if granted);
    leave 'opus-5' OUT (forbidden) and, for a hard refusal over a silent drop to Sonnet, 'sonnet-5' too.
  · fallbackModel — opt-IN, fires only on overload (not rate-limit/billing). Leave unset for none.
  · switchModelsOnFlag:false — stops the safety classifier swapping Fable/Opus mid-task.
  · The silent Opus→Sonnet quota downgrade has no first-class opt-out (issue claude-code#3434); the
    availableModels allowlist is the workaround. See USER-GUIDE.md §Keep Fable from downgrading."""


def declared_fable_seats():
    subs = mborch.load_config("subscriptions.json", required=False).get("subscriptions", {})
    windows = mborch.load_config("usage-windows.json", required=False).get("seats", {})
    sub_seats, win_seats = {}, {}
    for sid, s in subs.items():
        if s.get("grants", {}).get("fable"):
            sub_seats[s.get("seat_id") or sid] = sid
    for seat, w in windows.items():
        if w.get("fable"):
            win_seats[seat] = w.get("subscription")
    return sub_seats, win_seats


def teamclaude_fable():
    tc = shutil.which("teamclaude")
    if not tc:
        return None, "teamclaude not installed here — cannot verify live (run on the worker Mini). Trusting declared grants."
    for cmd in (["teamclaude", "status", "--json"], ["teamclaude", "models", "--json"]):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
            blob = (out.stdout or "") + (out.stderr or "")
            if out.returncode == 0 and blob.strip():
                return ("fable" in blob.lower()), f"teamclaude reported {'a' if 'fable' in blob.lower() else 'NO'} fable seat via `{' '.join(cmd)}`"
        except Exception:
            continue
    return None, "teamclaude present but no parseable output — verify manually."


def load_ledger():
    lp = mborch.ledger_path()
    return (json.loads(lp.read_text()) if lp.exists() else {}), lp


def write_ledger(mutate):
    lp = mborch.ledger_path()
    lock = Path(str(lp) + ".lock")
    lp.parent.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            lock.mkdir()
            break
        except FileExistsError:
            pass
    try:
        data = json.loads(lp.read_text()) if lp.exists() else {}
        mutate(data)
        fd, tmp = tempfile.mkstemp(prefix=".usage-ledger.", dir=str(lp.parent))
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, lp)
    finally:
        lock.rmdir()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def superseding_models():
    prov = mborch.load_config("providers.json", required=False).get("providers", {})
    out = []
    for pid, p in prov.items():
        if p.get("supersedes"):
            out.append({"new": pid, "old": p["supersedes"], "old_enabled": prov.get(p["supersedes"], {}).get("enabled", True)})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Bidirectional capability (downgrade+upgrade) detection.")
    ap.add_argument("--check", action="store_true", help="report declared vs observed (default)")
    ap.add_argument("--record-downgrade", metavar="SEAT", help="mark a seat's Fable grant as lost")
    ap.add_argument("--record-upgrade", metavar="SEAT", help="clear a seat's downgrade marker (capability restored)")
    ap.add_argument("--clear", metavar="SEAT", help="alias for --record-upgrade")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.record_downgrade:
        seat = args.record_downgrade
        write_ledger(lambda d: d.__setitem__(f"fable-downgrade:{seat}",
                     {"grant_lost": "fable", "note": "recorded by detect-capability", "updated": now_iso()}))
        print(f"DOWNGRADE recorded fable-downgrade:{seat} — resolve-route drops it from Fable-capable.")
        return 0
    restore = args.record_upgrade or args.clear
    if restore:
        write_ledger(lambda d: d.pop(f"fable-downgrade:{restore}", None))
        print(f"UPGRADE: cleared fable-downgrade:{restore} — seat re-adopted as Fable-capable.")
        return 0

    sub_seats, win_seats = declared_fable_seats()
    ledger, lp = load_ledger()
    marked = sorted(k.split(":", 1)[1] for k in ledger if str(k).startswith("fable-downgrade:"))
    live, note = teamclaude_fable()
    conflict = set(sub_seats) ^ set(win_seats)
    effective = sorted(set(sub_seats) - set(marked))
    supers = superseding_models()

    # UPGRADE signals: a marked seat that teamclaude now shows as fable-capable.
    upgrades = []
    if live is True and marked:
        upgrades = marked  # capability appears restored → suggest clearing markers

    if args.json:
        print(json.dumps({
            "declared_subscriptions": sub_seats, "declared_windows": win_seats,
            "declaration_conflict": sorted(conflict), "downgrade_marked": marked,
            "effective_fable_seats": effective, "live_check": {"available": live, "note": note},
            "upgrade_candidates": upgrades, "superseding_models": supers,
        }, indent=2))
    else:
        print("detect-capability")
        print("-" * 72)
        print(f"declared Fable seats (subscriptions): {', '.join(sorted(sub_seats)) or '(none)'}")
        print(f"declared Fable seats (usage-windows): {', '.join(sorted(win_seats)) or '(none)'}")
        if conflict:
            print(f"⚠ DECLARATION CONFLICT (subscriptions vs windows disagree): {', '.join(sorted(conflict))}")
        print(f"downgrade markers: {', '.join(marked) or '(none)'}")
        print(f"effective Fable-capable seats now: {', '.join(effective) or '(NONE — review starts at Sol/Opus)'}")
        print(f"live check: {note}")
        if live is False and effective:
            print("⚠ DOWNGRADE suspected: teamclaude reports NO fable though grants declare one.")
            print("  record it:  bin/detect-capability.py --record-downgrade <seat>")
        if upgrades:
            print(f"⬆ UPGRADE available: {', '.join(upgrades)} appear Fable-capable again.")
            print("  adopt it:   bin/detect-capability.py --record-upgrade <seat>")
        if supers:
            for s in supers:
                flag = " (incumbent still enabled — disable it)" if s["old_enabled"] else ""
                print(f"⬆ MODEL slot-in: {s['new']} supersedes {s['old']}{flag}")
        print("-" * 72)
        print(DOWNGRADE_GUIDANCE)

    return 2 if conflict else 0


if __name__ == "__main__":
    raise SystemExit(main())
