#!/usr/bin/env python3
"""model-registry — canonical catalog of models, routes, and per-role rankings.

Providers.json is the runtime seat/host registry (billing, detect, capability
level). This file is the model/route catalog: identity, family/lab, public
lifecycle, route state, harness/invocation id, evidence, and per-role quality
vs selection. Rank never grants tools, credentials, write access, publish
authority, or data access.

Only routes in state `live_verified` may resolve for active dispatch. A catalog
entry or announcement is not a usable route. Unknown availability fails closed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mborch  # noqa: E402
import routing  # noqa: E402

SCHEMA_VERSION = 1
ROUTE_STATES = (
    "live_verified",
    "catalog_verified",
    "unwired",
    "auth_blocked",
    "quota_spent",
    "disabled",
)
ACTIVE_RESOLVE_STATES = frozenset({"live_verified"})
LIFECYCLES = ("preview", "stable", "superseded", "restricted", "retired")
ROUTABLE_LIFECYCLES = frozenset({"preview", "stable", "superseded", "restricted"})
EVIDENCE_STRENGTHS = (
    "local_smoke",
    "cli_listing",
    "independent_benchmark",
    "vendor_self_reported",
    "owner_eval",
    "none",
)
# live_verified local-access signal: a direct invocation, or an explicit standing-provider
# operational signal. A listing is not an invocation; both must be labeled, never implied.
LIVE_SIGNALS = ("direct_invocation", "standing_provider")
ATTESTATION_STATES = ("attested", "missing", "not_applicable", "waived")
QUALITY_BASES = (
    "local_same_harness",
    "independent_external_prior",
    "vendor_external_prior",
    "operational_prior",
)
QUALITY_CONFIDENCE = ("high", "medium", "low")
# Source text that cannot satisfy `attested` and cannot launder missing evidence
# into `not_applicable`. Positive `evidence_kind` / `structural_code` are primary.
ATTESTATION_ABSENCE_MARKERS = (
    "no suite",
    "not invented",
    "missing",
    "not available",
    "unavailable",
    "no dedicated",
    "no new ",
    "no independent-anchor",
    "no separate",
    "none invented",
    "absent",
    "without",
    "no evidence",
    "evaluation suite absent",
)
WAIVER_AUTHORITIES = ("existing_operational_state",)
LOCAL_SAME_HARNESS_ROLE = "architecture_spec_critique"
LOCAL_SAME_HARNESS_ROUTES = frozenset({"opus-5-teamclaude", "fable-5-teamclaude"})
# Frozen one-time migration identities. A route id alone is not an identity:
# every field below must still match before a grandfathered waiver is usable.
# Config may document the ids, but it cannot extend or rewrite these tuples.
LEGACY_WAIVER_IDENTITIES = {
    # route: (model, provider, host, harness, invocation_id, family, independence_group)
    "fable-5-teamclaude": (
        "claude-fable-5", "fable-5", "teamclaude", "claude-cli",
        "claude-fable-5", "anthropic", "anthropic",
    ),
    "gpt-5.6-luna-codex": (
        "gpt-5.6-luna", "codex-luna", "codex", "gpt-wrapper",
        "gpt-5.6-luna", "openai", "openai",
    ),
    "gpt-5.6-sol-codex": (
        "gpt-5.6-sol", "codex-sol", "codex", "gpt-wrapper",
        "gpt-5.6-sol", "openai", "openai",
    ),
    "gpt-5.6-terra-codex": (
        "gpt-5.6-terra", "codex-terra", "codex", "gpt-wrapper",
        "gpt-5.6-terra", "openai", "openai",
    ),
    "grok-4.6-build": (
        "grok-4.6", "grok-build", "grok-cli", "grok", "grok-4.6", "xai", "xai",
    ),
    "grok-4.6-cursor": (
        "grok-4.6", "cursor-grok", "cursor", "cursor-agent", "grok-4.6", "xai", "xai",
    ),
    "grok-bot-heat-map": (
        "grok-4.6", "grok-bot-heat-map", "grok-bot", "grok-bot-app",
        "heat-map", "xai", "xai",
    ),
    "grok-bot-visual-qa": (
        "grok-4.6", "grok-bot-review-d", "grok-bot", "grok-bot-app",
        "website-visual-qa", "xai", "xai",
    ),
    "opus-4.8-teamclaude": (
        "claude-opus-4-8", "opus-4.8", "teamclaude", "claude-cli",
        "claude-opus-4-8", "anthropic", "anthropic",
    ),
    "opus-5-teamclaude": (
        "claude-opus-5", "opus-5", "teamclaude", "claude-cli",
        "claude-opus-5", "anthropic", "anthropic",
    ),
}
LEGACY_WAIVER_ROUTES = tuple(sorted(LEGACY_WAIVER_IDENTITIES))
OFFICIAL_ID_KINDS = ("official_vendor_catalog", "official_vendor_release")
ROLE_EVAL_KINDS = ("normalized_receipt",)
INDEPENDENT_EVIDENCE_KINDS = ("independent_benchmark", "independent_source")
COST_CONTEXT_KINDS = (
    "provider_receipt",
    "official_pricing",
    "standing_contract",
    "independent_pricing",
)
OWNER_APPROVAL_KINDS = ("committed_owner_record",)
ATTESTED_EVIDENCE_KINDS = {
    "official_id": OFFICIAL_ID_KINDS,
    "local_access_smoke": LIVE_SIGNALS,
    "role_evals": ROLE_EVAL_KINDS,
    "independent_evidence": INDEPENDENT_EVIDENCE_KINDS,
    "cost_context": COST_CONTEXT_KINDS,
    "owner_approval": OWNER_APPROVAL_KINDS,
}
STRUCTURAL_CODES = (
    "compatibility_fallback_not_ranked",
    "app_only_pixel_walk_not_text_suite",
    "app_only_analytics_input_not_text_suite",
)
# Structural N/A is a code-owned exception for an exact route/model/field, not
# a conclusion a mutable route flag can manufacture.
STRUCTURAL_NA_TRUST_ROOT = {
    ("opus-4.8-teamclaude", "claude-opus-4-8", "role_evals"):
        "compatibility_fallback_not_ranked",
    ("opus-4.8-teamclaude", "claude-opus-4-8", "independent_evidence"):
        "compatibility_fallback_not_ranked",
    ("grok-bot-visual-qa", "grok-4.6", "role_evals"):
        "app_only_pixel_walk_not_text_suite",
    ("grok-bot-heat-map", "grok-4.6", "role_evals"):
        "app_only_analytics_input_not_text_suite",
}
# Official-domain policy is a validator trust root. The JSON catalog mirrors
# this mapping for auditors, but cannot authorize a new suffix itself.
OFFICIAL_DOMAINS_BY_FAMILY = {
    "openai": ("openai.com", "developers.openai.com"),
    "anthropic": ("anthropic.com", "claude.com"),
    "xai": ("x.ai",),
    "google": ("ai.google.dev",),
    "moonshot": ("kimi.ai", "moonshot.ai"),
    "zhipu": ("z.ai",),
    "alibaba": ("alibabagroup.com", "alibabacloud.com"),
    "deepseek": ("deepseek.com",),
    "meta": ("ai.meta.com", "meta.com", "llama.com"),
}
# Operational priors are allowed only for these exact role/route pairs and the
# structured source that binds the live route. Arbitrary prose is not evidence.
OPERATIONAL_PRIOR_SOURCES = {
    ("dispatch", "gpt-5.6-terra-codex"): "config/providers.json",
    ("dispatch", "opus-5-teamclaude"): "config/entrypoints.json",
    ("dispatch", "gpt-5.6-luna-codex"): "config/providers.json",
    ("context_scouting", "gpt-5.6-luna-codex"): "config/providers.json",
    ("context_scouting", "grok-4.6-build"): "config/providers.json",
    ("research_synthesis", "grok-4.6-build"): "config/providers.json",
    ("implementation", "grok-4.6-build"): "config/providers.json",
    ("code_review", "review-e-fireworks"): "config/providers.json",
    ("mcp_volume", "gpt-5.6-terra-codex"): "config/connectors.json",
    ("mcp_judgment", "opus-5-teamclaude"): "config/providers.json",
    ("mcp_judgment", "gpt-5.6-sol-codex"): "config/providers.json",
    ("visual_qa", "grok-bot-visual-qa"): "config/providers.json",
    ("evidence_audit", "opus-5-teamclaude"): "config/providers.json",
    ("evidence_audit", "gpt-5.6-sol-codex"): "config/providers.json",
    ("model_evaluation_admin", "opus-5-teamclaude"): "config/providers.json",
    ("model_evaluation_admin", "gpt-5.6-sol-codex"): "config/providers.json",
}
INDEPENDENT_SOURCE_DOMAINS = (
    "artificialanalysis.ai",
    "openreview.net",
    "huggingface.co",
    "lmsys.org",
    "arena.lmsys.org",
)
_HTTPS_RE = re.compile(r"https://[^\s)>\"]+")
_ABSENCE_WORD_RE = re.compile(
    r"\b(absent|missing|unavailable|without|no evidence|no suite|not available|"
    r"not invented|evaluation suite absent)\b",
    re.IGNORECASE,
)
REQUIRED_CENSUS_LABS = (
    "OpenAI",
    "Anthropic",
    "xAI",
    "Google",
    "Moonshot",
    "Z.AI",
    "Alibaba",
    "DeepSeek",
    "Meta",
)
REQUIRED_RANKING_KINDS = ("quality", "selection")
OPTIONAL_RANKING_KINDS = ("efficiency",)
DATA_BOUNDARIES = ("subscription", "metered_third_party", "local", "unknown")
AUTHORITY_KEYS = frozenset({
    "tools_granted", "credentials", "write_access", "publish_authority",
    "data_access", "can_dispatch", "mcp_granted",
})
REQUIRED_ROLES = (
    "dispatch",
    "context_scouting",
    "research_synthesis",
    "implementation",
    "architecture_spec_critique",
    "code_review",
    "mcp_volume",
    "mcp_judgment",
    "visual_qa",
    "evidence_audit",
    "model_evaluation_admin",
)


class RegistryError(ValueError):
    """Invalid catalog or unsatisfiable resolve request."""


def load(path: Path | None = None) -> dict:
    if path is None:
        return mborch.load_config("model-registry.json")
    try:
        return json.loads(Path(path).read_text())
    except Exception as exc:
        raise RegistryError(f"cannot parse {path}: {exc}") from exc


def _as_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def _is_https_url(value) -> bool:
    return isinstance(value, str) and value.startswith("https://") and len(value) > 8


def _model_is_placeholder(model) -> bool:
    if not isinstance(model, dict):
        return False
    return bool(
        model.get("placeholder")
        or model.get("local_placeholder")
        or model.get("kind") == "local_placeholder"
    )


def _absence_markers_in(text: str) -> list[str]:
    low = (text or "").lower()
    found = [m.strip() for m in ATTESTATION_ABSENCE_MARKERS if m in low]
    for word in _ABSENCE_WORD_RE.findall(low):
        marker = word.lower()
        if marker not in found:
            found.append(marker)
    return found


def _https_urls_in(text: str) -> list[str]:
    return [u.rstrip(".,);") for u in _HTTPS_RE.findall(text or "")]


def _url_host(url: str) -> str:
    if not _is_https_url(url):
        return ""
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return ""
    return host.lower().rstrip(".")


def _host_matches_domain(host: str, domain: str) -> bool:
    host = (host or "").lower().rstrip(".")
    domain = (domain or "").lower().rstrip(".")
    if not host or not domain:
        return False
    return host == domain or host.endswith("." + domain)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def official_domains_for_family(registry: dict, family) -> list[str]:
    """Return the code-owned domain trust root, never a catalog-supplied grant."""
    _ = registry
    return list(OFFICIAL_DOMAINS_BY_FAMILY.get(family, ()))


def _url_allowed_for_family(registry: dict, family, url: str) -> bool:
    host = _url_host(url)
    if not host:
        return False
    return any(_host_matches_domain(host, d) for d in official_domains_for_family(registry, family))


def _url_is_independent(url: str) -> bool:
    host = _url_host(url)
    return any(_host_matches_domain(host, d) for d in INDEPENDENT_SOURCE_DOMAINS)


def _text_mentions_model(text: str, model_id: str, model: dict) -> bool:
    blob = _slug(text)
    if not blob:
        return False
    names = [model_id, model.get("label") or "", *(model.get("official_ids") or [])]
    return any(_slug(name) and _slug(name) in blob for name in names if name)


def _first_pointer(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    urls = _https_urls_in(raw)
    if urls:
        return urls[0]
    return raw.split()[0].strip(".,);")


def _repo_rel_path(token: str) -> Path | None:
    if not token or token.startswith("https://") or token.startswith("/") or token.startswith("file:"):
        return None
    candidate = Path(token)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    path = (mborch.REPO / candidate).resolve()
    try:
        path.relative_to(mborch.REPO.resolve())
    except ValueError:
        return None
    return path


def official_urls_for_model(registry: dict, model_id: str, model: dict | None = None) -> list[str]:
    """Direct official vendor https URLs for a model (model-level + family coverage)."""
    models = registry.get("models") or {}
    model = model if isinstance(model, dict) else (models.get(model_id) or {})
    urls: list[str] = []
    for u in model.get("official_sources") or []:
        if _is_https_url(u):
            urls.append(u)
    fam = model.get("family")
    entry = ((registry.get("official_sources") or {}).get("by_family") or {}).get(fam) or {}
    covers = entry.get("covers_models")
    if isinstance(covers, list) and model_id in covers:
        for u in entry.get("urls") or []:
            if _is_https_url(u):
                urls.append(u)
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def legacy_waiver_route_ids(registry: dict) -> frozenset[str]:
    raw = (registry.get("intake") or {}).get("legacy_waiver_routes") or []
    return frozenset(x for x in raw if isinstance(x, str) and x)


def _eval_case_roles() -> dict[str, str]:
    path = mborch.REPO / "model-evals" / "cases.json"
    if not path.exists():
        return {}
    try:
        blob = json.loads(path.read_text())
    except Exception:
        return {}
    out: dict[str, str] = {}
    for case in blob.get("cases") or []:
        if isinstance(case, dict) and case.get("id") and case.get("role"):
            out[str(case["id"])] = str(case["role"])
    return out


def _jsonl_records(path: Path) -> list[dict]:
    recs: list[dict] = []
    try:
        text = path.read_text()
    except Exception:
        return recs
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if isinstance(rec, dict):
            recs.append(rec)
    return recs


def _receipt_matches_route(path: Path, rid: str, model_id: str, model: dict) -> bool:
    ids = {rid, model_id, *(model.get("official_ids") or [])}
    for rec in _jsonl_records(path):
        if rec.get("route") == rid or rec.get("model") in ids:
            return True
    return False


def _receipt_matches_role(path: Path, rid: str, model_id: str, role: str, case_roles: dict[str, str]) -> bool:
    for rec in _jsonl_records(path):
        if rec.get("route") != rid and rec.get("model") != model_id:
            continue
        rec_role = rec.get("role") or case_roles.get(rec.get("case_id") or "")
        if rec_role == role:
            return True
    return False


def _structural_code_allowed(rid: str, model_id: str, key: str, code: str) -> bool:
    return STRUCTURAL_NA_TRUST_ROOT.get((rid, model_id, key)) == code


def _waiver_forbidden_reason(registry: dict, rid: str, route: dict, model: dict) -> str | None:
    """Legacy waivers require an exact frozen identity, not merely a familiar id."""
    if rid not in legacy_waiver_route_ids(registry) or rid not in LEGACY_WAIVER_IDENTITIES:
        return "route id is not on the committed intake.legacy_waiver_routes manifest"
    family = model.get("family")
    actual = (
        route.get("model"), route.get("provider"), route.get("host"),
        route.get("harness"), route.get("invocation_id"), family,
        independence_group_of(registry, family),
    )
    expected = LEGACY_WAIVER_IDENTITIES[rid]
    if actual != expected:
        return f"route identity {actual!r} does not match frozen migration identity {expected!r}"
    return None


def _attestation_kind_errors(
    registry: dict,
    rid: str,
    route: dict,
    model: dict,
    key: str,
    rec: dict,
) -> list[str]:
    """Positive evidence_kind checks for an attested field."""
    errors: list[str] = []
    allowed = ATTESTED_EVIDENCE_KINDS.get(key)
    kind = rec.get("evidence_kind")
    src = rec.get("source") or ""
    pointer = _first_pointer(src)
    model_id = route.get("model") or ""
    family = model.get("family")
    if not allowed:
        return errors
    if kind not in allowed:
        errors.append(
            f"route {rid}: attestation {key!r} attested needs evidence_kind "
            f"{'|'.join(allowed)}"
        )
        return errors

    if key == "local_access_smoke":
        signal = rec.get("signal")
        if signal not in LIVE_SIGNALS:
            errors.append(
                f"route {rid}: local_access_smoke attestation needs signal "
                "direct_invocation|standing_provider"
            )
        elif kind != signal:
            errors.append(
                f"route {rid}: local_access_smoke evidence_kind {kind!r} must match "
                f"signal {signal!r}"
            )
        live_recs = [
            ev for ev in (route.get("evidence") or [])
            if isinstance(ev, dict) and ev.get("route_state", route.get("route_state"))
            in ACTIVE_RESOLVE_STATES
        ]
        if not any(ev.get("signal") == signal for ev in live_recs):
            errors.append(
                f"route {rid}: local_access_smoke {signal!r} needs matching live route evidence"
            )

    if key == "official_id":
        if not (model.get("official_ids") or []):
            errors.append(
                f"route {rid}: official_id attestation but model has no official_ids"
            )
        urls = _https_urls_in(src)
        official_urls = official_urls_for_model(registry, model_id, model)
        if not urls:
            errors.append(
                f"route {rid}: official_id attestation needs a direct official https "
                "source URL (local JSON paths are not sufficient)"
            )
        else:
            for url in urls:
                if not _url_allowed_for_family(registry, family, url):
                    errors.append(
                        f"route {rid}: official_id URL {url} is not an allowed official "
                        f"domain for family {family!r}"
                    )
            if official_urls and not any(u in src for u in official_urls):
                errors.append(
                    f"route {rid}: official_id attestation needs a direct official https "
                    "source URL (local JSON paths are not sufficient)"
                )

    if key == "role_evals":
        path = _repo_rel_path(pointer)
        if path is None or not str(pointer).startswith("model-evals/") or not path.exists():
            errors.append(
                f"route {rid}: role_evals attested needs a committed model-evals receipt/"
                "suite pointer"
            )
        elif not _receipt_matches_route(path, rid, model_id, model):
            errors.append(
                f"route {rid}: role_evals receipt {pointer} does not match this route/model"
            )

    if key == "independent_evidence":
        urls = _https_urls_in(src)
        if not urls:
            errors.append(
                f"route {rid}: independent_evidence attested needs a direct independent https URL"
            )
        else:
            for url in urls:
                if _url_allowed_for_family(registry, family, url):
                    errors.append(
                        f"route {rid}: independent_evidence URL {url} is a vendor domain, "
                        "not an independent source"
                    )
                elif not _url_is_independent(url):
                    errors.append(
                        f"route {rid}: independent_evidence URL {url} is not a recognized "
                        "independent source domain"
                    )
                elif not _text_mentions_model(url, model_id, model):
                    errors.append(
                        f"route {rid}: independent_evidence URL {url} does not name model "
                        f"{model_id}"
                    )

    if key == "cost_context":
        if kind == "official_pricing":
            urls = _https_urls_in(src)
            if not urls or any(not _url_allowed_for_family(registry, family, u) for u in urls):
                errors.append(
                    f"route {rid}: cost_context official_pricing needs an official vendor "
                    f"pricing/context URL for family {family!r}"
                )
        elif kind == "independent_pricing":
            urls = _https_urls_in(src)
            if not urls or any(not _url_is_independent(u) for u in urls):
                errors.append(
                    f"route {rid}: cost_context independent_pricing needs an independent "
                    "https pricing source"
                )
        elif kind == "standing_contract":
            path = _repo_rel_path(pointer) or _repo_rel_path("config/subscriptions.json")
            if "subscriptions.json" not in src or path is None or not path.exists():
                errors.append(
                    f"route {rid}: cost_context standing_contract needs config/subscriptions.json"
                )
        elif kind == "provider_receipt":
            path = _repo_rel_path(pointer)
            if path is None or not path.exists():
                errors.append(
                    f"route {rid}: cost_context provider_receipt needs a committed receipt "
                    "or provider/config pointer"
                )

    if key == "owner_approval":
        errors.append(
            f"route {rid}: owner_approval committed_owner_record is not accepted until a "
            "code-approved structured owner-record manifest binds route, model, authority, and date; "
            "existing files and provider bindings are not approval receipts"
        )

    repo_path = _repo_rel_path(pointer)
    if pointer.startswith("model-evals/") and (repo_path is None or not repo_path.exists()):
        errors.append(f"route {rid}: attestation {key!r} source {pointer} is missing")
    return errors


def _attestation_record_errors(
    registry: dict,
    rid: str,
    route: dict,
    model: dict,
    key: str,
    rec,
    as_of: date,
    freshness_days: int,
) -> list[str]:
    """Field-specific typed attestation checks. Empty = this field is live-eligible."""
    errors: list[str] = []
    if not isinstance(rec, dict):
        errors.append(f"route {rid}: attestation {key!r} missing or not attested")
        return errors
    state = rec.get("state")
    if state not in ATTESTATION_STATES:
        if rec.get("attested") is True:
            errors.append(
                f"route {rid}: attestation {key!r} uses boolean attested; "
                "typed state attested|missing|not_applicable|waived is required"
            )
        else:
            errors.append(f"route {rid}: attestation {key!r} missing or not attested")
        return errors
    if state == "missing":
        errors.append(
            f"route {rid}: attestation {key!r} is missing; cannot be live_verified"
        )
        return errors

    src = rec.get("source")
    d = _as_date(rec.get("date"))
    rationale = rec.get("rationale") or ""

    if state == "attested":
        if d is None:
            errors.append(f"route {rid}: attestation {key!r} needs a valid date")
        elif d > as_of:
            errors.append(
                f"route {rid}: attestation {key!r} date {d.isoformat()} is in the future"
            )
        elif (as_of - d).days > freshness_days:
            errors.append(f"route {rid}: attestation {key!r} is stale")
        if not src:
            errors.append(f"route {rid}: attestation {key!r} needs an auditable source")
        markers = _absence_markers_in(f"{src} {rationale}")
        if markers:
            errors.append(
                f"route {rid}: attestation {key!r} is attested but source semantics "
                f"indicate absence ({', '.join(markers)})"
            )
        errors.extend(_attestation_kind_errors(registry, rid, route, model, key, rec))
        return errors

    if state == "not_applicable":
        code = rec.get("structural_code")
        if code not in STRUCTURAL_CODES or not _structural_code_allowed(
            rid, str(route.get("model") or ""), key, str(code),
        ):
            errors.append(
                f"route {rid}: attestation {key!r} not_applicable needs a valid "
                "structural_code for this field and route role/lifecycle "
                "(free-form rationale cannot establish N/A)"
            )
        if not isinstance(rationale, str) or not rationale.strip():
            errors.append(
                f"route {rid}: attestation {key!r} not_applicable needs a structural rationale"
            )
        markers = _absence_markers_in(f"{src or ''} {rationale}")
        if markers:
            errors.append(
                f"route {rid}: attestation {key!r} not_applicable cannot use absence language "
                f"({', '.join(markers)}); missing evidence is not N/A"
            )
        if d is None:
            errors.append(f"route {rid}: attestation {key!r} needs a valid date")
        elif d > as_of:
            errors.append(
                f"route {rid}: attestation {key!r} date {d.isoformat()} is in the future"
            )
        return errors

    # waived
    forbidden = _waiver_forbidden_reason(registry, rid, route, model)
    if forbidden:
        errors.append(f"route {rid}: attestation {key!r} waiver forbidden ({forbidden})")
    if not isinstance(rationale, str) or not rationale.strip():
        errors.append(f"route {rid}: attestation {key!r} waived needs an honest rationale")
    if rec.get("authority") not in WAIVER_AUTHORITIES:
        errors.append(
            f"route {rid}: attestation {key!r} waived needs authority "
            "existing_operational_state (do not claim owner approval without a committed source)"
        )
    if not src:
        errors.append(f"route {rid}: attestation {key!r} waived needs a source")
    if d is None:
        errors.append(f"route {rid}: attestation {key!r} needs a valid date")
    elif d > as_of:
        errors.append(
            f"route {rid}: attestation {key!r} date {d.isoformat()} is in the future"
        )
    exp = _as_date(rec.get("expires"))
    if exp is None:
        errors.append(f"route {rid}: attestation {key!r} waived needs a short expiry date")
    else:
        if as_of > exp:
            errors.append(
                f"route {rid}: attestation {key!r} waiver expired {exp.isoformat()}"
            )
        if d and (exp - d).days > freshness_days:
            errors.append(
                f"route {rid}: attestation {key!r} waiver expiry {exp.isoformat()} "
                f"exceeds freshness_days={freshness_days}"
            )
        if d and exp < d:
            errors.append(
                f"route {rid}: attestation {key!r} waiver expiry is before the waiver date"
            )
    return errors


def _sorted_items(mapping: dict) -> list[tuple[str, dict]]:
    return sorted((mapping or {}).items(), key=lambda kv: kv[0])


def independence_group_of(registry: dict, family) -> str:
    """Configured independence group, never a free-form family string alone.

    Missing, unknown, or empty groups return empty string so they cannot count
    toward family diversity.
    """
    meta = (registry.get("families") or {}).get(family)
    if not isinstance(meta, dict):
        return ""
    group = meta.get("independence_group")
    if isinstance(group, str) and group.strip():
        return group
    return ""


def physical_invocation(route_or_row: dict) -> tuple:
    return (
        route_or_row.get("host"),
        route_or_row.get("harness"),
        route_or_row.get("invocation_id"),
    )


def _freshness_days(registry: dict) -> int:
    days = registry.get("freshness_days", 90)
    return days if isinstance(days, int) and days >= 1 else 90


def _dated_evidence(records) -> tuple[list[tuple[date, dict]], list[str]]:
    errors: list[str] = []
    dated: list[tuple[date, dict]] = []
    if not isinstance(records, list):
        return dated, ["evidence must be a list"]
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            errors.append(f"evidence[{i}] must be an object")
            continue
        d = _as_date(rec.get("date"))
        if d is None:
            errors.append(f"evidence[{i}] missing date")
            continue
        dated.append((d, rec))
    dated.sort(key=lambda x: x[0])
    return dated, errors


def _official_id_families(models: dict) -> dict[str, set]:
    """official_id → set of families that claim it. Used by route-local identity checks."""
    out: dict[str, set] = {}
    for model in (models or {}).values():
        if not isinstance(model, dict):
            continue
        fam = model.get("family")
        ids = model.get("official_ids")
        if not isinstance(ids, list):
            continue
        for oid in ids:
            if isinstance(oid, str) and oid:
                out.setdefault(oid, set()).add(fam)
    return out


def _family_declaration_errors(registry: dict, rid: str, route: dict, mid, model: dict) -> list[str]:
    """Family must be declared, grouped, and agree with the route. Used by the live predicate."""
    errors: list[str] = []
    families = registry.get("families") if isinstance(registry.get("families"), dict) else {}
    mf = model.get("family") if isinstance(model, dict) else None
    if not mf:
        errors.append(f"route {rid}: model {mid!r} has no family")
        return errors
    fam_meta = families.get(mf)
    if not isinstance(fam_meta, dict):
        errors.append(f"route {rid}: family {mf!r} is not declared")
        return errors
    group = fam_meta.get("independence_group")
    if not isinstance(group, str) or not group.strip():
        errors.append(f"route {rid}: family {mf!r} has no independence_group")
    route_fam = route.get("family")
    if route_fam not in (None, "") and route_fam != mf:
        errors.append(
            f"route {rid}: family {route_fam!r} does not match model {mid} family {mf!r}"
        )
    return errors


def _route_local_errors(registry: dict, rid: str, route: dict) -> list[str]:
    """Route-local identity/family/invocation/shape invariants.

    Shared by `validate` and `route_is_live` so public `resolve()` cannot return a
    route that CLI validation would reject for these reasons. Undeclared family
    or independence group is not live and cannot count toward family diversity.
    """
    errors: list[str] = []
    models = registry.get("models") or {}
    routes = registry.get("routes") or {}
    mid = route.get("model")
    if mid not in models:
        errors.append(f"route {rid}: model {mid!r} is not in models")
        model: dict = {}
    else:
        model = models[mid] if isinstance(models.get(mid), dict) else {}
        errors.extend(_family_declaration_errors(registry, rid, route, mid, model))
    if not route.get("host") or not route.get("harness") or not route.get("invocation_id"):
        errors.append(f"route {rid}: host, harness, and invocation_id are required")
    if not isinstance(route.get("capabilities"), list):
        errors.append(f"route {rid}: capabilities must be a list")
    if not isinstance(route.get("tools"), list) and route.get("tools") is not None:
        errors.append(f"route {rid}: tools must be a list")
    if AUTHORITY_KEYS.intersection(route):
        errors.append(f"route {rid}: must not grant {sorted(AUTHORITY_KEYS.intersection(route))}")
    inv = route.get("invocation_id")
    mf = model.get("family")
    official_id_families = _official_id_families(models)
    if inv in official_id_families and mf not in official_id_families[inv]:
        errors.append(
            f"route {rid}: invocation_id {inv!r} is an official id of family "
            f"{sorted(official_id_families[inv])}, not {mf!r}"
        )
    alias_of = route.get("invocation_alias_of")
    if alias_of is not None and alias_of not in routes:
        errors.append(f"route {rid}: invocation_alias_of {alias_of!r} is not a cataloged route")
    return errors


def route_is_live(registry: dict, route_id, as_of: date | None = None) -> bool:
    """Shared live-route predicate: bound catalog route is live_verified, current, and valid.

    Unknown, missing, catalog-only, unwired, auth-blocked, disabled, incubation, stale,
    future, unattested, undeclared family/independence group, or route-local
    identity/family/invocation contradiction fails closed. Used by review, implement,
    MCP, last-resort, and public `resolve()` — there is no Review E (or any provider)
    exception.
    """
    if not isinstance(registry, dict) or not route_id:
        return False
    route = (registry.get("routes") or {}).get(route_id)
    if not isinstance(route, dict):
        return False
    rid = str(route_id)
    if route.get("invocation_alias_of"):
        return False
    if _route_local_errors(registry, rid, route):
        return False
    return not _live_route_errors(registry, rid, route, as_of or date.today())


def provider_route_is_live(registry: dict, provider: dict | None, as_of: date | None = None) -> bool:
    """True iff an enabled provider's bound catalog route passes route_is_live."""
    if not isinstance(provider, dict) or provider.get("enabled", True) is False:
        return False
    return route_is_live(registry, provider.get("route"), as_of=as_of)


