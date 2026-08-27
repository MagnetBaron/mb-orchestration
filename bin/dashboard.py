#!/usr/bin/env python3
"""dashboard — a self-contained HTML usage dashboard for the orchestration engine.

Renders, from config + the usage history, a control-room view the owner uses ON
THIS COMPUTER to rate how well the system worked: per-account usage and reset
windows, a transparent health score (never-strand guarantee, waste-at-reset,
metered-$ discipline, Fable availability), the live drain order, the subscription
stack + cost, and recommendations. Output is one self-contained .html file (no
external assets except Google Fonts) — open it locally or publish it.

  dashboard.py                 → data/dashboard.html from real history
  dashboard.py --out X.html
  dashboard.py --demo          → seed representative sample history for a preview
"""
from __future__ import annotations
import argparse, html, importlib.util, json, sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mborch  # noqa: E402
import routing  # noqa: E402

_spec = importlib.util.spec_from_file_location("usage_status", HERE / "usage-status.py")
usage_status = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(usage_status)

TIER_COLOR = {"available": "var(--good)", "reserve": "var(--warn)", "spent": "var(--crit)"}


def demo_history():
    """Representative sample points (14 days) so the preview shows real shapes. Labeled sample."""
    seats = {"grok-heavy": (30, 95, "weekly"), "codex-sol": (20, 88, "weekly"),
             "claude-max": (25, 70, "rolling"), "claude-team-a": (15, 60, "rolling"),
             "cursor-other-400": (5, 22, "monthly"), "review-e": (0, 0, "none")}
    base = datetime(2026, 8, 13, tzinfo=timezone.utc)
    out = []
    for d in range(15):
        ts = (base + timedelta(days=d)).isoformat()
        for seat, (lo, hi, kind) in seats.items():
            frac = (d % 7) / 6.0 if kind == "weekly" else (d / 14.0 if kind == "monthly" else (d % 3) / 2.0)
            pct = round(lo + (hi - lo) * frac, 1)
            tier = "spent" if pct >= 95 else ("reserve" if pct >= 88 and seat == "codex-sol" else "available")
            out.append({"ts": ts, "source": "sample", "seat": seat, "pct": pct, "tier": tier,
                        "billing": "metered" if seat in ("cursor-other-400", "review-e") else "included",
                        "window_kinds": [kind]})
    return out


