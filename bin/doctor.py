#!/usr/bin/env python3
"""doctor — validate the whole mb-orchestration setup so it stays durable.

Two layers:
  ERRORS (always fail): the machine contract — config parses, schema holds, and
    every cross-reference resolves (providers ↔ subscriptions ↔ connectors ↔
    entrypoints ↔ usage-windows ↔ roles ↔ review-depth). No forbidden model is
    selected. Fable declarations agree across files. This is what lets a new
    user drop in their own subscriptions.json and trust the routing.
  WARNINGS (report; fail only with --strict): prose hygiene — broken internal
    links, references to moved/old paths, and raw live IDs that should live in
    config/connectors.json instead of going stale in prose.

No network calls. `jsonschema` is used when importable; otherwise the built-in
structural checks below are authoritative. Exit 0 = clean; 1 = errors (or
warnings under --strict).
"""
from __future__ import annotations
import argparse, importlib.util, json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mborch  # noqa: E402

ROOT = HERE.parent
CONFIG = ROOT / "config"
LEVELS = ("frontier", "sole", "terra", "luna")

ERRORS: list[str] = []
WARNINGS: list[str] = []
INFO: list[str] = []

# Gitignored runtime files that are legitimately absent in a clean checkout.
ALLOWED_MISSING = {"config/usage-ledger.json", "usage-ledger.json"}


def err(msg):
    ERRORS.append(msg)


def warn(msg):
    WARNINGS.append(msg)


def info(msg):
    INFO.append(msg)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_json(name, required=True):
    path = mborch.find_config(name)
    if not path.exists():
        if required:
            err(f"missing config file: {name} (looked in {[str(d) for d in mborch.config_dirs()]})")
        return None
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        err(f"{name}: JSON parse error: {exc}")
        return None


def schema_validate(datas):
    try:
        import jsonschema  # type: ignore
    except Exception:
        info("jsonschema not installed — relying on built-in structural checks (schema file is the published contract).")
        return
    schema = json.loads(mborch.find_config("orchestration.schema.json").read_text())
    for key, data in datas.items():
        if data is None:
            continue
        sub = dict(schema)
        sub["$ref"] = f"#/$defs/{key}"
        try:
            jsonschema.validate(instance=data, schema=sub)
        except jsonschema.ValidationError as e:  # pragma: no cover
            err(f"schema[{key}]: {e.message} at {list(e.path)}")


def check_providers(providers):
    if not providers:
        return {}, set(), set()
    cl = providers.get("capability_levels", {})
    if tuple(cl) != LEVELS:
        err("providers.json capability_levels must be frontier, sole, terra, luna in order")
    provs = providers.get("providers", {})
    forbidden = set()
    for fid, meta in (providers.get("forbidden_models") or {}).items():
        forbidden.add(fid)
        forbidden.update(meta.get("aliases", []))
    families = set(providers.get("families", {}))
    ids = set(provs)
    review_fns = {}
    for pid, p in provs.items():
        if p.get("level") not in LEVELS:
            err(f"provider {pid}: bad level {p.get('level')!r}")
        if p.get("family") not in families:
            err(f"provider {pid}: family {p.get('family')!r} not declared in families")
        if not p.get("functions"):
            err(f"provider {pid}: empty functions")
        if mborch.model_is_forbidden(p.get("model"), providers.get("forbidden_models")):
            err(f"provider {pid}: selects FORBIDDEN model {p.get('model')!r} (Opus 5.0 is the one hard block; 5.1+ are allowed — pin opus-4.8)")
        if p.get("billing") not in (None, "included", "metered"):
            err(f"provider {pid}: billing must be 'included' or 'metered', got {p.get('billing')!r}")
        sup = p.get("supersedes")
        if sup is not None:
            if sup not in provs:
                err(f"provider {pid}: supersedes unknown provider {sup!r}")
            elif provs[sup].get("enabled", True):
                warn(f"provider {pid} supersedes {sup!r}, but {sup} is still enabled — disable/remove the incumbent (clean slot-in)")
        review_fns[pid] = p.get("functions", [])
    order = providers.get("review_order", [])
    for pid in order:
        if pid not in ids:
            err(f"review_order references unknown provider {pid!r}")
    return provs, ids, forbidden


def check_subscriptions(subs, provider_ids):
    fable_seats = set()
    if not subs:
        return fable_seats
    for sid, s in subs.get("subscriptions", {}).items():
        for pid in s.get("backs_providers", []):
            if pid not in provider_ids:
                err(f"subscription {sid}: backs unknown provider {pid!r}")
        if s.get("grants", {}).get("fable"):
            fable_seats.add(s.get("seat_id") or sid)
    return fable_seats


def check_connectors(conns, provider_ids):
    if not conns:
        return
    for name, m in conns.get("mcp_connectors", {}).items():
        for pid in m.get("available_on", []):
            if pid not in provider_ids:
                err(f"connector {name}: available_on unknown provider {pid!r}")


