#!/usr/bin/env python3
"""connectors — read the live connector/binding registry and render paste-ready blocks.

config/connectors.json is the single source for which MCP/analytics/store binding
lives where, plus the concrete live IDs (Clarity project ids, analytics login,
Shopify stores/themes, and Grok CLI role bindings). Policy prose points here instead of
hardcoding IDs that go stale. This renders the human-facing blocks (agent allowlists,
Grok CLI prompt packets, Clarity binding) FROM that config, so there is exactly one
place to edit when a binding moves.

  connectors.py                         # summary of all bindings
  connectors.py --render visual-qa-allowlist
  connectors.py --render visual-qa-ticket <store> --changed-path PATH --page PAGE
  connectors.py --render visual-qa-live-ticket <store> [--page PAGE]
  connectors.py --render clarity
  connectors.py --json
"""
from __future__ import annotations
import argparse, json, posixpath, re, sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

_MAX_URL_DECODES = 4
_MALFORMED_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})")
_C0_OR_DEL = re.compile(r"[\x00-\x1f\x7f]")
_SCHEME_PREFIX = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
_MAX_CHANGED_PATHS = 8
# Conservative code-owned cap for a single repo-relative Shopify/theme path.
MAX_CHANGED_PATH_BYTES = 192
_CHANGED_PATH_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_CHANGED_PATH_META = re.compile(r"[^A-Za-z0-9._/-]")
PREVIEW_PAGES = ("home", "collection", "pdp", "cart")
LIVE_PAGES = ("home", "search", "collection", "pdp")
REVIEW_D_SCALAR_FIELDS = ("role", "mode", "store", "site", "url")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mborch  # noqa: E402


def load():
    return mborch.load_config("connectors.json", required=True)


def render_allowlist(c):
    stores = c.get("stores", {})
    out = ["## Review D allowlist (rendered from config/connectors.json — edit there, not here)"]
    for i, (sid, s) in enumerate(stores.items(), 1):
        name = sid.replace("-", " ").title()
        out.append(f"\n### {i}) {name}")
        out.append(f"- Live: {', '.join(s.get('live_hosts', []))}")
        out.append(f"- Preview: `{s.get('preview_host')}` when the brief names {name}")
        if s.get("preview_extra"):
            out.append(f"- Extra: {s['preview_extra']}")
        out.append(f"- Never: {', '.join(s.get('never', []))}")
        if s.get("review_d_preview_url"):
            try:
                _validate_preview_url(c, sid, s["review_d_preview_url"])
            except SystemExit:
                out.append("- Review D preview URL: invalid; ticket renderer will refuse it")
            else:
                out.append(f"- Review D preview URL: {s['review_d_preview_url']}")
    policy = c.get("grok_cli", {}).get("visual_qa", {})
    live = policy.get("modes", {}).get("live-storefront-audit", {})
    preview = policy.get("modes", {}).get("preview-review", {})
    deny = policy.get("deny_before_navigation", {})
    out.append("\n### Mode and deny gate")
    out.append(f"- Shared-preview host: `{preview.get('shared_preview_host')}`")
    for item in preview.get("configured_host_rules") or []:
        out.append(
            f"- Exact-host preview rule ({item.get('store')}): "
            f"host={item.get('exact_host')}; "
            f"requires {item.get('required_query_parameter')}"
        )
    out.append("- Live-audit packet: `role: review-d` plus `mode: live-storefront-audit`")
    out.append(f"- Live-audit host match: {live.get('host_source')} ({live.get('host_match')})")
    out.append(f"- Denied hosts: {', '.join(deny.get('hosts', []))}")
    out.append(f"- Denied path prefixes: {', '.join(deny.get('path_prefixes', []))}")
    out.append(f"- Denied markers: {', '.join(deny.get('case_insensitive_markers', []))}")
    return "\n".join(out)


def _store(c, store):
    stores = c.get("stores", {})
    if store not in stores:
        sys.exit(f"connectors: unknown store {store!r}; known: {', '.join(stores)}")
    return stores[store]


def _decode_to_fixed_point(value):
    current = value
    for _ in range(_MAX_URL_DECODES):
        decoded = unquote(current)
        if decoded == current:
            if _MALFORMED_PERCENT.search(decoded) or "%" in decoded:
                raise ValueError("percent-encoding did not reach a safe fixed point")
            return decoded
        current = decoded
    raise ValueError("percent-encoding exceeds the safe decode bound")


