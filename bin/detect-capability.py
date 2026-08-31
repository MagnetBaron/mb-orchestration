#!/usr/bin/env python3
"""detect-capability — bidirectional (downgrade + upgrade) capability detection.

Capabilities like Fable can silently vanish (plan downgrade) OR silently appear
(plan upgrade / new grant). Either way the system should re-route without a prose
edit. This script:

  1. DOWNGRADE: a declared capability (e.g. Fable on a seat) no longer served →
     record `fable-downgrade:<seat>`; the marker lowers the anonymous declared
     Fable ceiling that live TeamClaude capability must reconcile against.
  2. UPGRADE: a seat regains a capability (or gains one config didn't declare) →
     surface it so the owner clears the marker / updates config and the system
     adopts the stronger seat.
  3. MODELS: surface providers that declare `supersedes` (a newer model waiting to
     replace an incumbent) so a clean slot-in (Opus 5.1, Fable 5.1, …) is adopted.

Verification is best-effort via TeamClaude's anonymous aggregate status. On a
portable box without that transport, declared grants remain inventory only and
Anthropic routing parks rather than inventing live accounts. Prints the verified
disable-auto-downgrade levers.

Exit 0 normally; 2 if a declared/observed conflict is detected in --check.
"""
from __future__ import annotations
import argparse, json, os, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mborch  # noqa: E402
import teamclaude_status  # noqa: E402

LEDGER_LOCK_TIMEOUT_SECONDS = 5.0
LEDGER_LOCK_POLL_SECONDS = 0.02

DOWNGRADE_GUIDANCE = """\
Disable automatic model downgrades (verified against code.claude.com/docs/en/model-config):
  · availableModels allowlist — the practical lever. Include 'claude-opus-5' (and 'fable-5' if granted);
    for a hard refusal over a silent drop to Sonnet, leave 'sonnet-5' out too. Opus 4.8 may remain as a compatibility fallback while available.
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


def teamclaude_fable_report():
    """Return aggregate Fable capability presence, not current quota headroom.

    A fully quota-spent Fable pool is still capable and must not be mislabeled as
    a plan downgrade.  Dispatch availability is reported separately by the
    TeamClaude adapter and consumed by resolve-route.
    """
    report = teamclaude_status.inspect_status(models=("claude-fable-5",))
    if report["transport_present"] is False:
        return None, report["status"], report
    if report["service_reachable"] is not True or report["schema_valid"] is not True:
        return None, report["status"], report
    row = report.get("models", {}).get("fable", {})
    live = bool(report.get("reconciled") and row.get("capable_account_count", 0) > 0)
    note = (
        f"TeamClaude aggregate: {row.get('eligible_account_count', 0)} eligible / "
        f"{row.get('capable_account_count', 0)} capable / "
        f"{row.get('declared_seat_count', 0)} declared Fable accounts; "
        f"fleet reconciliation {'passed' if report.get('reconciled') else 'failed'}"
    )
    return live, note, report


def teamclaude_fable():
    """Compatibility API: return the historical (available, note) pair."""
    live, note, _report = teamclaude_fable_report()
    return live, note


def load_ledger():
    lp = mborch.ledger_path()
    return (json.loads(lp.read_text()) if lp.exists() else {}), lp


def write_ledger(mutate):
    lp = mborch.ledger_path()
    lock = Path(str(lp) + ".lock")
    lp.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + LEDGER_LOCK_TIMEOUT_SECONDS
    acquired = False
    tmp = None
    while not acquired:
        try:
            lock.mkdir()
            acquired = True
        except FileExistsError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("timed out waiting for the usage-ledger lock")
            time.sleep(min(LEDGER_LOCK_POLL_SECONDS, remaining))
    try:
        data = json.loads(lp.read_text()) if lp.exists() else {}
        if not isinstance(data, dict):
            raise ValueError("usage ledger root must be an object")
        mutate(data)
        fd, tmp = tempfile.mkstemp(prefix=".usage-ledger.", dir=str(lp.parent))
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, lp)
        tmp = None
    finally:
        if tmp is not None:
            Path(tmp).unlink(missing_ok=True)
        if acquired:
            try:
                lock.rmdir()
            except FileNotFoundError:
                pass


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def superseding_models():
    prov = mborch.load_config("providers.json", required=False).get("providers", {})
    out = []
    for pid, p in prov.items():
        if p.get("supersedes"):
            out.append({
                "new": pid,
                "old": p["supersedes"],
                "old_enabled": prov.get(p["supersedes"], {}).get("enabled", True) is True,
            })
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Bidirectional capability (downgrade+upgrade) detection.")
    ap.add_argument("--check", action="store_true", help="report declared vs observed (default)")
    ap.add_argument("--record-downgrade", metavar="SEAT", help="mark a seat's Fable grant as lost")
    ap.add_argument("--record-upgrade", metavar="SEAT", help="clear a seat's downgrade marker (capability restored)")
    ap.add_argument("--clear", metavar="SEAT", help="alias for --record-upgrade")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    sub_seats, win_seats = declared_fable_seats()
    if args.record_downgrade:
        seat = args.record_downgrade
        if seat not in sub_seats or seat not in win_seats:
            print(
                f"detect-capability: {seat!r} is not a consistently declared Fable seat",
                file=sys.stderr,
            )
            return 2
        write_ledger(lambda d: d.__setitem__(f"fable-downgrade:{seat}",
                     {"grant_lost": "fable", "note": "recorded by detect-capability", "updated": now_iso()}))
        print(
            f"DOWNGRADE recorded fable-downgrade:{seat} — the anonymous declared "
            "Fable ceiling is reduced until cleared."
        )
        return 0
    restore = args.record_upgrade or args.clear
    if restore:
        write_ledger(lambda d: d.pop(f"fable-downgrade:{restore}", None))
        print(f"UPGRADE: cleared fable-downgrade:{restore} — seat re-adopted as Fable-capable.")
        return 0

    ledger, lp = load_ledger()
    marked = sorted(k.split(":", 1)[1] for k in ledger if str(k).startswith("fable-downgrade:"))
    live, note, teamclaude = teamclaude_fable_report()
    conflict = set(sub_seats) ^ set(win_seats)
    effective = sorted(set(sub_seats) - set(marked))
    supers = superseding_models()

    # The privacy-safe TeamClaude receipt is aggregate-only.  It can prove that
    # some Fable capability exists, but it cannot map that capability to a named
    # downgrade marker, so never invent per-seat upgrade candidates here.
    upgrades = []

    if args.json:
        print(json.dumps({
            "declared_subscriptions": sub_seats, "declared_windows": win_seats,
            "declaration_conflict": sorted(conflict), "downgrade_marked": marked,
            "declared_fable_seats_after_markers": effective,
            "live_check": {"capability_present": live, "note": note},
            "teamclaude": teamclaude,
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
        print(f"declared Fable seats minus downgrade markers: {', '.join(effective) or '(none)'}")
        print(f"live check: {note}")
        if (teamclaude.get("service_reachable") is True
                and teamclaude.get("schema_valid") is True
                and teamclaude.get("reconciled") is False):
            print("⚠ ROTATION BLOCKED: live anonymous fleet/capability counts do not reconcile with declarations.")
        elif live is False and effective:
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