def _live_route_errors(registry: dict, rid: str, route: dict, as_of: date) -> list[str]:
    """Errors that keep a route out of any live chain. Empty = live-eligible."""
    errors: list[str] = []
    state = route.get("route_state")
    if state not in ACTIVE_RESOLVE_STATES:
        errors.append(f"route {rid}: route_state {state!r} is not live_verified")
        return errors
    if route.get("incubation"):
        errors.append(f"route {rid}: incubation routes cannot be live_verified")
    models = registry.get("models") or {}
    model = models.get(route.get("model")) or {}
    if _model_is_placeholder(model):
        errors.append(
            f"route {rid}: local placeholder {route.get('model')!r} cannot be live_verified "
            "until a named candidate model plus an official source replaces it"
        )
    life = route.get("lifecycle_override") or model.get("lifecycle")
    if life not in ROUTABLE_LIFECYCLES:
        errors.append(f"route {rid}: lifecycle {life!r} cannot be live_verified")
    if model.get("lifecycle") == "retired":
        errors.append(f"route {rid}: retired model {route.get('model')} cannot be live_verified")
    if route.get("host") in (None, "", "none", "unknown"):
        errors.append(f"route {rid}: host {route.get('host')!r} cannot be live_verified")
    freshness_days = _freshness_days(registry)
    evidence_date = _as_date(route.get("evidence_date"))
    if evidence_date is None:
        errors.append(f"route {rid}: evidence_date is required (YYYY-MM-DD)")
    elif evidence_date > as_of:
        errors.append(
            f"route {rid}: evidence_date {evidence_date.isoformat()} is in the future "
            f"(after {as_of.isoformat()})"
        )
    elif (as_of - evidence_date).days > freshness_days:
        errors.append(
            f"route {rid}: live_verified evidence_date {evidence_date.isoformat()} is stale "
            f"(>{freshness_days} days before {as_of.isoformat()})"
        )
    records = route.get("evidence")
    dated, ev_errors = _dated_evidence(records)
    for e in ev_errors:
        errors.append(f"route {rid}: {e}")
    if not dated:
        errors.append(f"route {rid}: live_verified requires non-empty dated evidence")
    else:
        for d, rec in dated:
            if d > as_of:
                errors.append(
                    f"route {rid}: evidence dated {d.isoformat()} is in the future "
                    f"(after {as_of.isoformat()})"
                )
        last_state = None
        last_date = None
        for d, rec in dated:
            st = rec.get("route_state", state)
            if last_state is not None and st != last_state and d == last_date:
                errors.append(
                    f"route {rid}: contradictory evidence on {d.isoformat()} "
                    f"({last_state!r} vs {st!r})"
                )
            last_state, last_date = st, d
        latest_state = dated[-1][1].get("route_state", state)
        if latest_state not in ACTIVE_RESOLVE_STATES:
            errors.append(
                f"route {rid}: route_state {state!r} contradicts latest evidence "
                f"{latest_state!r} dated {dated[-1][0].isoformat()}"
            )
        live_recs = [rec for d, rec in dated if rec.get("route_state", state) in ACTIVE_RESOLVE_STATES]
        if not any(rec.get("signal") in LIVE_SIGNALS for rec in live_recs):
            errors.append(
                f"route {rid}: live_verified evidence needs signal "
                f"direct_invocation|standing_provider (got "
                f"{sorted({rec.get('signal') for rec in live_recs})})"
            )
    required = list((registry.get("intake") or {}).get("promote_requires") or [])
    atts = route.get("attestations")
    if not required:
        errors.append("model-registry: intake.promote_requires is required (two-phase new-model intake)")
    elif not isinstance(atts, dict) or not atts:
        errors.append(
            f"route {rid}: live_verified requires attestations covering intake.promote_requires"
        )
    else:
        for key in required:
            errors.extend(
                _attestation_record_errors(
                    registry, rid, route, model, key, atts.get(key), as_of, freshness_days,
                )
            )
    return errors


