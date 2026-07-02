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
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db as dbmod  # noqa: E402


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


def main() -> None:
    st.set_page_config(page_title="AI-SDLC Dashboard", page_icon="🤖", layout="wide")
    st.title("🤖 AI-SDLC Dashboard")
    st.caption("Pillar 7 — usage + attribution, read together. Metrics: docs/methodology/continuous-improvement.md.")
    sessions = load("sessions")
    commits = load("commits")
    tab1, tab2 = st.tabs(["Utilization", "Commit attribution"])
    with tab1:
        utilization_tab(sessions)
    with tab2:
        attribution_tab(commits, sessions)


if __name__ == "__main__":
    main()
