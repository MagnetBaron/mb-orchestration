#!/usr/bin/env python3
"""run-brief — the DRY-RUN pipeline planner (NO live execution, ever).

The router (bin/resolve-route.py) decides WHAT should happen for a class; this shows
what an executor WOULD do — without doing any of it. It consumes resolve-route.py's
JSON decision AS-IS, the seat-exec.json invocation recipes, and the run-ledger, then
PRINTS three things:
  1. the resolved review depth + concrete review chain + gates (straight from resolve-route);
  2. the seat-exec command it WOULD run per implement/review seat — and, for a metered or
     no-CLI host, WHY it would refuse to shell (the never-metered-host invariant, as data);
  3. the state-machine transition it WOULD take (from the lane's current folded ledger state).

It SHELLS NOTHING — no subprocess, no model call. That is the whole point of this slice:
the value-hunter owner can SEE the plan before anything autonomous is ever enabled. Any
path toward live execution exits with a clear "gated — not built" message. The executor
(the first component that ACTS) is deferred pending an owner go/no-go — see pipeline-graph.md.

  bin/run-brief.py --dry-run --class repo-code --scale routine
  bin/run-brief.py --dry-run --class money-data --scale elevated --json
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mborch  # noqa: E402
import integrations  # noqa: E402
try:
    import observe  # noqa: E402
except Exception as _OBS_IMPORT_ERROR:
    observe = None
else:
    _OBS_IMPORT_ERROR = None


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# In-process imports (NOT subprocesses): the router and the ledger core.
resolve_route = _load("resolve_route", HERE / "resolve-route.py")
runledger = _load("runledger", HERE / "runledger.py")

GATED_MSG = (
    "live execution is gated — NOT built. This planner is DRY-RUN ONLY: it prints the plan "
    "and shells nothing. Re-run with --dry-run.\nThe executor is the first component that ACTS "
    "(writes/lands), so it is deferred pending an owner go/no-go — see pipeline-graph.md "
    "(gates interlocked, per-run caps, never a metered host, concurrency proven)."
)
_LIVE_FLAGS = ("execute", "live", "run", "go", "apply")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def build_decision(klass, scale, risk, pixels, needs_mcp, needs_connector,
                   task_seconds, user_said_ship, ledger, intake_provider="",
                   profile="default", artifacts="", run_id="", actor_id="",
                   record_observability=False, no_record_observability=False,
                   integration_observation=None) -> dict:
    """Consume resolve-route.py's JSON decision verbatim (exact shape — never reshaped).
    Called in-process with stdout captured; this is not a subprocess and shells nothing."""
    argv = ["--class", klass, "--scale", scale, "--implement", "--json"]
    if risk:
        argv += ["--risk", risk]
    if pixels:
        argv.append("--pixels")
    if needs_mcp:
        argv += ["--needs-mcp", needs_mcp]
    if needs_connector:
        argv += ["--needs-connector", needs_connector]
    if task_seconds:
        argv += ["--task-seconds", str(task_seconds)]
    if user_said_ship:
        argv.append("--user-said-ship")
    if ledger:
        argv += ["--ledger", ledger]
    if intake_provider:
        argv += ["--intake-provider", intake_provider]
    if profile:
        argv += ["--profile", profile]
    if artifacts:
        argv += ["--artifacts", artifacts]
    if run_id:
        argv += ["--run-id", run_id]
    if actor_id:
        argv += ["--actor-id", actor_id]
    if no_record_observability:
        argv.append("--no-record")
    # --record-observability records the run_plan only; it does not force the
    # inner resolve-route emit (so emit-on-run-brief-only remains possible).
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = resolve_route.main(argv, integration_observation=integration_observation)
    if rc != 0:
        raise SystemExit(f"run-brief: resolve-route returned {rc}")
    return json.loads(buf.getvalue())


def render_cmd(recipe, ctx):
    """Render the args template for DISPLAY ONLY (never executed)."""
    bin_ = recipe.get("bin")
    if not bin_:
        return None
    out = [bin_]
    for tok in recipe.get("args_template", []):
        for k, v in ctx.items():
            tok = tok.replace("{" + k + "}", v)
        out.append(tok)
    return out


def plan_for_seat(
    pid, recipes, ctx, role, dispatcher=None, review_scope=None,
    *, available=True, input_seat=False,
):
    """What the executor WOULD do for one seat — or WHY it would refuse to shell it.
    Encodes the hard invariant as an inspectable decision, not a hidden branch."""
    r = recipes.get(pid)
    if r is None:
        return {"seat": pid, "role": role, "shellable": False, "would_run": None,
                "available": bool(available), "input_seat": bool(input_seat),
                "reason": f"no seat-exec recipe for {pid!r} (pseudo/last-resort seat) — hand off out-of-band"}
    nmh = bool(r.get("never_metered_host"))
    bin_ = r.get("bin")
    entry = {"seat": pid, "role": role, "reads": r.get("reads"), "worktree": bool(r.get("worktree")),
             "never_metered_host": nmh, "shellable": False, "would_run": None,
             "available": bool(available), "input_seat": bool(input_seat)}
    if input_seat:
        if available:
            entry["reason"] = (
                "standing input seat is never direct-shellable from the dry-run recipe; "
                "only bin/grok-agent.py may validate, stage, and invoke it"
            )
        else:
            entry["reason"] = (
                "standing input seat is unavailable until its code-owned input binding and "
                "live gates pass; no direct argv is shown, and only bin/grok-agent.py may "
                "validate, stage, and invoke it afterward"
            )
    elif not available:
        entry["reason"] = "route step is unavailable — fail closed with no display argv"
    elif not nmh:
        entry["reason"] = ("METERED host — executor guard: never shell a diff/brief to a metered "
                           "inference host (secrets/PII ban); included capacity or owner-land only")
    elif not bin_:
        entry["reason"] = "no CLI (app/API seat) — reached out-of-band, never shelled"
    else:
        entry["shellable"] = True
        entry["would_run"] = render_cmd(r, ctx)
        if (role == "review" and r.get("separate_invocation_when_dispatcher")
                and review_scope == "artifact-only"):
            entry["note"] = ("same-family or same-provider review of the effective dispatcher → "
                             "separate physical invocation; artifact-only, does not independently "
                             "attest to dispatch intent/risk")
    if review_scope:
        entry["review_scope"] = review_scope
    return entry


def build_plan(args, integration_observation=None) -> dict:
    decision = build_decision(args.klass, args.scale, args.risk, args.pixels,
                              args.needs_mcp.strip(), args.needs_connector.strip(),
                              args.task_seconds, args.user_said_ship, args.ledger,
                              args.intake_provider.strip(), args.profile, args.artifacts.strip(),
                              getattr(args, "run_id", "") or "",
                              getattr(args, "actor_id", "") or "",
                              getattr(args, "record_observability", False),
                              getattr(args, "no_record_observability", False),
                              integration_observation)
    lane = args.lane or f"lane-{args.klass}"
    recipes = mborch.load_config("seat-exec.json")["recipes"]
    ctx = {
        "brief_path": args.brief or "<brief.md>",
        "worktree": f".worktrees/{lane}",
        "branch": lane,
        "repo": ".",
        "output_path": "<output_path>",
        "preview_url": "<preview-url>",
        "agent_profile": "<validated-agent-profile>",
        "sandbox_profile": "<ephemeral-sandbox-profile>",
    }

    impl_plans = []
    for step in (decision.get("implement") or []):
        input_seat = bool(step.get("input_seat"))
        available = bool(step.get("available", True))
        role = "review-d-input" if input_seat else "implement"
        p = plan_for_seat(
            step.get("seat"), recipes, ctx, role,
            available=available, input_seat=input_seat,
        )
        p["why"] = step.get("why")
        if step.get("last_resort"):
            p["last_resort"] = True
        if step.get("on"):
            p["on"] = step["on"]
        impl_plans.append(p)

    effective_dispatcher = decision["dispatcher"].get("effective")
    review_plans = [plan_for_seat(c["provider"], recipes, ctx, "review",
                                  dispatcher=effective_dispatcher,
                                  review_scope=c.get("review_scope"))
                    for c in decision["review"]["chain"]]

    cur = runledger.fold_to_state(lane, args.run_ledger)
    transition_to = "routed" if decision.get("routing_satisfied") else "parked"
    trans = {"lane": lane, "from": cur["status"], "to": transition_to,
             "fix_loops": cur["fix_loops"], "fix_loop_exhausted": cur["fix_loop_exhausted"],
             "terminal_before": cur["terminal"]}
    if decision.get("park_reason"):
        trans["park_reason"] = decision["park_reason"]
    if cur["terminal"]:
        trans["warning"] = f"lane already {cur['status']} (terminal) — planning again re-opens it"
    if cur["fix_loop_exhausted"]:
        trans["warning_fix_loops"] = f"fix-loop cap {runledger.FIX_LOOP_CAP} reached — park unless a NOVEL defect"

    implement_seat = next((p["seat"] for p in impl_plans if p["role"] == "implement"), None)
    plan = {
        "lane": lane, "dry_run": True, "class": args.klass, "scale": args.scale,
        "risk_flags": decision["risk_flags"], "review_depth": decision["review_depth"],
        "depth_reasons": decision["depth_reasons"], "review": decision["review"],
        "dispatcher": decision["dispatcher"], "handoff": decision["handoff"],
        "authors": decision.get("authors") or [],
        "routing_satisfied": decision.get("routing_satisfied", False),
        "gates": decision["gates"], "user_said_ship": decision["user_said_ship"],
        "implement": impl_plans, "review_plan": review_plans, "transition": trans,
        "implement_seat": implement_seat,
        "review_chain": [c["provider"] for c in decision["review"]["chain"]],
        "implement_decision": decision.get("implement"),
        "implement_requested": True,
        "park_reason": decision.get("park_reason"),
    }
    if decision.get("integration_observation") is not None:
        plan["integration_observation"] = decision["integration_observation"]
    return plan


def record_trace(plan, run_ledger_path):
    """Append a decision-trace event to the run-ledger (auditability): after the fact you
    can prove what was routed and whether the gates were honored before a land."""
    event_fields = {"class": plan["class"], "scale": plan["scale"],
                    "review_depth": plan["review_depth"],
                    "requested_dispatcher": plan["dispatcher"].get("requested"),
                    "effective_dispatcher": plan["dispatcher"].get("effective"),
                    "implement_seat": plan["implement_seat"],
                    "review_chain": plan["review_chain"], "gates": plan["gates"],
                    "handoff": plan["handoff"], "dry_run": True,
                    "decided_by": "run-brief"}
    if plan.get("integration_observation") is not None:
        event_fields["integration_observation"] = plan["integration_observation"]
    ev = runledger.make_event(
        plan["lane"], plan["transition"]["to"], _now_iso(),
        **event_fields)
    return runledger.append(ev, run_ledger_path)


def _print_plan(plan):
    print(f"DRY-RUN PLAN  lane={plan['lane']}  class={plan['class']} scale={plan['scale']} "
          f"risk={plan['risk_flags'] or '-'}")
    print("=" * 72)
    print(f"review depth: {plan['review_depth']}")
    for r in plan["depth_reasons"]:
        print(f"  · {r}")
    dp = plan["dispatcher"]
    print(f"dispatcher: {'SATISFIED' if dp['satisfied'] else 'NOT SATISFIED (park)'} — {dp['explanation']}")
    hp = plan["handoff"]
    print(f"handoff: {'ALLOWED' if hp['allowed'] else 'PARK'} — {hp['reason']} (permission prompt: no)")
    rv = plan["review"]
    print(f"review: {'SATISFIED' if rv['satisfied'] else 'NOT SATISFIED (park)'} — {rv['explanation']}")
    print(f"gates: {', '.join(k for k, v in plan['gates'].items() if v) or '(none)'}")
    if plan["user_said_ship"]:
        print("  note: user said ship = LAND; the floor's landing lock / green test / pixel / owner gates still apply.")
    observation = plan.get("integration_observation")
    if observation is not None:
        reported = ",".join(observation["reported_callable_ids"]) or "[]"
        print(
            f"integration observation: runtime={observation['runtime']} "
            f"reported_callable_ids={reported} dispatch_authority=false"
        )

    print("-" * 72)
    print("WOULD IMPLEMENT:")
    for p in plan["implement"]:
        _print_seat(p)
    if plan["review_plan"]:
        print("WOULD REVIEW (sequential; blocked wins on disagreement):")
        for p in plan["review_plan"]:
            _print_seat(p)
    else:
        print("WOULD REVIEW: none — no second-model review at this depth (landing lock + green test + owner gates still apply)")

    t = plan["transition"]
    print("-" * 72)
    print(f"state-machine transition: {t['from']} → {t['to']}  (fix-loops={t['fix_loops']}"
          f"{', EXHAUSTED' if t['fix_loop_exhausted'] else ''})")
    for key in ("warning", "warning_fix_loops"):
        if t.get(key):
            print(f"  ⚠ {t[key]}")
    if t.get("park_reason"):
        print(f"  park reason: {t['park_reason']}")
    print("=" * 72)
    print("DRY-RUN: nothing was shelled, no model was called. Live execution is gated — see pipeline-graph.md.")


def _print_seat(p):
    head = f"  → {p['seat']}"
    if p.get("on"):
        head += f" on {p['on']}"
    if p.get("last_resort"):
        head += " [LAST RESORT]"
    print(head + f"  [{p['role']}, reads {p.get('reads', '?')}]")
    if p.get("review_scope"):
        print(f"      scope: {p['review_scope']}")
    if p.get("would_run"):
        print(f"      would run: {' '.join(p['would_run'])}")
    if p.get("reason"):
        print(f"      not shelled: {p['reason']}")
    if p.get("note"):
        print(f"      note: {p['note']}")
    if p.get("why"):
        print(f"      why: {p['why']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="DRY-RUN pipeline planner (no live execution).")
    ap.add_argument("--class", dest="klass", required=True)
    ap.add_argument("--scale", default="routine", choices=["routine", "elevated"])
    ap.add_argument("--risk", default="")
    ap.add_argument("--implement", action="store_true", help="(always on in a plan; accepted for parity)")
    ap.add_argument("--pixels", action="store_true")
    ap.add_argument("--needs-mcp", default="")
    ap.add_argument("--needs-connector", default="")
    ap.add_argument("--runtime-tools", choices=["codex"], default="",
                    help="read a bounded {tool_name:boolean} inventory from stdin as diagnostic observation only; never grants MCP dispatch authority")
    ap.add_argument("--task-seconds", type=int, default=0)
    ap.add_argument("--user-said-ship", action="store_true")
    ap.add_argument("--intake-provider", default="", help="user-selected dispatcher for this run")
    ap.add_argument("--profile", default="default", help="dispatcher preference profile")
    ap.add_argument("--artifacts", default="", help="comma-separated handoff artifact classes")
    ap.add_argument("--lane", default=None)
    ap.add_argument("--brief", default=None, help="path to the 6-field brief file (paths only)")
    ap.add_argument("--ledger", default=None, help="usage ledger passthrough to resolve-route")
    ap.add_argument("--run-ledger", default=None, help="run-ledger path (default data_dir/run-ledger.jsonl)")
    ap.add_argument("--dry-run", action="store_true", help="REQUIRED — this planner only ever dry-runs")
    ap.add_argument("--record", action="store_true", help="append the decision-trace event to the run-ledger (default: a dry-run is side-effect-free)")
    ap.add_argument("--run-id", default="", help="correlates observability events (generated if omitted)")
    ap.add_argument("--actor-id", default="", help="explicit pseudonymous actor id; never inferred")
    obsrec = ap.add_mutually_exclusive_group()
    obsrec.add_argument("--record-observability", action="store_true",
                        help="force-emit an observability run_plan event")
    obsrec.add_argument("--no-record-observability", action="store_true",
                        help="suppress observability emit (does not change the plan)")
    ap.add_argument("--json", action="store_true")
    for f in _LIVE_FLAGS:  # any live-execution intent is refused, loudly
        ap.add_argument(f"--{f}", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    if any(getattr(args, f) for f in _LIVE_FLAGS) or not args.dry_run:
        print(GATED_MSG, file=sys.stderr)
        return 2
    if args.brief and not Path(args.brief).expanduser().exists():
        print(f"run-brief: --brief path does not exist: {args.brief}", file=sys.stderr)
        return 2

    started = time.perf_counter()
    if not args.run_id:
        args.run_id = observe.new_run_id() if observe else str(uuid.uuid4())
    integration_observation = None
    if args.runtime_tools:
        try:
            raw = sys.stdin.buffer.read(integrations.RUNTIME_TOOLS_MAX_BYTES + 1)
            integration_observation = integrations.build_runtime_tool_observation(
                args.runtime_tools, raw
            )
        except (integrations.InventoryError, OSError) as exc:
            print(f"run-brief: invalid runtime tool inventory (fail closed): {exc}", file=sys.stderr)
            return 2
    else:
        integrations.clear_process_session()
    plan = build_plan(args, integration_observation=integration_observation)
    duration_ms = int((time.perf_counter() - started) * 1000)
    if args.record:
        record_trace(plan, args.run_ledger)
    routing_ok = bool(plan.get("routing_satisfied"))
    obs_meta = {"recorded": False, "event_id": None, "run_id": args.run_id,
                "write_error": None, "routing_satisfied_unchanged": routing_ok}
    if observe is None:
        obs_meta["write_error"] = f"observe import failed: {_OBS_IMPORT_ERROR}"
    else:
        try:
            obs_meta = observe.try_emit_route_decision(
                plan, source="run-brief",
                record=args.record_observability, no_record=args.no_record_observability,
                run_id=args.run_id, actor_id=args.actor_id.strip() or None,
                profile_id=args.profile, duration_ms=duration_ms, emit_key="emit_on_run_brief",
            )
        except Exception as exc:
            obs_meta["write_error"] = f"{type(exc).__name__}: {exc}"
    plan["observability"] = obs_meta
    if obs_meta.get("write_error") and not args.json:
        print(f"observability write failed (plan unchanged): {obs_meta['write_error']}",
              file=sys.stderr)

    print(json.dumps(plan, indent=2)) if args.json else _print_plan(plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