def mcp_bulk_layer_flags(provider, registry) -> tuple[bool, bool, bool]:
    """Whether mcp_bulk is declared on functions, provider capabilities, and bound-route capabilities."""
    if not isinstance(provider, dict) or not isinstance(registry, dict):
        return False, False, False
    fn = "mcp_bulk" in (provider.get("functions") or [])
    cap = "mcp_bulk" in (provider.get("capabilities") or [])
    route = (registry.get("routes") or {}).get(provider.get("route") or "") or {}
    route_cap = isinstance(route, dict) and "mcp_bulk" in (route.get("capabilities") or [])
    return fn, cap, route_cap


def _mcp_volume_assigned(pid, connectors) -> bool:
    """True if pid is the MCP volume seat assigned on an active connector (or unknown map)."""
    if pid != routing.MCP_VOLUME_PROVIDER:
        return False
    if connectors is None:
        return True  # fail closed when the connector map is unknown
    return any(
        routing.connector_is_active(meta) and pid in (meta.get("available_on") or [])
        for meta in (connectors.get("mcp_connectors") or {}).values()
        if isinstance(meta, dict)
    )


def validate(registry: dict, as_of: date | None = None, providers: dict | None = None,
             connectors: dict | None = None) -> list[str]:
    """Return ERROR strings. Empty list = valid. Stale or contradictory evidence fails.

    Freshness and future-date checks use the actual current date unless `as_of` is
    supplied (CLI `--as-of` / tests). `registry.as_of` is a catalog label, not the clock.
    """
    errors: list[str] = []
    if not isinstance(registry, dict):
        return ["model-registry: root must be an object"]
    if registry.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"model-registry: schema_version must be {SCHEMA_VERSION}")
    as_of = as_of or date.today()
    freshness_days = registry.get("freshness_days", 90)
    if not isinstance(freshness_days, int) or freshness_days < 1:
        errors.append("model-registry: freshness_days must be a positive integer")
        freshness_days = 90

    families = registry.get("families")
    if not isinstance(families, dict) or not families:
        errors.append("model-registry: families must be a non-empty object")
        families = {}
    models = registry.get("models")
    if not isinstance(models, dict) or not models:
        errors.append("model-registry: models must be a non-empty object")
        models = {}
    routes = registry.get("routes")
    if not isinstance(routes, dict) or not routes:
        errors.append("model-registry: routes must be a non-empty object")
        routes = {}
    roles = registry.get("roles")
    if not isinstance(roles, dict):
        errors.append("model-registry: roles must be an object")
        roles = {}
    rankings = registry.get("rankings")
    if not isinstance(rankings, dict):
        errors.append("model-registry: rankings must be an object")
        rankings = {}

    for rid in REQUIRED_ROLES:
        if rid not in roles:
            errors.append(f"model-registry: missing required ranking role {rid!r}")
        if rid not in rankings:
            errors.append(f"model-registry: missing rankings for role {rid!r}")

    for fid, fam in families.items():
        if not isinstance(fam, dict):
            errors.append(f"family {fid}: must be an object")
            continue
        group = fam.get("independence_group")
        if not isinstance(group, str) or not group:
            errors.append(f"family {fid}: independence_group is required")

    for mid, model in models.items():
        if not isinstance(model, dict):
            errors.append(f"model {mid}: must be an object")
            continue
        if model.get("family") not in families:
            errors.append(f"model {mid}: family {model.get('family')!r} is not declared")
        if model.get("lifecycle") not in LIFECYCLES:
            errors.append(f"model {mid}: lifecycle {model.get('lifecycle')!r} not in {LIFECYCLES}")
        ids = model.get("official_ids")
        if not isinstance(ids, list) or not ids or any(not isinstance(x, str) or not x for x in ids):
            errors.append(f"model {mid}: official_ids must be a non-empty list of strings")
        if AUTHORITY_KEYS.intersection(model):
            errors.append(f"model {mid}: rank/catalog must not grant {sorted(AUTHORITY_KEYS.intersection(model))}")
        placeholder = _model_is_placeholder(model)
        urls = official_urls_for_model(registry, mid, model)
        if placeholder:
            if urls:
                errors.append(
                    f"model {mid}: local placeholder must not carry official vendor sources "
                    "until a named candidate replaces it"
                )
        else:
            if not urls:
                errors.append(
                    f"model {mid}: needs at least one direct official https source "
                    "(local JSON paths are not sufficient)"
                )
            for url in urls:
                if not _url_allowed_for_family(registry, model.get("family"), url):
                    errors.append(
                        f"model {mid}: official URL {url} is not an allowed official domain "
                        f"for family {model.get('family')!r}"
                    )

    seen_invocations: dict[tuple, list[str]] = {}
    for rid, route in routes.items():
        if not isinstance(route, dict):
            errors.append(f"route {rid}: must be an object")
            continue
        state = route.get("route_state")
        if state not in ROUTE_STATES:
            errors.append(f"route {rid}: route_state {state!r} not in {ROUTE_STATES}")
        if route.get("lifecycle_override") not in (None, *LIFECYCLES):
            errors.append(f"route {rid}: lifecycle_override {route.get('lifecycle_override')!r} invalid")
        evidence_date = _as_date(route.get("evidence_date"))
        if evidence_date is None:
            errors.append(f"route {rid}: evidence_date is required (YYYY-MM-DD)")
        elif evidence_date > as_of:
            errors.append(
                f"route {rid}: evidence_date {evidence_date.isoformat()} is in the future "
                f"(after {as_of.isoformat()})"
            )
        strength = route.get("evidence_strength")
        if strength not in EVIDENCE_STRENGTHS:
            errors.append(f"route {rid}: evidence_strength {strength!r} not in {EVIDENCE_STRENGTHS}")
        if route.get("data_boundary") not in DATA_BOUNDARIES:
            errors.append(f"route {rid}: data_boundary {route.get('data_boundary')!r} not in {DATA_BOUNDARIES}")
        errors.extend(_route_local_errors(registry, rid, route))
        model = models.get(route.get("model")) or {}
        if _model_is_placeholder(model) and state == "catalog_verified":
            errors.append(
                f"route {rid}: local placeholder {route.get('model')!r} cannot be promoted "
                "until a named candidate model plus an official source replaces it"
            )
        if state in ACTIVE_RESOLVE_STATES:
            errors.extend(_live_route_errors(registry, rid, route, as_of))
        else:
            dated, ev_errors = _dated_evidence(route.get("evidence") or [])
            for e in ev_errors:
                errors.append(f"route {rid}: {e}")
            last_state = None
            last_date = None
            for d, rec in dated:
                if d > as_of:
                    errors.append(
                        f"route {rid}: evidence dated {d.isoformat()} is in the future "
                        f"(after {as_of.isoformat()})"
                    )
                st = rec.get("route_state", state)
                if last_state is not None and st != last_state and d == last_date:
                    errors.append(
                        f"route {rid}: contradictory evidence on {d.isoformat()} "
                        f"({last_state!r} vs {st!r})"
                    )
                last_state, last_date = st, d
            if dated:
                latest_state = dated[-1][1].get("route_state", state)
                if latest_state != state:
                    errors.append(
                        f"route {rid}: route_state {state!r} contradicts latest evidence "
                        f"{latest_state!r} dated {dated[-1][0].isoformat()}"
                    )
        key = physical_invocation(route)
        seen_invocations.setdefault(key, []).append(rid)

    for key, rids in seen_invocations.items():
        if any(part in (None, "") for part in key):
            continue
        if len(rids) <= 1:
            continue
        canonical = [rid for rid in rids if not (routes.get(rid) or {}).get("invocation_alias_of")]
        aliases = [rid for rid in rids if (routes.get(rid) or {}).get("invocation_alias_of")]
        if len(canonical) != 1:
            errors.append(
                f"duplicate invocation {key[0]}/{key[1]}/{key[2]} on routes {rids} — "
                "physical (host, harness, invocation_id) identities must be unique unless "
                "exactly one canonical route is aliased via invocation_alias_of"
            )
            continue
        can = canonical[0]
        can_fam = (models.get((routes.get(can) or {}).get("model")) or {}).get("family")
        can_group = independence_group_of(registry, can_fam)
        for rid in aliases:
            alias_of = (routes.get(rid) or {}).get("invocation_alias_of")
            if alias_of != can:
                errors.append(
                    f"route {rid}: invocation_alias_of {alias_of!r} must point at canonical {can}"
                )
            alias_fam = (models.get((routes.get(rid) or {}).get("model")) or {}).get("family")
            if independence_group_of(registry, alias_fam) != can_group:
                errors.append(
                    f"route {rid}: alias cannot change independence group of invocation "
                    f"{key[0]}/{key[1]}/{key[2]} ({can_group!r} vs "
                    f"{independence_group_of(registry, alias_fam)!r})"
                )
            if (routes.get(rid) or {}).get("route_state") in ACTIVE_RESOLVE_STATES:
                errors.append(
                    f"route {rid}: invocation_alias_of cannot be live_verified "
                    "(aliases document a physical identity; they cannot count twice)"
                )

    for rid, rnk in rankings.items():
        if rid not in roles:
            errors.append(f"rankings {rid}: role is not declared in roles")
        if not isinstance(rnk, dict):
            errors.append(f"rankings {rid}: must be an object")
            continue
        if AUTHORITY_KEYS.intersection(rnk):
            errors.append(f"rankings {rid}: must not grant {sorted(AUTHORITY_KEYS.intersection(rnk))}")
        for kind in REQUIRED_RANKING_KINDS + OPTIONAL_RANKING_KINDS:
            rows = rnk.get(kind)
            if kind in OPTIONAL_RANKING_KINDS and not rows:
                continue
            if not isinstance(rows, list) or not rows:
                errors.append(f"rankings.{rid}.{kind} must be a non-empty list")
                continue
            ranks = []
            for i, row in enumerate(rows):
                if not isinstance(row, dict) or row.get("route") not in routes:
                    errors.append(f"rankings.{rid}.{kind}[{i}]: route must name a cataloged route")
                    continue
                n = row.get("rank") if kind != "selection" else row.get("priority")
                if not isinstance(n, int) or n < 1:
                    errors.append(f"rankings.{rid}.{kind}[{i}]: rank/priority must be a positive integer")
                else:
                    ranks.append(n)
                if row.get("confidence") not in (None, *QUALITY_CONFIDENCE):
                    errors.append(f"rankings.{rid}.{kind}[{i}]: confidence must be high|medium|low")
                if kind == "quality":
                    errors.extend(_quality_row_errors(registry, rid, i, row, routes, models))
            if len(ranks) != len(set(ranks)):
                errors.append(f"rankings.{rid}.{kind}: rank/priority values must be unique")

    if providers:
        provs = providers.get("providers") or {}
        for pid, p in provs.items():
            if not isinstance(p, dict) or p.get("enabled", True) is False:
                continue
            fn, cap, route_cap = mcp_bulk_layer_flags(p, registry)
            assigned = _mcp_volume_assigned(pid, connectors)
            if (assigned or fn or cap or route_cap) and not (fn and cap and route_cap):
                errors.append(
                    f"provider {pid}: mcp_bulk declarations are inconsistent "
                    f"(functions={fn}, capabilities={cap}, bound-route={route_cap}); "
                    "enabled MCP assignment requires mcp_bulk on provider functions, "
                    "provider capabilities, and bound-route capabilities together"
                )
            route_id = p.get("route")
            if p.get("wired") is True and route_id:
                bound = routes.get(route_id) or {}
                bound_model = models.get(bound.get("model")) or {}
                if _model_is_placeholder(bound_model):
                    errors.append(
                        f"provider {pid}: placeholder model {bound.get('model')!r} cannot be "
                        "wired until a named candidate plus an official source replaces it"
                    )
            if not route_id:
                continue
            if route_id not in routes:
                errors.append(f"provider {pid}: route {route_id!r} is not in model-registry.json")
                continue
            route = routes[route_id]
            if route.get("provider") not in (None, pid):
                errors.append(
                    f"provider {pid}: bound route {route_id} names provider {route.get('provider')!r}"
                )
            model = models.get(route.get("model"), {})
            inv = p.get("model")
            official = set(model.get("official_ids") or [])
            if inv and inv not in official and inv != route.get("invocation_id"):
                errors.append(
                    f"provider {pid}: model {inv!r} is not an official id of catalog model "
                    f"{route.get('model')!r} and does not match route invocation_id"
                )
            pf = p.get("family")
            mf = model.get("family")
            harness_families = {"cursor-pool"}
            if pf and mf and pf != mf and pf not in harness_families:
                errors.append(
                    f"provider {pid}: family {pf!r} != catalog family {mf!r}"
                )
        order = providers.get("review_order") or []
        for pid in order:
            p = provs.get(pid) or {}
            route_id = p.get("route")
            if not route_id:
                continue
            route = routes.get(route_id)
            if route and route.get("route_state") not in ACTIVE_RESOLVE_STATES | {"unwired", "quota_spent"}:
                errors.append(
                    f"review_order provider {pid}: bound route {route_id} is "
                    f"{route.get('route_state')!r} (auth_blocked/disabled cannot sit in the gate order)"
                )

    intake = registry.get("intake") or {}
    if not isinstance(intake, dict) or not intake.get("promote_requires"):
        errors.append("model-registry: intake.promote_requires is required (two-phase new-model intake)")
    listed = [x for x in (intake.get("legacy_waiver_routes") or []) if isinstance(x, str)]
    if sorted(listed) != sorted(LEGACY_WAIVER_ROUTES):
        errors.append(
            "model-registry: intake.legacy_waiver_routes must equal the frozen migration "
            "allowlist (exact route ids only; new/candidate/unwired routes cannot be added)"
        )
    elif len(listed) != len(set(listed)):
        errors.append("model-registry: intake.legacy_waiver_routes must not contain duplicates")

    census = registry.get("census") or {}
    if census:
        if not census.get("as_of") or not census.get("scope"):
            errors.append("model-registry: census.as_of and census.scope are required when census is present")
        labs = census.get("labs_in_scope") or []
        if not isinstance(labs, list):
            errors.append("census: labs_in_scope must be a list")
            labs = []
        for lab in REQUIRED_CENSUS_LABS:
            if lab not in labs:
                errors.append(f"census: labs_in_scope missing {lab!r}")
        for lab in labs:
            low = str(lab).lower()
            if "review e" in low or "open-weight" in low:
                errors.append(
                    "census: Review E / open-weight is a local placeholder slot, "
                    "not a frontier lab in scope"
                )
        for mid in census.get("required_model_ids") or []:
            if mid not in models:
                errors.append(f"census: required model {mid!r} is missing")
                continue
            if _model_is_placeholder(models.get(mid) or {}):
                errors.append(f"census: placeholder {mid!r} cannot be a required census model")
            if not any(r.get("model") == mid for r in routes.values()):
                errors.append(f"census: required model {mid!r} has no route")
        for mid in census.get("ambiguous_ids_forbidden") or []:
            if mid in models:
                errors.append(f"census: ambiguous model id {mid!r} is forbidden")
        for mid in census.get("placeholder_model_ids") or []:
            if mid not in models or not _model_is_placeholder(models.get(mid) or {}):
                errors.append(f"census: placeholder_model_ids {mid!r} must name a placeholder model")

    errors.extend(_official_source_coverage_errors(registry, models))

    return errors


