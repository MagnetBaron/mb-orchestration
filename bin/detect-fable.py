#!/usr/bin/env python3
"""detect-fable — is Fable actually available on the seats that claim it?

Fable availability is a subscription grant that can silently disappear on a plan
change/downgrade. This script:

  1. Reads which seats DECLARE Fable (subscriptions.json grants.fable / usage-windows
     seat.fable) and checks the two agree.
  2. Tries to VERIFY live via teamclaude (which tracks per-model caps per account) if
     it is installed; on a portable box without it, it says so and trusts the
     declaration rather than guessing.
  3. Lets the owner record/clear a `fable-downgrade:<seat>` marker in the ledger —
     resolve-route.py drops a marked seat from the Fable-capable set immediately, so
     a downgrade re-routes review without any prose edit.
  4. Prints the (verified) levers to DISABLE automatic model downgrades.

Exit 0 normally; exit 2 if a declared/observed Fable conflict is detected in --check.
"""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE.parent / "config"
LEDGER = CONFIG / "usage-ledger.json"

DOWNGRADE_GUIDANCE = """\
Disable automatic model downgrades (verified against code.claude.com/docs/en/model-config):
  · availableModels allowlist — the practical lever. Exclude 'opus-5' (owner policy: forbidden)
    and, to REFUSE rather than silently drop to Sonnet under an Opus cap, exclude 'sonnet-5'.
    A request for an unavailable model then fails loudly instead of downgrading.
  · fallbackModel — opt-IN only; fires on overload/unavailable server errors for ONE turn,
    NOT on rate-limit/billing. Leave unset for no such switch.
  · switchModelsOnFlag:false (or /config → "Switch models when a message is flagged") — stops the
    safety-classifier from swapping Fable/Opus mid-task.
  · The silent Opus->Sonnet quota downgrade has NO first-class opt-out (issue anthropics/claude-code#3434,
    closed); availableModels is the workaround. Pin opus-4.8 as the model, never opus-5.
See USER-GUIDE.md §Keep Fable (and your model) from silently downgrading."""


def load(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        sys.exit(f"detect-fable: cannot parse {path}: {exc}")


def declared_fable_seats():
    subs = load(CONFIG / "subscriptions.json", {}).get("subscriptions", {})
    windows = load(CONFIG / "usage-windows.json", {}).get("seats", {})
    sub_seats, win_seats = {}, {}
    for sid, s in subs.items():
        if s.get("grants", {}).get("fable"):
            seat = s.get("seat_id") or sid
            sub_seats[seat] = sid
    for seat, w in windows.items():
        if w.get("fable"):
            win_seats[seat] = w.get("subscription")
    return sub_seats, win_seats


def teamclaude_fable_status():
    """Best-effort live check. Returns (available_bool_or_None, note)."""
    tc = shutil.which("teamclaude")
    if not tc:
        return None, "teamclaude not installed here — cannot verify live (run on the worker Mini). Trusting declared grants."
    for cmd in (["teamclaude", "status", "--json"], ["teamclaude", "models", "--json"]):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
            blob = (out.stdout or "") + (out.stderr or "")
            if out.returncode == 0 and blob.strip():
                has_fable = "fable" in blob.lower()
                return has_fable, f"teamclaude reported {'a' if has_fable else 'NO'} fable-capable seat via `{' '.join(cmd)}`"
        except Exception:
            continue
    return None, "teamclaude present but no parseable status/models output — verify manually."


def write_ledger(mutate):
    lock = Path(str(LEDGER) + ".lock")
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            lock.mkdir()
            break
        except FileExistsError:
            pass
    try:
        data = load(LEDGER, {})
        mutate(data)
        fd, tmp = tempfile.mkstemp(prefix=".usage-ledger.", dir=str(LEDGER.parent))
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, LEDGER)
    finally:
        lock.rmdir()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Detect Fable availability / downgrades.")
    ap.add_argument("--check", action="store_true", help="report declared vs observed (default)")
    ap.add_argument("--record-downgrade", metavar="SEAT", help="mark a seat's Fable grant as lost")
    ap.add_argument("--clear", metavar="SEAT", help="clear a seat's fable-downgrade marker")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.record_downgrade:
        seat = args.record_downgrade
        write_ledger(lambda d: d.__setitem__(f"fable-downgrade:{seat}",
                     {"grant_lost": "fable", "note": "recorded by detect-fable", "updated": now_iso()}))
        print(f"recorded fable-downgrade:{seat} — resolve-route now drops it from Fable-capable.")
        return 0
    if args.clear:
        seat = args.clear
        def drop(d):
            d.pop(f"fable-downgrade:{seat}", None)
        write_ledger(drop)
        print(f"cleared fable-downgrade:{seat}.")
        return 0

    sub_seats, win_seats = declared_fable_seats()
    ledger = load(LEDGER, {})
    marked = sorted(k.split(":", 1)[1] for k in ledger if str(k).startswith("fable-downgrade:"))
    live, note = teamclaude_fable_status()

    conflict = set(sub_seats) ^ set(win_seats)
    effective = sorted(set(sub_seats) - set(marked))

    if args.json:
        print(json.dumps({
            "declared_subscriptions": sub_seats, "declared_windows": win_seats,
            "declaration_conflict": sorted(conflict), "downgrade_marked": marked,
            "effective_fable_seats": effective, "live_check": {"available": live, "note": note},
        }, indent=2))
    else:
        print("detect-fable")
        print("-" * 72)
        print(f"declared Fable seats (subscriptions): {', '.join(sorted(sub_seats)) or '(none)'}")
        print(f"declared Fable seats (usage-windows): {', '.join(sorted(win_seats)) or '(none)'}")
        if conflict:
            print(f"⚠ DECLARATION CONFLICT (subscriptions vs windows disagree): {', '.join(sorted(conflict))}")
        print(f"downgrade markers in ledger: {', '.join(marked) or '(none)'}")
        print(f"effective Fable-capable seats now: {', '.join(effective) or '(NONE — review order starts at Sol/Opus)'}")
        print(f"live check: {note}")
        if live is False:
            print("⚠ teamclaude reports NO fable seat though grants declare one — likely a DOWNGRADE.")
            print("  record it:  bin/detect-fable.py --record-downgrade <seat>")
        print("-" * 72)
        print(DOWNGRADE_GUIDANCE)

    if conflict:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
