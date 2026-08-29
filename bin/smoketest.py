#!/usr/bin/env python3
"""smoketest — walk the whole orchestration path and prove it hangs together.

Runs every script the way dispatch/agents invoke it, asserts the expected
behavior (including the never-strand / drain / history / dashboard / example
scaling added in phase 2), and cleans up after itself (temp ledgers/data dirs —
never touches config/usage-ledger.json or data/). A green smoketest means a fresh
clone, or a new user's MB_CONFIG_DIR, is wired correctly.

  bin/smoketest.py            run all checks
  bin/smoketest.py --strict   also require doctor warning-clean
"""
from __future__ import annotations
import argparse, importlib.util, json, os, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = sys.executable
RESULTS = []

_spec = importlib.util.spec_from_file_location("dash", HERE / "dashboard.py")
dash = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dash)


def run(cmd, env=None, **kw):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, env=e, **kw)


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as exc:
        ok, detail = False, f"exception: {exc}"
    RESULTS.append((name, ok, detail))
    print(f"  {'✓' if ok else '✗'} {name}: {detail}")
    return ok


def seed_ledger(tmp, data):
    p = Path(tmp) / "ledger.json"
    p.write_text(json.dumps(data))
    return str(p)


HARD = {"spent_until": "2099-01-01T00:00:00-05:00"}


def c_doctor(strict):
    def fn():
        r = run([PY, "bin/doctor.py"] + (["--strict"] if strict else []))
        return r.returncode == 0, (r.stdout.strip().splitlines() or ["(no output)"])[-1]
    return fn


def c_usage_status():
    r = run([PY, "bin/usage-status.py", "--json"])
    d = json.loads(r.stdout)
    seats = d.get("seats", [])
    fable = [s for s in seats if s.get("fable")]
    tiers = {s["tier"] for s in seats}
    return len(seats) == 11 and len(fable) == 3 and "reserve" in tiers, \
        f"{len(seats)} seats, {len(fable)} fable, tiers={sorted(tiers)}"


def c_resolve(klass, scale, risk, expect):
    def fn():
        cmd = [PY, "bin/resolve-route.py", "--class", klass, "--scale", scale, "--json"]
        if risk:
            cmd += ["--risk", risk]
        d = json.loads(run(cmd).stdout)
        return d["review_depth"] == expect, f"{klass}/{scale}{'/'+risk if risk else ''} → {d['review_depth']} (want {expect})"
    return fn


def c_never_strand():
    """Fable seats hard-spent, Sol only in reserve → cross-family SATISFIED (Sol released)."""
    def fn():
        with tempfile.TemporaryDirectory() as tmp:
            led = seed_ledger(tmp, {"claude-max": HARD, "claude-team-a": HARD, "claude-team-b": HARD})
            d = json.loads(run([PY, "bin/resolve-route.py", "--class", "money-data", "--scale", "elevated",
                                "--ledger", led, "--json"]).stdout)
            fams = {c["family"] for c in d["review"]["chain"]}
            return d["review"]["satisfied"] and fams == {"anthropic", "openai"}, \
                f"satisfied={d['review']['satisfied']} via {sorted(fams)} (reserve Sol released)"
    return fn


def c_genuine_park():
    """Fable seats AND Sol hard-spent → cross-family truly parks; single-frontier survives on Opus."""
    def fn():
        with tempfile.TemporaryDirectory() as tmp:
            led = seed_ledger(tmp, {"claude-max": HARD, "claude-team-a": HARD, "claude-team-b": HARD, "codex-sol": HARD})
            cf = json.loads(run([PY, "bin/resolve-route.py", "--class", "money-data", "--scale", "elevated",
                                 "--ledger", led, "--json"]).stdout)
            sf = json.loads(run([PY, "bin/resolve-route.py", "--class", "catalog-data", "--scale", "elevated",
                                 "--ledger", led, "--json"]).stdout)
            ok = (not cf["review"]["satisfied"]) and sf["review"]["satisfied"] and sf["review"]["chain"][0]["provider"] == "opus-5"
            return ok, f"cross-family parks={not cf['review']['satisfied']}, single-frontier→opus={sf['review']['chain'][0]['provider'] if sf['review']['chain'] else None}"
    return fn


