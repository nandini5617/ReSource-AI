"""Resource Explorer page: browse, filter, inspect and request exchanges.

Business logic stays in the backend:
  * stats.search_resources(...)                 read-only search
  * tools.dispatch("find_matches", ...)         organisation matching
  * tools.dispatch("create_exchange_request")   creates a PENDING request only
Approval and completion are NOT available here (Exchanges page only).
"""
from __future__ import annotations

import streamlit as st

import database
import knowledge as K
import stats
import tools
import ui_theme

STATUS_BADGE = {
    "available": "🟢 available",
    "requested": "🟡 requested",
    "transferred": "✅ transferred",
}
CARD_LIMIT = 30
COLUMNS = 3


def _notice() -> None:
    """Show (once) the message left by the previous action."""
    note = st.session_state.pop("exp_notice", None)
    if note:
        getattr(st, note[0])(note[1])


def _filters() -> dict:
    c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
    query = c1.text_input("Search", key="exp_query",
                          placeholder="name, material, notes or city")
    category = c2.selectbox("Category", ["All"] + K.CATEGORIES, key="exp_category")
    condition = c3.selectbox("Condition", ["All"] + K.CONDITIONS, key="exp_condition")
    status = c4.selectbox("Status", ["All", "available", "requested", "transferred"],
                          key="exp_status")
    return {
        "query": query,
        "category": None if category == "All" else category,
        "condition": None if condition == "All" else condition,
        "status": None if status == "All" else status,
    }


def _view_button(resource_id: int) -> bool:
    """Full-width button that works on older and newer Streamlit versions."""
    key = f"exp_view_{resource_id}"
    try:
        return st.button("View details", key=key, width="stretch")
    except TypeError:
        return st.button("View details", key=key, use_container_width=True)


def _card(resource: dict) -> None:
    with st.container(border=True):
        st.markdown(f"**{resource['name'][:48]}**")
        st.caption(f"#{resource['id']} · {resource['category']} · {resource['condition']}")
        st.write(f"{resource['quantity']:g} {resource['unit']} · {resource['location']}")
        ui_theme.status_badge(resource["status"])
        st.caption(f"Suggested action: {resource['disposition']}")
        if _view_button(resource["id"]):
            st.session_state["exp_selected"] = resource["id"]


def _details(resource_id: int) -> None:
    resource = database.get_resource(resource_id)
    if not resource:
        st.warning("That resource no longer exists.")
        st.session_state.pop("exp_selected", None)
        return

    st.divider()
    st.subheader(f"#{resource['id']} {resource['name']}")
    left, right = st.columns(2)
    with left:
        st.write(f"**Category:** {resource['category']}")
        st.write(f"**Material:** {resource['material'] or '-'}")
        st.write(f"**Condition:** {resource['condition']}")
        st.write(f"**Quantity:** {resource['quantity']:g} {resource['unit']}")
    with right:
        st.write(f"**City:** {resource['location']}")
        st.write(f"**Suggested action:** {resource['disposition']}")
        st.write(f"**Status:** {STATUS_BADGE.get(resource['status'], resource['status'])}")
        st.write(f"**Registered:** {resource['created_at']}")
    if resource.get("notes"):
        st.write(f"**Notes:** {resource['notes']}")

    st.markdown("#### Recommended organisations")
    out = tools.dispatch("find_matches", {"resource_id": resource_id})
    if "error" in out:
        st.error(out["error"])
        return
    st.caption(out["note"])

    can_request = resource["status"] == "available"
    if not can_request:
        st.info(f"This resource is '{resource['status']}', so a new request cannot be "
                "created. Manage existing requests on the Exchanges page.")
    if not out["matches"]:
        st.info("No organisation in the directory accepts this item in this condition.")

    for match in out["matches"]:
        title = f"{match['name']}: {match['score']}/100 ({match['role']}, {match['city']})"
        with st.expander(title):
            st.progress(min(100, max(0, int(match["score"]))) / 100)
            for reason in match["reasons"]:
                st.write("- " + reason)
            message = st.text_input("Message to the organisation (optional)",
                                    key=f"exp_msg_{resource_id}_{match['org_id']}")
            if st.button("Request exchange", key=f"exp_req_{resource_id}_{match['org_id']}",
                         disabled=not can_request):
                made = tools.dispatch("create_exchange_request", {
                    "resource_id": resource_id, "org_id": match["org_id"],
                    "message": message})
                if "error" in made:
                    st.session_state["exp_notice"] = ("error", made["error"])
                else:
                    text = (f"Exchange #{made['exchange_id']} created (pending). "
                            "Confirm the organisation's reply on the Exchanges page.")
                    if made.get("warning"):
                        text += " Warning: " + made["warning"]
                    st.session_state["exp_notice"] = ("success", text)
                st.rerun()

    if st.button("Close details", key="exp_close"):
        st.session_state.pop("exp_selected", None)
        st.rerun()


def render() -> None:
    ui_theme.page_header(
        "Explorer",
        "Browse resources, filter them and find organisations that could take them.",
        "📦",
    )
    st.caption("Organisations are SAMPLE directory entries; availability must be "
               "confirmed with them. Match scores are rule-based, not guarantees.")
    _notice()

    filters = _filters()
    resources = stats.search_resources(limit=500, **filters)

    if not resources:
        ui_theme.empty_state("No resources match. Add one from the chat or the Add "
                             "Resource page, or clear the filters.")
    else:
        shown = resources[:CARD_LIMIT]
        st.write(f"Showing {len(shown)} of {len(resources)} resource(s).")
        for start in range(0, len(shown), COLUMNS):
            cols = st.columns(COLUMNS)
            for col, resource in zip(cols, shown[start:start + COLUMNS]):
                with col:
                    _card(resource)

    selected = st.session_state.get("exp_selected")
    if selected:
        _details(int(selected))