def check_entrypoints(entry, provs, provider_ids):
    if not entry:
        return
    disp = entry.get("dispatcher", {})
    dp = disp.get("provider")
    if dp not in provider_ids:
        err(f"entrypoints dispatcher.provider {dp!r} is not a known provider")
    elif "dispatch" not in provs.get(dp, {}).get("functions", []):
        err(f"entrypoints dispatcher.provider {dp!r} lacks the 'dispatch' function")
    surfaces = entry.get("entry_surfaces", {})
    if not any(s.get("can_dispatch") for s in surfaces.values()):
        err("entrypoints: no entry surface has can_dispatch:true (nobody can dispatch)")
    if entry.get("rules", {}).get("single_dispatcher") is not True:
        err("entrypoints rules.single_dispatcher must be true")
    for name, s in surfaces.items():
        p = s.get("provider")
        if p is not None and p not in provider_ids:
            err(f"entry surface {name}: provider {p!r} unknown")


def check_windows(windows, subs_ids, fable_from_subs):
    fable_from_windows = set()
    if not windows:
        return
    for seat, w in windows.get("seats", {}).items():
        sub = w.get("subscription")
        if sub is not None and sub not in subs_ids:
            err(f"usage-window seat {seat}: subscription {sub!r} not in subscriptions.json")
        for win in w.get("windows", []):
            if win.get("kind") not in ("weekly", "monthly", "rolling", "none"):
                err(f"usage-window seat {seat}: bad window kind {win.get('kind')!r}")
        drain = w.get("drain", "full")
        if drain not in ("full", "reserve"):
            err(f"usage-window seat {seat}: drain must be 'full' or 'reserve', got {drain!r}")
        billing = w.get("billing", "included")
        if billing not in ("included", "metered"):
            err(f"usage-window seat {seat}: billing must be 'included' or 'metered', got {billing!r}")
        rp = w.get("reserve_pct", w.get("soft_cap_pct"))
        if rp is not None and not (isinstance(rp, (int, float)) and 0 <= rp <= 100):
            err(f"usage-window seat {seat}: reserve_pct must be 0-100 or null, got {rp!r}")
        if w.get("fable"):
            fable_from_windows.add(seat)
    # Fable declarations must agree between subscriptions and windows (drift = latent downgrade bug)
    if fable_from_subs != fable_from_windows:
        err(f"Fable declaration drift: subscriptions say {sorted(fable_from_subs)} but usage-windows say "
            f"{sorted(fable_from_windows)} — reconcile grants.fable and seat.fable")


def check_review_depth(depth):
    if not depth:
        return
    order = depth.get("levels_order", [])
    if order != ["none", "self-check", "single-frontier", "cross-family"]:
        err(f"review-depth levels_order wrong: {order}")
    for cid, spec in depth.get("classes", {}).items():
        for col in ("routine", "elevated", "risk"):
            if spec.get(col) not in order:
                err(f"review-depth class {cid}: {col}={spec.get(col)!r} not a valid level")


def check_roles_and_windows_run(providers_path, roles_path):
    try:
        gen = load_module("gen_roles", HERE / "generate-roles.py")
        gen.load(roles_path, providers_path)
    except Exception as exc:
        err(f"roles registry invalid (generate-roles.load): {exc}")
    try:
        us = load_module("usage_status_doc", HERE / "usage-status.py")
        us.compute()
    except SystemExit as exc:
        err(f"usage-status cannot compute: {exc}")
    except Exception as exc:
        err(f"usage-status cannot compute: {exc}")


def check_doctrine_has_classes(depth):
    if not depth:
        return
    doctrine = ROOT / "DOCTRINE.md"
    if not doctrine.exists():
        warn("DOCTRINE.md missing — cannot confirm review-depth classes are documented")
        return
    text = doctrine.read_text()
    for cid in depth.get("classes", {}):
        if cid not in text:
            warn(f"review-depth class {cid!r} not mentioned in DOCTRINE.md §Review depth (doc/machine drift)")


STALE_PATHS = [
    "roles/generate.py", "roles/roles.json", "roles/record-429.sh", "roles/test_generate.py",
    "roles/README.md", "roles/PROPOSAL.md",
]
RAW_IDS = ["wpxqdpcski", "wpxjicd0hx", "151997710406", "151997775942", "151997743174", "C0BS66SEV0R"]


