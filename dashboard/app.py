"""Ops dashboard: lead funnel, outcomes, bookings and call health.

Run from the project root: streamlit run dashboard/app.py
"""

import json
import os
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path(os.environ.get("DB_PATH", "data/rider_agent.db"))

OUTCOME_LABELS = {
    "qualified_booked": "Qualified & booked",
    "not_qualified": "Not qualified",
    "not_interested": "Not interested",
    "follow_up_needed": "Follow-up needed",
}


@st.cache_data(ttl=5)
def query(sql: str) -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(sql, conn)


def percent(numerator: int, denominator: int) -> str:
    return f"{numerator / denominator:.0%}" if denominator else "n/a"


def render_kpis(leads: pd.DataFrame, attempts: pd.DataFrame, outcomes: pd.DataFrame) -> None:
    finished = attempts[attempts["status"] != "initiated"]
    connected = int((finished["status"] == "connected").sum())
    booked = int((outcomes["outcome"] == "qualified_booked").sum())
    judged = outcomes["matches_agent"].dropna()

    columns = st.columns(5)
    columns[0].metric("Leads", len(leads))
    columns[1].metric("Calls placed", len(attempts))
    columns[2].metric("Connect rate", percent(connected, len(finished)))
    columns[3].metric("Booked", booked, help="Qualified leads with an onboarding slot")
    columns[4].metric(
        "Lead to booking",
        percent(booked, len(leads)),
        help="Verdict agreement with the agent: " + percent(int(judged.sum()), len(judged)),
    )


def render_charts(leads: pd.DataFrame, outcomes: pd.DataFrame, bookings: pd.DataFrame) -> None:
    left, right = st.columns(2)
    with left:
        st.subheader("Call outcomes")
        if outcomes.empty:
            st.info("No completed calls yet.")
        else:
            counts = outcomes["outcome"].map(OUTCOME_LABELS).value_counts()
            st.bar_chart(counts)
    with right:
        st.subheader("Why leads did not qualify")
        reasons = outcomes["reason"].dropna().value_counts()
        if reasons.empty:
            st.info("No disqualified leads yet.")
        else:
            st.bar_chart(reasons)

    left, right = st.columns(2)
    with left:
        st.subheader("Lead pipeline")
        st.bar_chart(leads["status"].value_counts())
    with right:
        st.subheader("Bookings by centre")
        if bookings.empty:
            st.info("No bookings yet.")
        else:
            st.bar_chart(bookings["centre"].value_counts())


def render_calls(outcomes: pd.DataFrame) -> None:
    st.subheader("Recent calls")
    if outcomes.empty:
        return
    table = outcomes[
        ["updated_at", "name", "city", "language", "outcome", "reason", "matches_agent"]
    ].copy()
    table["outcome"] = table["outcome"].map(OUTCOME_LABELS)
    st.dataframe(table, use_container_width=True, hide_index=True)

    with_transcript = outcomes[outcomes["transcript"].notna()]
    if with_transcript.empty:
        return
    chosen = st.selectbox(
        "Transcript",
        with_transcript["interaction_id"],
        format_func=lambda i: f"{with_transcript.set_index('interaction_id').loc[i, 'name']} ({i})",
    )
    raw = with_transcript.set_index("interaction_id").loc[chosen, "transcript"]
    try:
        turns = json.loads(raw)
        for turn in turns:
            st.chat_message("assistant" if turn.get("role") == "agent" else "user").write(
                turn.get("en_text", "")
            )
    except (json.JSONDecodeError, AttributeError):
        st.text(raw)


def main() -> None:
    st.set_page_config(page_title="Rider Onboarding Agent", layout="wide")
    st.title("Swiggy Rider Onboarding: Voice Agent Ops")
    if not DB_PATH.exists():
        st.warning(f"No database at {DB_PATH}. Start the backend first: rider-agent serve")
        return

    leads = query("SELECT * FROM leads")
    attempts = query("SELECT * FROM attempts")
    outcomes = query("SELECT * FROM outcomes ORDER BY updated_at DESC")
    bookings = query(
        "SELECT b.created_at, s.city, s.centre, s.starts_at FROM bookings b "
        "JOIN slots s ON s.id = b.slot_id"
    )

    render_kpis(leads, attempts, outcomes)
    render_charts(leads, outcomes, bookings)
    render_calls(outcomes)
    st.sidebar.caption(f"Database: {DB_PATH}")
    st.sidebar.button("Refresh")


main()