def c_dispatch_codes():
    def fn():
        with tempfile.TemporaryDirectory() as tmp:
            led = seed_ledger(tmp, {"grok-heavy": HARD, "cursor-models": HARD, "cursor-other-400": HARD})
            d = json.loads(run([PY, "bin/resolve-route.py", "--class", "repo-code", "--implement",
                                "--ledger", led, "--json"]).stdout)
            lr = any(s.get("last_resort") for s in d["implement"])
            return lr, f"intake codes as last resort={lr}"
    return fn


def c_drain_plan():
    d = json.loads(run([PY, "bin/drain-plan.py", "--json"]).stdout)
    order = d["drain_order"]
    last_two = {order[-1]["billing"], order[-2]["billing"]}
    reserves = d["reserve_recommendations"]
    return last_two == {"metered"} and len(reserves) >= 1, \
        f"metered drained last={last_two == {'metered'}}, reserve recs={len(reserves)}"


def c_detect_agents():
    d = json.loads(run([PY, "bin/detect-agents.py", "--json"]).stdout)
    return len(d.get("detected", [])) >= 10, f"{len(d.get('detected', []))} providers probed"


def c_rotation_status():
    """Graceful degradation: teamclaude is a runtime dep that is ABSENT here (as in CI). detect-agents
    must still exit 0 and REPORT a rotation status (available/unavailable) rather than error — the
    missing multi-seat rotation is a detected degraded mode, never a suite failure. Proves A1: the
    gap is surfaced, not silent, and its detection stays informational."""
    r = run([PY, "bin/detect-agents.py", "--json"])
    d = json.loads(r.stdout)
    rot = d.get("rotation")
    ok = (r.returncode == 0 and isinstance(rot, dict)
          and isinstance(rot.get("available"), bool)
          and isinstance(rot.get("status"), str) and bool(rot["status"]))
    avail = rot.get("available") if isinstance(rot, dict) else None
    return ok, f"rc={r.returncode}, rotation reported (available={avail}), no-error={r.returncode == 0}"


def c_detect_capability():
    r = run([PY, "bin/detect-capability.py", "--json"])
    d = json.loads(r.stdout)
    return len(d["effective_fable_seats"]) == 3 and not d["declaration_conflict"], \
        f"{len(d['effective_fable_seats'])} fable effective, conflict={d['declaration_conflict']}"


def c_generate_roles():
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        a = run([PY, "bin/generate-roles.py", "--claude-dir", str(t/"c"), "--grok-dir", str(t/"g"), "--codex-output", str(t/"x.toml")])
        if a.returncode != 0:
            return False, a.stderr.strip()[:160]
        before = {p: p.read_bytes() for p in list((t/"c").iterdir()) + list((t/"g").iterdir()) + [t/"x.toml"]}
        run([PY, "bin/generate-roles.py", "--claude-dir", str(t/"c"), "--grok-dir", str(t/"g"), "--codex-output", str(t/"x.toml")])
        after = {p: p.read_bytes() for p in before}
        import tomllib
        tomllib.loads((t/"x.toml").read_text())
        return before == after, f"idempotent={before == after}, toml parses"


def c_record_429():
    with tempfile.TemporaryDirectory() as tmp:
        led = Path(tmp)/"ledger.json"
        env = {"MB_USAGE_LEDGER": str(led), "MB_429_RESET": "2099-01-01T00:00:00Z"}
        run(["bash", "bin/record-429.sh", "grok-heavy", "HTTP 429 rate limit exceeded"], env=env)
        wrote = led.exists() and "grok-heavy" in led.read_text()
        run(["bash", "bin/record-429.sh", "grok-heavy", "connection timed out"], env=env)
        only = list(json.loads(led.read_text()).keys()) == ["grok-heavy"]
        return wrote and only, f"429 recorded={wrote}, timeout ignored={only}"