def _quality_row_errors(registry: dict, role: str, index: int, row: dict, routes: dict, models: dict) -> list[str]:
    """Runtime ranking-basis invariant: confidence and evidence pointer, not snapshot-only."""
    errors: list[str] = []
    loc = f"rankings.{role}.quality[{index}]"
    basis = row.get("basis")
    if basis not in QUALITY_BASES:
        errors.append(
            f"{loc}: basis must be "
            "local_same_harness|independent_external_prior|"
            "vendor_external_prior|operational_prior"
        )
        return errors
    route_id = row.get("route")
    route = routes.get(route_id) if isinstance(routes.get(route_id), dict) else {}
    model_id = route.get("model") or ""
    model = models.get(model_id) if isinstance(models.get(model_id), dict) else {}
    family = model.get("family")
    confidence = row.get("confidence")
    if confidence == "high" and basis != "local_same_harness":
        errors.append(
            f"{loc}: confidence high is only allowed for basis local_same_harness "
            f"with a committed same-role receipt (got {basis})"
        )
    source = row.get("source") or ""
    pointer = _first_pointer(source)
    if not source or not pointer:
        if basis == "local_same_harness":
            errors.append(
                f"{loc}: local_same_harness needs a committed model-evals receipt pointer"
            )
        else:
            errors.append(
                f"{loc}: quality row needs a basis-appropriate evidence/source pointer "
                f"for {basis}"
            )
        return errors

    if basis == "local_same_harness":
        if role != LOCAL_SAME_HARNESS_ROLE or route_id not in LOCAL_SAME_HARNESS_ROUTES:
            errors.append(
                f"{loc}: local_same_harness is only the "
                "architecture_spec_critique Opus 5 vs Fable 5 receipt"
            )
        path = _repo_rel_path(pointer)
        if path is None or not str(pointer).startswith("model-evals/") or not path.exists():
            errors.append(
                f"{loc}: local_same_harness needs a committed model-evals receipt pointer"
            )
        else:
            case_roles = _eval_case_roles()
            if not _receipt_matches_route(path, route_id, model_id, model):
                errors.append(f"{loc}: receipt {pointer} does not match route/model {route_id}")
            elif not _receipt_matches_role(path, route_id, model_id, role, case_roles):
                errors.append(f"{loc}: receipt {pointer} does not match role {role}")
        return errors

    urls = _https_urls_in(source)
    if basis == "independent_external_prior":
        if not urls:
            errors.append(f"{loc}: independent_external_prior needs a direct independent https URL")
        else:
            for url in urls:
                if _url_allowed_for_family(registry, family, url):
                    errors.append(
                        f"{loc}: independent_external_prior URL {url} is a vendor domain"
                    )
                elif not _url_is_independent(url):
                    errors.append(
                        f"{loc}: independent_external_prior URL {url} is not a recognized "
                        "independent source domain"
                    )
                elif model_id and not _text_mentions_model(url, model_id, model):
                    errors.append(
                        f"{loc}: independent_external_prior URL {url} does not name model "
                        f"{model_id}"
                    )
        return errors

    if basis == "vendor_external_prior":
        if not urls:
            errors.append(f"{loc}: vendor_external_prior needs a direct official vendor https URL")
        else:
            for url in urls:
                if not _url_allowed_for_family(registry, family, url):
                    errors.append(
                        f"{loc}: vendor_external_prior URL {url} is not an allowed official "
                        f"domain for family {family!r}"
                    )
        return errors

    # operational_prior
    errors.extend(_operational_prior_errors(registry, role, route_id, model_id, pointer, loc))
    return errors