def _parse_navigation_url(store, url):
    if not isinstance(url, str) or not url or _C0_OR_DEL.search(url):
        raise ValueError("contains control characters")
    if _MALFORMED_PERCENT.search(url):
        raise ValueError("malformed percent-encoding")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        if "port" in str(exc).lower():
            raise ValueError("invalid port") from exc
        raise ValueError("malformed") from exc
    if port is not None and not (1 <= port <= 65535):
        raise ValueError("invalid port")
    if port not in (None, 443):
        raise ValueError("non-default HTTPS origin port")
    if parsed.scheme != "https" or parsed.username is not None or parsed.password is not None:
        raise ValueError("must be credential-free HTTPS")
    if "@" in (parsed.netloc or ""):
        raise ValueError("must be credential-free HTTPS")
    decoded = _decode_to_fixed_point(url)
    if _C0_OR_DEL.search(decoded):
        raise ValueError("contains control characters")
    if "\\" in decoded:
        raise ValueError("uses a denied browser path separator")
    try:
        decoded_parsed = urlsplit(decoded)
        decoded_port = decoded_parsed.port
    except ValueError as exc:
        if "port" in str(exc).lower():
            raise ValueError("invalid port") from exc
        raise ValueError("malformed after decoding") from exc
    if decoded_port is not None and not (1 <= decoded_port <= 65535):
        raise ValueError("invalid port")
    if decoded_port not in (None, 443):
        raise ValueError("non-default HTTPS origin port")
    original_host = (parsed.hostname or "").lower()
    decoded_host = (decoded_parsed.hostname or "").lower()
    if (
        decoded_parsed.scheme != parsed.scheme
        or decoded_host != original_host
        or decoded_port != port
        or decoded_parsed.username is not None
        or decoded_parsed.password is not None
        or "@" in (decoded_parsed.netloc or "")
    ):
        raise ValueError("authority differs after canonical decoding")
    if not original_host:
        raise ValueError("malformed")
    return parsed, original_host, decoded, decoded_parsed


def _validate_navigation_url(c, store, url):
    """Apply the common deny-before-navigation contract and return parsed URL data."""
    _store(c, store)
    try:
        parsed, host, decoded_url, decoded_parsed = _parse_navigation_url(store, url)
    except ValueError as exc:
        reason = str(exc)
        if "non-default HTTPS origin port" in reason:
            sys.exit(f"connectors: store {store!r} URL has a non-default HTTPS origin port")
        if "HTTPS" in reason:
            sys.exit(f"connectors: store {store!r} URL must be credential-free HTTPS")
        if "browser path separator" in reason:
            sys.exit(f"connectors: store {store!r} URL uses a denied browser path separator")
        if "control" in reason:
            sys.exit(f"connectors: store {store!r} URL contains a control character")
        if "percent" in reason or "decode bound" in reason:
            sys.exit(f"connectors: store {store!r} URL uses unsafe percent-encoding")
        if "port" in reason:
            sys.exit(f"connectors: store {store!r} URL has an invalid port")
        if "authority" in reason:
            sys.exit(f"connectors: store {store!r} URL authority is ambiguous")
        sys.exit(f"connectors: store {store!r} URL is malformed")
    deny = c.get("grok_cli", {}).get("visual_qa", {}).get("deny_before_navigation", {})
    decoded_path = decoded_parsed.path.lower()
    if "\\" in decoded_url:
        sys.exit(f"connectors: store {store!r} URL uses a denied browser path separator")
    if ";" in decoded_path:
        sys.exit(f"connectors: store {store!r} URL uses a denied path parameter separator")
    normalized_path = posixpath.normpath("/" + decoded_path.lstrip("/"))
    if host in {str(value).lower() for value in deny.get("hosts") or []}:
        sys.exit(f"connectors: store {store!r} URL uses a denied host")
    if any(normalized_path == str(prefix).lower()
           or normalized_path.startswith(str(prefix).lower() + "/")
           for prefix in deny.get("path_prefixes") or []):
        sys.exit(f"connectors: store {store!r} URL uses a denied path")
    if any(str(marker).lower() in decoded_url.lower()
           for marker in deny.get("case_insensitive_markers") or []):
        sys.exit(f"connectors: store {store!r} URL contains a denied marker")
    return parsed, host, normalized_path