def prose_hygiene():
    md_files = list(ROOT.glob("*.md")) + list((ROOT / ".claude").rglob("*.md"))
    link_re = re.compile(r"\]\(([\w./-]+\.(?:md|json|py|sh|toml))\)")
    backtick_re = re.compile(r"`((?:bin|config|roles|\.claude|\.cursor)/[\w./-]+|[A-Z][\w-]+\.md)`")
    for md in md_files:
        rel = md.relative_to(ROOT).as_posix()
        text = md.read_text()
        # broken internal links + backtick repo paths
        for m in list(link_re.finditer(text)) + list(backtick_re.finditer(text)):
            target = m.group(1)
            if target.startswith("http"):
                continue
            if target.startswith("./"):
                target = target[2:]
            target = target.rstrip("/") or target
            if target in ALLOWED_MISSING or target.startswith("generated/"):
                continue
            if not (ROOT / target).exists():
                warn(f"{rel}: reference to missing repo path '{m.group(1)}'")
        for sp in STALE_PATHS:
            if sp in text:
                warn(f"{rel}: references removed path '{sp}' (moved under bin/ or config/)")
        for rid in RAW_IDS:
            if rid in text:
                warn(f"{rel}: contains raw live id '{rid}' — should come from config/connectors.json via bin/connectors.py")


def check_forbidden_matcher():
    """Locked test for the ONE hard invariant (bin/mborch.is_opus5_zero): Opus 5.0 —
    and ONLY 5.0 — is refused; Opus 5.1+ and non-Opus-5 models must pass through so
    they can slot in via capability+prowess. Running inside doctor means any regression
    (a matcher that widens to the whole 5-series, or narrows and lets a 5.0 build run)
    fails the gate and can never land silently."""
    must_block = ["opus-5", "claude-opus-5", "claude-opus-5-0", "claude-opus-5.0",
                  "claude-opus-5-20260401", "opus5"]
    must_allow = ["opus-5-1", "claude-opus-5-1", "opus-5.1", "claude-opus-5.1",
                  "claude-opus-5-2", "opus-5-2",
                  "opus-5-10", "claude-opus-5-10",       # minor 10 — must NOT be misread as a 5.0 date
                  "opus-5-1-20260401",                   # minor >=1 before a dated build
                  "opus-4-8", "claude-opus-4-8",
                  "sonnet-5", "fable-5", "claude-haiku-4-5-20260101"]
    for m in must_block:
        if not mborch.is_opus5_zero(m):
            err(f"forbidden-matcher regression: Opus-5.0 form {m!r} is NOT being blocked")
    for m in must_allow:
        if mborch.is_opus5_zero(m):
            err(f"forbidden-matcher regression: {m!r} is WRONGLY blocked (only Opus 5.0 is forbidden; 5.1+ allowed)")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validate the mb-orchestration setup.")
    ap.add_argument("--strict", action="store_true", help="treat warnings as failures")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    providers = load_json("providers.json")
    subs = load_json("subscriptions.json")
    conns = load_json("connectors.json")
    entry = load_json("entrypoints.json")
    windows = load_json("usage-windows.json")
    roles = load_json("roles.json")
    depth = load_json("review-depth.json")
    monitoring = load_json("monitoring.json", required=False)

    schema_validate({"providers": providers, "subscriptions": subs, "connectors": conns,
                     "entrypoints": entry, "usage_windows": windows, "roles": roles,
                     "review_depth": depth, "monitoring": monitoring})

    if monitoring is not None:
        rd = monitoring.get("retention_days")
        if not isinstance(rd, int) or rd < 0:
            err(f"monitoring.retention_days must be a non-negative integer, got {rd!r}")

    provs, provider_ids, _ = check_providers(providers)
    fable_from_subs = check_subscriptions(subs, provider_ids)
    check_connectors(conns, provider_ids)
    check_entrypoints(entry, provs, provider_ids)
    subs_ids = set((subs or {}).get("subscriptions", {}))
    check_windows(windows, subs_ids, fable_from_subs)
    check_review_depth(depth)
    check_doctrine_has_classes(depth)
    check_roles_and_windows_run(CONFIG / "providers.json", CONFIG / "roles.json")
    check_forbidden_matcher()
    prose_hygiene()

    if args.json:
        print(json.dumps({"errors": ERRORS, "warnings": WARNINGS, "info": INFO,
                          "ok": not ERRORS and (not WARNINGS or not args.strict)}, indent=2))
    else:
        print("doctor — mb-orchestration setup validation")
        print("=" * 72)
        if ERRORS:
            print(f"ERRORS ({len(ERRORS)}):")
            for e in ERRORS:
                print(f"  ✗ {e}")
        if WARNINGS:
            print(f"WARNINGS ({len(WARNINGS)}):")
            for w in WARNINGS:
                print(f"  ! {w}")
        if INFO:
            for i in INFO:
                print(f"  · {i}")
        if not ERRORS and not WARNINGS:
            print("  ✓ all checks passed — config integrity + prose hygiene clean")
        print("=" * 72)
        print(f"errors={len(ERRORS)} warnings={len(WARNINGS)} strict={args.strict}")

    if ERRORS or (args.strict and WARNINGS):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
