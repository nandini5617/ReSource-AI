"""Modern green-and-white theme and small UI helpers for ReSource AI.

Pure presentation: this module never touches the database, the AI providers,
or any exchange logic. Dynamic text is HTML-escaped before it is rendered.

Usage (once, near the top of app.py, after st.set_page_config):
    import ui_theme
    ui_theme.apply_theme()
"""
from __future__ import annotations

import html

import streamlit as st

PALETTE = {
    "primary": "#1B7F4C",
    "primary_dark": "#0F5132",
    "accent": "#2FA866",
    "soft": "#EAF7EF",
    "page": "#F6FBF8",
    "card": "#FFFFFF",
    "border": "#D3EADB",
    "text": "#16301F",
    "muted": "#5B7364",
}

# status -> (label, text colour, background colour)
STATUS_STYLES = {
    "available": ("Available", "#0F5132", "#D8F3E2"),
    "requested": ("Requested", "#7A5300", "#FFF1CC"),
    "transferred": ("Transferred", "#0B4F6C", "#D9EEF8"),
    "pending": ("Pending", "#7A5300", "#FFF1CC"),
    "approved": ("Approved", "#0F5132", "#D8F3E2"),
    "completed": ("Completed", "#0B4F6C", "#D9EEF8"),
    "rejected": ("Rejected", "#7B1E1E", "#FBE0E0"),
    "cancelled": ("Cancelled", "#4A4A4A", "#EAEAEA"),
}

_CSS = f"""
<style>
.stApp {{
    background: {PALETTE['page']};
    color: {PALETTE['text']};
}}
[data-testid="stHeader"] {{
    background: transparent;
}}
[data-testid="stSidebar"] {{
    background: {PALETTE['soft']};
    border-right: 1px solid {PALETTE['border']};
}}
.block-container {{
    padding-top: 2rem;
    padding-bottom: 3rem;
    max-width: 1200px;
}}
h1, h2, h3 {{
    color: {PALETTE['primary_dark']};
    letter-spacing: -0.01em;
}}

/* Buttons */
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {{
    border-radius: 10px;
    border: 1px solid {PALETTE['primary']};
    background: {PALETTE['primary']};
    color: #FFFFFF;
    font-weight: 600;
    transition: background 0.15s ease, box-shadow 0.15s ease;
}}
.stButton > button:hover, .stDownloadButton > button:hover,
[data-testid="stFormSubmitButton"] > button:hover {{
    background: {PALETTE['primary_dark']};
    border-color: {PALETTE['primary_dark']};
    color: #FFFFFF;
    box-shadow: 0 2px 8px rgba(15, 81, 50, 0.25);
}}
.stButton > button:disabled, [data-testid="stFormSubmitButton"] > button:disabled {{
    background: #DCE8E0;
    border-color: #DCE8E0;
    color: #8A9C90;
    box-shadow: none;
}}

/* Inputs */
[data-baseweb="input"], [data-baseweb="select"] > div, textarea {{
    border-radius: 10px !important;
}}

/* Expanders and forms */
[data-testid="stExpander"] {{
    background: {PALETTE['card']};
    border: 1px solid {PALETTE['border']};
    border-radius: 12px;
}}
[data-testid="stForm"] {{
    background: {PALETTE['card']};
    border: 1px solid {PALETTE['border']};
    border-radius: 14px;
}}

/* Chat */
[data-testid="stChatMessage"] {{
    background: {PALETTE['card']};
    border: 1px solid {PALETTE['border']};
    border-radius: 14px;
}}

/* Custom components */
.rs-header {{
    background: linear-gradient(135deg, {PALETTE['primary_dark']} 0%, {PALETTE['accent']} 100%);
    color: #FFFFFF;
    border-radius: 16px;
    padding: 1.4rem 1.6rem;
    margin-bottom: 1.2rem;
    box-shadow: 0 4px 14px rgba(15, 81, 50, 0.18);
}}
.rs-header h1 {{
    color: #FFFFFF;
    margin: 0;
    padding: 0;
    font-size: 1.8rem;
}}
.rs-header p {{
    margin: 0.3rem 0 0 0;
    color: #E3F6EA;
    font-size: 0.98rem;
}}
.rs-card {{
    background: {PALETTE['card']};
    border: 1px solid {PALETTE['border']};
    border-radius: 14px;
    padding: 1rem 1.1rem;
    box-shadow: 0 1px 4px rgba(15, 81, 50, 0.06);
    height: 100%;
}}
.rs-metric-label {{
    color: {PALETTE['muted']};
    font-size: 0.82rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}}
.rs-metric-value {{
    color: {PALETTE['primary_dark']};
    font-size: 2rem;
    font-weight: 700;
    line-height: 1.2;
    margin-top: 0.15rem;
}}
.rs-metric-hint {{
    color: {PALETTE['muted']};
    font-size: 0.8rem;
    margin-top: 0.2rem;
}}
.rs-badge {{
    display: inline-block;
    padding: 0.12rem 0.65rem;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
}}
.rs-empty {{
    background: {PALETTE['soft']};
    border: 1px dashed {PALETTE['accent']};
    color: {PALETTE['primary_dark']};
    border-radius: 14px;
    padding: 1.2rem;
    text-align: center;
}}
.rs-note {{
    background: #FFF9E6;
    border-left: 4px solid #E0B100;
    color: #5C4800;
    border-radius: 8px;
    padding: 0.7rem 0.9rem;
    font-size: 0.88rem;
}}
</style>
"""


