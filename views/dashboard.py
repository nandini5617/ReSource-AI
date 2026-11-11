"""Dashboard page: counts, estimated impact, categories and recent activity.

Read-only. All numbers come from stats.py; nothing here writes to the database.
"""
from __future__ import annotations

import streamlit as st

import stats
import ui_theme
from views import _common


def render() -> None:
    ui_theme.page_header(
        "Dashboard",
        "Your resources, exchanges and estimated impact at a glance.",
        "📊",
    )
    _common.show_flash()

    counts = stats.dashboard_counts()

    if counts["total_resources"] == 0:
        ui_theme.empty_state(
            "No resources yet. Describe an item in the AI chat or register one "
            "to get started."
        )
        left, right = st.columns(2)
        with left:
            _common.goto_button("Open AI Chat", "AI Chat", "dash_goto_chat")
        with right:
            _common.goto_button("Add a resource", "Add Resource", "dash_goto_add")
        return

    ui_theme.metric_cards([
        ("Total resources", counts["total_resources"]),
        ("Available", counts["available_resources"], "ready to be requested"),
        ("Pending exchanges", counts["pending_exchanges"], "waiting for your decision"),
        ("Completed exchanges", counts["completed_exchanges"]),
    ])
    st.write("")
    ui_theme.metric_cards([
        ("Approved exchanges", counts["approved_exchanges"],
         "awaiting hand-over confirmation"),
        ("Resources transferred", counts["transferred_resources"]),
        ("Waste diverted (kg, est.)", counts["kg_diverted_estimate"]),
        ("CO2e avoided (kg, est.)", counts["co2e_avoided_kg_estimate"]),
    ])
    st.write("")
    ui_theme.estimate_note()

    if counts["pending_exchanges"] or counts["approved_exchanges"]:
        st.write("")
        if counts["pending_exchanges"]:
            st.info(
                f"{counts['pending_exchanges']} exchange request(s) are waiting "
                "for you to record the organisation's decision."
            )
        if counts["approved_exchanges"]:
            st.info(
                f"{counts['approved_exchanges']} approved exchange(s) are waiting "
                "for you to confirm the physical hand-over."
            )
        _common.goto_button("Go to Exchanges", "Exchanges", "dash_goto_exchanges")

    st.write("")
    chart_col, recent_col = st.columns([1, 2])

    with chart_col:
        st.subheader("Resources by category")
        distribution = stats.category_distribution()
        if distribution:
            try:
                import pandas as pd

                frame = pd.DataFrame(distribution).set_index("category")["count"]
                _common.show_bar_chart(frame)
            except ImportError:
                _common.show_table(distribution)

    with recent_col:
        st.subheader("Recent resources")
        _common.show_table(
            _common.resource_rows(stats.recent_resources(6), compact=True)
        )

    st.subheader("Recent exchanges")
    recent = stats.recent_exchanges(6)
    if recent:
        _common.show_table(_common.exchange_rows(recent))
    else:
        ui_theme.empty_state(
            "No exchange requests yet. Find a match for a resource to start one."
        )