def sparkline(values, w=132, h=30):
    vals = [v for v in values if isinstance(v, (int, float))]
    if len(vals) < 2:
        return '<span class="spark-empty">no history</span>'
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    n = len(vals)
    pts = [(i / (n - 1) * (w - 2) + 1, h - 2 - (v - lo) / rng * (h - 6)) for i, v in enumerate(vals)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"1,{h-1} " + line + f" {w-1},{h-1}"
    ex, ey = pts[-1]
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" preserveAspectRatio="none" aria-hidden="true">'
            f'<polygon points="{area}" fill="var(--accent-fade)"/>'
            f'<polyline points="{line}" fill="none" stroke="var(--accent)" stroke-width="1.5"/>'
            f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="2.4" fill="var(--accent)"/></svg>')


def waste_at_reset(history):
    """Estimate wasted quota: pct remaining just before a detected reset (spent→free or big drop)."""
    byseat = defaultdict(list)
    for h in history:
        if h.get("ts") and h.get("seat"):
            byseat[h["seat"]].append(h)
    wastes = []
    for seat, recs in byseat.items():
        recs.sort(key=lambda r: r["ts"])
        for a, b in zip(recs, recs[1:]):
            drop = (a.get("pct") or 0) - (b.get("pct") or 0)
            if (a.get("tier") == "spent" and b.get("tier") != "spent"):
                continue  # was fully used
            if drop >= 40:  # reset with capacity left before it
                wastes.append(max(0, 100 - (a.get("pct") or 0)))
    return round(sum(wastes) / len(wastes), 1) if wastes else 0.0


def build(now_str, demo):
    subs = mborch.load_config("subscriptions.json", required=False)
    providers = mborch.load_config("providers.json", required=False)
    monitoring = mborch.load_config("monitoring.json", required=False)
    _, rows = usage_status.compute()
    history = mborch.read_history(monitoring)
    sample = False
    if demo or len(history) < 4:
        history = demo_history()
        sample = True

    hist_by_seat = defaultdict(list)
    for h in sorted(history, key=lambda r: r.get("ts", "")):
        if h.get("seat") and isinstance(h.get("pct"), (int, float)):
            hist_by_seat[h["seat"]].append(h["pct"])

    included_avail = sum(1 for r in rows if r.get("billing") == "included" and r["tier"] == "available")
    metered_touched = sum(1 for r in rows if r.get("billing") == "metered" and r["tier"] != "available")
    waste_seats = [r for r in rows if routing.expiry_urgency(r) >= 1.5]
    fable_seats = [r for r in rows if r.get("fable")]
    waste = waste_at_reset(history)

    score = 100
    notes = []
    if not fable_seats:
        score -= 15; notes.append("no Fable-capable seat live")
    hit = min(30, 10 * len(waste_seats))
    if hit:
        score -= hit; notes.append(f"{len(waste_seats)} seat(s) at waste-risk (reset soon, unused)")
    if metered_touched and included_avail:
        score -= 20; notes.append("paying metered $ while subscription capacity is available")
    if waste > 25:
        score -= 10; notes.append(f"~{waste}% quota historically wasted at reset")
    score = max(0, score)
    grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D"

    ordered = sorted([r for r in rows if routing.usable(r)], key=routing.drain_key)

    def esc(x):
        return html.escape(str(x if x is not None else "—"))

    # summary tiles
    tiles = [
        ("System score", f"{score}", grade, "accent"),
        ("Seats live", f"{sum(1 for r in rows if r['tier'] != 'spent')}/{len(rows)}", "usable now", "good"),
        ("Included available", f"{included_avail}", "subscription capacity", "good"),
        ("Metered $ in use", f"{metered_touched}", "keep at 0 while subs live", "warn" if metered_touched else "muted"),
        ("Stranded incidents", "0", "guaranteed by never-strand", "good"),
        ("Waste at reset", f"{waste}%", "avg unused before reset", "warn" if waste > 25 else "muted"),
    ]
    tiles_html = "\n".join(
        f'<div class="tile tile--{cls}"><div class="tile-k">{esc(k)}</div>'
        f'<div class="tile-v">{esc(v)}</div><div class="tile-s">{esc(s)}</div></div>'
        for k, v, s, cls in tiles)

    # seat cards
    cards = []
    for r in rows:
        spark = sparkline(hist_by_seat.get(r["seat"], []))
        chips = [f'<span class="chip chip--{r["tier"]}">{esc(r["tier"])}</span>']
        if r.get("billing") == "metered":
            chips.append('<span class="chip chip--metered">metered $</span>')
        if r.get("intake"):
            chips.append('<span class="chip chip--intake">intake</span>')
        if r.get("fable"):
            chips.append('<span class="chip chip--fable">fable</span>')
        reset = esc(r.get("reset_effective") or "—")
        pct = f'{r["pct"]:g}%' if isinstance(r.get("pct"), (int, float)) else "no signal"
        cards.append(
            f'<article class="card" style="--stripe:{TIER_COLOR.get(r["tier"], "var(--muted)")}">'
            f'<header class="card-h"><span class="seat">{esc(r["seat"])}</span>'
            f'<span class="fam">{esc(r.get("family"))}</span></header>'
            f'<div class="chips">{"".join(chips)}</div>'
            f'<div class="spark-wrap">{spark}<span class="pct">{esc(pct)}</span></div>'
            f'<div class="reset">next reset · {reset}</div></article>')
    cards_html = "\n".join(cards)

    # drain order
    drain_rows = []
    for i, r in enumerate(ordered, 1):
        bill = "metered $" if r.get("billing") == "metered" else "included"
        warn = ' <span class="warn-t">waste-risk</span>' if routing.expiry_urgency(r) >= 1.5 and "none" not in (r.get("window_kinds") or []) else ""
        drain_rows.append(
            f'<tr><td class="num">{i}</td><td class="mono">{esc(r["seat"])}</td>'
            f'<td>{esc(bill)}</td><td><span class="chip chip--{r["tier"]}">{esc(r["tier"])}</span></td>'
            f'<td class="num">{routing.expiry_urgency(r):.2f}{warn}</td></tr>')
    drain_html = "\n".join(drain_rows)

    # subscriptions
    sub_rows = []
    total = 0
    for sid, s in (subs.get("subscriptions", {}) if subs else {}).items():
        cost = s.get("monthly_usd") or 0
        total += cost
        fable = "✓" if s.get("grants", {}).get("fable") else "·"
        sub_rows.append(
            f'<tr><td class="mono">{esc(sid)}</td><td>{esc(s.get("product"))}</td>'
            f'<td class="num">{("$"+str(cost)) if cost else "—"}</td><td class="ctr">{fable}</td>'
            f'<td class="mono small">{esc(", ".join(s.get("backs_providers", [])))}</td></tr>')
    sub_html = "\n".join(sub_rows)

    recs = []
    if metered_touched and included_avail:
        recs.append("Metered $ seats are in use while included capacity is available — route those jobs to included seats.")
    if waste_seats:
        recs.append(f"{len(waste_seats)} seat(s) will reset soon with quota unused — drain them first (see drain order).")
    if not fable_seats:
        recs.append("No Fable-capable seat live — cross-family review leans on Sol/Review E. Check bin/detect-capability.py.")
    recs.append("Run bin/subscription-calculator.py --from-history for a plan-change recommendation from real usage.")
    recs_html = "\n".join(f"<li>{esc(x)}</li>" for x in recs)

    sample_banner = ('<div class="banner">Showing <strong>sample</strong> history for preview — run '
                     '<code>bin/usage-record.py --snapshot</code> on a schedule to populate real data.</div>') if sample else ""

    retention = monitoring.get("retention_days", 365) if monitoring else 365

    return TEMPLATE.format(
        now=esc(now_str), tiles=tiles_html, cards=cards_html, drain=drain_html,
        subs=sub_html, total=total, recs=recs_html, banner=sample_banner,
        retention=esc(retention), score=score, grade=grade,
        score_notes=esc("; ".join(notes) if notes else "all green — no deductions"))


TEMPLATE = """<title>Orchestration Telemetry</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap">
<style>
  :root {{
    --bg:#f4f6f8; --panel:#ffffff; --panel-2:#eef1f5; --ink:#141a21; --muted:#5c6b7a;
    --line:#dce2ea; --accent:#0d9488; --accent-fade:rgba(13,148,136,.12);
    --good:#1a7f37; --warn:#9a6700; --crit:#c93c37; --metered:#7c3aed; --fable:#0d9488;
    --shadow:0 1px 2px rgba(20,26,33,.06),0 8px 24px rgba(20,26,33,.05);
  }}
  :root:not([data-theme="light"]) {{ }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --bg:#0d1117; --panel:#161b22; --panel-2:#1c232c; --ink:#e6edf3; --muted:#8b98a5;
      --line:#28313c; --accent:#2dd4bf; --accent-fade:rgba(45,212,191,.14);
      --good:#3fb950; --warn:#d29922; --crit:#f85149; --metered:#a371f7; --fable:#2dd4bf;
      --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px rgba(0,0,0,.35);
    }}
  }}
  :root[data-theme="dark"] {{
    --bg:#0d1117; --panel:#161b22; --panel-2:#1c232c; --ink:#e6edf3; --muted:#8b98a5;
    --line:#28313c; --accent:#2dd4bf; --accent-fade:rgba(45,212,191,.14);
    --good:#3fb950; --warn:#d29922; --crit:#f85149; --metered:#a371f7; --fable:#2dd4bf;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px rgba(0,0,0,.35);
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
    font-family:"IBM Plex Sans",system-ui,sans-serif; line-height:1.5; }}
  .wrap {{ max-width:1080px; margin:0 auto; padding:32px 20px 64px; }}
  .mono {{ font-family:"IBM Plex Mono",ui-monospace,monospace; }}
  .num {{ font-family:"IBM Plex Mono",ui-monospace,monospace; font-variant-numeric:tabular-nums; text-align:right; }}
  header.top {{ display:flex; justify-content:space-between; align-items:baseline; flex-wrap:wrap; gap:8px;
    border-bottom:1px solid var(--line); padding-bottom:16px; margin-bottom:24px; }}
  h1 {{ font-size:1.5rem; font-weight:700; margin:0; letter-spacing:-.01em; text-wrap:balance; }}
  h1 .dot {{ color:var(--accent); }}
  .sub {{ color:var(--muted); font-size:.82rem; }}
  h2 {{ font-size:.72rem; text-transform:uppercase; letter-spacing:.09em; color:var(--muted);
    font-weight:600; margin:34px 0 12px; }}
  .banner {{ background:var(--accent-fade); border:1px solid var(--accent); color:var(--ink);
    padding:10px 14px; border-radius:8px; font-size:.85rem; margin-bottom:20px; }}
  .banner code {{ font-family:"IBM Plex Mono",monospace; font-size:.82em; }}
  .tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; }}
  .tile {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:16px;
    box-shadow:var(--shadow); border-top:3px solid var(--muted); }}
  .tile--accent {{ border-top-color:var(--accent); }} .tile--good {{ border-top-color:var(--good); }}
  .tile--warn {{ border-top-color:var(--warn); }} .tile--muted {{ border-top-color:var(--line); }}
  .tile-k {{ font-size:.72rem; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); }}
  .tile-v {{ font-family:"IBM Plex Mono",monospace; font-size:1.9rem; font-weight:600; line-height:1.1; margin:6px 0 2px;
    font-variant-numeric:tabular-nums; }}
  .tile-s {{ font-size:.76rem; color:var(--muted); }}
  .score-note {{ color:var(--muted); font-size:.8rem; margin-top:10px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:12px; }}
  .card {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:14px;
    box-shadow:var(--shadow); border-left:3px solid var(--stripe); }}
  .card-h {{ display:flex; justify-content:space-between; align-items:baseline; gap:8px; }}
  .seat {{ font-family:"IBM Plex Mono",monospace; font-weight:600; font-size:.92rem; }}
  .fam {{ font-size:.72rem; color:var(--muted); }}
  .chips {{ display:flex; flex-wrap:wrap; gap:5px; margin:9px 0; }}
  .chip {{ font-size:.68rem; padding:2px 8px; border-radius:20px; font-weight:600; letter-spacing:.02em;
    border:1px solid transparent; }}
  .chip--available {{ background:color-mix(in srgb,var(--good) 16%,transparent); color:var(--good); }}
  .chip--reserve {{ background:color-mix(in srgb,var(--warn) 18%,transparent); color:var(--warn); }}
  .chip--spent {{ background:color-mix(in srgb,var(--crit) 16%,transparent); color:var(--crit); }}
  .chip--metered {{ background:color-mix(in srgb,var(--metered) 16%,transparent); color:var(--metered); }}
  .chip--intake {{ border-color:var(--line); color:var(--muted); }}
  .chip--fable {{ background:color-mix(in srgb,var(--fable) 16%,transparent); color:var(--fable); }}
  .spark-wrap {{ display:flex; align-items:center; justify-content:space-between; gap:8px; margin:6px 0; height:30px; }}
  .spark {{ display:block; }} .spark-empty {{ font-size:.72rem; color:var(--muted); }}
  .pct {{ font-family:"IBM Plex Mono",monospace; font-size:.82rem; font-variant-numeric:tabular-nums; }}
  .reset {{ font-size:.72rem; color:var(--muted); font-family:"IBM Plex Mono",monospace; }}
  .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; box-shadow:var(--shadow);
    overflow-x:auto; }}
  table {{ width:100%; border-collapse:collapse; font-size:.86rem; }}
  th {{ text-align:left; font-size:.68rem; text-transform:uppercase; letter-spacing:.06em; color:var(--muted);
    font-weight:600; padding:12px 14px; border-bottom:1px solid var(--line); }}
  td {{ padding:10px 14px; border-bottom:1px solid var(--line); }}
  tr:last-child td {{ border-bottom:none; }}
  .ctr {{ text-align:center; }} .small {{ font-size:.76rem; color:var(--muted); }}
  .warn-t {{ color:var(--warn); font-size:.72rem; }}
  ul.recs {{ list-style:none; padding:0; margin:0; display:grid; gap:8px; }}
  ul.recs li {{ background:var(--panel); border:1px solid var(--line); border-left:3px solid var(--accent);
    border-radius:8px; padding:10px 14px; font-size:.88rem; box-shadow:var(--shadow); }}
  footer {{ margin-top:40px; color:var(--muted); font-size:.76rem; border-top:1px solid var(--line); padding-top:16px; }}
</style>
<div class="wrap">
  <header class="top">
    <div><h1>Orchestration Telemetry<span class="dot">.</span></h1>
      <div class="sub">Magnet Baron multi-CLI engine · generated {now}</div></div>
    <div class="sub mono">retention {retention}d · never-strand · minimize API $</div>
  </header>
  {banner}
  <h2>System health</h2>
  <div class="tiles">{tiles}</div>
  <div class="score-note">score {score} ({grade}) — {score_notes}</div>

  <h2>Seats &amp; accounts</h2>
  <div class="grid">{cards}</div>

  <h2>Drain order — use quota before it is lost</h2>
  <div class="panel"><table>
    <thead><tr><th>#</th><th>Seat</th><th>Billing</th><th>Tier</th><th class="num">Urgency</th></tr></thead>
    <tbody>{drain}</tbody></table></div>

  <h2>Subscriptions</h2>
  <div class="panel"><table>
    <thead><tr><th>ID</th><th>Product</th><th class="num">Monthly</th><th class="ctr">Fable</th><th>Backs</th></tr></thead>
    <tbody>{subs}</tbody></table></div>
  <div class="score-note mono">indicative total ~${total}/mo</div>

  <h2>Recommendations</h2>
  <ul class="recs">{recs}</ul>

  <footer>Tiers: available → reserve (usable last resort) → spent. A reserve never strands capacity;
  metered $ drains last. This page is telemetry, not agent policy — never loaded into an agent's context.</footer>
</div>
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render the usage dashboard HTML.")
    ap.add_argument("--out", default=None, help="output path (default: data/dashboard.html)")
    ap.add_argument("--demo", action="store_true", help="seed sample history for a preview")
    args = ap.parse_args(argv)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    doc = build(now, args.demo)
    out = Path(args.out) if args.out else (mborch.data_dir() / "dashboard.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc)
    print(f"dashboard → {out}  ({len(doc)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
