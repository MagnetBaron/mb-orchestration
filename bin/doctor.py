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
            err(f"provider {pid}: selects FORBIDDEN model {p.get('model')!r} (listed in providers.json forbidden_models)")
        if p.get("billing") not in (None, "included", "metered"):
            err(f"provider {pid}: billing must be 'included' or 'metered', got {p.get('billing')!r}")
        sup = p.get("supersedes")
        if sup is not None:
            if sup not in provs:
                err(f"provider {pid}: supersedes unknown provider {sup!r}")
            elif provs[sup].get("enabled", True) and not provs[sup].get("compatibility_fallback"):
                warn(f"provider {pid} supersedes {sup!r}, but {sup} is still enabled — disable/remove the incumbent (clean slot-in) or mark it compatibility_fallback")
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


VALID_CONNECTOR_STATUS = ("active", "ready", "primed")
_SERVER_TRANSPORTS = ("stdio", "http", "sse")
# Keys that would smuggle a credential VALUE into the repo — the sanctioned channel is
# `env_keys` (env-var NAMES the admin sets out of band). Any of these on a server block fails.
_CREDENTIAL_KEYS = {
    "token", "secret", "secrets", "key", "keys", "api_key", "apikey", "password", "passwd",
    "pass", "credential", "credentials", "bearer", "auth", "authorization", "access_token",
    "refresh_token", "client_secret", "private_key", "passphrase",
}


def _check_server_block(name, server):
    """SHAPE-only validation of a bundled server DEFINITION. Reads strings; never runs
    `command`, never opens `url`. Enforces the no-credentials-in-repo rule."""
    if not isinstance(server, dict):
        err(f"connector {name}: server block must be an object")
        return
    for k in server:
        if str(k).lower() in _CREDENTIAL_KEYS:
            err(f"connector {name}: server block key {k!r} looks like an inline credential — "
                "no secrets in-repo; name the env var in 'env_keys' (NAMES only) and set the value out of band")
    transport = server.get("transport")
    if transport not in _SERVER_TRANSPORTS:
        err(f"connector {name}: server.transport {transport!r} not one of {_SERVER_TRANSPORTS}")
    ek = server.get("env_keys", [])
    if not isinstance(ek, list) or any(not isinstance(x, str) or not x for x in ek):
        err(f"connector {name}: server.env_keys must be a list of env-var NAME strings")
    else:
        for x in ek:
            if "=" in x or len(x) > 64:
                err(f"connector {name}: server.env_keys entry {x!r} must be a bare env-var NAME (no value)")
    if transport == "stdio":
        cmd = server.get("command")
        if not isinstance(cmd, str) or not cmd:
            err(f"connector {name}: stdio server needs a non-empty 'command' string")
        args = server.get("args", [])
        if not isinstance(args, list) or any(not isinstance(a, str) for a in args):
            err(f"connector {name}: server.args must be a list of strings")
    elif transport in ("http", "sse"):
        url = server.get("url")
        if not isinstance(url, str) or "://" not in url:
            err(f"connector {name}: {transport} server needs a 'url' string")
        elif "@" in url.split("://", 1)[1].split("/", 1)[0]:
            err(f"connector {name}: server.url must not embed userinfo credentials (user:pass@host)")


