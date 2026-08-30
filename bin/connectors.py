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
  connectors.py --render visual-qa-ticket <store>
  connectors.py --render visual-qa-live-ticket <store>
  connectors.py --render clarity
  connectors.py --json
"""
from __future__ import annotations
import argparse, json, posixpath, sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

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


def _fully_unquote(value):
    for _ in range(4):
        decoded = unquote(value)
        if decoded == value:
            break
        value = decoded
    return value


def _validate_navigation_url(c, store, url):
    """Apply the common deny-before-navigation contract and return parsed URL data."""
    _store(c, store)
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or parsed.username is not None or parsed.password is not None:
        sys.exit(f"connectors: store {store!r} URL must be credential-free HTTPS")
    deny = c.get("grok_cli", {}).get("visual_qa", {}).get("deny_before_navigation", {})
    decoded_url = _fully_unquote(url).lower()
    decoded_path = _fully_unquote(parsed.path).lower()
    normalized_path = posixpath.normpath("/" + decoded_path.lstrip("/"))
    if host in {str(value).lower() for value in deny.get("hosts") or []}:
        sys.exit(f"connectors: store {store!r} URL uses a denied host")
    if any(normalized_path == str(prefix).lower()
           or normalized_path.startswith(str(prefix).lower() + "/")
           for prefix in deny.get("path_prefixes") or []):
        sys.exit(f"connectors: store {store!r} URL uses a denied path")
    if any(str(marker).lower() in decoded_url
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


def render_ticket(c, store):
    s = _store(c, store)
    name = store.replace("-", " ").title()
    url = s.get("review_d_preview_url")
    if not url:
        sys.exit(f"connectors: store {store!r} has no concrete review_d_preview_url")
    _validate_preview_url(c, store, url)
    return (
        "role: review-d\n"
        "mode: preview-review\n"
        f"site: {name}\n"
        f"url: {url}\n"
        "changed: <one line>\n"
        "pages: Home, collection, PDP, cart\n"
    )


def render_live_ticket(c, store):
    s = _store(c, store)
    name = store.replace("-", " ").title()
    live_hosts = s.get("live_hosts") or []
    if not live_hosts:
        sys.exit(f"connectors: store {store!r} has no configured live_hosts")
    url = f"https://{live_hosts[0]}/"
    parsed, host, normalized_path = _validate_navigation_url(c, store, url)
    configured_hosts = {str(value).lower() for value in live_hosts}
    if host not in configured_hosts or normalized_path != "/" or parsed.query or parsed.fragment:
        sys.exit(f"connectors: store {store!r} live URL must be an exact configured root host")
    return (
        "role: review-d\n"
        "mode: live-storefront-audit\n"
        f"site: {name}\n"
        f"url: {url}\n"
        "scope: public storefront read-only\n"
        "pages: Home, search, collection, PDP\n"
    )


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
        print(render_ticket(c, args.store))
        return 0
    if args.render == "visual-qa-live-ticket":
        if not args.store:
            sys.exit("connectors: visual-qa-live-ticket needs a store id (e.g. magnet-baron)")
        print(render_live_ticket(c, args.store))
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
