#!/usr/bin/env python3
"""connectors — read the live connector/binding registry and render paste-ready blocks.

config/connectors.json is the single source for which MCP/analytics/store binding
lives where, plus the concrete live IDs (Clarity project ids, analytics login,
Shopify stores/themes, Slack channel). Policy prose points here instead of
hardcoding IDs that go stale. This renders the human-facing blocks (bot allowlists,
Slack ticket templates, Clarity binding) FROM that config, so there is exactly one
place to edit when a binding moves.

  connectors.py                         # summary of all bindings
  connectors.py --render visual-qa-allowlist
  connectors.py --render visual-qa-ticket <store>
  connectors.py --render clarity
  connectors.py --json
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE.parent / "config"


def load():
    path = CONFIG / "connectors.json"
    if not path.exists():
        sys.exit(f"connectors: missing {path}")
    return json.loads(path.read_text())


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
    return "\n".join(out)


def render_ticket(c, store):
    stores = c.get("stores", {})
    if store not in stores:
        sys.exit(f"connectors: unknown store {store!r}; known: {', '.join(stores)}")
    s = stores[store]
    name = store.replace("-", " ").title()
    chan = c.get("slack", {}).get("visual_qa_channel", {}).get("name", "#visual-qa")
    url = s.get("review_d_preview_url", f"https://<token>-<shop_id>.{s.get('preview_host','shopifypreview.com').lstrip('*.')}")
    return (
        f"Channel: {chan}\n\n"
        "@Website Visual QA\n"
        f"site: {name}\n"
        f"url: {url}\n"
        "changed: <one line>\n"
        "pages: Home, collection, PDP, cart\n"
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
    ap.add_argument("--render", choices=["visual-qa-allowlist", "visual-qa-ticket", "clarity"])
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
    if args.render == "clarity":
        print(render_clarity(c))
        return 0

    # summary
    print("connectors  (config/connectors.json)")
    print("-" * 72)
    print("MCP connectors → available_on:")
    for name, m in c.get("mcp_connectors", {}).items():
        print(f"  {name:<24} {', '.join(m.get('available_on', []))}")
    print("stores:", ", ".join(c.get("stores", {})))
    cl = c.get("analytics", {}).get("clarity", {})
    print("clarity login:", cl.get("login_identity"), "projects:", ", ".join(cl.get("projects", {})))
    print("slack:", c.get("slack", {}).get("visual_qa_channel", {}).get("name"))
    print("-" * 72)
    print("render blocks: --render visual-qa-allowlist | visual-qa-ticket <store> | clarity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
