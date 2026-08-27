#!/usr/bin/env python3
"""smoketest — walk the whole orchestration path and prove it hangs together.

Runs every script the way dispatch/agents actually invoke it, asserts the
expected behavior, and cleans up after itself (temp ledgers/dirs — never touches
config/usage-ledger.json). This is the acceptance gate: a green smoketest means a
fresh clone (or a new user's edited subscriptions.json) is wired correctly.

  bin/smoketest.py            run all checks, human summary
  bin/smoketest.py --strict   also require doctor to be warning-clean
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = sys.executable
RESULTS = []


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, **kw)


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as exc:  # pragma: no cover
        ok, detail = False, f"exception: {exc}"
    RESULTS.append((name, ok, detail))
    mark = "✓" if ok else "✗"
    print(f"  {mark} {name}: {detail}")
    return ok


def c_doctor(strict):
    def fn():
        r = run([PY, "bin/doctor.py"] + (["--strict"] if strict else []))
        # errors always fail; warnings fail only under strict
        return r.returncode == 0, (r.stdout.strip().splitlines() or ["(no output)"])[-1]
    return fn


def c_usage_status():
    r = run([PY, "bin/usage-status.py", "--json"])
    if r.returncode != 0:
        return False, r.stderr.strip()[:120]
    data = json.loads(r.stdout)
    seats = data.get("seats", [])
    fable = [s["seat"] for s in seats if s.get("fable")]
    return len(seats) >= 10 and len(fable) == 3, f"{len(seats)} seats, {len(fable)} Fable-capable"


def c_resolve(klass, scale, risk, expect_depth):
    def fn():
        cmd = [PY, "bin/resolve-route.py", "--class", klass, "--scale", scale, "--json"]
        if risk:
            cmd += ["--risk", risk]
        r = run(cmd)
        if r.returncode != 0:
            return False, r.stderr.strip()[:120]
        d = json.loads(r.stdout)
        got = d["review_depth"]
        return got == expect_depth, f"{klass}/{scale}{'/'+risk if risk else ''} → {got} (want {expect_depth})"
    return fn


def c_fallback_park():
    """With all Fable seats + Sol spent, a cross-family item must PARK (no 2nd family)."""
    def fn():
        with tempfile.TemporaryDirectory() as tmp:
            led = Path(tmp) / "ledger.json"
            led.write_text(json.dumps({
                "claude-max": {"spent_until": "2099-01-01T00:00:00-05:00"},
                "claude-team-a": {"spent_until": "2099-01-01T00:00:00-05:00"},
                "claude-team-b": {"spent_until": "2099-01-01T00:00:00-05:00"},
                "codex-sol": {"pct": 99},
            }))
            r = run([PY, "bin/resolve-route.py", "--class", "money-data", "--scale", "elevated",
                     "--ledger", str(led), "--json"])
            d = json.loads(r.stdout)
            satisfied = d["review"]["satisfied"]
            # single-frontier on a Pro seat must still work
            r2 = run([PY, "bin/resolve-route.py", "--class", "catalog-data", "--scale", "elevated",
                      "--ledger", str(led), "--json"])
            d2 = json.loads(r2.stdout)
            sf_ok = d2["review"]["satisfied"] and d2["review"]["chain"][0]["provider"] == "opus-4.8"
            return (not satisfied) and sf_ok, f"cross-family parks={not satisfied}, single-frontier→opus-4.8={sf_ok}"
    return fn


def c_detect_agents():
    r = run([PY, "bin/detect-agents.py", "--json"])
    if r.returncode != 0:
        return False, r.stderr.strip()[:120]
    d = json.loads(r.stdout)
    return "detected" in d and len(d["detected"]) >= 10, f"{len(d.get('detected', []))} providers probed"


def c_detect_fable():
    r = run([PY, "bin/detect-fable.py", "--json"])
    if r.returncode not in (0, 2):
        return False, r.stderr.strip()[:120]
    d = json.loads(r.stdout)
    return len(d["effective_fable_seats"]) == 3 and not d["declaration_conflict"], \
        f"{len(d['effective_fable_seats'])} effective, conflict={d['declaration_conflict']}"


def c_generate_roles():
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        a = run([PY, "bin/generate-roles.py", "--claude-dir", str(t / "c"),
                 "--grok-dir", str(t / "g"), "--codex-output", str(t / "x.toml")])
        if a.returncode != 0:
            return False, a.stderr.strip()[:160]
        before = {p: p.read_bytes() for p in list((t / "c").iterdir()) + list((t / "g").iterdir()) + [t / "x.toml"]}
        run([PY, "bin/generate-roles.py", "--claude-dir", str(t / "c"),
             "--grok-dir", str(t / "g"), "--codex-output", str(t / "x.toml")])
        after = {p: p.read_bytes() for p in before}
        idem = before == after
        import tomllib
        tomllib.loads((t / "x.toml").read_text())
        return idem, f"idempotent={idem}, toml parses, {len(before)} artifacts"


def c_record_429():
    with tempfile.TemporaryDirectory() as tmp:
        led = Path(tmp) / "ledger.json"
        env = dict(os.environ, MB_USAGE_LEDGER=str(led), MB_429_RESET="2099-01-01T00:00:00Z")
        # a real 429 writes
        run(["bash", "bin/record-429.sh", "grok-heavy", "HTTP 429 rate limit exceeded"], env=env)
        wrote = led.exists() and "grok-heavy" in led.read_text()
        # a timeout writes nothing
        run(["bash", "bin/record-429.sh", "grok-heavy", "connection timed out"], env=env)
        data = json.loads(led.read_text())
        only_429 = list(data.keys()) == ["grok-heavy"]
        return wrote and only_429, f"429 recorded={wrote}, timeout ignored={only_429}"


def c_connectors():
    r = run([PY, "bin/connectors.py", "--render", "visual-qa-allowlist"])
    r2 = run([PY, "bin/connectors.py", "--render", "visual-qa-ticket", "gadget-duke"])
    ok = r.returncode == 0 and "Magnet Baron" in r.stdout and "Gadget Duke" in r.stdout \
        and r2.returncode == 0 and "preview_theme_id" in r2.stdout
    return ok, "allowlist + ticket render from connectors.json"


def c_unit_tests():
    r = run([PY, "bin/test_generate.py"])
    tail = (r.stderr.strip().splitlines() or ["(no output)"])[-1]
    return r.returncode == 0, tail


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="require doctor warning-clean too")
    args = ap.parse_args(argv)

    print("smoketest — walking the orchestration path")
    print("=" * 72)
    check("doctor (config integrity)", c_doctor(args.strict))
    check("usage-status", c_usage_status)
    check("route: internal-notes/routine → none", c_resolve("internal-notes", "routine", "", "none"))
    check("route: catalog-data/elevated → single-frontier", c_resolve("catalog-data", "elevated", "", "single-frontier"))
    check("route: money-data/elevated → cross-family", c_resolve("money-data", "elevated", "", "cross-family"))
    check("route: repo-code + auth risk → cross-family", c_resolve("repo-code", "routine", "auth", "cross-family"))
    check("fallback: spent seats park cross-family, single-frontier survives", c_fallback_park())
    check("detect-agents", c_detect_agents)
    check("detect-fable", c_detect_fable)
    check("generate-roles (idempotent + toml)", c_generate_roles)
    check("record-429 (429 writes, timeout ignored)", c_record_429)
    check("connectors render", c_connectors)
    check("unit tests (test_generate)", c_unit_tests)
    print("=" * 72)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f"{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