def _load_structured_repo_json(pointer: str) -> dict | None:
    path = _repo_rel_path(pointer)
    if path is None or not path.is_file() or path.suffix != ".json":
        return None
    try:
        value = json.loads(path.read_text())
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _provider_binding_for_route(route_id: str) -> tuple[str, dict] | None:
    data = _load_structured_repo_json("config/providers.json") or {}
    matches = [
        (pid, p) for pid, p in (data.get("providers") or {}).items()
        if isinstance(p, dict) and p.get("route") == route_id
    ]
    return matches[0] if len(matches) == 1 else None


def _operational_prior_errors(
    registry: dict, role: str, route_id: str, model_id: str, pointer: str, loc: str,
) -> list[str]:
    """Require an exact approved structured source with a matching route binding."""
    errors: list[str] = []
    expected = OPERATIONAL_PRIOR_SOURCES.get((role, route_id))
    if pointer != expected:
        errors.append(
            f"{loc}: operational_prior source {pointer!r} is not the code-approved structured "
            f"source for role/route {(role, route_id)!r} (expected {expected!r})"
        )
        return errors
    data = _load_structured_repo_json(pointer)
    if data is None:
        return [f"{loc}: operational_prior source {pointer!r} is not a readable structured JSON config"]
    binding = _provider_binding_for_route(route_id)
    if binding is None:
        return [f"{loc}: operational_prior has no unique provider binding for route {route_id!r}"]
    provider_id, provider = binding
    route = (registry.get("routes") or {}).get(route_id) or {}
    model = (registry.get("models") or {}).get(model_id) or {}
    declared_model = provider.get("model")
    if declared_model and declared_model not in set(model.get("official_ids") or ()) \
            and declared_model != route.get("invocation_id"):
        errors.append(
            f"{loc}: operational_prior provider {provider_id!r} model {declared_model!r} "
            f"does not bind route model {model_id!r}"
        )
    if pointer == "config/entrypoints.json":
        dispatcher = data.get("dispatcher") or {}
        bound = {dispatcher.get("default_provider")}
        bound.update(dispatcher.get("fallback_order") or [])
        bound.update(
            p.get("preferred_dispatcher")
            for p in (data.get("profiles") or {}).values()
            if isinstance(p, dict)
        )
        if provider_id not in bound:
            errors.append(f"{loc}: entrypoints dispatcher does not bind provider {provider_id!r}")
    elif pointer == "config/connectors.json":
        connectors = data.get("mcp_connectors") or {}
        if not any(
            isinstance(c, dict) and c.get("status") == "active"
            and provider_id in (c.get("available_on") or [])
            for c in connectors.values()
        ):
            errors.append(
                f"{loc}: connectors config has no active connector binding for provider {provider_id!r}"
            )
    elif pointer != "config/providers.json":
        errors.append(f"{loc}: operational_prior source {pointer!r} is not approved")
    return errors