def c_usage_record():
    with tempfile.TemporaryDirectory() as tmp:
        env = {"MB_DATA_DIR": tmp}
        run([PY, "bin/usage-record.py", "--snapshot"], env=env)
        hist = Path(tmp)/"usage-history.jsonl"
        wrote = hist.exists() and hist.read_text().count("\n") >= 10
        # synthetic resets → learn a weekly anchor for grok-heavy
        hist.write_text("\n".join(json.dumps(r) for r in [
            {"ts": "2026-08-12T13:59:00+00:00", "seat": "grok-heavy", "tier": "spent", "pct": 98, "window_kinds": ["weekly"]},
            {"ts": "2026-08-12T14:00:00+00:00", "seat": "grok-heavy", "tier": "available", "pct": 2, "window_kinds": ["weekly"]},
        ]))
        run([PY, "bin/usage-record.py", "--learn-windows"], env=env)
        learned = json.loads((Path(tmp)/"observed-windows.json").read_text())
        run([PY, "bin/usage-record.py", "--prune"], env=env)
        return wrote and "grok-heavy" in learned, f"snapshot={wrote}, learned={list(learned)}"


def c_dashboard():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)/"d.html"
        r = run([PY, "bin/dashboard.py", "--demo", "--out", str(out)])
        html = out.read_text() if out.exists() else ""
        return r.returncode == 0 and "<title>" in html and "System score" in html and "<svg" in html, \
            f"rendered {len(html)} bytes with title+score+svg"


def c_calc_history():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp)/"usage-history.jsonl").write_text("\n".join(json.dumps(r) for r in dash.demo_history()))
        d = json.loads(run([PY, "bin/subscription-calculator.py", "--from-history", "--json"], env={"MB_DATA_DIR": tmp}).stdout)
        return len(d["utilization"]) >= 4 and isinstance(d["recommendations"], list), \
            f"{len(d['utilization'])} seats analyzed, {len(d['recommendations'])} recs"


def c_examples():
    ok_all, details = True, []
    for ex in ("solo-pro", "two-sub", "agency"):
        d = json.loads(run([PY, "bin/doctor.py", "--json"], env={"MB_CONFIG_DIR": f"config/examples/{ex}"}).stdout)
        ok = not d["errors"]
        ok_all = ok_all and ok
        details.append(f"{ex}={'ok' if ok else d['errors'][:1]}")
    return ok_all, ", ".join(details)


def c_unit_tests():
    a = run([PY, "bin/test_generate.py"])
    b = run([PY, "bin/test_model_registry.py"])
    ok = a.returncode == 0 and b.returncode == 0
    detail = "generate=" + (a.stderr.strip().splitlines() or ["ok"])[-1]
    detail += " registry=" + (b.stderr.strip().splitlines() or ["ok"])[-1]
    return ok, detail


def c_model_registry():
    a = run([PY, "bin/model-registry.py", "validate"])
    b = run([PY, "bin/model-registry.py", "write-matrix", "--check"])
    c = run([PY, "bin/model-registry.py", "resolve", "--role", "code_review", "--family-diversity", "2", "--json"])
    ok_res = False
    detail = f"validate_rc={a.returncode} matrix_rc={b.returncode}"
    if c.returncode == 0:
        d = json.loads(c.stdout)
        fams = {r["family"] for r in d.get("routes", [])}
        ok_res = d.get("ok") and fams == {"anthropic", "openai"}
        detail += f" cross_family={sorted(fams)}"
    return a.returncode == 0 and b.returncode == 0 and ok_res, detail


