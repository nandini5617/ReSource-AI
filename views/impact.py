"""Impact page: ESTIMATED sustainability analytics and a downloadable report.

Read-only. Numbers come from stats.py (impact_log rows written only after the
user confirms a completed hand-over). Everything is labelled as an estimate.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime

import streamlit as st

import impact as impact_model
import stats
import ui_theme
from views import _common

CSV_COLUMNS = [
    ("record", "record"), ("exchange_id", "exchange_id"),
    ("resource", "resource"), ("category", "category"),
    ("action", "action"), ("organisation", "organisation"),
    ("kg_diverted", "kg_diverted_ESTIMATE"),
    ("co2e_avoided_kg", "co2e_avoided_kg_ESTIMATE"),
    ("created_at", "recorded_at"),
]
DISCLAIMER = ("All environmental values are ESTIMATES from generic, placeholder "
              "factors. They are not verified measurements.")


# ------------------------------------------------------------ pure builders
def csv_safe(value):
    """Neutralise spreadsheet formulas in text cells; numbers pass through."""
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return value
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def build_csv(rows: list[dict]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([header for _, header in CSV_COLUMNS])
    for row in rows:
        writer.writerow([csv_safe(row.get(key)) for key, _ in CSV_COLUMNS])
    return out.getvalue()


def build_report_md(counts: dict, by_category: list[dict], generated: str) -> str:
    lines = [
        "# ReSource AI impact report",
        "",
        f"Generated: {generated}",
        "",
        f"> {DISCLAIMER}",
        "",
        "## Totals (estimates)",
        "",
        f"- Completed exchanges: {counts['completed_exchanges']}",
        f"- Waste diverted: ~{counts['kg_diverted_estimate']} kg (estimate)",
        f"- CO2e avoided: ~{counts['co2e_avoided_kg_estimate']} kg (estimate)",
        "",
        "## By category (estimates)",
        "",
        "| Category | Transfers | kg diverted | kg CO2e avoided |",
        "|---|---|---|---|",
    ]
    for r in by_category:
        lines.append(f"| {r['category']} | {r['transfers']} | {r['kg']} | {r['co2e']} |")
    if not by_category:
        lines.append("| (none yet) | 0 | 0 | 0 |")
    lines += [
        "",
        "Impact is recorded only after a user confirms that the physical "
        "hand-over happened. Organisations in the directory are sample entries.",
    ]
    return "\n".join(lines)


def trend_rows(by_date: list[dict]) -> list[dict]:
    """Add a running (cumulative) CO2e total to the per-day rows."""
    total = 0.0
    rows = []
    for r in by_date:
        total += float(r["co2e"] or 0)
        rows.append({**r, "cumulative_co2e": round(total, 2)})
    return rows


# --------------------------------------------------------------- widgets
def _line_chart(frame, color: str = "#1B7F4C") -> None:
    try:
        st.line_chart(frame, color=color)
    except TypeError:
        st.line_chart(frame)


def render() -> None:
    ui_theme.page_header(
        "Impact",
        "Estimated waste diverted and CO2e avoided from completed exchanges.",
        "🌍",
    )
    _common.show_flash()

    counts = stats.dashboard_counts()
    by_category = stats.impact_by_category()
    by_date = stats.impact_by_date()

    ui_theme.estimate_note(DISCLAIMER + " Impact is recorded only after you confirm "
                           "a completed hand-over.")
    st.write("")

    if counts["completed_exchanges"] == 0 and not by_category:
        ui_theme.empty_state(
            "No impact recorded yet. It appears here after you confirm a completed "
            "hand-over on the Exchanges page."
        )
        _common.goto_button("Go to Exchanges", "Exchanges", "impact_goto_ex")
        _factors()
        return

    ui_theme.metric_cards([
        ("Completed exchanges", counts["completed_exchanges"]),
        ("Waste diverted (kg, est.)", counts["kg_diverted_estimate"]),
        ("CO2e avoided (kg, est.)", counts["co2e_avoided_kg_estimate"]),
        ("Categories", len(by_category)),
    ])
    st.write("")

    try:
        import pandas as pd
    except ImportError:
        pd = None

    left, right = st.columns(2)
    with left:
        st.subheader("CO2e avoided by category (est.)")
        if pd is not None and by_category:
            _common.show_bar_chart(pd.DataFrame(by_category).set_index("category")["co2e"])
    with right:
        st.subheader("Waste diverted by category (est.)")
        if pd is not None and by_category:
            _common.show_bar_chart(pd.DataFrame(by_category).set_index("category")["kg"])
    _common.show_table([
        {"Category": r["category"], "Transfers": r["transfers"],
         "kg diverted (est.)": r["kg"], "kg CO2e avoided (est.)": r["co2e"]}
        for r in by_category
    ])

    st.subheader("Trend over time (est.)")
    trend = trend_rows(by_date)
    if len(trend) >= 2 and pd is not None:
        _line_chart(pd.DataFrame(trend).set_index("day")[["cumulative_co2e"]])
        st.caption("Cumulative estimated CO2e avoided, by day.")
    elif trend:
        st.caption("A trend line needs at least two days of data. Daily totals so far:")
    _common.show_table([
        {"Day": r["day"], "Transfers": r["transfers"], "kg (est.)": r["kg"],
         "CO2e kg (est.)": r["co2e"], "Cumulative CO2e (est.)": r["cumulative_co2e"]}
        for r in trend
    ])

    st.subheader("Download report")
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    d1, d2 = st.columns(2)
    d1.download_button(
        "Download CSV (one row per transfer)",
        data=build_csv(stats.impact_report_rows()),
        file_name="resource_ai_impact.csv", mime="text/csv", key="impact_dl_csv",
    )
    d2.download_button(
        "Download summary (Markdown)",
        data=build_report_md(counts, by_category, generated),
        file_name="resource_ai_impact_report.md", mime="text/markdown",
        key="impact_dl_md",
    )
    _factors()


def _factors() -> None:
    with st.expander("How these estimates are calculated"):
        st.write("Estimate = weight × factor × action share. Weight comes from the "
                 "quantity you entered (pieces use a typical item weight). The factors "
                 "below are rough PLACEHOLDERS and should be replaced with values from "
                 "a published life-cycle database before the numbers are presented "
                 "as science.")
        _common.show_table([
            {"Category": c, "kg CO2e per kg (placeholder)": f}
            for c, f in impact_model.EMISSION_FACTORS.items()
        ])
        st.write("Action share: reuse 100%, repair 80%, recycle 50%, dispose 0%.")