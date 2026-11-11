"""ReSource AI - Streamlit interface (navigation shell).

Run:  streamlit run app.py

This file only wires things together. Every page lives in views/ and calls the
backend (tools.py, stats.py, database.py). Exchange approval and completion
are USER-ONLY actions on the Exchanges page; the AI agent cannot perform them.
"""
from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="ReSource AI", page_icon="♻️", layout="wide")

import database  # noqa: E402
import ui_theme  # noqa: E402
from config import is_mock_mode, redact  # noqa: E402
from views import _common  # noqa: E402
from views import (  # noqa: E402
    add_resource,
    chat,
    dashboard,
    exchanges,
    explorer,
    impact,
)

database.init_db()
ui_theme.apply_theme()
_common.init_state()

PAGE_RENDERERS = {
    "Dashboard": dashboard.render,
    "AI Chat": chat.render,
    "Add Resource": add_resource.render,
    "Explorer": explorer.render,
    "Exchanges": exchanges.render,
    "Impact": impact.render,
}
PAGE_ICONS = {
    "Dashboard": "📊",
    "AI Chat": "💬",
    "Add Resource": "➕",
    "Explorer": "📦",
    "Exchanges": "🔁",
    "Impact": "🌍",
}


def _sidebar() -> None:
    with st.sidebar:
        st.title("♻️ ReSource AI")
        st.caption("SecondLife + WasteWise: give resources a second life.")

        st.radio(
            "Navigate",
            _common.PAGES,
            key="nav",
            format_func=lambda page: f"{PAGE_ICONS.get(page, '')} {page}",
        )
        st.divider()

        # Only shown when results come from keyword rules instead of cloud AI,
        # so offline output is never mistaken for real AI output.
        if is_mock_mode():
            st.warning("Offline demo mode: keyword rules, no cloud AI.")

        if st.button("Clear chat and session memory", key="sidebar_clear"):
            if "agent" in st.session_state:
                st.session_state.agent.reset()
            st.session_state.chat = []
            st.rerun()
        st.caption(
            "Organisations are SAMPLE directory entries. Impact numbers are "
            "ESTIMATES from generic factors, not verified measurements."
        )


def main() -> None:
    _sidebar()
    page = st.session_state.get("nav", _common.PAGES[0])
    renderer = PAGE_RENDERERS.get(page, dashboard.render)
    try:
        renderer()
    except Exception as exc:  # noqa: BLE001 - one broken page must not kill the app
        st.error(f"Sorry, the '{page}' page hit an error: {redact(str(exc))}")
        st.caption("Other pages still work. Please report this error text.")


main()