def _validate_preview_url(c, store, url):
    """Return the matched preview policy after validating the rendered CLI packet.

    Shared-domain previews must really be HTTPS subdomains of the configured wildcard.
    Live-host theme previews need an explicit per-store filter, exact configured host,
    and preview_theme_id. Anything else fails closed before Grok CLI is launched.
    """
    s = _store(c, store)
    preview = c.get("grok_cli", {}).get("visual_qa", {}).get("modes", {}).get("preview-review", {})
    parsed, host, _path = _validate_navigation_url(c, store, url)

    pattern = preview.get("shared_preview_host") or s.get("preview_host", "")
    if pattern.startswith("*."):
        suffix = pattern[1:].lower()
        if host.endswith(suffix) and host != suffix.lstrip("."):
            return "shared-preview-host"

    query = parse_qs(parsed.query, keep_blank_values=True)
    configured_hosts = {str(h).lower() for h in s.get("live_hosts", [])}
    for item in preview.get("configured_host_rules") or []:
        required = item.get("required_query_parameter")
        exact_host = str(item.get("exact_host") or "").lower()
        required_values = query.get(required, []) if required else []
        if (item.get("store") == store and exact_host in configured_hosts and host == exact_host
                and any(str(value).strip() for value in required_values)):
            return "exact-host-preview"

    sys.exit(f"connectors: store {store!r} preview URL has no safe configured CLI preview rule")


def _store_title(store):
    return store.replace("-", " ").title()


def validate_changed_path(raw):
    if not isinstance(raw, str) or not raw:
        raise ValueError("changed path is empty")
    if not raw.isascii():
        raise ValueError("changed path is not ASCII")
    encoded = raw.encode("ascii")
    if len(encoded) > MAX_CHANGED_PATH_BYTES:
        raise ValueError("changed path exceeds the code-owned length cap")
    if _C0_OR_DEL.search(raw):
        raise ValueError("changed path contains a control character")
    if any(ch.isspace() for ch in raw):
        raise ValueError("changed path contains whitespace")
    if "%" in raw:
        raise ValueError("changed path contains percent encoding")
    if "\\" in raw:
        raise ValueError("changed path uses a denied path separator")
    if raw.startswith("/") or raw.startswith("~"):
        raise ValueError("changed path is absolute")
    if "://" in raw or _SCHEME_PREFIX.search(raw):
        raise ValueError("changed path contains a URL or scheme")
    if _CHANGED_PATH_META.search(raw):
        raise ValueError("changed path contains shell, URL, or instruction punctuation")
    parts = raw.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("changed path contains a dot or empty segment")
    if any(not _CHANGED_PATH_SEGMENT.fullmatch(part) for part in parts):
        raise ValueError("changed path is not a safe repo-relative POSIX path")
    return raw


def bind_changed_path(cwd, raw):
    """Bind a grammar-valid changed-path to cwd without following a symlink escape."""
    rel = validate_changed_path(raw)
    if not isinstance(cwd, Path):
        cwd = Path(cwd)
    try:
        if cwd.is_symlink() or not cwd.is_dir():
            raise ValueError("repository cwd is not a regular directory")
        repo = cwd.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise ValueError(f"repository cwd cannot be bound: {exc}") from exc
    current = repo
    for part in rel.split("/"):
        if current.is_symlink():
            raise ValueError("changed path escapes through a symlink")
        current = current / part
        try:
            if current.is_symlink():
                raise ValueError("changed path escapes through a symlink")
        except OSError as exc:
            raise ValueError(f"changed path cannot be proven in the repository: {exc}") from exc
    if not current.is_file() or current.is_symlink():
        raise ValueError("changed path is not an existing regular non-symlink file")
    try:
        resolved = current.resolve(strict=True)
        repo_resolved = repo.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"changed path cannot be proven in the repository: {exc}") from exc
    try:
        resolved.relative_to(repo_resolved)
    except ValueError as exc:
        raise ValueError("changed path escapes the requested repository cwd") from exc
    return resolved


def validate_changed_paths(paths):
    if not isinstance(paths, (list, tuple)) or not (1 <= len(paths) <= _MAX_CHANGED_PATHS):
        raise ValueError("changed paths must be 1 to 8 unique safe repo-relative POSIX paths")
    seen = set()
    out = []
    for raw in paths:
        path = validate_changed_path(raw)
        if path in seen:
            raise ValueError("changed path is duplicated")
        seen.add(path)
        out.append(path)
    return tuple(out)


