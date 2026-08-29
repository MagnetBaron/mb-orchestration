#!/usr/bin/env python3
"""runledger — the append-only run/lane ledger (the stateful spine).

Turns the pipeline's in-the-agent's-head counters into durable, auditable, machine
truth. Today the fix-loop cap (EDGE-CASES.md "max two fix loops then park") and the
review-starvation guard (DOCTRINE.md "≥3 change-sets awaiting review") live only in
the live dispatcher's context; if that session dies there is no record of which lanes
were dispatched/returned/parked or which loop a lane is on. This is the sibling of
config/usage-ledger.json — that one durably records SEAT quota; this one durably
records the state of WORK in flight.

Design (matches this repo's "behavior in bin/, deterministic, testable" ethos):
  * APPEND-ONLY JSONL at data_dir()/run-ledger.jsonl (gitignored). No in-place
    mutation, no rewrite — crash-safe, and every state is a fold over history so the
    whole run is auditable after the fact ("did that money-data change get its
    cross-family gate before it landed?").
  * The fold/event CORE is PURE and TIME-AGNOSTIC — the timestamp is always passed in,
    so tests are deterministic. Only the thin CLI/runtime edge stamps real time.
  * NOT a daemon, NOT a watcher, NOT an executor (DOCTRINE.md non-goals). It records
    and reconciles state; it never acts.

Lane lifecycle (see pipeline-graph.md for the full state machine):
  created → classified → routed → implemented → review-verdict(ship|fix-list|blocked)
          → gated → landed | parked

  bin/runledger.py append --lane L --event classified --set class=repo-code --set review_depth=single-frontier
  bin/runledger.py state  --lane L [--json]
  bin/runledger.py list   [--status fixing] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mborch  # noqa: E402

# Canonical append-only lane lifecycle events. The fold maps each to a status.
EVENTS = ("created", "classified", "routed", "implemented",
          "review-verdict", "gated", "landed", "parked")
VERDICTS = ("ship", "fix-list", "blocked")
TERMINAL = ("landed", "parked")
# AGENTS.md / EDGE-CASES.md: max two fix loops on a change-set, then park unless a novel defect.
FIX_LOOP_CAP = 2
# Decision fields carried forward onto the folded state whenever an event supplies them.
_CARRY = ("class", "scale", "review_depth", "implement_seat", "review_chain", "gates")
# status after a non-verdict event (review-verdict depends on its verdict field)
_STATUS = {"created": "created", "classified": "classified", "routed": "routed",
           "implemented": "implemented", "gated": "gated", "landed": "landed", "parked": "parked"}


def ledger_file(path=None) -> Path:
    """Run-ledger path — override-aware (tests point MB_DATA_DIR at a temp dir)."""
    if path:
        return Path(path).expanduser()
    return mborch.data_dir() / "run-ledger.jsonl"


# ------------------------------------------------------------------ pure core --
# Everything here is deterministic: no clock, no I/O. `ts` is supplied by the caller.

def make_event(lane, kind, ts, **fields) -> dict:
    """Pure event constructor. The timestamp is passed IN (the CLI/runtime edge
    stamps real time) so the core stays deterministic and unit-testable."""
    if kind not in EVENTS:
        raise ValueError(f"unknown event {kind!r}; known: {', '.join(EVENTS)}")
    if not lane:
        raise ValueError("event requires a lane id")
    if kind == "review-verdict" and fields.get("verdict") not in VERDICTS:
        raise ValueError(f"review-verdict needs verdict in {VERDICTS}, got {fields.get('verdict')!r}")
    ev = {"lane": str(lane), "event": kind, "ts": ts}
    ev.update(fields)
    return ev


def fold(events) -> dict:
    """Pure fold: an ordered list of events (assumed one lane, append order) →
    the lane's current state. This is what makes the fix-loop cap and the
    starvation guard machine-truth instead of memory."""
    st = {
        "lane": None, "status": "new", "class": None, "scale": None,
        "review_depth": None, "implement_seat": None, "review_chain": None, "gates": None,
        "fix_loops": 0, "verdicts": [], "last_event": None, "last_verdict": None,
        "event_count": 0, "first_ts": None, "last_ts": None, "terminal": False,
    }
    for ev in events:
        kind = ev.get("event")
        if kind not in EVENTS:
            continue  # tolerate blank/forward-compatible lines
        st["lane"] = ev.get("lane", st["lane"])
        st["event_count"] += 1
        if st["first_ts"] is None:
            st["first_ts"] = ev.get("ts")
        st["last_ts"] = ev.get("ts")
        st["last_event"] = kind
        for k in _CARRY:
            if ev.get(k) is not None:
                st[k] = ev[k]
        if kind == "review-verdict":
            v = ev.get("verdict")
            st["verdicts"].append({"seat": ev.get("seat"), "verdict": v, "ts": ev.get("ts")})
            st["last_verdict"] = v
            if v == "fix-list":
                st["fix_loops"] += 1
                st["status"] = "fixing"
            elif v == "blocked":
                st["status"] = "blocked"
            else:  # ship
                st["status"] = "review-passed"
        else:
            st["status"] = _STATUS.get(kind, st["status"])
    st["fix_loop_exhausted"] = st["fix_loops"] >= FIX_LOOP_CAP
    st["terminal"] = st["status"] in TERMINAL
    return st


def lane_events(lane, events):
    """Pure filter to one lane, order preserved."""
    return [e for e in events if e.get("lane") == str(lane)]


def lane_ids(events):
    """Pure: distinct lane ids in first-seen order."""
    seen = []
    for e in events:
        lid = e.get("lane")
        if lid is not None and lid not in seen:
            seen.append(lid)
    return seen


def awaiting_review_count(states) -> int:
    """Review-starvation guard input (DOCTRINE §Refill law): lanes sitting in a
    review queue — implemented (awaiting a verdict) or fixing (awaiting re-review).
    Guard trips at >=3."""
    return sum(1 for s in states if s["status"] in ("implemented", "fixing"))


# --------------------------------------------------------------------- I/O edge --

def append(event, path=None) -> Path:
    """Append ONE event as a JSON line (append-only; never rewrites existing lines)."""
    p = ledger_file(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")
    return p


def read(path=None):
    """Read all events, tolerant of blank/corrupt lines (mirrors mborch.read_history)."""
    p = ledger_file(path)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def fold_to_state(lane, path=None, events=None) -> dict:
    """Current state of one lane: read (or use given events), filter to the lane, fold."""
    evs = read(path) if events is None else events
    return fold(lane_events(lane, evs))


def query(path=None, status=None, events=None):
    """Folded state of every lane (optionally filtered by status)."""
    evs = read(path) if events is None else events
    out = [fold(lane_events(lid, evs)) for lid in lane_ids(evs)]
    return [s for s in out if s["status"] == status] if status else out


# ----------------------------------------------------------------------- CLI ---

def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _parse_set(pairs):
    fields = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise SystemExit(f"runledger: --set expects k=v, got {pair!r}")
        k, v = pair.split("=", 1)
        try:
            fields[k] = json.loads(v)  # numbers/bools/json values decode; barewords fall through
        except Exception:
            fields[k] = v
    return fields


def _print_state(st, one_line=False):
    loop = f" fix-loops={st['fix_loops']}{'(EXHAUSTED)' if st['fix_loop_exhausted'] else ''}" if st["fix_loops"] else ""
    if one_line:
        print(f"  {st['lane']:<22} {st['status']:<14} class={st['class'] or '-'} "
              f"depth={st['review_depth'] or '-'}{loop}")
        return
    print(f"lane {st['lane']}  →  {st['status']}{' [TERMINAL]' if st['terminal'] else ''}")
    print(f"  class={st['class']} scale={st['scale']} review_depth={st['review_depth']}")
    print(f"  implement_seat={st['implement_seat']} review_chain={st['review_chain']}")
    print(f"  fix_loops={st['fix_loops']} (cap {FIX_LOOP_CAP}{', EXHAUSTED' if st['fix_loop_exhausted'] else ''}) "
          f"last_event={st['last_event']} last_verdict={st['last_verdict']}")
    print(f"  events={st['event_count']} first={st['first_ts']} last={st['last_ts']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Append-only run/lane ledger (the stateful spine).")
    ap.add_argument("--path", default=None, help="ledger file (default data_dir()/run-ledger.jsonl, gitignored)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("append", help="append one lifecycle event")
    a.add_argument("--lane", required=True)
    a.add_argument("--event", required=True, choices=list(EVENTS))
    a.add_argument("--ts", default=None, help="ISO timestamp; default now (the runtime edge stamps time)")
    a.add_argument("--set", action="append", default=[], metavar="k=v", help="extra field (JSON value if parseable)")
    a.add_argument("--json", action="store_true")

    s = sub.add_parser("state", help="folded current state of one lane")
    s.add_argument("--lane", required=True)
    s.add_argument("--json", action="store_true")

    lst = sub.add_parser("list", help="folded state of every lane")
    lst.add_argument("--status", default=None)
    lst.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)

    if args.cmd == "append":
        try:
            ev = make_event(args.lane, args.event, args.ts or _now_iso(), **_parse_set(args.set))
        except ValueError as exc:
            raise SystemExit(f"runledger: {exc}")
        p = append(ev, args.path)
        print(json.dumps(ev, indent=2) if args.json else f"appended {args.event} for lane {args.lane} → {p}")
        return 0

    if args.cmd == "state":
        st = fold_to_state(args.lane, args.path)
        print(json.dumps(st, indent=2)) if args.json else _print_state(st)
        return 0

    if args.cmd == "list":
        states = query(args.path, status=args.status)
        if args.json:
            print(json.dumps({"lanes": states, "awaiting_review": awaiting_review_count(states)}, indent=2))
        else:
            for st in states:
                _print_state(st, one_line=True)
            n = awaiting_review_count(states)
            print(f"awaiting review: {n} (starvation guard trips at 3 → Build claims only none/self-check)")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