def _official_source_coverage_errors(registry: dict, models: dict) -> list[str]:
    """Family coverage lists must be complete; every in-scope model needs an official URL."""
    errors: list[str] = []
    blob = registry.get("official_sources")
    if not isinstance(blob, dict) or not isinstance(blob.get("by_family"), dict):
        errors.append(
            "model-registry: official_sources.by_family is required "
            "(direct vendor URLs per family with explicit model coverage)"
        )
        return errors
    by_family = blob["by_family"]
    families = registry.get("families") or {}
    allowed = blob.get("allowed_domains_by_family")
    if not isinstance(allowed, dict) or not allowed:
        errors.append(
            "official_sources: allowed_domains_by_family is required "
            "(machine-readable official-domain allowlist per family/lab)"
        )
        allowed = {}
    normalized_allowed = {
        fid: tuple(domains) if isinstance(domains, list) else domains
        for fid, domains in allowed.items()
    }
    if normalized_allowed != OFFICIAL_DOMAINS_BY_FAMILY:
        errors.append(
            "official_sources.allowed_domains_by_family must exactly mirror the code-owned "
            "official-domain trust root (catalog entries cannot add or rewrite trusted suffixes)"
        )
    for fid, fam_models in _models_by_family(models).items():
        in_scope = [mid for mid in fam_models if not _model_is_placeholder(models.get(mid) or {})]
        if not in_scope:
            continue
        domains = allowed.get(fid)
        if not isinstance(domains, list) or not domains or any(
            not isinstance(d, str) or not d or "/" in d or " " in d for d in domains
        ):
            errors.append(
                f"official_sources.allowed_domains_by_family.{fid}: must be a non-empty "
                "list of hostname suffixes"
            )
        if fid not in by_family:
            errors.append(f"official_sources: family {fid!r} has in-scope models but no coverage entry")
            continue
        entry = by_family.get(fid) or {}
        urls = entry.get("urls") or []
        if not isinstance(urls, list) or not urls or any(not _is_https_url(u) for u in urls):
            errors.append(f"official_sources.{fid}: urls must be a non-empty list of https URLs")
        else:
            for url in urls:
                if not _url_allowed_for_family(registry, fid, url):
                    errors.append(
                        f"official_sources.{fid}: URL {url} is not an allowed official domain "
                        f"for family {fid!r}"
                    )
        covers = entry.get("covers_models")
        if not isinstance(covers, list) or not covers:
            errors.append(f"official_sources.{fid}: covers_models must list the in-scope models")
            continue
        for mid in covers:
            m = models.get(mid)
            if not isinstance(m, dict):
                errors.append(f"official_sources.{fid}: covers unknown model {mid!r}")
                continue
            if m.get("family") != fid:
                errors.append(
                    f"official_sources.{fid}: covers {mid!r} which is family {m.get('family')!r}"
                )
            if _model_is_placeholder(m):
                errors.append(f"official_sources.{fid}: placeholder {mid!r} is outside the census")
        missing = [mid for mid in in_scope if mid not in covers]
        extra = [mid for mid in covers if mid in models and mid not in in_scope]
        if missing:
            errors.append(
                f"official_sources.{fid}: covers_models missing {missing}"
            )
        if extra:
            errors.append(
                f"official_sources.{fid}: covers_models has non-census/placeholder ids {extra}"
            )
    for fid in by_family:
        if fid not in families:
            errors.append(f"official_sources: family {fid!r} is not declared")
    for fid in allowed:
        if fid not in families:
            errors.append(f"official_sources.allowed_domains_by_family: family {fid!r} is not declared")
    return errors