def check_connector_lifecycle(conns, providers):
    """Validate the MCP strap-in lifecycle (status enum + optional bundled server block) and
    PROVE inertness: a connector that is not 'active' (i.e. primed/ready) must never be treated
    as live — the router must not grant it to any provider, including seats outside available_on
    and providers that copied the connector name into coarse capabilities. Rejects capability/
    connector-name collisions. This is SHAPE + pure-logic only; it NEVER opens a socket, spawns
    a subprocess, or hits the network (the whole point of priming)."""
    if not conns:
        return
    prov = (providers or {}).get("providers", {})
    try:
        routing = load_module("routing_doc", HERE / "routing.py")
    except Exception as exc:  # pragma: no cover
        routing = None
        err(f"connector lifecycle: cannot import routing for the inertness proof: {exc}")
    known = routing.connector_ids(conns) if routing is not None else set()
    for pid, p in prov.items():
        for cap in (p.get("capabilities") or []) if isinstance(p, dict) else []:
            if cap in known:
                err(
                    f"provider {pid}: capability {cap!r} collides with a connector id/alias — "
                    "connector access is granted only via connectors.json available_on + status=active, "
                    "never as a coarse provider capability"
                )
    for name, m in conns.get("mcp_connectors", {}).items():
        status = m.get("status")
        if status not in VALID_CONNECTOR_STATUS:
            err(
                f"connector {name}: status {status!r} is required (active|ready|primed); "
                "missing/unknown defaults inert, never active"
            )
        server = m.get("server")
        if server is not None:
            _check_server_block(name, server)
            # a repo-carried launch spec is pre-activation scaffolding: it may ride only on a
            # non-active entry, so it can never be mistaken for a live/wired connector.
            if status == "active":
                err(f"connector {name}: carries a bundled 'server' block but status is 'active' — "
                    "a repo-carried server definition must stay primed/ready (inert) until the admin activates it")
        # INERTNESS PROOF (pure function): a non-active connector is granted to NO provider,
        # not only those listed in available_on (coarse-label leaks must not hide).
        if status != "active" and routing is not None:
            alias = m.get("alias")
            for pid in prov:
                caps = routing.capabilities_of(pid, prov.get(pid, {}), conns)
                if name in caps or (alias and alias in caps):
                    err(f"connector {name}: status={status} but the router still grants it to seat "
                        f"{pid!r} — a non-active connector MUST be inert (never routed). "
                        "See bin/routing.connector_is_active.")


def check_skills(skills, providers, conns):
    """skills.json registry hygiene (mirrors check_connectors for MCP): every skill's
    required_capability resolves to a known coarse capability (providers.json `capabilities` /
    `capability_catalog`) or a known connector (connectors.json `mcp_connectors`); hosts are valid;
    and each skill's in-repo SKILL.md resolves through the repo marketplace (host-discoverable).
    The FAIL-CLOSED binding enforcement itself (unregistered skill, write-skill on a read_only role,
    seat missing a required_capability) runs in generate-roles.load via check_roles_and_windows_run."""
    if not skills:
        return
    provs = (providers or {}).get("providers", {})
    coarse = {k for k in (providers or {}).get("capability_catalog", {}) if k != "_note"}
    for p in provs.values():
        coarse.update(p.get("capabilities", []) or [])
    connector_names = set((conns or {}).get("mcp_connectors", {}))
    for m in (conns or {}).get("mcp_connectors", {}).values():
        if isinstance(m, dict) and m.get("alias"):
            connector_names.add(m["alias"])
    coarse -= connector_names
    try:
        gen = load_module("gen_roles_skills", HERE / "generate-roles.py")
    except Exception as exc:
        gen = None
        warn(f"skills.json: cannot load generate-roles for SKILL.md resolution: {exc}")
    for sid, meta in skills.get("skills", {}).items():
        if not isinstance(meta, dict):
            err(f"skill {sid!r}: entry must be an object")
            continue
        if meta.get("kind") not in ("read", "write"):
            err(f"skill {sid!r}: kind must be 'read' or 'write', got {meta.get('kind')!r}")
        cap = meta.get("required_capability")
        if cap is not None and cap not in coarse and cap not in connector_names:
            err(f"skill {sid!r}: required_capability {cap!r} is neither a providers.json capability "
                "nor a connectors.json connector — unresolvable capability gate")
        hosts = meta.get("hosts")
        if not isinstance(hosts, list) or not hosts or any(h not in ("claude", "grok", "codex") for h in hosts):
            err(f"skill {sid!r}: hosts must be a non-empty subset of claude, grok, codex")
        if gen is not None and not gen.skill_md_path(sid).exists():
            err(f"skill {sid!r}: SKILL.md not found at {gen.skill_md_path(sid)} — in-repo plugin skill unresolvable")


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
    dispatchers = [(name, s) for name, s in surfaces.items() if s.get("can_dispatch")]
    if len(dispatchers) != 1:
        names = [n for n, _ in dispatchers]
        err(f"entrypoints: exactly one can_dispatch:true required, found {len(dispatchers)} {names}")
    else:
        name, s = dispatchers[0]
        if s.get("provider") != dp:
            err(
                f"entrypoints: can_dispatch surface {name} provider {s.get('provider')!r} "
                f"!= dispatcher.provider {dp!r}"
            )
        declared = disp.get("level")
        actual = (provs.get(dp) or {}).get("level")
        if declared != actual:
            err(
                f"entrypoints: dispatcher.level {declared!r} != provider {dp} level {actual!r}"
            )
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