def pages_for_mode(mode):
    if mode == "preview-review":
        return PREVIEW_PAGES
    if mode == "live-storefront-audit":
        return LIVE_PAGES
    raise ValueError("unknown Review D mode")


def validate_pages(mode, pages):
    allowed = pages_for_mode(mode)
    if not isinstance(pages, (list, tuple)) or not pages:
        raise ValueError("pages must be a non-empty mode-appropriate enum")
    seen = set()
    out = []
    for raw in pages:
        if not isinstance(raw, str) or raw not in allowed:
            raise ValueError("page is unknown for this Review D mode")
        if raw in seen:
            raise ValueError("page is duplicated")
        seen.add(raw)
        out.append(raw)
    return tuple(out)


def _die_packet(exc):
    sys.exit(f"connectors: {exc}")


def parse_review_d_packet(text):
    if not isinstance(text, str) or not text or "\r" in text or "\x00" in text:
        raise ValueError("Review D packet is not canonical UTF-8 text")
    if not text.endswith("\n") or "\n\n" in text:
        raise ValueError("Review D packet is multiline or missing a trailing newline")
    scalars = {}
    changed_paths = []
    pages = []
    seen_keys = []
    repeatable_started = None
    for line in text.splitlines():
        key, sep, rest = line.partition(":")
        if not sep or key != key.strip() or not key or " " in key:
            raise ValueError("Review D packet contains an unstructured field")
        if rest[:1] != " " or rest[1:] != rest[1:].rstrip("\n"):
            raise ValueError("Review D packet field is not canonical")
        value = rest[1:]
        if not value or _C0_OR_DEL.search(value):
            raise ValueError("Review D packet field is empty or contains a control character")
        if key in REVIEW_D_SCALAR_FIELDS:
            if repeatable_started is not None:
                raise ValueError("Review D packet fields are reordered")
            if key in scalars:
                raise ValueError(f"Review D packet contains duplicate field: {key}")
            scalars[key] = value
            seen_keys.append(key)
            continue
        if key == "changed-path":
            if repeatable_started not in (None, "changed-path"):
                raise ValueError("Review D packet fields are reordered")
            if seen_keys != list(REVIEW_D_SCALAR_FIELDS):
                raise ValueError("Review D packet fields are reordered")
            repeatable_started = "changed-path"
            changed_paths.append(value)
            continue
        if key == "page":
            if seen_keys != list(REVIEW_D_SCALAR_FIELDS):
                raise ValueError("Review D packet fields are reordered")
            if repeatable_started not in (None, "changed-path", "page"):
                raise ValueError("Review D packet fields are reordered")
            repeatable_started = "page"
            pages.append(value)
            continue
        raise ValueError("Review D packet contains an unknown field")
    if tuple(seen_keys) != REVIEW_D_SCALAR_FIELDS:
        raise ValueError("Review D packet is missing a required field")
    if scalars.get("role") != "review-d":
        raise ValueError("Review D packet role is not canonical")
    mode = scalars.get("mode")
    if mode == "preview-review":
        changed_paths = list(validate_changed_paths(changed_paths))
    elif mode == "live-storefront-audit":
        if changed_paths:
            raise ValueError("live Review D packet must not carry changed paths")
        changed_paths = []
    else:
        raise ValueError("Review D packet mode is unknown")
    pages = list(validate_pages(mode, pages))
    return {
        "role": "review-d",
        "mode": mode,
        "store": scalars["store"],
        "site": scalars["site"],
        "url": scalars["url"],
        "changed_paths": changed_paths,
        "pages": pages,
    }


def _format_packet(mode, store, url, changed_paths, pages):
    lines = [
        "role: review-d",
        f"mode: {mode}",
        f"store: {store}",
        f"site: {_store_title(store)}",
        f"url: {url}",
    ]
    for path in changed_paths:
        lines.append(f"changed-path: {path}")
    for page in pages:
        lines.append(f"page: {page}")
    return "\n".join(lines) + "\n"


def render_ticket(c, store, changed_paths, pages):
    s = _store(c, store)
    url = s.get("review_d_preview_url")
    if not url:
        sys.exit(f"connectors: store {store!r} has no concrete review_d_preview_url")
    _validate_preview_url(c, store, url)
    try:
        paths = validate_changed_paths(changed_paths)
        selected = validate_pages("preview-review", pages)
    except ValueError as exc:
        _die_packet(exc)
    return _format_packet("preview-review", store, url, paths, selected)


