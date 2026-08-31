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
import argparse, importlib.util, json, os, subprocess, shlex, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = sys.executable
RESULTS = []
INTEGRATION_FIXTURE = ROOT / "model-evals/fixtures/integrations/all-observed.json"
os.environ["MB_INTEGRATION_FIXTURE"] = str(INTEGRATION_FIXTURE)

_spec = importlib.util.spec_from_file_location("dash", HERE / "dashboard.py")
dash = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dash)


def run(cmd, env=None, **kw):
    e = dict(os.environ)
    e["MB_INTEGRATION_FIXTURE"] = str(INTEGRATION_FIXTURE)
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


def teamclaude_fixture_env(tmp, *, fable_eligible=False):
    """Deterministic anonymous rotation receipt for routing invariants.

    These smoke checks exercise quota combinations, not the operator host's
    current account state.  They still cross the real bounded status adapter and
    resolver CLI; only the native TeamClaude status process is replaced.
    """
    probed_at = datetime.now(timezone.utc).isoformat()
    accounts = []
    for index in range(3):
        accounts.append({
            "name": f"smoke-{index}",
            "type": "oauth",
            "disabled": False,
            "status": "active",
            "quota": {
                "unified5h": 0.1,
                "unified7d": 0.2,
                "unified7dFable": 0.2 if fable_eligible else 1.0,
                "unified7dSonnet": None,
                "unifiedStatus": "allowed",
                "unified5hStatus": None,
                "unified7dStatus": None,
                "unified7dFableStatus": None,
                "unified7dSonnetStatus": None,
            },
        })
    document = {
        "switchThreshold": 0.98,
        "blockedModels": [],
        "accounts": accounts,
        "routes": [],
        "probe": {
            "enabled": True,
            "intervalSeconds": 300,
            "accounts": [
                {"name": row["name"], "status": "ok", "lastProbedAt": probed_at}
                for row in accounts
            ],
        },
        "persistence": {
            "healthy": True,
            "lastSuccessAt": probed_at,
            "lastErrorAt": None,
            "errorCode": None,
        },
    }
    binary = Path(tmp) / "teamclaude-status-fixture"
    binary.write_text(
        "#!/bin/sh\n"
        "test \"$1\" = status && test \"$2\" = --json || exit 2\n"
        f"printf '%s\\n' {shlex.quote(json.dumps(document))}\n"
    )
    binary.chmod(0o700)
    return {"TEAMCLAUDE_STATUS_BIN": str(binary)}


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
                                "--ledger", led, "--json"],
                               env=teamclaude_fixture_env(tmp)).stdout)
            fams = {c["family"] for c in d["review"]["chain"]}
            return d["review"]["satisfied"] and fams == {"anthropic", "openai"}, \
                f"satisfied={d['review']['satisfied']} via {sorted(fams)} (reserve Sol released)"
    return fn


def c_genuine_park():
    """With Sol spent, same-pipe Opus cannot independently validate an Opus dispatcher."""
    def fn():
        with tempfile.TemporaryDirectory() as tmp:
            led = seed_ledger(tmp, {"claude-max": HARD, "claude-team-a": HARD, "claude-team-b": HARD, "codex-sol": HARD})
            cf = json.loads(run([PY, "bin/resolve-route.py", "--class", "money-data", "--scale", "elevated",
                                 "--ledger", led, "--json"],
                                env=teamclaude_fixture_env(tmp)).stdout)
            sf = json.loads(run([PY, "bin/resolve-route.py", "--class", "catalog-data", "--scale", "elevated",
                                 "--ledger", led, "--json"],
                                env=teamclaude_fixture_env(tmp)).stdout)
            chain = sf["review"]["chain"]
            ok = (not cf["review"]["satisfied"] and not sf["review"]["satisfied"]
                  and bool(chain) and not chain[0].get("dispatch_independent", True))
            return ok, (f"cross-family parks={not cf['review']['satisfied']}, "
                        f"same-pipe single-frontier parks={not sf['review']['satisfied']}")
    return fn


