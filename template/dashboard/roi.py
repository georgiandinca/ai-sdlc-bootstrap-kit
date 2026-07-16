#!/usr/bin/env python3
"""ROI logic for the dashboard (token-roi design §3, §6). Stdlib only so CI
can test it without pandas; app.py wraps these for display.

Per-ticket AI cost = session tokens only. Invoice/flat-rate spend cannot
honestly be split per ticket, so it joins the ROI at period level
(period_rollup) — coarse money is counted exactly once, where it is honest.
"""
from __future__ import annotations

import html
from datetime import date

TIER_ORDER = ["calibration", "pre-estimate", "velocity", "post-hoc"]


def _d(value):
    return date.fromisoformat(str(value)[:10])


def ticket_rows(conn):
    cols = ["ticket", "estimate_human_days", "actual_human_days", "day_rate_eur",
            "evidence_tier", "closed_at", "ai_cost_usd", "human_cost_eur",
            "value_eur", "hde", "flagged_low_actual"]
    return [dict(zip(cols, row)) for row in conn.execute(
        f"SELECT {', '.join(cols)} FROM roi_view ORDER BY closed_at")]


def amortized_spend_eur(conn, start_iso, end_iso):
    lo, hi = _d(start_iso), _d(end_iso)
    total = 0.0
    for ps, pe, cost in conn.execute(
            "SELECT period_start, period_end, cost_eur FROM spend"):
        p0, p1 = _d(ps), _d(pe)
        days = (p1 - p0).days
        if days <= 0:
            continue
        overlap = (min(p1, hi) - max(p0, lo)).days
        if overlap > 0:
            total += cost * overlap / days
    return total


def period_rollup(conn, start_iso, end_iso, eur_per_usd):
    sessions_usd = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM sessions WHERE ts >= ? AND ts < ?",
        (start_iso, end_iso)).fetchone()[0]
    spend_eur = amortized_spend_eur(conn, start_iso, end_iso)
    sessions_eur = sessions_usd * eur_per_usd
    return {"ai_sessions_eur": sessions_eur, "ai_spend_eur": spend_eur,
            "ai_total_eur": sessions_eur + spend_eur}


def _roi(rows, eur_per_usd):
    value = sum(r["value_eur"] for r in rows)
    cost = sum(r["human_cost_eur"] + r["ai_cost_usd"] * eur_per_usd for r in rows)
    return value / cost if cost > 0 else None


def roi_summary(conn, eur_per_usd):
    rows = ticket_rows(conn)          # closed tickets only (the view filters)
    usable = [r for r in rows
              if r["estimate_human_days"] is not None
              and r["actual_human_days"] is not None
              and not r["flagged_low_actual"]]
    per_tier = {}
    for tier in TIER_ORDER:
        tier_roi = _roi([r for r in usable if r["evidence_tier"] == tier], eur_per_usd)
        if tier_roi is not None:
            per_tier[tier] = tier_roi
    band = (min(per_tier.values()), max(per_tier.values())) if per_tier else None
    return {
        "roi": _roi(usable, eur_per_usd),
        "band": band,
        "per_tier": per_tier,
        "coverage": (len(usable), len(rows)),
        "flagged": sorted(r["ticket"] for r in rows if r["flagged_low_actual"]),
    }


def render_client_report(summary, rollup, rows, period_label):
    used, closed = summary["coverage"]
    roi_txt = f"{summary['roi']:.2f}" if summary["roi"] is not None else "n/a"
    band_txt = (f"{summary['band'][0]:.2f} – {summary['band'][1]:.2f}"
                if summary["band"] else "n/a")
    tier_rows = "".join(
        f"<tr><td>{html.escape(t)}</td><td>{v:.2f}</td></tr>"
        for t, v in summary["per_tier"].items())
    ticket_trs = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(r[c] if r[c] is not None else '—'))}</td>"
                         for c in ("ticket", "estimate_human_days",
                                   "actual_human_days", "ai_cost_usd", "hde",
                                   "evidence_tier")) + "</tr>"
        for r in rows)
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>AI ROI report — {html.escape(period_label)}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:52rem;margin:2rem auto;padding:0 1rem}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:.35rem .6rem;text-align:left}}
h1{{font-size:1.4rem}}.kpi{{font-size:2rem;font-weight:700}}.note{{color:#555;font-size:.85rem}}</style>
</head><body>
<h1>AI utilization &amp; ROI — {html.escape(period_label)}</h1>
<p class="kpi">ROI {roi_txt}</p>
<p>Evidence-weighted band: <strong>{band_txt}</strong> ·
   ROI computed over {used} of {closed} closed tickets.</p>
<p>AI spend this period: €{rollup['ai_total_eur']:.2f}
   (sessions €{rollup['ai_sessions_eur']:.2f} + subscriptions/invoices
   €{rollup['ai_spend_eur']:.2f}, flat-rate amortized pro-rata).</p>
<h2>ROI by evidence tier</h2><table><tr><th>Tier</th><th>ROI</th></tr>{tier_rows}</table>
<h2>Per-ticket detail</h2>
<table><tr><th>Ticket</th><th>Estimate (days)</th><th>Actual (days)</th>
<th>AI cost (USD)</th><th>HDE</th><th>Evidence</th></tr>{ticket_trs}</table>
<p class="note"><strong>Methodology.</strong> Value = pre-work estimate ×
day rate; cost = actual human-days × day rate + AI spend. Human-day-equivalent
(HDE) = estimate ÷ actual. Evidence tiers, strongest first: calibration A/B,
pre-work estimate, historical velocity, post-hoc judgment. Tickets without an
estimate or actual are excluded from the ratio but counted in coverage;
per-ticket AI cost covers session tokens only — invoice/flat-rate spend is
amortized at period level. Flagged tickets (actual &lt; 0.1 day):
{html.escape(', '.join(summary['flagged']) or 'none')}. Where the org cost
report and locally collected sessions cover the same tokens, period totals
count them twice — see scripts/spend/README.md; import the cost report only
for non-session API spend.</p>
</body></html>"""
