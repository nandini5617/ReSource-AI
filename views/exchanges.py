"""Exchanges page: track requests and record the user's real-world confirmations.

SAFETY-CRITICAL. Approval and completion are USER-ONLY actions:
  checkbox ticked  ->  button enabled  ->  tools.<user-only function>(eid, True)
The AI agent cannot reach these functions. tools.py re-checks everything, so a
UI mistake here cannot approve or complete an exchange by itself.
"""
from __future__ import annotations

import streamlit as st

import database
import stats
import tools
import ui_theme

FILTERS = ["All", "pending", "approved", "completed", "rejected", "cancelled"]


def _notify(kind: str, message: str) -> None:
    st.session_state.setdefault("ex_notice", []).append((kind, message))


def _show_notices() -> None:
    for kind, message in st.session_state.pop("ex_notice", []):
        getattr(st, kind)(message)


def _report(result: dict, ok_message: str) -> None:
    """Turn a tools.* result into messages shown on the next run."""
    if "error" in result:
        _notify("error", result["error"])
        return
    _notify("success", ok_message)
    est = result.get("impact_logged")
    if est:
        _notify("info",
                f"Impact recorded ({est['label']}): ~{est['kg_diverted']} kg diverted, "
                f"~{est['co2e_avoided_kg']} kg CO2e avoided.")


def _details(ex: dict, resource: dict | None, org: dict | None) -> None:
    left, right = st.columns(2)
    with left:
        st.markdown("**Resource**")
        if resource:
            st.write(f"{resource['name']} (#{resource['id']})")
            st.write(f"{resource['category']} · {resource['condition']} · "
                     f"{resource['quantity']:g} {resource['unit']} · {resource['location']}")
        else:
            st.write("Record not found.")
    with right:
        st.markdown("**Organisation (sample directory entry)**")
        if org:
            st.write(f"{org['name']}")
            st.write(f"{org['org_type']} · role: {org['role']} · "
                     f"{org['city']}" + (f" ({org['area']})" if org.get("area") else ""))
        else:
            st.write("Record not found.")
    if ex.get("message"):
        st.write(f"**Your message:** {ex['message']}")

    st.markdown("**Timeline**")
    for event in stats.exchange_timeline(ex):
        when = event["time"] or event["note"] or ""
        st.write(f"- {event['event']}" + (f" — {when}" if when else ""))


def _actions(ex: dict) -> None:
    eid = ex["id"]

    if ex["status"] == "pending":
        ok = st.checkbox("I confirm the organisation has accepted this exchange",
                         key=f"ok_appr_{eid}")
        c1, c2, c3 = st.columns(3)
        if c1.button("Approve", key=f"appr_{eid}", disabled=not ok):
            _report(tools.confirm_exchange_approval(eid, True),
                    f"Exchange #{eid} approved.")
            st.rerun()
        if c2.button("Organisation declined", key=f"rej_{eid}", disabled=not ok):
            _report(tools.reject_exchange(eid, True),
                    f"Exchange #{eid} marked as rejected.")
            st.rerun()
        if c3.button("Cancel request", key=f"canc_{eid}"):
            _report(tools.cancel_exchange(eid), f"Exchange #{eid} cancelled.")
            st.rerun()
        st.caption("Tick the box first. It also enables 'Organisation declined' "
                   "(it records the organisation's decision).")

    elif ex["status"] == "approved":
        ok = st.checkbox("I confirm the physical hand-over really happened",
                         key=f"ok_comp_{eid}")
        c1, c2 = st.columns(2)
        if c1.button("Mark completed", key=f"comp_{eid}", disabled=not ok):
            _report(tools.confirm_exchange_completion(eid, True),
                    f"Exchange #{eid} completed.")
            st.rerun()
        if c2.button("Cancel request", key=f"canc2_{eid}"):
            _report(tools.cancel_exchange(eid), f"Exchange #{eid} cancelled.")
            st.rerun()
        st.caption("Completing records the estimated environmental impact once.")

    else:
        st.caption(f"This exchange is {ex['status']}. No further action is possible.")


def render() -> None:
    ui_theme.page_header(
        "Exchanges",
        "Only you can approve or complete an exchange. The AI agent cannot.",
        "🔁",
    )
    _show_notices()
    st.caption("Approve only after the organisation really accepted; complete only "
               "after the physical hand-over really happened.")

    choice = st.selectbox("Show", FILTERS, key="ex_filter")
    exchanges = database.list_exchanges(200)
    if choice != "All":
        exchanges = [e for e in exchanges if e["status"] == choice]

    if not exchanges:
        ui_theme.empty_state("No exchange requests to show. Request one from the "
                             "Explorer or the AI chat.")
        return

    for ex in exchanges:
        resource = database.get_resource(ex["resource_id"])
        org = database.get_org(ex["org_id"])
        title = (f"#{ex['id']} · {ex['status'].upper()} · "
                 f"{resource['name'][:40] if resource else '?'} → "
                 f"{org['name'] if org else '?'}")
        with st.expander(title, expanded=ex["status"] in ("pending", "approved")):
            ui_theme.status_badge(ex["status"])
            _details(ex, resource, org)
            st.divider()
            _actions(ex)