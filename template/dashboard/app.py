#!/usr/bin/env python3
"""AI-utilization dashboard (board pillar 4 / pillar 7: "Dashboard utilization — DB + web").

A minimal, runnable Streamlit app over a local SQLite DB (schema.sql). It surfaces the
small, stable metric set from docs/methodology/continuous-improvement.md so a human retro
can see how AI is used, what it costs, and whether it's grounded — then improve the rules.

Run:
    pip install -r dashboard/requirements.txt
    streamlit run dashboard/app.py

The DB is created and seeded from schema.sql on first run. Your agent harness writes real
rows into the `sessions` table (or you import an export of your AI tool's usage logs).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "utilization.db"
SCHEMA = HERE / "schema.sql"


def get_conn() -> sqlite3.Connection:
    first_run = not DB_PATH.exists()
    conn = sqlite3.connect(DB_PATH)
    if first_run and SCHEMA.exists():
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        conn.commit()
    return conn


@st.cache_data(ttl=30)
def load() -> pd.DataFrame:
    conn = get_conn()
    try:
        df = pd.read_sql_query("SELECT * FROM sessions", conn, parse_dates=["ts"])
    finally:
        conn.close()
    if not df.empty:
        df["tokens_total"] = df["tokens_in"] + df["tokens_out"]
    return df


def main() -> None:
    st.set_page_config(page_title="AI-SDLC Utilization", page_icon="🤖", layout="wide")
    st.title("🤖 AI-SDLC Utilization Dashboard")
    st.caption(
        "Pillar 7 — the human-in-the-loop feedback machine. "
        "Metrics defined in docs/methodology/continuous-improvement.md."
    )

    df = load()
    if df.empty:
        st.info("No sessions yet. Seed rows are in schema.sql; your harness writes real ones.")
        return

    # ---- Filters ---------------------------------------------------------
    seats = sorted(df["seat"].unique())
    picked = st.sidebar.multiselect("Seats", seats, default=seats)
    dmin, dmax = df["ts"].min().date(), df["ts"].max().date()
    drange = st.sidebar.date_input("Date range", (dmin, dmax))
    view = df[df["seat"].isin(picked)]
    if isinstance(drange, (list, tuple)) and len(drange) == 2:
        lo, hi = pd.Timestamp(drange[0]), pd.Timestamp(drange[1]) + pd.Timedelta(days=1)
        view = view[(view["ts"] >= lo) & (view["ts"] < hi)]

    if view.empty:
        st.warning("No sessions in the selected range.")
        return

    # ---- Headline metrics (the small, stable set) ------------------------
    n = len(view)
    accepted = (view["outcome"] == "accepted").sum()
    reworked = (view["outcome"] == "reworked").sum()
    acc_rate = accepted / n if n else 0
    cost_total = view["cost_usd"].sum()
    cost_per_accepted = cost_total / accepted if accepted else float("nan")
    grounding_rate = view["grounded"].mean() if n else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Sessions", n)
    c2.metric("Acceptance rate", f"{acc_rate:.0%}")
    c3.metric("Rework rate", f"{reworked / n:.0%}")
    c4.metric("Cost / accepted", f"${cost_per_accepted:,.2f}" if accepted else "—")
    c5.metric("Grounding rate", f"{grounding_rate:.0%}")

    st.divider()

    # ---- Charts ----------------------------------------------------------
    left, right = st.columns(2)
    with left:
        st.subheader("Sessions by seat")
        st.bar_chart(view.groupby("seat").size().rename("sessions"))
        st.subheader("Cost by seat ($)")
        st.bar_chart(view.groupby("seat")["cost_usd"].sum())
    with right:
        st.subheader("Outcome mix")
        st.bar_chart(view.groupby("outcome").size().rename("sessions"))
        st.subheader("Tokens over time")
        ts = view.set_index("ts").sort_index()["tokens_total"].resample("D").sum()
        st.line_chart(ts)

    st.divider()
    st.subheader("Sessions")
    st.dataframe(
        view.sort_values("ts", ascending=False)[
            ["ts", "seat", "tool", "task", "ticket", "tokens_total", "cost_usd", "outcome", "grounded"]
        ],
        use_container_width=True,
        hide_index=True,
    )


if __name__ == "__main__":
    main()