def c_dispatch_codes():
    """Live Codex intake (Luna/Terra/Sol) has no coding function — last-resort PARKS."""
    def fn():
        with tempfile.TemporaryDirectory() as tmp:
            led = seed_ledger(tmp, {"grok-heavy": HARD, "cursor-models": HARD, "cursor-other-400": HARD})
            d = json.loads(run([PY, "bin/resolve-route.py", "--class", "repo-code", "--implement",
                                "--ledger", led, "--json"]).stdout)
            impl = d["implement"]
            lr = [s for s in impl if s.get("last_resort")]
            generic = any(s.get("seat") == "dispatch/intake" for s in impl)
            parked = any(not s.get("available") and "PARK" in (s.get("why") or "") for s in impl)
            ok = parked and not lr and not generic
            return ok, f"parked={parked} last_resort={bool(lr)} generic_dispatch_intake={generic}"
    return fn


def c_last_resort_names_coder():
    """A concrete live implement/ide + code provider on the intake sub is named, not generic."""
    spec_rr = importlib.util.spec_from_file_location("resolve_route_smoke", HERE / "resolve-route.py")
    rr = importlib.util.module_from_spec(spec_rr)
    spec_rr.loader.exec_module(rr)
    provs = json.loads((ROOT / "config" / "providers.json").read_text())
    registry = json.loads((ROOT / "config" / "model-registry.json").read_text())
    conns = json.loads((ROOT / "config" / "connectors.json").read_text())
    luna = provs["providers"]["codex-luna"]
    luna["functions"] = list(luna["functions"]) + ["implement"]
    luna["capabilities"] = list(luna["capabilities"]) + ["code"]
    registry["routes"]["gpt-5.6-luna-codex"]["capabilities"] = list(
        registry["routes"]["gpt-5.6-luna-codex"]["capabilities"]
    ) + ["code"]
    rows = [
        {"seat": "grok-heavy", "subscription": "grok-heavy", "tier": "spent",
         "billing": "included", "intake": False, "window_kinds": ["weekly"],
         "runway_seconds": 1, "family": "xai"},
        {"seat": "cursor-models", "subscription": "cursor-ultra", "tier": "spent",
         "billing": "included", "intake": False, "window_kinds": ["monthly"],
         "runway_seconds": 1, "family": "cursor-pool"},
        {"seat": "codex-plan", "subscription": "codex-200", "tier": "reserve",
         "billing": "included", "intake": True, "window_kinds": ["weekly"],
         "runway_seconds": 864000, "family": "openai"},
    ]
    steps = rr.pick_implement(provs, conns, rows, "repo-code", "", "", False, 0, registry)
    hit = [s for s in steps if s.get("last_resort")]
    ok = (len(hit) == 1 and hit[0]["seat"] == "codex-luna" and hit[0]["on"] == "codex-plan"
          and hit[0]["seat"] != "dispatch/intake")
    return ok, f"last_resort={hit[0]['seat'] if hit else None} on={hit[0].get('on') if hit else None}"


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
    """Accept either live verified rotation or explicit portable degradation.

    TeamClaude is optional on CI but may be healthy on an operator host. Detection
    must exit 0 and report a schema-bound state in both cases; neither presence nor
    absence may be silently inferred from the binary alone.
    """
    r = run([PY, "bin/detect-agents.py", "--json"])
    d = json.loads(r.stdout)
    rot = d.get("rotation")
    ok = (r.returncode == 0 and isinstance(rot, dict)
          and isinstance(rot.get("transport_present"), bool)
          and rot.get("available") in (True, False, None)
          and rot.get("readiness") in ("ready", "not evaluated", "blocked")
          and isinstance(rot.get("status"), str) and bool(rot["status"]))
    avail = rot.get("available") if isinstance(rot, dict) else None
    return ok, f"rc={r.returncode}, rotation reported (available={avail}), no-error={r.returncode == 0}"


