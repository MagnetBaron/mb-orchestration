#!/usr/bin/env python3
"""usage-record — gather usage signals into a retained history, and learn windows.

The dashboard and the subscription recommendation need a history of usage. This
gathers it from the sources config/monitoring.json enables, writes an append-only
JSONL under data/ (gitignored), enforces user-controlled retention (default 1
year), and can LEARN reset anchors from observed resets so refresh windows stay
current automatically.

  usage-record.py --snapshot                 capture current seat state (+ prune)
  usage-record.py --owner codex-sol=88 grok-heavy=40   record owner-noted % (→ ledger + history)
  usage-record.py --from-teamclaude          probe teamclaude JSON (no ingestion adapter)
  usage-record.py --from-ccusage             probe ccusage JSON (no ingestion adapter)
  usage-record.py --prune                    apply retention_days now
  usage-record.py --learn-windows            infer null anchors → data/observed-windows.json
  usage-record.py                            summarize the history store

External commands are probe-only until a source-specific, schema-bound seat adapter
is implemented. A successful parse persists zero history rows and never claims capture.
Only a real 429 (record-429.sh) may mark a seat spent.
"""
from __future__ import annotations
import argparse, json, math, os, shutil, subprocess, sys, tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mborch  # noqa: E402
import importlib.util

_spec = importlib.util.spec_from_file_location("usage_status", Path(__file__).resolve().parent / "usage-status.py")
usage_status = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(usage_status)

_WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
LEDGER_LOCK_TIMEOUT_SECONDS = 5.0
LEDGER_LOCK_POLL_SECONDS = 0.02


def parse_owner_pairs(pairs, configured_seats):
    parsed = []
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"--owner expects SEAT=PCT, got {pair!r}")
        seat, raw_pct = pair.split("=", 1)
        if seat not in configured_seats:
            raise ValueError(f"--owner seat {seat!r} is not configured")
        try:
            pct = float(raw_pct)
        except (TypeError, ValueError):
            raise ValueError(f"--owner pct for {seat!r} must be a number from 0 to 100") from None
        if not math.isfinite(pct) or not 0 <= pct <= 100:
            raise ValueError(f"--owner pct for {seat!r} must be finite and between 0 and 100")
        parsed.append((seat, pct))
    return parsed


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def append_history(records, monitoring):
    p = mborch.history_path(monitoring)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return p


def prune_history(monitoring):
    days = int(monitoring.get("retention_days", 365) or 0)
    if days <= 0:
        return 0
    p = mborch.history_path(monitoring)
    if not p.exists():
        return 0
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    kept, dropped = [], 0
    for h in mborch.read_history(monitoring):
        ts = h.get("ts")
        try:
            t = datetime.fromisoformat(ts).timestamp() if ts else None
        except Exception:
            t = None
        if t is None or t >= cutoff:
            kept.append(h)
        else:
            dropped += 1
    fd, tmp = tempfile.mkstemp(prefix=".usage-history.", dir=str(p.parent))
    with os.fdopen(fd, "w") as f:
        for h in kept:
            f.write(json.dumps(h) + "\n")
    os.replace(tmp, p)
    return dropped


def snapshot(monitoring):
    _, rows = usage_status.compute()
    ts = now_iso()
    recs = []
    for r in rows:
        recs.append({"ts": ts, "source": "snapshot", "seat": r["seat"], "subscription": r.get("subscription"),
                     "family": r.get("family"), "billing": r.get("billing"), "tier": r["tier"],
                     "pct": r.get("pct"), "next_reset": r.get("reset_effective"),
                     "window_kinds": r.get("window_kinds")})
    append_history(recs, monitoring)
    return recs


def write_ledger_pct(seat, pct):
    lp = mborch.ledger_path()
    lock = Path(str(lp) + ".lock")
    lp.parent.mkdir(parents=True, exist_ok=True)
    lock_token = mborch.acquire_directory_lock(
        lock,
        timeout_seconds=LEDGER_LOCK_TIMEOUT_SECONDS,
        poll_seconds=LEDGER_LOCK_POLL_SECONDS,
    )
    tmp = None
    try:
        data = json.loads(lp.read_text()) if lp.exists() else {}
        if not isinstance(data, dict):
            raise ValueError("usage ledger root must be an object")
        entry = data.get(seat) if isinstance(data.get(seat), dict) else {}
        entry.update({"pct": pct, "note": "owner-noted via usage-record", "updated": now_iso()})
        data[seat] = entry
        fd, tmp = tempfile.mkstemp(prefix=".usage-ledger.", dir=str(lp.parent))
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, lp)
        tmp = None
    finally:
        if tmp is not None:
            Path(tmp).unlink(missing_ok=True)
        mborch.release_directory_lock(lock, lock_token)