def check_seat_exec(seat_exec, provs, provider_ids):
    """seat-exec.json recipes must not drift from the registry: every recipe keys a known
    provider; the never_metered_host marker matches providers.json `billing` (the secrets/PII
    executor guard, as data); and `bin` matches `kind` (CLI seats have a bin, app/api/local
    seats do not). Consumed by bin/run-brief.py."""
    if not seat_exec:
        return
    recipes = seat_exec.get("recipes", {})
    if not recipes:
        err("seat-exec.json: no recipes defined")
        return
    valid_reads = {"brief", "git-diff", "preview-url", "analytics", "none"}
    for pid, r in recipes.items():
        if pid not in provider_ids:
            err(f"seat-exec recipe {pid!r}: not a known provider (config/providers.json)")
            continue
        p = provs.get(pid, {})
        kind, billing = p.get("kind"), p.get("billing", "included")
        nmh = r.get("never_metered_host")
        if not isinstance(nmh, bool):
            err(f"seat-exec recipe {pid!r}: never_metered_host must be a boolean")
        elif billing == "metered" and nmh is not False:
            err(f"seat-exec recipe {pid!r}: provider billing=metered → never_metered_host must be false "
                "(the executor must never shell a metered inference host — secrets/PII ban)")
        elif billing == "included" and nmh is not True:
            err(f"seat-exec recipe {pid!r}: provider billing=included → never_metered_host must be true")
        bin_ = r.get("bin")
        if kind in ("cli", "ide") and not (isinstance(bin_, str) and bin_):
            err(f"seat-exec recipe {pid!r}: provider kind={kind} needs a CLI bin (non-empty string)")
        if kind in ("app", "api", "local") and bin_ is not None:
            err(f"seat-exec recipe {pid!r}: provider kind={kind} has no CLI → bin must be null")
        if r.get("reads") not in valid_reads:
            err(f"seat-exec recipe {pid!r}: reads={r.get('reads')!r} not in {sorted(valid_reads)}")
        if not isinstance(r.get("args_template"), list):
            err(f"seat-exec recipe {pid!r}: args_template must be a list")
        if not isinstance(r.get("worktree"), bool):
            err(f"seat-exec recipe {pid!r}: worktree must be a boolean")


def check_runledger():
    """The stateful spine must import and its pure fold must round-trip deterministically —
    a broken ledger silently loses run-state (fix-loop cap, starvation guard become vibes)."""
    try:
        rl = load_module("runledger_doc", HERE / "runledger.py")
    except Exception as exc:
        err(f"runledger cannot import: {exc}")
        return
    try:
        evs = [
            rl.make_event("lane-doctor", "created", "2026-01-01T00:00:00+00:00"),
            rl.make_event("lane-doctor", "classified", "2026-01-01T00:00:01+00:00",
                          **{"class": "repo-code", "review_depth": "single-frontier"}),
            rl.make_event("lane-doctor", "review-verdict", "2026-01-01T00:00:02+00:00",
                          seat="opus-5", verdict="fix-list"),
            rl.make_event("lane-doctor", "review-verdict", "2026-01-01T00:00:03+00:00",
                          seat="opus-5", verdict="ship"),
        ]
        st = rl.fold(evs)
        ok = (st["status"] == "review-passed" and st["class"] == "repo-code"
              and st["fix_loops"] == 1 and st["event_count"] == 4 and st["terminal"] is False)
        if not ok:
            err(f"runledger fold round-trip wrong: {st}")
    except Exception as exc:
        err(f"runledger fold raised: {exc}")


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


_BIN_REF_RE = re.compile(r"\bbin/([A-Za-z0-9_][A-Za-z0-9_.-]*\.(?:py|sh))\b")


