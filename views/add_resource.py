"""Add Resource page: describe an item or upload a photo, review, then save.

Safety and privacy:
  * Analysis only PRE-FILLS the form. Nothing is saved until the user presses
    "Save resource", and saving goes through tools.dispatch("save_resource").
  * This page never creates, approves, rejects or completes an exchange.
  * Photos are validated and analysed in memory by vision.py. They are never
    written to disk or the database.
  * A photo cannot show quantity, unit or city, so those start as clearly
    marked placeholders the user must confirm.

Helpers defined here (vision_status, vision_to_analysis, vision_markdown,
prefill_from_vision, validate_upload) are reused by views/chat.py.
"""
from __future__ import annotations

import streamlit as st

import knowledge as K
import tools
import ui_theme
import vision
from config import get_vision_providers, is_mock_mode
from views import _common

PHOTO_TYPES = ["jpg", "jpeg", "png", "webp"]

PROVIDER_NOTE = {
    "groq": "Groq (verified working in this project's live test)",
    "gemini": "Gemini (optional; may fail if its quota is exhausted)",
    "openrouter": "OpenRouter (only if a vision model is configured)",
}


# --------------------------------------------------------- pure helpers
def vision_status() -> dict:
    """Describe whether photo analysis can run. Never reads or shows keys."""
    if is_mock_mode():
        return {
            "state": "offline",
            "providers": [],
            "message": "Offline demo mode: photos are NOT analysed. You can still "
                       "fill in the form by hand.",
        }
    providers = get_vision_providers()
    if not providers:
        return {
            "state": "none",
            "providers": [],
            "message": "No vision-capable provider is configured, so photo analysis "
                       "is unavailable. Images are never sent to text-only models. "
                       "You can describe the item in text instead.",
        }
    names = [PROVIDER_NOTE.get(p, p) for p in providers]
    message = "Photo analysis will try, in order: " + "; ".join(names) + "."
    if "gemini" in providers:
        message += " If one provider fails, the next is used automatically."
    return {"state": "ready", "providers": providers, "message": message}


def _pick(value, allowed: list[str], default: str) -> str:
    text = str(value or "").strip().lower()
    return text if text in allowed else default


def vision_to_analysis(result: dict) -> dict:
    """Turn a vision result into the same shape the text analyser returns.

    Quantity, unit and city are placeholders: a photo cannot show them.
    """
    provider = result.get("provider") or "unknown"
    model = result.get("model") or ""
    return {
        "name": str(result.get("name") or "Unidentified item")[:80],
        "category": _pick(result.get("category"), K.CATEGORIES, "other"),
        "condition": _pick(result.get("visible_condition"), K.CONDITIONS, "fair"),
        "disposition": _pick(result.get("disposition"), K.DISPOSITIONS, "reuse"),
        "quantity": 1.0,
        "unit": "pieces",
        "location": K.DEFAULT_CITY,
        "material": _pick(result.get("category"), K.CATEGORIES, "other"),
        "reasoning": str(result.get("reasoning") or ""),
        "hazardous": result.get("hazardous") is True,
        "source": f"photo analysis ({provider}{' / ' + model if model else ''})",
        "ideas": list(result.get("ideas") or []),
        "confidence": result.get("confidence") or "low",
        "from_photo": True,
        "notes_hint": f"Suggested from a photo by {provider}; details confirmed by me.",
    }


def vision_markdown(result: dict) -> str:
    """Readable summary of a photo analysis (plain markdown, no HTML)."""
    provider = result.get("provider") or "unknown"
    model = result.get("model") or ""
    via = f"{provider} / {model}" if model else provider
    lines = [
        f"**Photo analysis** (via {via})",
        "",
        f"- **Item:** {result.get('name', 'Unidentified item')}",
        f"- **Category:** {result.get('category', 'other')}",
        f"- **Visible condition:** {result.get('visible_condition', 'fair')}",
        f"- **Suggested action:** {result.get('disposition', 'reuse')}",
        f"- **Confidence:** {result.get('confidence', 'low')}",
    ]
    if result.get("hazardous") is True:
        lines.append("- ⚠️ **Possibly hazardous:** use an authorised hazardous-waste channel.")
    if result.get("reasoning"):
        lines += ["", result["reasoning"]]
    ideas = result.get("ideas") or []
    if ideas:
        lines += ["", "**Ideas:**"] + [f"- {idea}" for idea in ideas]
    if result.get("limitations"):
        lines += ["", f"*{result['limitations']}*"]
    return "\n".join(lines)


def _index(options: list[str], value, default: int = 0) -> int:
    return options.index(value) if value in options else default


def validate_upload(uploaded) -> tuple[bytes | None, str | None]:
    """Check an uploaded photo. Returns (data, None) or (None, error message)."""
    if uploaded is None:
        return None, None
    data = uploaded.getvalue()
    try:
        vision.validate_image(data, uploaded.name)
    except vision.VisionError as exc:
        return None, str(exc)
    return data, None


# ---------------------------------------------------------- state changes
def _set_analysis(analysis: dict, vision_result: dict | None = None) -> None:
    st.session_state["analysis"] = analysis
    st.session_state["vision"] = vision_result
    st.session_state["analysis_serial"] = st.session_state.get("analysis_serial", 0) + 1


def _clear_analysis() -> None:
    st.session_state["analysis"] = None
    st.session_state["vision"] = None


def prefill_from_vision(result: dict) -> None:
    """Button callback (used by the chat page): load a photo result into the form."""
    _set_analysis(vision_to_analysis(result), result)
    _common.go_to("Add Resource")