def c_run_brief():
    """DRY-RUN planner prints a plan and shells nothing; without --dry-run it fails closed;
    and a default dry-run is side-effect-free (never writes the run-ledger)."""
    with tempfile.TemporaryDirectory() as tmp:
        rl = str(Path(tmp) / "rl.jsonl")
        a = run([PY, "bin/run-brief.py", "--dry-run", "--class", "money-data",
                 "--scale", "elevated", "--run-ledger", rl])
        dry = a.returncode == 0 and "DRY-RUN PLAN" in a.stdout and "nothing was shelled" in a.stdout
        side_effect_free = not Path(rl).exists()
        b = run([PY, "bin/run-brief.py", "--class", "money-data", "--scale", "elevated"])
        closed = b.returncode != 0 and "gated" in (b.stderr + b.stdout)
        ok = dry and closed and side_effect_free
        return ok, f"dry-run plan={dry}, fail-closed={closed}, side-effect-free={side_effect_free}"


def c_skills():
    """Skills wiring: the bound plugin skills resolve + render into the claude agents, and
    generate-roles FAILS CLOSED on each negative — an unregistered skill, a write-skill on a
    read_only role, and a seat missing the skill's required capability."""
    spec = importlib.util.spec_from_file_location("gen_skills_smoke", HERE / "generate-roles.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    roles_path = ROOT / "config" / "roles.json"
    prov_path = ROOT / "config" / "providers.json"
    live = json.loads(roles_path.read_text())

    def loads_with(mutate):
        with tempfile.TemporaryDirectory() as tmp:
            data = json.loads(json.dumps(live))
            mutate(data)
            rp = Path(tmp) / "roles.json"
            rp.write_text(json.dumps(data))
            try:
                gen.load(rp, prov_path)
                return None
            except Exception as exc:
                return str(exc)

    # positive: live registry resolves and the three binding roles render their skill line
    reg = gen.load(roles_path, prov_path)
    outs = gen.artifacts(reg, Path("/smoke/claude"), Path("/smoke/grok"), Path("/smoke/codex.toml"))

    def claude_text(role_name):
        p = next((q for q in outs if q.name == f"mb-{role_name}.md" and "claude" in q.parts), None)
        return outs.get(p, "")

    rendered = all(f"skills: magnet-baron-skills:{skill}" in claude_text(role)
                   for role, skill in [("shopify-theme-build", "shopify-theme"),
                                       ("web-build", "web-coding"),
                                       ("mobile-app-build", "mobile-app")])
    bound = {"shopify-theme-build", "web-build", "mobile-app-build"}.issubset(reg["roles"])

    # negative 1: an unregistered skill bound to a role → ERROR
    e1 = loads_with(lambda d: d["roles"]["web-build"]["claude"]["skills"].append("magnet-baron-skills:does-not-exist"))
    n1 = e1 is not None and "registry" in e1
    # negative 2: a kind:write skill reaching a read_only role (seo-research) → ERROR
    e2 = loads_with(lambda d: d["roles"]["seo-research"]["claude"].update({"skills": ["magnet-baron-skills:web-coding"]}))
    n2 = e2 is not None and "write-skill" in e2
    # negative 3: a seat lacking the skill's required_capability (terra seat off shopify-mb-internal) → ERROR
    e3 = loads_with(lambda d: d["roles"]["shopify-theme-build"].update({"seat": "codex-terra"}))
    n3 = e3 is not None and "lacks capability" in e3

    ok = rendered and bound and n1 and n2 and n3
    return ok, (f"render+bind={rendered and bound}, unregistered→err={n1}, "
                f"write-on-readonly→err={n2}, missing-capability→err={n3}")


def c_runledger():
    """Append-only run-ledger: events append to the file and the fold recovers lane state."""
    spec = importlib.util.spec_from_file_location("runledger_smoke", HERE / "runledger.py")
    rl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rl)
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "rl.jsonl"
        rl.append(rl.make_event("lane-x", "created", "2026-01-01T00:00:00+00:00"), str(p))
        rl.append(rl.make_event("lane-x", "review-verdict", "2026-01-01T00:00:02+00:00",
                                 seat="opus-5", verdict="ship"), str(p))
        lines = [ln for ln in p.read_text().splitlines() if ln.strip()]
        st = rl.fold_to_state("lane-x", str(p))
        ok = len(lines) == 2 and isinstance(st, dict) and "status" in st
        return ok, f"appended={len(lines)} lines, folded status={st.get('status')}"