def _models_by_family(models: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for mid, model in (models or {}).items():
        if not isinstance(model, dict):
            continue
        out.setdefault(model.get("family") or "", []).append(mid)
    return out


def assert_valid(registry: dict, **kw) -> dict:
    errors = validate(registry, **kw)
    if errors:
        raise RegistryError("model-registry invalid:\n  - " + "\n  - ".join(errors))
    return registry


def _lifecycle(route: dict, model: dict) -> str:
    return route.get("lifecycle_override") or model.get("lifecycle")


def _route_row(rid: str, route: dict, model: dict) -> dict:
    return {
        "route": rid,
        "model": route.get("model"),
        "label": model.get("label") or route.get("model"),
        "family": model.get("family"),
        "lab": model.get("lab"),
        "lifecycle": _lifecycle(route, model),
        "route_state": route.get("route_state"),
        "host": route.get("host"),
        "harness": route.get("harness"),
        "invocation_id": route.get("invocation_id"),
        "provider": route.get("provider"),
        "capabilities": list(route.get("capabilities") or []),
        "tools": list(route.get("tools") or []),
        "independence_group": None,
        "physical": physical_invocation(route),
        "connectors": list(route.get("connectors") or []),
        "data_boundary": route.get("data_boundary"),
        "quota_bucket": route.get("quota_bucket"),
        "evidence_date": route.get("evidence_date"),
        "evidence_strength": route.get("evidence_strength"),
        "incubation": bool(route.get("incubation")),
        "compatibility_fallback": bool(route.get("compatibility_fallback")),
        "fallback_until": route.get("fallback_until"),
        "notes": route.get("notes") or model.get("notes") or "",
        "placeholder": _model_is_placeholder(model),
        "attestation_states": {
            key: rec.get("state")
            for key, rec in (route.get("attestations") or {}).items()
            if isinstance(rec, dict)
        },
        "waivers": [
            {
                "field": key,
                "expires": rec.get("expires"),
                "authority": rec.get("authority"),
                "rationale": rec.get("rationale"),
            }
            for key, rec in (route.get("attestations") or {}).items()
            if isinstance(rec, dict) and rec.get("state") == "waived"
        ],
    }


def inventory(registry: dict) -> list[dict]:
    models = registry.get("models") or {}
    out = []
    for rid, route in _sorted_items(registry.get("routes") or {}):
        model = models.get(route.get("model"), {})
        out.append(_route_row(rid, route, model))
    return out


def _matches(row: dict, *, required_capabilities=None, required_tools=None,
             data_boundary=None, exclude_models=None, exclude_families=None,
             exclude_routes=None, hosts=None, quota_spent=None) -> bool:
    """Role filters only. Live-ness is `route_is_live` — callers must pre-filter."""
    caps = set(row.get("capabilities") or [])
    tools = set(row.get("tools") or [])
    if required_capabilities and not set(required_capabilities).issubset(caps):
        return False
    if required_tools and not set(required_tools).issubset(tools):
        return False
    if data_boundary and row.get("data_boundary") != data_boundary:
        return False
    if exclude_models and row.get("model") in set(exclude_models):
        return False
    if exclude_families and row.get("family") in set(exclude_families):
        return False
    if exclude_routes and row.get("route") in set(exclude_routes):
        return False
    if hosts and row.get("host") not in set(hosts):
        return False
    spent = set(quota_spent or [])
    if row.get("quota_bucket") in spent or row.get("provider") in spent or row.get("route") in spent:
        return False
    return True


def resolve(registry: dict, role: str, *, n: int = 1, family_diversity: int | None = None,
            required_capabilities=None, required_tools=None, data_boundary=None,
            exclude_models=None, exclude_families=None, exclude_routes=None,
            hosts=None, quota_spent=None, use_quality: bool = False,
            as_of: date | None = None) -> dict:
    """Fail-closed resolver. Rank does not grant authority.

    Every candidate is filtered with `route_is_live` before matching/ranking. Missing,
    stale, future, mismatched, unattested evidence, undeclared family/independence
    group, or a route-local identity/family/invocation contradiction never returns
    the route — this function does not depend on CLI `assert_valid`. `as_of` defaults
    to the current date.

    family_diversity=2 requires distinct configured independence groups AND distinct
    physical (host, harness, invocation_id) identities — never family strings alone.
    An empty/undeclared group cannot count toward diversity.
    """
    as_of = as_of or date.today()
    roles = registry.get("roles") or {}
    rankings = registry.get("rankings") or {}
    if role not in roles or role not in rankings:
        return {"ok": False, "role": role, "routes": [], "reason": f"unknown role {role!r}"}
    spec = roles[role]
    req_caps = list(required_capabilities or spec.get("required_capabilities") or [])
    models = registry.get("models") or {}
    routes = registry.get("routes") or {}
    kind = "quality" if use_quality else "selection"
    order_key = "rank" if use_quality else "priority"
    ranked = sorted(
        rankings[role].get(kind) or [],
        key=lambda row: (row.get(order_key, 99), row.get("route") or ""),
    )
    candidates = []
    seen = set()
    for entry in ranked:
        rid = entry.get("route")
        if rid in seen or rid not in routes:
            continue
        seen.add(rid)
        if not route_is_live(registry, rid, as_of=as_of):
            continue
        row = _route_row(rid, routes[rid], models.get(routes[rid].get("model"), {}))
        row["independence_group"] = independence_group_of(registry, row.get("family"))
        row["physical"] = physical_invocation(row)
        if routes[rid].get("invocation_alias_of"):
            continue
        row["quality_rank"] = next(
            (x.get("rank") for x in (rankings[role].get("quality") or []) if x.get("route") == rid),
            None,
        )
        row["selection_priority"] = next(
            (x.get("priority") for x in (rankings[role].get("selection") or []) if x.get("route") == rid),
            None,
        )
        row["confidence"] = entry.get("confidence")
        row["rationale"] = entry.get("rationale")
        if _matches(
            row,
            required_capabilities=req_caps,
            required_tools=required_tools,
            data_boundary=data_boundary,
            exclude_models=exclude_models,
            exclude_families=exclude_families,
            exclude_routes=exclude_routes,
            hosts=hosts,
            quota_spent=quota_spent,
        ):
            candidates.append(row)

    want = family_diversity if family_diversity else n
    picked = []
    used_groups = set()
    used_physical = set()
    rejected_same_family = []
    for row in candidates:
        group = row.get("independence_group") or independence_group_of(registry, row.get("family"))
        phys = tuple(row.get("physical") or physical_invocation(row))
        if family_diversity and (not group or group in used_groups or phys in used_physical):
            rejected_same_family.append(row["route"])
            continue
        picked.append(row)
        used_groups.add(group)
        used_physical.add(phys)
        if len(picked) >= want:
            break

    result = {
        "ok": False,
        "role": role,
        "routes": picked,
        "rejected_same_family": rejected_same_family,
        "authority_grants": False,
        "reason": "",
    }
    if family_diversity and family_diversity >= 2 and len(picked) < family_diversity:
        groups = sorted(used_groups)
        result["reason"] = (
            f"fail-closed: cross-family needs {family_diversity} distinct independence "
            f"groups and unique physical invocations; only {groups or 'none'} resolved "
            f"from live_verified routes"
        )
        return result
    if not picked:
        result["reason"] = (
            f"fail-closed: no live_verified route for role {role!r} after filters "
            f"(lifecycle, capabilities, data boundary, exclusions, quota)"
        )
        return result
    if n > 1 and not family_diversity and len(picked) < n:
        result["reason"] = f"fail-closed: needed {n} routes, resolved {len(picked)}"
        return result
    result["ok"] = True
    result["reason"] = "resolved from live_verified routes; rank did not grant tools or data"
    if not family_diversity:
        result["routes"] = picked[:n]
    return result


def rankings_for(registry: dict, role: str) -> dict:
    rnk = (registry.get("rankings") or {}).get(role)
    if not rnk:
        raise RegistryError(f"unknown role {role!r}")
    blob = {
        "role": role,
        "quality": rnk.get("quality") or [],
        "selection": rnk.get("selection") or [],
        "note": (
            "quality_rank and selection_priority are independent; neither grants authority. "
            "Descending ranks are evidence-bounded and role/harness-specific, not a universal ordering. "
            "Cost/token efficiency is selection or an explicit efficiency field, not quality."
        ),
        "authority_grants": False,
    }
    if rnk.get("efficiency"):
        blob["efficiency"] = rnk.get("efficiency")
    return blob


def live_review_providers(registry: dict, providers: dict, as_of: date | None = None) -> list[str]:
    """review_order filtered to providers whose bound catalog route is live.

    No exceptions: Review E (or any provider) enters only when route_is_live is true.
    `providers.review-e.wired` does not override an unwired/catalog/disabled route.
    """
    if not isinstance(registry, dict) or not isinstance(providers, dict):
        return []
    provs = providers.get("providers") or {}
    out = []
    for pid in providers.get("review_order") or []:
        p = provs.get(pid) or {}
        if not p.get("review_eligible"):
            continue
        if not provider_route_is_live(registry, p, as_of=as_of):
            continue
        out.append(pid)
    return out


def _attestation_evaluation_label(route: dict) -> str:
    atts = route.get("attestations") or {}
    smoke = atts.get("local_access_smoke") or {}
    waived = [
        key for key, rec in atts.items()
        if isinstance(rec, dict) and rec.get("state") == "waived"
    ]
    if smoke.get("state") == "attested" and smoke.get("signal") == "direct_invocation":
        label = "direct"
    elif smoke.get("state") == "attested" and smoke.get("signal") == "standing_provider":
        label = "standing"
    else:
        label = "unevaluated"
    if waived:
        label += "+grandfathered"
    return label


def _render_attestation_section(registry: dict) -> list[str]:
    keys = list((registry.get("intake") or {}).get("promote_requires") or [])
    lines = [
        "",
        "## Live-route attestations",
        "",
        "Typed promotion state. `attested` means a field-specific `evidence_kind` plus a dated supporting source whose semantics match the requirement. `waived` is a time-bounded legacy/standing-provider migration exception (exact route id on `intake.legacy_waiver_routes`) and does **not** assert that the evidence exists. `not_applicable` requires a closed `structural_code` for the field and route; it is never a synonym for missing. `missing` cannot be `live_verified`.",
        "",
        "Evaluation: `direct` = `local_access_smoke` attested with `direct_invocation`; `standing` = standing-provider signal. `+grandfathered` means at least one field is `waived`. Cell extras are `evidence_kind` or `structural_code`.",
        "",
        "| route | evaluation | "
        + " | ".join(keys)
        + " | waivers expire |",
        "|---|---|" + "|".join(["---"] * len(keys)) + "|---|",
    ]
    for rid, route in _sorted_items(registry.get("routes") or {}):
        if route.get("route_state") not in ACTIVE_RESOLVE_STATES:
            continue
        atts = route.get("attestations") or {}
        cells = []
        expires = []
        for key in keys:
            rec = atts.get(key) if isinstance(atts.get(key), dict) else {}
            state = rec.get("state") or ""
            extra = ""
            kind = rec.get("evidence_kind") or rec.get("structural_code")
            if kind:
                extra = f"/{kind}"
            elif key == "local_access_smoke" and rec.get("signal"):
                extra = f"/{rec.get('signal')}"
            cells.append(f"{state}{extra}")
            if rec.get("state") == "waived" and rec.get("expires"):
                expires.append(str(rec.get("expires")))
        exp = ", ".join(sorted(set(expires))) or "—"
        lines.append(
            f"| `{rid}` | {_attestation_evaluation_label(route)} | "
            + " | ".join(cells)
            + f" | {exp} |"
        )
    return lines


def _render_official_source_section(registry: dict) -> list[str]:
    blob = registry.get("official_sources") or {}
    by_family = blob.get("by_family") or {}
    lines = [
        "",
        "## Official vendor sources",
        "",
        "Direct official https URLs. Family coverage and `allowed_domains_by_family` are mechanically validated. Local JSON paths are not official sources. Review E / `open-weight-review-e` is a local placeholder outside the census.",
        "",
        "| family | allowed domains | covers | urls |",
        "|---|---|---|---|",
    ]
    domains_by_family = (registry.get("official_sources") or {}).get("allowed_domains_by_family") or {}
    for fid, entry in _sorted_items(by_family):
        covers = ", ".join(f"`{m}`" for m in (entry.get("covers_models") or []))
        urls = " · ".join(entry.get("urls") or [])
        domains = ", ".join(f"`{d}`" for d in (domains_by_family.get(fid) or []))
        lines.append(f"| `{fid}` | {domains} | {covers} | {urls} |")
    placeholders = [
        mid for mid, model in _sorted_items(registry.get("models") or {})
        if _model_is_placeholder(model)
    ]
    if placeholders:
        lines += [
            "",
            "Local placeholders (not labs in scope; cannot be promoted or wired until a named candidate plus official source replaces them): "
            + ", ".join(f"`{m}`" for m in placeholders)
            + ".",
        ]
    return lines


def render_matrix(registry: dict) -> str:
    """Byte-idempotent markdown audit surface. Stable key order, trailing newline."""
    lines = [
        "# Model matrix",
        "",
        f"Generated from `config/model-registry.json` as of {registry.get('as_of')}.",
        "Deterministic. Do not hand-edit; run `python3 bin/model-registry.py write-matrix`.",
        "",
        "A catalog entry is not a usable route. Only `live_verified` routes resolve.",
        "The public resolver API is fail-closed: every candidate is filtered by `route_is_live` (missing/stale/future/mismatched/unattested evidence, undeclared family/independence group, or a route-local identity/family/invocation contradiction never returns).",
        "Last-resort coding requires a concrete live provider with `implement`/`ide` and `code` on both the provider and its bound live route; sharing a plan is not enough.",
        "Quality rank is not selection priority. Rank never grants tools or data.",
        "Descending ranks are evidence-bounded and role/harness-specific, not a universal ordering.",
        "live_verified freshness is compared to the current date (or `--as-of`), not frozen `registry.as_of`.",
        "Promotion attestations (`intake.promote_requires`) use typed state: attested, missing, not_applicable, waived.",
        "`attested` requires a field-specific `evidence_kind` and a dated source whose semantics support the requirement; absence language cannot pass.",
        "`not_applicable` requires a closed `structural_code` validated per field and route; free-form rationale cannot establish N/A.",
        "`waived` is a time-bounded legacy/standing-provider migration exception and does not assert the evidence exists.",
        "Legacy waivers are exact route ids on `intake.legacy_waiver_routes` only.",
        "Official vendor URLs are checked against `official_sources.allowed_domains_by_family`.",
        "Quality rows carry an explicit `basis` plus a basis-appropriate evidence pointer. `confidence: high` is only `local_same_harness` with a committed receipt. The only local same-harness role comparison is architecture_spec_critique Opus 5 vs Fable 5.",
        "Token-efficiency of added roles is a hypothesis to measure, not a realized-savings claim.",
        "",
    ]
    census = registry.get("census") or {}
    if census:
        lines += [
            "## Census scope",
            "",
            f"- as_of: {census.get('as_of', '')}",
            f"- cutoff: {census.get('cutoff') or census.get('as_of', '')}",
            f"- scope: {census.get('scope', '')}",
            "",
        ]
    lines += [
        "## Models",
        "",
        "| id | family | lab | lifecycle | official ids | official source | placeholder | excluded |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for mid, model in _sorted_items(registry.get("models") or {}):
        ids = ", ".join(model.get("official_ids") or [])
        excl = "yes" if model.get("excluded") else "no"
        placeholder = "yes" if _model_is_placeholder(model) else "no"
        srcs = official_urls_for_model(registry, mid, model)
        src = srcs[0] if srcs else ("—" if placeholder == "yes" else "")
        lines.append(
            f"| `{mid}` | {model.get('family','')} | {model.get('lab','')} | "
            f"{model.get('lifecycle','')} | {ids} | {src} | {placeholder} | {excl} |"
        )
    lines += [
        "",
        "## Routes",
        "",
        "| route | model | state | lifecycle | host | harness | invocation | evidence | signal | provider |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    models = registry.get("models") or {}
    for rid, route in _sorted_items(registry.get("routes") or {}):
        model = models.get(route.get("model"), {})
        signal = ((route.get("attestations") or {}).get("local_access_smoke") or {}).get("signal") or ""
        if not signal:
            recs = route.get("evidence") or []
            if isinstance(recs, list):
                for rec in reversed(recs):
                    if isinstance(rec, dict) and rec.get("signal"):
                        signal = rec.get("signal")
                        break
        lines.append(
            f"| `{rid}` | `{route.get('model')}` | {route.get('route_state')} | "
            f"{_lifecycle(route, model)} | {route.get('host')} | {route.get('harness')} | "
            f"`{route.get('invocation_id')}` | {route.get('evidence_date')} "
            f"{route.get('evidence_strength')} | {signal or '—'} | {route.get('provider') or '—'} |"
        )
    lines += _render_attestation_section(registry)
    lines += _render_official_source_section(registry)
    lines += ["", "## Per-role rankings (selection vs quality)", ""]
    lines.append(
        "Quality `basis` is machine-readable. `local_same_harness` is only the committed "
        "architecture_spec_critique Opus 5 vs Fable 5 receipt (n=1). `confidence: high` "
        "requires that basis plus a committed receipt pointer. Other quality rows are "
        "external or operational priors with a basis-appropriate source, not same-role "
        "local comparisons."
    )
    lines.append("")
    for role in REQUIRED_ROLES:
        rnk = (registry.get("rankings") or {}).get(role) or {}
        lines.append(f"### `{role}`")
        lines.append("")
        desc = ((registry.get("roles") or {}).get(role) or {}).get("description") or ""
        if desc:
            lines.append(desc)
            lines.append("")
        lines.append("| kind | n | route | confidence | basis | evidence |")
        lines.append("|---|---:|---|---|---|---|")
        for kind, key in (("quality", "rank"), ("selection", "priority"), ("efficiency", "rank")):
            for row in rnk.get(kind) or []:
                basis = row.get("basis") or "" if kind == "quality" else ""
                evidence = row.get("source") or "" if kind == "quality" else ""
                lines.append(
                    f"| {kind} | {row.get(key)} | `{row.get('route')}` | "
                    f"{row.get('confidence') or ''} | {basis} | {evidence} |"
                )
        lines.append("")
    lines.append("## Invariants")
    lines.append("")
    inv = registry.get("invariants") or {}
    for k in sorted(inv):
        v = inv[k]
        if isinstance(v, bool):
            v = "true" if v else "false"
        lines.append(f"- `{k}`: {v}")
    lines.append("")
    return "\n".join(lines)


def matrix_path() -> Path:
    return mborch.REPO / "generated" / "model-matrix.md"


def write_matrix(registry: dict, path: Path | None = None, check: bool = False) -> Path:
    path = path or matrix_path()
    text = render_matrix(registry)
    if check:
        if not path.exists():
            raise RegistryError(f"missing generated matrix {path}")
        existing = path.read_text()
        if existing != text:
            raise RegistryError(
                f"{path} is stale or hand-edited — run `python3 bin/model-registry.py write-matrix`"
            )
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Validate and query the model registry.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_val = sub.add_parser("validate", help="schema + freshness + contradiction checks")
    p_val.add_argument("--json", action="store_true")
    p_val.add_argument(
        "--as-of",
        default="",
        help="YYYY-MM-DD freshness clock (default: actual current date, not registry.as_of)",
    )

    p_inv = sub.add_parser("inventory", help="list every cataloged route")
    p_inv.add_argument("--json", action="store_true")
    p_inv.add_argument("--state", default="")

    p_res = sub.add_parser("resolve", help="fail-closed role resolution")
    p_res.add_argument("--role", required=True)
    p_res.add_argument("--n", type=int, default=1)
    p_res.add_argument("--family-diversity", type=int, default=0)
    p_res.add_argument("--require-cap", default="", help="comma-separated capabilities")
    p_res.add_argument("--require-tool", default="", help="comma-separated tools (matched against route.tools only)")
    p_res.add_argument("--exclude-family", default="")
    p_res.add_argument("--exclude-model", default="")
    p_res.add_argument("--data-boundary", default="")
    p_res.add_argument("--quota-spent", default="")
    p_res.add_argument("--quality", action="store_true", help="order by quality rank instead of selection")
    p_res.add_argument(
        "--as-of",
        default="",
        help="YYYY-MM-DD live-route clock (default: actual current date, not registry.as_of)",
    )
    p_res.add_argument("--json", action="store_true")

    p_rnk = sub.add_parser("rankings", help="quality vs selection for one role")
    p_rnk.add_argument("--role", required=True)
    p_rnk.add_argument("--json", action="store_true")

    p_mat = sub.add_parser("write-matrix", help="write generated/model-matrix.md")
    p_mat.add_argument("--check", action="store_true")

    args = ap.parse_args(argv)
    registry = load()
    providers = mborch.load_config("providers.json", required=False) or None
    connectors = mborch.load_config("connectors.json", required=False) or None

    if args.cmd == "validate":
        as_of = _as_date(args.as_of) if getattr(args, "as_of", "") else None
        errors = validate(registry, as_of=as_of, providers=providers, connectors=connectors)
        if args.json:
            print(json.dumps({"ok": not errors, "errors": errors}, indent=2))
        else:
            if errors:
                print("model-registry INVALID")
                for e in errors:
                    print(f"  ✗ {e}")
            else:
                print("model-registry OK")
        return 1 if errors else 0

    as_of = _as_date(getattr(args, "as_of", "") or "") or None
    if args.cmd != "resolve":
        assert_valid(registry, providers=providers, as_of=as_of, connectors=connectors)

    if args.cmd == "inventory":
        rows = inventory(registry)
        if args.state:
            rows = [r for r in rows if r["route_state"] == args.state]
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            print(f"{len(rows)} routes")
            for r in rows:
                print(f"  {r['route_state']:16} {r['route']:28} {r['family']:12} {r['invocation_id']}")
        return 0

    if args.cmd == "resolve":
        def split(s):
            return [x.strip() for x in s.split(",") if x.strip()]
        decision = resolve(
            registry,
            args.role,
            n=args.n,
            family_diversity=args.family_diversity or None,
            required_capabilities=split(args.require_cap) or None,
            required_tools=split(getattr(args, "require_tool", "") or "") or None,
            exclude_families=split(args.exclude_family) or None,
            exclude_models=split(args.exclude_model) or None,
            data_boundary=args.data_boundary or None,
            quota_spent=split(args.quota_spent) or None,
            use_quality=args.quality,
            as_of=as_of,
        )
        if args.json:
            print(json.dumps(decision, indent=2))
        else:
            print(f"{'OK' if decision['ok'] else 'FAIL'}  {decision['reason']}")
            for i, r in enumerate(decision["routes"], 1):
                print(f"  {i}. {r['route']} [{r['family']}] {r['route_state']} sel={r.get('selection_priority')} q={r.get('quality_rank')}")
        return 0 if decision["ok"] else 1

    if args.cmd == "rankings":
        blob = rankings_for(registry, args.role)
        if args.json:
            print(json.dumps(blob, indent=2))
        else:
            print(f"role {args.role} (authority_grants={blob['authority_grants']})")
            print("selection:")
            for row in blob["selection"]:
                print(f"  {row['priority']}. {row['route']} ({row.get('confidence')})")
            print("quality:")
            for row in blob["quality"]:
                print(f"  {row['rank']}. {row['route']} ({row.get('confidence')})")
        return 0

    if args.cmd == "write-matrix":
        path = write_matrix(registry, check=args.check)
        print(("checked " if args.check else "wrote ") + str(path.relative_to(mborch.REPO)))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