def c_detect_capability():
    r = run([PY, "bin/detect-capability.py", "--json"])
    d = json.loads(r.stdout)
    declared = d["declared_fable_seats_after_markers"]
    capability = d["live_check"]["capability_present"]
    coherent = capability in (True, False, None)
    return len(declared) == 3 and coherent and not d["declaration_conflict"], \
        (f"{len(declared)} fable declared after markers, "
         f"aggregate capability={capability}, conflict={d['declaration_conflict']}")


def c_connectors():
    r = run([PY, "bin/test_connectors.py"])
    detail = "visual-QA CLI packet/URL/deny regression suite"
    if r.returncode != 0:
        detail = (r.stderr or r.stdout).strip().splitlines()[-1]
    return r.returncode == 0, detail


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
    c = run([PY, "bin/test_observability.py"])
    d = run([PY, "bin/test_doctor.py"])
    e = run([PY, "bin/test_sync_commands.py"])
    f = run([PY, "bin/test_grok_agent.py"])
    g = run([PY, "bin/test_sync_grok_agents.py"])
    h = run([PY, "bin/test_subscription_calculator.py"])
    ok = all(x.returncode == 0 for x in (a, b, c, d, e, f, g, h))
    detail = "generate=" + (a.stderr.strip().splitlines() or ["ok"])[-1]
    detail += " registry=" + (b.stderr.strip().splitlines() or ["ok"])[-1]
    detail += " observability=" + (c.stderr.strip().splitlines() or ["ok"])[-1]
    detail += " doctor=" + (d.stderr.strip().splitlines() or ["ok"])[-1]
    detail += " sync=" + (e.stderr.strip().splitlines() or ["ok"])[-1]
    detail += " grok-agent=" + (f.stderr.strip().splitlines() or ["ok"])[-1]
    detail += " grok-sync=" + (g.stderr.strip().splitlines() or ["ok"])[-1]
    detail += " subscriptions=" + (h.stderr.strip().splitlines() or ["ok"])[-1]
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
        c = run([PY, "bin/run-brief.py", "--dry-run", "--class", "repo-code", "--scale", "elevated",
                 "--intake-provider", "codex-sol", "--artifacts", "brief,credentials", "--json"])
        restricted = json.loads(c.stdout)
        parked = (c.returncode == 0 and not restricted["handoff"]["allowed"]
                  and not restricted["handoff"]["requires_user_permission"]
                  and restricted["transition"]["to"] == "parked")
        d = run(
            [PY, "bin/run-brief.py", "--dry-run", "--class", "repo-code",
             "--scale", "routine", "--pixels", "--json", "--no-record-observability"],
            env={"MB_DATA_DIR": tmp},
        )
        pixel_plan = json.loads(d.stdout) if d.returncode == 0 else {}
        input_steps = [p for p in pixel_plan.get("implement", []) if p.get("input_seat")]
        input_park = (
            len(input_steps) == 1
            and input_steps[0].get("available") is False
            and input_steps[0].get("shellable") is False
            and input_steps[0].get("would_run") is None
            and "{sandbox_profile}" not in d.stdout
        )
        ok = dry and closed and side_effect_free and parked and input_park
        return ok, (f"dry-run plan={dry}, fail-closed={closed}, side-effect-free={side_effect_free}, "
                    f"restricted-parks-without-prompt={parked}, input-seat-no-argv={input_park}")


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