def check_bin_references():
    """Referential integrity for CITED scripts (ERROR, not just a prose warning): every
    bin/<script>.(py|sh) named in a config/*.json (across the active config layer) OR in prose
    (*.md) MUST exist under bin/. prose_hygiene only WARNS on backtick repo paths and never
    scans JSON at all — so a config file citing a renamed/removed script (e.g. the
    detect-fable.py → detect-capability.py rename) passed doctor clean while mis-pointing every
    reader. Fail closed: a dangling bin/ citation is a hard error."""
    sources: list[Path] = []
    seen: set[Path] = set()
    for d in mborch.config_dirs():
        rd = d.resolve()
        if rd in seen or not d.exists():
            continue
        seen.add(rd)
        sources += sorted(d.glob("*.json"))
    sources += sorted(ROOT.glob("*.md")) + sorted((ROOT / ".claude").rglob("*.md"))
    reported: set[tuple[str, str]] = set()
    for src in sources:
        try:
            text = src.read_text()
        except Exception:
            continue
        try:
            rel = src.relative_to(ROOT).as_posix()
        except ValueError:
            rel = str(src)
        for m in _BIN_REF_RE.finditer(text):
            script = m.group(1)
            if (ROOT / "bin" / script).exists():
                continue
            key = (rel, script)
            if key in reported:
                continue
            reported.add(key)
            err(f"{rel}: cites bin/{script} which does not exist under bin/ "
                "(renamed or removed? fix the reference or restore the script)")


def check_forbidden_matcher():
    """Forbidden models are the explicit providers.json map only. Opus 5 must NOT be
    auto-blocked (it is the operational Anthropic gate). is_opus5_zero remains a
    classifier for the 5 GA line vs later minors."""
    if mborch.model_is_forbidden("claude-opus-5", {}):
        err("forbidden-matcher regression: Opus 5 is auto-forbidden; it must route")
    if mborch.model_is_forbidden("opus-5", {}):
        err("forbidden-matcher regression: bare opus-5 is auto-forbidden; it must route")
    if not mborch.is_opus5_zero("claude-opus-5") or not mborch.is_opus5_zero("opus-5"):
        err("classifier regression: Opus 5 GA forms should still match is_opus5_zero")
    if mborch.is_opus5_zero("opus-5-1") or mborch.is_opus5_zero("claude-opus-4-8"):
        err("classifier regression: 5.1+ / 4.8 must not match is_opus5_zero")
    fake = {"do-not-run": {"aliases": ["never-this-model"]}}
    if not mborch.model_is_forbidden("never-this-model", fake):
        err("forbidden-matcher regression: explicit alias was not forbidden")
    if mborch.model_is_forbidden("claude-opus-5", fake):
        err("forbidden-matcher regression: Opus 5 blocked by an unrelated map")


def check_model_registry(providers):
    """The model catalog must parse, stay fresh, and stay bound to providers.json."""
    try:
        mr = load_module("model_registry_doc", HERE / "model-registry.py")
    except Exception as exc:
        err(f"model-registry.py cannot import: {exc}")
        return
    try:
        registry = mr.load()
    except Exception as exc:
        err(f"model-registry.json cannot load: {exc}")
        return
    for e in mr.validate(registry, providers=providers):
        err(e)
    try:
        mr.write_matrix(registry, check=True)
    except Exception as exc:
        err(f"generated/model-matrix.md: {exc}")
    try:
        cases_mod = load_module("model_eval_doc", HERE / "model-eval.py")
        cases = cases_mod.load_cases()
        for e in cases_mod.validate_cases(cases):
            err(e)
    except Exception as exc:
        err(f"model-evals/cases.json: {exc}")


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
    seat_exec = load_json("seat-exec.json", required=False)
    skills = load_json("skills.json", required=False)
    model_reg = load_json("model-registry.json")

    schema_validate({"providers": providers, "subscriptions": subs, "connectors": conns,
                     "entrypoints": entry, "usage_windows": windows, "roles": roles,
                     "review_depth": depth, "monitoring": monitoring, "seat_exec": seat_exec,
                     "skills": skills, "model_registry": model_reg})

    if monitoring is not None:
        rd = monitoring.get("retention_days")
        if not isinstance(rd, int) or rd < 0:
            err(f"monitoring.retention_days must be a non-negative integer, got {rd!r}")

    provs, provider_ids, _ = check_providers(providers)
    fable_from_subs = check_subscriptions(subs, provider_ids)
    check_connectors(conns, provider_ids)
    check_connector_lifecycle(conns, providers)
    check_skills(skills, providers, conns)
    check_entrypoints(entry, provs, provider_ids)
    subs_ids = set((subs or {}).get("subscriptions", {}))
    check_windows(windows, subs_ids, fable_from_subs)
    check_review_depth(depth)
    check_doctrine_has_classes(depth)
    check_roles_and_windows_run(CONFIG / "providers.json", CONFIG / "roles.json")
    check_forbidden_matcher()
    check_model_registry(providers)
    check_seat_exec(seat_exec, provs, provider_ids)
    check_runledger()
    prose_hygiene()
    check_bin_references()

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
