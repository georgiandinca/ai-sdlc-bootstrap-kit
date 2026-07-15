#!/usr/bin/env python3
"""AI-SDLC dashboard (board pillar 4 / 7). Two tabs over a local SQLite DB:
Utilization (AI session cost/outcome/grounding) and Commit attribution
(AI / mixed / human by LOC, from collect_commits.py). Volume is always shown
next to a quality metric — never volume alone.

Run:
    pip install -r dashboard/requirements.txt
    streamlit run dashboard/app.py
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db as dbmod  # noqa: E402

import json

import roi as roimod

_PRICES = Path(__file__).resolve().parents[1] / "scripts" / "spend" / "prices.json"
EUR_PER_USD = (json.loads(_PRICES.read_text(encoding="utf-8")).get("eur_per_usd", 1.0)
               if _PRICES.exists() else 1.0)


@st.cache_data(ttl=30)
def load(table: str) -> pd.DataFrame:
    conn = dbmod.connect()
    try:
        df = pd.read_sql_query(f"SELECT * FROM {table}", conn, parse_dates=["ts"])
    finally:
        conn.close()
    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce").dt.tz_localize(None)
    return df


def _date_filter(df: pd.DataFrame, key: str) -> pd.DataFrame:
    if df.empty:
        return df
    dmin, dmax = df["ts"].min().date(), df["ts"].max().date()
    drange = st.sidebar.date_input("Date range", (dmin, dmax), key=key)
    if isinstance(drange, (list, tuple)) and len(drange) == 2:
        lo, hi = pd.Timestamp(drange[0]), pd.Timestamp(drange[1]) + pd.Timedelta(days=1)
        return df[(df["ts"] >= lo) & (df["ts"] < hi)]
    return df


def utilization_tab(sessions: pd.DataFrame) -> None:
    if sessions.empty:
        st.info("No sessions yet. Seed rows are in seed.sql; your harness writes real ones.")
        return
    view = _date_filter(sessions, "util_dates")
    if view.empty:
        st.warning("No sessions in range."); return
    n = len(view)
    accepted = int((view["outcome"] == "accepted").sum())
    reworked = int((view["outcome"] == "reworked").sum())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sessions", n)
    c2.metric("Acceptance rate", f"{accepted / n:.0%}")
    c3.metric("Rework rate", f"{reworked / n:.0%}")
    c4.metric("Grounding rate", f"{view['grounded'].mean():.0%}")
    left, right = st.columns(2)
    with left:
        st.subheader("Sessions by seat")
        st.bar_chart(view.groupby("seat").size().rename("sessions"))
    with right:
        st.subheader("Outcome mix")
        st.bar_chart(view.groupby("outcome").size().rename("sessions"))


def attribution_tab(commits: pd.DataFrame, sessions: pd.DataFrame) -> None:
    if commits.empty:
        st.info("No commits yet. Run `python3 dashboard/collect_commits.py` to populate.")
        return
    view = _date_filter(commits, "attr_dates")
    if view.empty:
        st.warning("No commits in range."); return
    n = len(view)
    ai = int((view["klass"].isin(["ai", "ai-assisted"])).sum())
    mixed = int((view["klass"] == "mixed").sum())
    ai_loc = int(view["ai_lines"].sum())
    total_loc = int(view["ai_lines"].sum() + view["human_lines"].sum()) or 1
    # quality pairing: rework rate from sessions over the same window
    rework = "—"
    if not sessions.empty:
        s = _sessions_in_range(sessions, view)
        if len(s):
            rework = f"{(s['outcome'] == 'reworked').mean():.0%}"
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Commits", n)
    c2.metric("AI-involved", f"{ai / n:.0%}")
    c3.metric("Mixed", f"{mixed / n:.0%}")
    c4.metric("AI lines", f"{ai_loc / total_loc:.0%}")
    c5.metric("Rework rate (quality)", rework, help="Read volume next to quality — never alone.")
    st.caption("Deep defect-linkage (which bug fixed which AI code) is Phase 4 (knowledge graph).")
    left, right = st.columns(2)
    with left:
        st.subheader("Commits by class")
        st.bar_chart(view.groupby("klass").size().rename("commits"))
        st.subheader("Lines by class")
        st.bar_chart(pd.Series({"ai": view["ai_lines"].sum(), "human": view["human_lines"].sum()}))
    with right:
        st.subheader("Class over time")
        ot = view.assign(day=view["ts"].dt.date).groupby(["day", "klass"]).size().unstack(fill_value=0)
        st.line_chart(ot)
        by = "seat" if view["seat"].notna().any() else "author_name"
        st.subheader(f"AI lines by {by}")
        st.bar_chart(view.groupby(by)["ai_lines"].sum())
    st.subheader("Recent commits")
    st.dataframe(
        view.sort_values("ts", ascending=False)[
            ["ts", "author_name", "seat", "klass", "source", "ai_lines", "human_lines", "subject", "tool"]
        ],
        use_container_width=True, hide_index=True,
    )


def _sessions_in_range(sessions: pd.DataFrame, commits_view: pd.DataFrame) -> pd.DataFrame:
    lo, hi = commits_view["ts"].min(), commits_view["ts"].max()
    return sessions[(sessions["ts"] >= lo) & (sessions["ts"] <= hi)]


def waste_tab(sessions: pd.DataFrame, spend: pd.DataFrame) -> None:
    """Technique-pack validation (token-economy.md): each chart names the
    technique it validates; a technique with no effect after two sprints is a
    deletion candidate at retro."""
    if sessions.empty:
        st.info("No sessions yet — scripts/session/collect-usage.sh writes real rows on SessionEnd.")
        return
    view = _date_filter(sessions, "waste_dates")
    if view.empty:
        st.warning("No sessions in range."); return
    view = view.copy()
    view["cache_read_tokens"] = view.get("cache_read_tokens", 0).fillna(0)
    total_tokens = (view["tokens_in"] + view["tokens_out"]).sum() or 1
    accepted = int((view["outcome"] == "accepted").sum())
    rework_tokens = (view.loc[view["outcome"].isin(["reworked", "rejected"]),
                              ["tokens_in", "tokens_out"]].sum().sum())
    cache_denom = view["cache_read_tokens"].sum() + view["tokens_in"].sum() or 1
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cost / accepted outcome",
              f"${view['cost_usd'].sum() / accepted:.2f}" if accepted else "—",
              help="Headline: total AI $ ÷ accepted sessions. Should fall over time.")
    c2.metric("Rework burn", f"{rework_tokens / total_tokens:.0%}",
              help="Tokens spent in reworked/rejected sessions — the #1 waste lever (technique 5).")
    c3.metric("Cache-hit ratio", f"{view['cache_read_tokens'].sum() / cache_denom:.0%}",
              help="cache_read ÷ (cache_read + fresh input) — technique 2, prompt-cache hygiene.")
    c4.metric("Unattributed", f"{view['ticket'].isna().mean():.0%}",
              help="Sessions with no ticket. Visible, never dropped.")
    left, right = st.columns(2)
    with left:
        st.subheader("Cost by model — technique 1 (routing)")
        st.bar_chart(view.groupby(view["model"].fillna("unknown"))["cost_usd"].sum())
        st.subheader("Tokens per session — technique 3 (context hygiene)")
        st.bar_chart((view["tokens_in"] + view["tokens_out"]).reset_index(drop=True))
    with right:
        st.subheader("Cost: grounded vs ungrounded — technique 4")
        st.bar_chart(view.groupby(view["grounded"].map({0: "ungrounded", 1: "grounded"}))["cost_usd"].sum())
        st.subheader("Cache-hit ratio by seat — technique 2")
        ratios = view.groupby("seat").apply(
            lambda g: g["cache_read_tokens"].sum()
            / max(1, g["cache_read_tokens"].sum() + g["tokens_in"].sum()))
        st.bar_chart(ratios)
    unpriced = view["notes"].fillna("").str.contains("unpriced models")
    if unpriced.any():
        st.warning(f"{int(unpriced.sum())} session(s) contain unpriced models "
                   "(cost recorded as 0) — update scripts/spend/prices.json.")
    if not spend.empty:
        st.subheader("Non-session spend (granularity is the honesty flag)")
        st.dataframe(spend, use_container_width=True, hide_index=True)


def roi_tab() -> None:
    conn = dbmod.connect()
    try:
        summary = roimod.roi_summary(conn, EUR_PER_USD)
        rows = roimod.ticket_rows(conn)
        col1, col2 = st.columns(2)
        start = col1.date_input("Period start", key="roi_start",
                                value=pd.Timestamp.today().replace(day=1))
        end = col2.date_input("Period end (incl.)", key="roi_end",
                              value=pd.Timestamp.today())
        end_excl = end + timedelta(days=1)
        rollup = roimod.period_rollup(conn, str(start), str(end_excl), EUR_PER_USD)
    finally:
        conn.close()
    used, closed = summary["coverage"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("ROI", f"{summary['roi']:.2f}" if summary["roi"] is not None else "—",
              help="Value delivered ÷ (human cost + AI cost). 1.4 ⇒ 1 dev + AI ≈ 1.4 devs.")
    c2.metric("Evidence band",
              f"{summary['band'][0]:.2f}–{summary['band'][1]:.2f}" if summary["band"] else "—",
              help="Range across evidence tiers: calibration > pre-estimate > velocity > post-hoc.")
    c3.metric("Coverage", f"{used} / {closed}",
              help="Closed tickets included in the ratio — never a cherry-picked subset.")
    c4.metric("AI € this period", f"€{rollup['ai_total_eur']:.0f}",
              help="Session tokens + amortized subscriptions/invoices, counted once.")
    if summary["flagged"]:
        st.warning("Flagged (actual < 0.1 day, review before trusting): "
                   + ", ".join(summary["flagged"]))
    st.subheader("Per-ticket detail")
    df = pd.DataFrame(rows)
    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.subheader("HDE trend (by close month)")
        df2 = df.dropna(subset=["hde", "closed_at"]).copy()
        if not df2.empty:
            df2["month"] = df2["closed_at"].str[:7]
            st.line_chart(df2.groupby("month")["hde"].mean())
    else:
        st.info("No closed tickets yet — run scripts/spend/import_tickets.py.")
    label = f"{start} → {end}"
    st.download_button(
        "Download client report (HTML)",
        data=roimod.render_client_report(summary, rollup, rows, label),
        file_name=f"ai-roi-report-{start}.html", mime="text/html",
    )
    st.caption("Methodology: HDE = estimate ÷ actual; evidence tiers weight the band; "
               "per-ticket AI cost is session tokens only, coarse spend joins at period level.")


def main() -> None:
    st.set_page_config(page_title="AI-SDLC Dashboard", page_icon="🤖", layout="wide")
    st.title("🤖 AI-SDLC Dashboard")
    st.caption("Pillar 7 — usage + attribution, read together. Metrics: docs/methodology/continuous-improvement.md.")
    sessions = load("sessions")
    commits = load("commits")
    spend = load("spend")
    tab1, tab2, tab3, tab4 = st.tabs(
        ["Utilization", "Commit attribution", "Waste signals", "ROI"])
    with tab1:
        utilization_tab(sessions)
    with tab2:
        attribution_tab(commits, sessions)
    with tab3:
        waste_tab(sessions, spend)
    with tab4:
        roi_tab()


if __name__ == "__main__":
    main()
