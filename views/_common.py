"""Shared helpers for all ReSource AI pages.

Presentation and session-state plumbing only. No business logic lives here:
saving, matching and exchange changes stay in tools.py / database.py, and
read-only queries stay in stats.py.
"""
from __future__ import annotations

from datetime import datetime

import streamlit as st

PAGES = [
    "Dashboard",
    "AI Chat",
    "Add Resource",
    "Explorer",
    "Exchanges",
    "Impact",
]

STATUS_LABEL = {
    "pending": "🟡 pending",
    "approved": "🟢 approved",
    "completed": "✅ completed",
    "rejected": "🔴 rejected",
    "cancelled": "⚪ cancelled",
}

_FLASH_KINDS = ("success", "info", "warning", "error")


# ------------------------------------------------------------ session state
def init_state() -> None:
    """Create the session keys every page relies on (safe to call every run)."""
    st.session_state.setdefault("chat", [])
    st.session_state.setdefault("analysis", None)
    st.session_state.setdefault("vision", None)
    st.session_state.setdefault("analysis_serial", 0)
    st.session_state.setdefault("photo_serial", 0)
    st.session_state.setdefault("flash", [])
    st.session_state.setdefault("nav", PAGES[0])


def get_agent():
    """Return the session's ResourceAgent, creating it on first use."""
    if "agent" not in st.session_state:
        from agent import ResourceAgent  # imported lazily: keeps this module light

        st.session_state.agent = ResourceAgent()
    return st.session_state.agent


# ------------------------------------------------------------------- flash
def flash(kind: str, message: str) -> None:
    """Queue a message to show on the next run (survives st.rerun())."""
    if kind not in _FLASH_KINDS:
        kind = "info"
    st.session_state.flash.append((kind, message))


def show_flash() -> None:
    """Display and clear queued messages."""
    queued = st.session_state.get("flash", [])
    st.session_state.flash = []
    for kind, message in queued:
        if kind not in _FLASH_KINDS:
            kind = "info"
        getattr(st, kind)(message)


def report(result: dict, ok_message: str) -> None:
    """Turn a tools.* result into flash messages."""
    if "error" in result:
        flash("error", result["error"])
        return
    flash("success", ok_message)
    est = result.get("impact_logged")
    if est:
        flash(
            "info",
            f"Impact recorded ({est['label']}): ~{est['kg_diverted']} kg diverted, "
            f"~{est['co2e_avoided_kg']} kg CO2e avoided.",
        )


# -------------------------------------------------------------- navigation
def go_to(page: str) -> None:
    """Button callback: switch the sidebar navigation to another page."""
    if page in PAGES:
        st.session_state["nav"] = page


def goto_button(label: str, page: str, key: str) -> None:
    st.button(label, key=key, on_click=go_to, args=(page,))


# --------------------------------------------------------------- formatting
def format_time(value, missing: str = "not recorded") -> str:
    """Readable form of a stored ISO timestamp. Never invents a time."""
    if not value:
        return missing
    try:
        return datetime.fromisoformat(str(value)).strftime("%d %b %Y, %H:%M")
    except ValueError:
        return str(value)


def quantity_text(quantity, unit) -> str:
    try:
        return f"{float(quantity):g} {unit}"
    except (TypeError, ValueError):
        return f"{quantity} {unit}"


def resource_rows(resources: list[dict], compact: bool = False) -> list[dict]:
    """Table rows for resources. compact=True leaves out city and action."""
    rows = []
    for r in resources:
        row = {
            "ID": r["id"],
            "Name": r["name"],
            "Category": r["category"],
            "Condition": r["condition"],
            "Qty": quantity_text(r["quantity"], r["unit"]),
        }
        if not compact:
            row["City"] = r.get("location") or ""
            row["Action"] = r.get("disposition") or ""
        row["Status"] = r["status"]
        row["Added"] = format_time(r.get("created_at"))
        rows.append(row)
    return rows


def exchange_rows(exchanges: list[dict]) -> list[dict]:
    """Table rows for stats.recent_exchanges() style records."""
    return [
        {
            "ID": e["id"],
            "Resource": e.get("resource") or "?",
            "Organisation": e.get("organisation") or "?",
            "Status": STATUS_LABEL.get(e["status"], e["status"]),
            "Created": format_time(e.get("created_at")),
            "Updated": format_time(e.get("updated_at")),
        }
        for e in exchanges
    ]


# ------------------------------------------------------------------ widgets
def show_table(rows: list[dict]) -> None:
    """Full-width table that works on older and newer Streamlit versions."""
    try:
        st.dataframe(rows, hide_index=True, width="stretch")
    except TypeError:
        st.dataframe(rows, hide_index=True, use_container_width=True)


def show_bar_chart(frame, color: str = "#1B7F4C") -> None:
    """Bar chart in the theme colour; falls back if 'color' is unsupported."""
    try:
        st.bar_chart(frame, color=color)
    except TypeError:
        st.bar_chart(frame)
