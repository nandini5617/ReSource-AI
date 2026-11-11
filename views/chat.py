"""AI Chat page: talk to the ResourceAgent, or analyse a photo.

Safety:
  * The agent can create a PENDING exchange request and cancel one. It cannot
    approve, reject or complete an exchange; that stays with the user on the
    Exchanges page (enforced in tools.py, not here).
  * Photo analysis never saves anything. "Use in Add Resource" only pre-fills
    the form on the Add Resource page, where the user reviews and saves.
  * Photos are analysed in memory; only the text result is kept in the chat.
"""
from __future__ import annotations

import streamlit as st

import ui_theme
import vision
from views import _common
from views.add_resource import (
    prefill_from_vision,
    validate_upload,
    vision_markdown,
    vision_status,
)


def _render_history() -> None:
    for index, msg in enumerate(st.session_state.chat):
        with st.chat_message(msg["role"]):
            if msg.get("vision"):
                st.markdown(vision_markdown(msg["vision"]))
                st.button(
                    "Use in Add Resource",
                    key=f"chat_use_vision_{index}",
                    on_click=prefill_from_vision,
                    args=(msg["vision"],),
                )
                st.caption(
                    "This only fills the form. You set the quantity and city, "
                    "and nothing is saved until you press Save."
                )
                continue
            if msg.get("error"):
                st.error(msg["content"])
            else:
                st.markdown(msg["content"])
            if msg.get("trace"):
                with st.expander(f"Tools used ({len(msg['trace'])})"):
                    for step in msg["trace"]:
                        state = "ERROR" if "error" in step["result"] else "ok"
                        st.code(f"{step['tool']}({step['args']}) -> {state}")
            if msg.get("provider"):
                st.caption(f"Answered by: {msg['provider']}")


def _photo_expander() -> None:
    serial = st.session_state.get("photo_serial", 0)
    with st.expander("📷 Analyse a photo of an item"):
        status = vision_status()
        if status["state"] == "ready":
            st.caption(status["message"])
        elif status["state"] == "offline":
            st.warning(status["message"])
        else:
            st.error(status["message"])

        uploaded = st.file_uploader(
            "Photo (JPG, PNG or WEBP)",
            type=["jpg", "jpeg", "png", "webp"],
            key=f"chat_photo_{serial}",
        )
        data, problem = validate_upload(uploaded)
        if problem:
            st.error(problem)
        elif data:
            st.image(data, caption=uploaded.name, width=260)

        hint = st.text_input("Optional hint", key=f"chat_photo_hint_{serial}")
        clicked = st.button(
            "Analyse photo",
            key="chat_analyse_photo",
            disabled=(data is None or status["state"] == "none"),
        )
        if clicked and data is not None:
            with st.spinner("Analysing the photo..."):
                try:
                    result = vision.analyze_image(data, uploaded.name, hint or "")
                except vision.VisionError as exc:
                    st.error(str(exc))
                    return
            st.session_state.chat.append(
                {"role": "user", "content": f"📷 Photo: {uploaded.name}"}
            )
            st.session_state.chat.append(
                {"role": "assistant", "content": vision_markdown(result), "vision": result}
            )
            st.session_state["photo_serial"] = serial + 1  # clears the uploader
            st.rerun()


def render() -> None:
    ui_theme.page_header(
        "AI Chat",
        "Describe a resource, ask about your records, or analyse a photo.",
        "💬",
    )
    _common.show_flash()

    st.write(
        "Example: *I have 12 kg of plastic bottles and 3 broken chairs in Noida.*"
    )
    st.caption(
        "The agent can create a pending exchange request, but only you can "
        "approve or complete an exchange, on the Exchanges page."
    )

    _render_history()
    _photo_expander()

    prompt = st.chat_input("Describe a resource or ask a question")
    if prompt:
        st.session_state.chat.append({"role": "user", "content": prompt})
        with st.spinner("The agent is working..."):
            result = _common.get_agent().run(prompt)
        st.session_state.chat.append({
            "role": "assistant",
            "content": result.answer,
            "trace": result.trace,
            "provider": result.provider,
            "error": result.error,
        })
        st.rerun()