def run_source(name, monitoring):
    sources = monitoring.get("sources") if isinstance(monitoring, dict) else None
    src = sources.get(name) if isinstance(sources, dict) else None
    if not isinstance(src, dict) or src.get("enabled") is not True:
        return None, f"source '{name}' not enabled in monitoring.json (wire it, then set enabled:true)"
    cmd = src.get("cmd")
    if not cmd:
        return None, f"source '{name}' has no cmd"
    exe = cmd.split()[0]
    if not shutil.which(exe):
        return None, f"source '{name}' cmd '{exe}' not found on PATH (run on the machine that has it)"
    try:
        out = subprocess.run(cmd.split(), capture_output=True, text=True, timeout=40)
        if out.returncode != 0:
            return None, (
                f"probe '{cmd}' exited {out.returncode}; 0 history rows persisted"
            )
        blob = out.stdout.strip()
        data = json.loads(blob) if blob.startswith(("{", "[")) else None
        if data is not None:
            return data, (
                f"probe ran '{cmd}' (JSON parse ok; 0 history rows persisted — "
                "no schema-bound ingestion adapter)"
            )
        return None, f"probe ran '{cmd}' (non-JSON; 0 history rows persisted)"
    except Exception as exc:
        return None, f"source '{name}' failed: {exc}"


def learn_windows(monitoring):
    history = mborch.read_history(monitoring)
    windows = mborch.load_config("usage-windows.json", required=False).get("seats", {})
    byseat = defaultdict(list)
    for h in history:
        if h.get("ts") and h.get("seat"):
            byseat[h["seat"]].append(h)
    learned = {}
    for seat, recs in byseat.items():
        recs.sort(key=lambda r: r["ts"])
        resets = []
        for a, b in zip(recs, recs[1:]):
            drop = (a.get("pct") or 0) - (b.get("pct") or 0)
            spent_to_free = a.get("tier") == "spent" and b.get("tier") != "spent"
            if spent_to_free or drop >= 40:
                try:
                    resets.append(datetime.fromisoformat(b["ts"]))
                except Exception:
                    pass
        if not resets:
            continue
        sc = windows.get(seat, {})
        wk = [w for w in sc.get("windows", [])]
        last = resets[-1]
        weekly = next((w for w in wk if w.get("kind") == "weekly"), None)
        monthly = next((w for w in wk if w.get("kind") == "monthly"), None)
        if weekly and not weekly.get("weekday"):  # only learn when owner has NOT set it
            learned[seat] = {"kind": "weekly", "weekday": _WD[last.weekday()], "time": last.strftime("%H:%M"),
                             "source": "learned", "from_resets": len(resets), "updated": now_iso()}
        elif monthly and not monthly.get("day"):
            learned[seat] = {"kind": "monthly", "day": last.day, "source": "learned",
                             "from_resets": len(resets), "updated": now_iso()}
    outp = mborch.data_dir() / "observed-windows.json"
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(learned, indent=2))
    return learned, outp


def summarize(monitoring):
    history = mborch.read_history(monitoring)
    p = mborch.history_path(monitoring)
    seats = sorted({h.get("seat") for h in history if h.get("seat")})
    ts = sorted(h.get("ts") for h in history if h.get("ts"))
    print(f"usage history: {p} {'(exists)' if p.exists() else '(none yet)'}")
    print(f"  records: {len(history)}  seats: {len(seats)}  retention_days: {monitoring.get('retention_days')}")
    if ts:
        print(f"  range: {ts[0]} … {ts[-1]}")
    print(
        "  sources enabled: "
        f"{[k for k, v in monitoring.get('sources', {}).items() if isinstance(v, dict) and v.get('enabled') is True]}"
    )


def main(argv=None):
    ap = argparse.ArgumentParser(description="Gather usage history; learn windows; prune.")
    ap.add_argument("--snapshot", action="store_true")
    ap.add_argument("--owner", nargs="+", metavar="SEAT=PCT")
    ap.add_argument("--from-teamclaude", action="store_true")
    ap.add_argument("--from-ccusage", action="store_true")
    ap.add_argument("--prune", action="store_true")
    ap.add_argument("--learn-windows", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    monitoring = mborch.load_config("monitoring.json", required=False) or {"retention_days": 365}
    did = []

    if args.owner:
        recs, ts = [], now_iso()
        configured_seats = (
            mborch.load_config("usage-windows.json", required=True).get("seats") or {}
        )
        try:
            owner_values = parse_owner_pairs(args.owner, configured_seats)
        except ValueError as exc:
            sys.exit(f"usage-record: {exc}")
        for seat, pct in owner_values:
            write_ledger_pct(seat, pct)
            recs.append({"ts": ts, "source": "owner-manual", "seat": seat, "pct": pct})
        append_history(recs, monitoring)
        did.append(f"owner: recorded {len(recs)} seat %(s) to ledger + history")

    for name, flag in (("teamclaude", args.from_teamclaude), ("ccusage", args.from_ccusage)):
        if flag:
            _data, msg = run_source(name, monitoring)
            did.append(f"source {name}: {msg}")

    if args.snapshot:
        recs = snapshot(monitoring)
        dropped = prune_history(monitoring)
        did.append(f"snapshot: {len(recs)} seat rows appended; pruned {dropped} old records")

    if args.prune:
        dropped = prune_history(monitoring)
        did.append(f"prune: dropped {dropped} records older than {monitoring.get('retention_days')} days")

    if args.learn_windows:
        learned, outp = learn_windows(monitoring)
        did.append(f"learn-windows: inferred {len(learned)} anchor(s) → {outp}")

    if args.json:
        print(json.dumps({"actions": did}, indent=2))
    elif did:
        for d in did:
            print(d)
    else:
        summarize(monitoring)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