def render_live_ticket(c, store, pages=None):
    s = _store(c, store)
    live_hosts = s.get("live_hosts") or []
    if not live_hosts:
        sys.exit(f"connectors: store {store!r} has no configured live_hosts")
    url = f"https://{live_hosts[0]}/"
    parsed, host, normalized_path = _validate_navigation_url(c, store, url)
    configured_hosts = {str(value).lower() for value in live_hosts}
    if host not in configured_hosts or normalized_path != "/" or parsed.query or parsed.fragment:
        sys.exit(f"connectors: store {store!r} live URL must be an exact configured root host")
    selected = LIVE_PAGES if pages is None else pages
    try:
        selected = validate_pages("live-storefront-audit", selected)
    except ValueError as exc:
        _die_packet(exc)
    return _format_packet("live-storefront-audit", store, url, (), selected)


def reconstruct_review_d_packet(c, text):
    try:
        parsed = parse_review_d_packet(text)
    except ValueError as exc:
        _die_packet(exc)
    store = parsed["store"]
    _store(c, store)
    if parsed["site"] != _store_title(store):
        sys.exit("connectors: Review D packet site does not match the canonical store id")
    if parsed["mode"] == "preview-review":
        rendered = render_ticket(c, store, parsed["changed_paths"], parsed["pages"])
    else:
        rendered = render_live_ticket(c, store, parsed["pages"])
    if parsed["url"] != rendered.split("url: ", 1)[1].split("\n", 1)[0]:
        sys.exit("connectors: Review D packet URL does not match the validated store URL")
    if rendered != text:
        sys.exit("connectors: Review D packet is not the canonical reconstructed form")
    return rendered


def render_clarity(c):
    cl = c.get("analytics", {}).get("clarity", {})
    proj = cl.get("projects", {})
    lines = ["## Heat Map / Clarity binding (rendered from config/connectors.json)",
             f"login: {cl.get('login_identity')} via {cl.get('login_method')} (Member; least-privilege={cl.get('least_privilege')})"]
    for pid, p in proj.items():
        lines.append(f"- {pid}: project id {p.get('id')}  host {p.get('host')}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render live connector bindings.")
    ap.add_argument("--render", choices=[
        "visual-qa-allowlist", "visual-qa-ticket", "visual-qa-live-ticket", "clarity"
    ])
    ap.add_argument("store", nargs="?", help="store id for visual-qa-ticket")
    ap.add_argument("--changed-path", action="append", dest="changed_paths", default=[])
    ap.add_argument("--page", action="append", dest="pages", default=[])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    c = load()

    if args.json:
        print(json.dumps(c, indent=2))
        return 0
    if args.render == "visual-qa-allowlist":
        print(render_allowlist(c))
        return 0
    if args.render == "visual-qa-ticket":
        if not args.store:
            sys.exit("connectors: visual-qa-ticket needs a store id (e.g. gadget-duke)")
        sys.stdout.write(render_ticket(c, args.store, args.changed_paths, args.pages))
        return 0
    if args.render == "visual-qa-live-ticket":
        if not args.store:
            sys.exit("connectors: visual-qa-live-ticket needs a store id (e.g. magnet-baron)")
        sys.stdout.write(render_live_ticket(c, args.store, args.pages or None))
        return 0
    if args.render == "clarity":
        print(render_clarity(c))
        return 0

    # summary
    print("connectors  (config/connectors.json)")
    print("-" * 72)
    print("MCP connectors → available_on policy ceiling (not proof of live/callable access):")
    for name, m in c.get("mcp_connectors", {}).items():
        print(f"  {name:<24} {', '.join(m.get('available_on', []))}")
    print("stores:", ", ".join(c.get("stores", {})))
    cl = c.get("analytics", {}).get("clarity", {})
    print("clarity login:", cl.get("login_identity"), "projects:", ", ".join(cl.get("projects", {})))
    gc = c.get("grok_cli", {})
    print("grok cli:", gc.get("binary"), gc.get("model"), "roles:", ", ".join(gc.get("roles", {})))
    print("-" * 72)
    print("effective runtime state: bin/detect-integrations.py [--json|--refresh|--check]")
    print("render blocks: --render visual-qa-allowlist | visual-qa-ticket <store> | "
          "visual-qa-live-ticket <store> | clarity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