# ------------------------------------------------------------ pure builders
def status_badge_html(status: str | None) -> str:
    """HTML for a coloured status pill. Unknown statuses get a neutral style."""
    key = (status or "").lower()
    label, fg, bg = STATUS_STYLES.get(
        key, (status or "unknown", "#4A4A4A", "#EAEAEA")
    )
    return (
        f'<span class="rs-badge" style="color:{fg};background:{bg};">'
        f"{html.escape(str(label))}</span>"
    )


def metric_card_html(label: str, value, hint: str = "") -> str:
    """HTML for one metric card. All text is escaped."""
    hint_html = (
        f'<div class="rs-metric-hint">{html.escape(str(hint))}</div>' if hint else ""
    )
    return (
        '<div class="rs-card">'
        f'<div class="rs-metric-label">{html.escape(str(label))}</div>'
        f'<div class="rs-metric-value">{html.escape(str(value))}</div>'
        f"{hint_html}</div>"
    )


def page_header_html(title: str, subtitle: str = "", icon: str = "") -> str:
    icon_part = f"{html.escape(icon)} " if icon else ""
    sub = f"<p>{html.escape(subtitle)}</p>" if subtitle else ""
    return (
        f'<div class="rs-header"><h1>{icon_part}{html.escape(title)}</h1>{sub}</div>'
    )


# ------------------------------------------------------------ streamlit API
def apply_theme() -> None:
    """Inject the global CSS. Call once per script run, near the top."""
    st.markdown(_CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "", icon: str = "") -> None:
    st.markdown(page_header_html(title, subtitle, icon), unsafe_allow_html=True)


def status_badge(status: str | None) -> None:
    st.markdown(status_badge_html(status), unsafe_allow_html=True)


def metric_cards(items: list[tuple]) -> None:
    """Render a row of metric cards.

    items: list of (label, value) or (label, value, hint) tuples.
    """
    if not items:
        return
    columns = st.columns(len(items))
    for column, item in zip(columns, items):
        label, value, *rest = item
        hint = rest[0] if rest else ""
        column.markdown(metric_card_html(label, value, hint), unsafe_allow_html=True)


def empty_state(message: str) -> None:
    st.markdown(
        f'<div class="rs-empty">{html.escape(message)}</div>', unsafe_allow_html=True
    )


def estimate_note(text: str | None = None) -> None:
    """Standard honesty note shown next to environmental numbers."""
    message = text or (
        "Impact figures are ESTIMATES from generic factors, not verified "
        "measurements. They are recorded only after you confirm a completed hand-over."
    )
    st.markdown(
        f'<div class="rs-note">{html.escape(message)}</div>', unsafe_allow_html=True
    )