def c_primed_connector_inert():
    """A bundled/primed MCP connector VALIDATES and is INERT: it carries a well-formed server
    DEFINITION, yet the router grants it to NO seat (not live), while an active connector still
    routes (existing live behaviour unchanged). Pure config + pure-function checks — nothing
    here connects, launches, or probes."""
    spec = importlib.util.spec_from_file_location("routing_smoke", HERE / "routing.py")
    routing = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(routing)
    conns = json.loads((ROOT / "config" / "connectors.json").read_text())
    prov = json.loads((ROOT / "config" / "providers.json").read_text())["providers"]
    mcp = conns.get("mcp_connectors", {})
    primed = {n: m for n, m in mcp.items() if m.get("status") in ("primed", "ready")}
    if not primed:
        return False, "no primed/ready connector present to prove inertness"
    # inert: no primed/ready connector is granted to any of its declared seats
    leaked = [f"{n}->{pid}" for n, m in primed.items()
              for pid in m.get("available_on", [])
              if n in routing.capabilities_of(pid, prov.get(pid, {}), conns)]
    # at least one primed entry carries a well-formed bundled server DEFINITION
    has_server = any(isinstance(m.get("server"), dict) and m["server"].get("transport") in ("stdio", "http", "sse")
                     for m in primed.values())
    # active connectors STILL route (absent status = active; live behaviour unchanged)
    gh = mcp.get("github", {})
    active_routes = bool(gh.get("available_on")) and all(
        "github" in routing.capabilities_of(pid, prov.get(pid, {}), conns) for pid in gh["available_on"])
    ok = not leaked and has_server and active_routes
    return ok, (f"primed={sorted(primed)}, inert(no-leak)={not leaked}, "
                f"server-defn-ok={has_server}, active-still-routes={active_routes}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args(argv)
    print("smoketest — walking the orchestration path")
    print("=" * 72)
    check("doctor (config integrity)", c_doctor(args.strict))
    check("usage-status (tri-state)", c_usage_status)
    check("route: internal-notes/routine → none", c_resolve("internal-notes", "routine", "", "none"))
    check("route: catalog-data/elevated → single-frontier", c_resolve("catalog-data", "elevated", "", "single-frontier"))
    check("route: money-data/elevated → cross-family", c_resolve("money-data", "elevated", "", "cross-family"))
    check("route: repo-code + auth → cross-family", c_resolve("repo-code", "routine", "auth", "cross-family"))
    check("never-strand: reserve Sol released for cross-family", c_never_strand())
    check("genuine park: real exhaustion parks; single-frontier survives", c_genuine_park())
    check("dispatch codes last resort when workers spent", c_dispatch_codes())
    check("run-brief dry-run plans + fails closed (shells nothing)", c_run_brief)
    check("run-ledger append→fold round-trip", c_runledger)
    check("drain-plan: metered last + reserve sizing", c_drain_plan)
    check("detect-agents", c_detect_agents)
    check("rotation status (graceful degradation: teamclaude absent)", c_rotation_status)
    check("detect-capability", c_detect_capability)
    check("generate-roles (idempotent + toml)", c_generate_roles)
    check("skills wiring (resolve + fail-closed negatives)", c_skills)
    check("primed MCP connector validates + inert (nothing wired)", c_primed_connector_inert)
    check("record-429 (429 writes, timeout ignored)", c_record_429)
    check("usage-record (snapshot + learn-windows + prune)", c_usage_record)
    check("dashboard renders", c_dashboard)
    check("subscription-calculator --from-history", c_calc_history)
    check("examples validate (1→N scale)", c_examples)
    check("unit tests (generate + model-registry)", c_unit_tests)
    check("model-registry validate + matrix + cross-family", c_model_registry)
    print("=" * 72)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"{passed}/{len(RESULTS)} checks passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