def c_observability():
    """Decision telemetry emits the v1 schema without changing routing, parks stay
    parks when the log cannot be written, and analysis refuses to invent tokens."""
    spec = importlib.util.spec_from_file_location("observe_smoke", HERE / "observe.py")
    obs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obs)
    with tempfile.TemporaryDirectory() as tmp:
        env = {"MB_DATA_DIR": tmp}
        routed = json.loads(run(
            [PY, "bin/resolve-route.py", "--class", "internal-notes", "--json",
             "--record", "--run-id", "smoke-obs-1", "--actor-id", "team-a"],
            env=env,
        ).stdout)
        parked = json.loads(run(
            [PY, "bin/resolve-route.py", "--class", "repo-code", "--json",
             "--artifacts", "brief,credentials", "--record",
             "--run-id", "smoke-obs-park", "--actor-id", "team-a"],
            env=env,
        ).stdout)
        planned = json.loads(run(
            [PY, "bin/run-brief.py", "--dry-run", "--class", "repo-code", "--json",
             "--record-observability", "--run-id", "smoke-obs-plan",
             "--actor-id", "team-b"],
            env=env,
        ).stdout)
        events = obs.read(str(Path(tmp) / "orchestration-events.jsonl"))
        report = json.loads(run(
            [PY, "bin/observe.py", "--path", str(Path(tmp) / "orchestration-events.jsonl"),
             "report", "--json"],
            env=env,
        ).stdout)
        cfg = json.loads(run([PY, "bin/observe.py", "validate-config", "--json"], env=env).stdout)
        fixture = json.loads(run(
            [PY, "bin/observe.py", "--path",
             "model-evals/fixtures/observability/v1-correlated-runs.jsonl",
             "validate-events", "--json"],
            env=env,
        ).stdout)
        decision_unchanged = routed.get("routing_satisfied") is True
        park_holds = (not parked.get("routing_satisfied")
                      and parked.get("handoff", {}).get("requires_user_permission") is False
                      and parked.get("handoff", {}).get("action") == "park")
        emitted = (routed.get("observability", {}).get("recorded")
                   and planned.get("observability", {}).get("recorded")
                   and len(events) >= 2)
        analysis_honest = report.get("causal_claim") is False
        # smoke runs do not include provider-reported tokens — must not invent them
        tok = report.get("tokens") or {}
        no_fabricated_tokens = tok.get("measured_runs") == 0 and tok.get("token_per_success") is None
        privacy = all("/Users/" not in json.dumps(e) and "prompt" not in e for e in events)
        ok = (decision_unchanged and park_holds and emitted and analysis_honest
              and no_fabricated_tokens and privacy and cfg.get("ok") and fixture.get("ok"))
        return ok, (f"routed={decision_unchanged} park-no-prompt={park_holds} "
                    f"emitted={len(events)} causal={report.get('causal_claim')} "
                    f"tokens={report.get('tokens', {}).get('token_per_success')} "
                    f"config={cfg.get('ok')} fixture={fixture.get('ok')}")


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
    os.environ["MB_INTEGRATION_FIXTURE"] = str(INTEGRATION_FIXTURE)
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
    # active connectors STILL route (explicit status=active; missing/unknown/primed are inert)
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
    check("genuine park: same-pipe review cannot validate dispatch", c_genuine_park())
    check("last-resort parks without a coding-capable intake provider", c_dispatch_codes())
    check("last-resort names a concrete coding-capable provider", c_last_resort_names_coder)
    check("run-brief dry-run plans + fails closed (shells nothing)", c_run_brief)
    check("observability emit + analysis (privacy, no token fabrication)", c_observability)
    check("run-ledger append→fold round-trip", c_runledger)
    check("drain-plan: metered last + reserve sizing", c_drain_plan)
    check("detect-agents", c_detect_agents)
    check("rotation status (live-ready or explicit graceful degradation)", c_rotation_status)
    check("detect-capability", c_detect_capability)
    check("integration inventory (dynamic fail-closed grants)",
          lambda: (run([PY, "bin/test_integrations.py"]).returncode == 0,
                   "add/remove/disable/recovery/concurrency/session/bypass suite"))
    check("connectors (visual-QA CLI packets and deny gates)", c_connectors)
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