# ------------------------------------------------------------------ panels
def _text_panel() -> None:
    description = st.text_area(
        "Describe the item",
        height=100,
        key="add_description",
        placeholder="e.g. 2 old wooden study tables, one with a loose leg, Gurugram",
    )
    if st.button("Analyse description", key="add_analyse_text"):
        if not (description or "").strip():
            st.error("Please describe the item first.")
        else:
            with st.spinner("Analysing..."):
                out = tools.dispatch("analyze_resource", {"description": description})
            if "error" in out:
                st.error(out["error"])
            else:
                _set_analysis(out)


def _photo_panel() -> None:
    serial = st.session_state.get("photo_serial", 0)
    status = vision_status()
    if status["state"] == "ready":
        st.caption(status["message"])
    elif status["state"] == "offline":
        st.warning(status["message"])
    else:
        st.error(status["message"])

    uploaded = st.file_uploader(
        "Photo of the item (JPG, PNG or WEBP)",
        type=PHOTO_TYPES,
        key=f"add_photo_{serial}",
    )
    data, problem = validate_upload(uploaded)
    if problem:
        st.error(problem)
    elif data:
        st.image(data, caption=uploaded.name, width=320)
        st.caption("The photo is analysed in memory and is not saved anywhere.")

    hint = st.text_input(
        "Optional hint (e.g. 'about 5 of these, in Noida')",
        key=f"add_photo_hint_{serial}",
    )
    clicked = st.button(
        "Analyse photo",
        key="add_analyse_photo",
        disabled=(data is None or status["state"] == "none"),
    )
    if clicked and data is not None:
        with st.spinner("Analysing the photo..."):
            try:
                result = vision.analyze_image(data, uploaded.name, hint or "")
            except vision.VisionError as exc:
                st.error(str(exc))
            else:
                _set_analysis(vision_to_analysis(result), result)


# ------------------------------------------------------------- review form
def _review_form() -> None:
    a = st.session_state.get("analysis")
    if not a:
        return
    serial = st.session_state.get("analysis_serial", 0)

    st.subheader("Review and save")
    st.info(
        f"Analysis source: {a.get('source', 'unknown')}. "
        "Review and edit before saving. Nothing is saved until you press Save."
    )

    if a.get("from_photo"):
        v = st.session_state.get("vision") or {}
        st.warning(
            "This is a suggestion from a photo (confidence: "
            f"{a.get('confidence', 'low')}). Quantity, unit and city below are "
            "PLACEHOLDERS. Please set them yourself, and check the condition."
        )
        if v:
            with st.expander("Photo analysis details"):
                st.markdown(vision_markdown(v))
    elif a.get("reasoning"):
        st.write(f"**Reasoning:** {a['reasoning']}")

    if a.get("hazardous"):
        st.warning("Possibly hazardous: use an authorised hazardous-waste channel.")

    with st.form(f"save_form_{serial}"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Name", a.get("name", ""), key=f"f_name_{serial}")
        location = c2.text_input(
            "City", a.get("location", K.DEFAULT_CITY), key=f"f_city_{serial}"
        )
        c3, c4, c5 = st.columns(3)
        category = c3.selectbox(
            "Category", K.CATEGORIES,
            index=_index(K.CATEGORIES, a.get("category")), key=f"f_cat_{serial}",
        )
        condition = c4.selectbox(
            "Condition", K.CONDITIONS,
            index=_index(K.CONDITIONS, a.get("condition")), key=f"f_cond_{serial}",
        )
        disposition = c5.selectbox(
            "Recommended action", K.DISPOSITIONS,
            index=_index(K.DISPOSITIONS, a.get("disposition")), key=f"f_disp_{serial}",
        )
        c6, c7, c8 = st.columns(3)
        quantity = c6.number_input(
            "Quantity", min_value=0.01, value=float(a.get("quantity") or 1.0),
            step=1.0, key=f"f_qty_{serial}",
        )
        unit = c7.selectbox(
            "Unit", K.UNITS, index=_index(K.UNITS, a.get("unit")), key=f"f_unit_{serial}"
        )
        material = c8.text_input(
            "Material", a.get("material", ""), key=f"f_mat_{serial}"
        )
        notes = st.text_input(
            "Notes (optional)", a.get("notes_hint", ""), key=f"f_notes_{serial}"
        )
        submitted = st.form_submit_button("Save resource")

    if submitted:
        saved = tools.dispatch("save_resource", {
            "name": name, "category": category, "condition": condition,
            "quantity": quantity, "unit": unit, "location": location,
            "disposition": disposition, "material": material, "notes": notes,
        })
        if "error" in saved:
            st.error(saved["error"])
        else:
            _clear_analysis()
            _common.flash(
                "success",
                f"Saved as resource #{saved['resource_id']}. "
                "Find matches for it on the Explorer page.",
            )
            st.rerun()

    if st.button("Discard this analysis", key=f"discard_{serial}"):
        _clear_analysis()
        st.rerun()


# -------------------------------------------------------------------- page
def render() -> None:
    ui_theme.page_header(
        "Add Resource",
        "Describe an item or upload a photo, review the suggestion, then save it.",
        "➕",
    )
    _common.show_flash()

    tab_text, tab_photo = st.tabs(["✍️ Describe it", "📷 Upload a photo"])
    with tab_text:
        _text_panel()
    with tab_photo:
        _photo_panel()

    _review_form()
