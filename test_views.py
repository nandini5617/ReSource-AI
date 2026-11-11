"""Run:  python test_views.py   (temporary database, no network, no API key)

Tests the page helpers and smoke-renders the pages with a MOCKED Streamlit, so
it checks that the page code runs against the real database, stats, tools and
vision modules without errors. Vision providers are replaced by a fake, so no
image ever leaves your machine. It does not check how the pages look; use
`streamlit run app.py` for that.
"""
import io
import os
import sys
import tempfile
from contextlib import contextmanager
from unittest.mock import MagicMock

_tmp = tempfile.mkdtemp()
os.environ["RESOURCE_AI_DB"] = os.path.join(_tmp, "views_test.db")
os.environ["RESOURCE_AI_MOCK"] = "1"


# ------------------------------------------------------------ fake Streamlit
class FakeState(dict):
    """dict with attribute access, like st.session_state."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


PRESSED: set = set()          # button keys that "were clicked" in this run
UPLOAD = [None]               # what st.file_uploader returns
TEXT_AREA = [""]              # what st.text_area returns
COLUMNS_CREATED: list = []


class FakeUpload:
    def __init__(self, data: bytes, name: str):
        self._data = data
        self.name = name

    def getvalue(self) -> bytes:
        return self._data


def _text_input(label, *args, **kwargs):
    return args[0] if args else kwargs.get("value", "")


def _text_area(label, *args, **kwargs):
    return TEXT_AREA[0]


def _selectbox(label, options=None, *args, **kwargs):
    options = options if options is not None else kwargs.get("options")
    return options[kwargs.get("index", 0)]


def _number_input(label, *args, **kwargs):
    return kwargs.get("value", 1.0)


def _button(label="", *args, **kwargs):
    if kwargs.get("disabled"):          # a disabled Streamlit button cannot be clicked
        return False
    return kwargs.get("key") in PRESSED


def _wire(target) -> None:
    target.text_input.side_effect = _text_input
    target.text_area.side_effect = _text_area
    target.selectbox.side_effect = _selectbox
    target.number_input.side_effect = _number_input


def _columns(spec, **_kwargs):
    """Fake st.columns; keeps every column so tests can read what was written."""
    n = spec if isinstance(spec, int) else len(spec)
    cols = []
    for _ in range(n):
        col = MagicMock()
        _wire(col)
        cols.append(col)
    COLUMNS_CREATED.extend(cols)
    return cols


def make_streamlit() -> MagicMock:
    mock = MagicMock(name="streamlit")
    mock.session_state = FakeState()
    _wire(mock)
    mock.button.side_effect = _button
    mock.checkbox.return_value = False
    mock.form_submit_button.return_value = False
    mock.chat_input.return_value = None
    mock.file_uploader.side_effect = lambda *a, **k: UPLOAD[0]
    mock.columns.side_effect = _columns
    mock.tabs.side_effect = lambda labels, **k: [MagicMock() for _ in labels]
    return mock


st = make_streamlit()
sys.modules["streamlit"] = st

import database  # noqa: E402
import knowledge as K  # noqa: E402
import stats  # noqa: E402
import tools  # noqa: E402
import ui_theme  # noqa: E402
import vision  # noqa: E402
from PIL import Image  # noqa: E402
from views import _common, add_resource, chat, dashboard  # noqa: E402

PASSED = 0


def check(condition: bool, label: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"FAILED: {label}")
    PASSED += 1
    print(f"  ok  {label}")


def reset_ui() -> None:
    st.reset_mock()
    st.session_state.clear()
    PRESSED.clear()
    UPLOAD[0] = None
    TEXT_AREA[0] = ""
    COLUMNS_CREATED.clear()
    st.chat_input.return_value = None
    st.form_submit_button.return_value = False


def markdown_text() -> str:
    """All markdown written directly or through any column."""
    parts = []
    for target in [st] + COLUMNS_CREATED:
        for call in target.markdown.call_args_list:
            if call.args:
                parts.append(str(call.args[0]))
    return "\n".join(parts)


def button_call(key: str):
    for call in st.button.call_args_list:
        if call.kwargs.get("key") == key:
            return call
    return None


@contextmanager
def env(**changes):
    saved = {k: os.environ.get(k) for k in changes}
    for k, v in changes.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


KEYS_OFF = dict(
    GEMINI_API_KEY=None, GROQ_API_KEY=None, OPENROUTER_API_KEY=None,
    GEMINI_VISION_MODEL=None, GROQ_VISION_MODEL=None,
    OPENROUTER_VISION_MODEL=None, RESOURCE_AI_VISION_ORDER=None,
)


def jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (40, 140, 60)).save(buf, format="JPEG")
    return buf.getvalue()


def counts() -> tuple:
    return (len(database.list_resources(10000)), len(database.list_exchanges(10000)))


# ---------------------------------------------------------------- helpers
check(_common.format_time(None) == "not recorded", "format_time: missing time is 'not recorded'")
check(_common.format_time("") == "not recorded", "format_time: empty string is 'not recorded'")
check(_common.format_time("2026-11-11T14:05:09") == "11 Nov 2026, 14:05", "format_time: ISO timestamp")
check(_common.format_time("garbage") == "garbage", "format_time: unparseable text shown as is")
check(_common.quantity_text(12.0, "kg") == "12 kg" and _common.quantity_text(2.5, "pieces") == "2.5 pieces",
      "quantity_text formats numbers compactly")

res = {"id": 3, "name": "Chair", "category": "furniture", "condition": "good",
       "quantity": 2.0, "unit": "pieces", "location": "Noida", "disposition": "reuse",
       "status": "available", "created_at": "2026-11-11T10:00:00"}
full = _common.resource_rows([res])[0]
compact = _common.resource_rows([res], compact=True)[0]
check(full["City"] == "Noida" and full["Action"] == "reuse" and full["Qty"] == "2 pieces",
      "resource_rows: full row")
check("City" not in compact and "Action" not in compact, "resource_rows: compact leaves out city and action")

ex = {"id": 1, "status": "approved", "resource": None, "organisation": "Org",
      "created_at": "2026-11-11T10:00:00", "updated_at": None}
row = _common.exchange_rows([ex])[0]
check(row["Resource"] == "?" and row["Organisation"] == "Org", "exchange_rows: missing resource shown as '?'")
check(row["Status"] == "🟢 approved" and row["Updated"] == "not recorded",
      "exchange_rows: status label and honest missing time")

# ---------------------------------------------------------- state and flash
reset_ui()
_common.init_state()
check(st.session_state["chat"] == [] and st.session_state["nav"] == "Dashboard",
      "init_state creates the session keys")
check(st.session_state["analysis_serial"] == 0 and st.session_state["photo_serial"] == 0,
      "init_state creates the serial counters")
st.session_state["nav"] = "Impact"
_common.init_state()
check(st.session_state["nav"] == "Impact", "init_state does not overwrite existing values")

_common.flash("success", "done")
_common.flash("nonsense-kind", "falls back to info")
_common.show_flash()
check(st.success.called and st.info.called, "show_flash displays queued messages by kind")
check(st.session_state["flash"] == [], "show_flash clears the queue")

reset_ui()
_common.init_state()
_common.report({"error": "bad"}, "ok")
check(st.session_state["flash"] == [("error", "bad")], "report: error result becomes an error message")
reset_ui()
_common.init_state()
_common.report({"status": "completed",
                "impact_logged": {"label": "reuse", "kg_diverted": 4.0, "co2e_avoided_kg": 2.0}},
               "Exchange #1 completed.")
kinds = [k for k, _ in st.session_state["flash"]]
check(kinds == ["success", "info"], "report: completed result adds a success and an impact note")

reset_ui()
_common.init_state()
_common.go_to("Explorer")
check(st.session_state["nav"] == "Explorer", "go_to switches page")
_common.go_to("Nowhere")
check(st.session_state["nav"] == "Explorer", "go_to ignores unknown pages")

# -------------------------------------------------------- dashboard: empty
database.init_db()
reset_ui()
_common.init_state()
dashboard.render()
check(st.markdown.called, "dashboard renders on an empty database without errors")
check("No resources yet" in markdown_text(), "dashboard shows the empty state")

# ----------------------------------------------- dashboard: with real data
rid1 = database.add_resource("Wooden chair", "furniture", "wood", "good", 2, "pieces",
                             "Delhi", "reuse", "")
rid2 = database.add_resource("Old novels", "books", "paper", "good", 10, "pieces",
                             "Delhi", "reuse", "")
org_id = database.list_orgs()[0]["id"]
eid = database.create_exchange(rid1, org_id, "please take it")
database.set_resource_status(rid1, "requested")

reset_ui()
_common.init_state()
dashboard.render()
text = markdown_text()
check("Total resources" in text and "Pending exchanges" in text, "dashboard shows count cards")
check("CO2e avoided" in text and "ESTIMATES" in text, "dashboard labels impact as estimates")
check(st.info.called, "dashboard points out the pending exchange")
check(st.bar_chart.called, "dashboard draws the category chart")
check(st.dataframe.call_count >= 2, "dashboard shows recent resources and exchanges tables")

before = (stats.dashboard_counts(), database.get_exchange(eid)["status"])
reset_ui()
_common.init_state()
dashboard.render()
after = (stats.dashboard_counts(), database.get_exchange(eid)["status"])
check(before == after and after[1] == "pending", "dashboard is read-only: no data or status changed")

# ------------------------------------------------- photo / vision helpers
FAKE_VISION = vision.normalize_result(
    {"name": "Wooden chair", "category": "furniture", "visible_condition": "fair",
     "disposition": "repair", "hazardous": False, "ideas": ["Tighten the legs", "Repaint it"],
     "reasoning": "Looks sturdy but scuffed.", "confidence": "medium"},
    "groq", "fake-vision-model")

a = add_resource.vision_to_analysis(FAKE_VISION)
check(a["category"] == "furniture" and a["condition"] == "fair" and a["disposition"] == "repair",
      "vision_to_analysis keeps the suggested category, condition and action")
check(a["quantity"] == 1.0 and a["unit"] == "pieces" and a["location"] == K.DEFAULT_CITY,
      "vision_to_analysis uses placeholders for quantity, unit and city")
check(a["from_photo"] is True and "groq" in a["source"], "vision_to_analysis records its source")
bad = add_resource.vision_to_analysis({"category": "spaceship", "visible_condition": "mint",
                                       "disposition": "burn", "hazardous": "yes"})
check(bad["category"] == "other" and bad["condition"] == "fair" and bad["disposition"] == "reuse"
      and bad["hazardous"] is False, "vision_to_analysis falls back to safe values")

md = add_resource.vision_markdown(FAKE_VISION)
check("Wooden chair" in md and "medium" in md and "groq" in md and "Tighten the legs" in md,
      "vision_markdown shows item, confidence, provider and ideas")
check("photo cannot" in md.lower() or "LOOKS" in md, "vision_markdown carries the photo limitations note")
check("Possibly hazardous" in add_resource.vision_markdown({**FAKE_VISION, "hazardous": True}),
      "vision_markdown flags hazardous items")

check(add_resource._index(["a", "b"], "b") == 1 and add_resource._index(["a", "b"], "zzz") == 0,
      "_index finds an option or falls back to the first")

data, problem = add_resource.validate_upload(None)
check(data is None and problem is None, "validate_upload: no file is not an error")
data, problem = add_resource.validate_upload(FakeUpload(jpeg_bytes(), "ok.jpg"))
check(data is not None and problem is None, "validate_upload accepts a real JPEG")
data, problem = add_resource.validate_upload(FakeUpload(b"plain text", "fake.jpg"))
check(data is None and problem, "validate_upload rejects a text file renamed .jpg")
data, problem = add_resource.validate_upload(FakeUpload(jpeg_bytes(), "pic.gif"))
check(data is None and "Unsupported" in problem, "validate_upload rejects the wrong extension")

# ------------------------------------------------------ vision status
with env(RESOURCE_AI_MOCK="1"):
    check(add_resource.vision_status()["state"] == "offline", "vision_status: offline demo mode")
with env(RESOURCE_AI_MOCK="0", **KEYS_OFF):
    s = add_resource.vision_status()
    check(s["state"] == "none" and s["providers"] == [], "vision_status: no provider configured")
with env(RESOURCE_AI_MOCK="0", **{**KEYS_OFF, "GROQ_API_KEY": "test-key-not-real",
                                  "GROQ_VISION_MODEL": "fake-groq-vision"}):
    s = add_resource.vision_status()
    check(s["state"] == "ready" and s["providers"] == ["groq"] and "Groq" in s["message"],
          "vision_status: Groq ready when a vision model is set")
    check("test-key-not-real" not in s["message"], "vision_status never shows key text")
with env(RESOURCE_AI_MOCK="0", **{**KEYS_OFF, "GROQ_API_KEY": "test-key-not-real",
                                  "GROQ_VISION_MODEL": "fake-groq-vision",
                                  "GEMINI_API_KEY": "test-key-not-real"}):
    s = add_resource.vision_status()
    check(s["providers"] == ["groq", "gemini"], "vision_status: Groq first, Gemini second")
    check("optional" in s["message"].lower() and "quota" in s["message"].lower(),
          "vision_status: Gemini described as optional, quota may fail")
with env(RESOURCE_AI_MOCK="0", **{**KEYS_OFF, "GROQ_API_KEY": "test-key-not-real"}):
    check(add_resource.vision_status()["state"] == "none",
          "vision_status: a key alone is not enough without a vision model (Groq)")

# ----------------------------------------- Add Resource page (safeguards)
approve_mock, complete_mock = MagicMock(), MagicMock()
reject_mock, cancel_mock = MagicMock(), MagicMock()
real_user_actions = (tools.confirm_exchange_approval, tools.confirm_exchange_completion,
                     tools.reject_exchange, tools.cancel_exchange)
tools.confirm_exchange_approval, tools.confirm_exchange_completion = approve_mock, complete_mock
tools.reject_exchange, tools.cancel_exchange = reject_mock, cancel_mock

reset_ui()
_common.init_state()
base = counts()
add_resource.render()
check(st.tabs.called and len(st.tabs.call_args.args[0]) == 2, "Add Resource renders with two tabs")
check(st.session_state["analysis"] is None, "Add Resource starts without an analysis")
photo_btn = button_call("add_analyse_photo")
check(photo_btn is not None and photo_btn.kwargs.get("disabled") is True,
      "Analyse photo is disabled until a valid photo is chosen")

# text: empty description
reset_ui()
_common.init_state()
PRESSED.add("add_analyse_text")
add_resource.render()
check(st.error.called and st.session_state["analysis"] is None, "empty description shows an error")

# text: analyse -> review form
reset_ui()
_common.init_state()
TEXT_AREA[0] = "2 old wooden chairs in Noida"
PRESSED.add("add_analyse_text")
add_resource.render()
an = st.session_state["analysis"]
check(an is not None and an["category"] in K.CATEGORIES and an["unit"] in K.UNITS,
      "text analysis produces a valid analysis")
check(counts() == base, "analysing text saves nothing")
PRESSED.clear()
add_resource.render()
check(st.form.called, "review form is shown after analysis")
check(counts() == base, "showing the review form saves nothing")

# save from the form
st.form_submit_button.return_value = True
add_resource.render()
after_counts = counts()
check(after_counts[0] == base[0] + 1, "Save creates exactly one resource")
check(after_counts[1] == base[1], "Save creates no exchange")
saved_row = database.list_resources(1)[0]
check(saved_row["status"] == "available", "saved resource starts as 'available'")
check(st.session_state["analysis"] is None, "analysis is cleared after saving")
check(any(k == "success" and "Saved as resource" in m for k, m in st.session_state["flash"]),
      "save queues a success message")

# save with an empty name -> error from tools, nothing saved
reset_ui()
_common.init_state()
st.session_state["analysis"] = {**add_resource.vision_to_analysis(FAKE_VISION), "name": ""}
st.session_state["analysis_serial"] = 1
st.form_submit_button.return_value = True
base = counts()
add_resource.render()
check(st.error.called and counts() == base and st.session_state["analysis"] is not None,
      "saving with an empty name shows the error and keeps the form")

# discard
reset_ui()
_common.init_state()
st.session_state["analysis"] = add_resource.vision_to_analysis(FAKE_VISION)
st.session_state["analysis_serial"] = 1
PRESSED.add("discard_1")
add_resource.render()
check(st.session_state["analysis"] is None, "Discard clears the analysis")

# ---------------------------------------------- Add Resource: photo flow
vision_calls = []


def fake_analyze(data, filename="", description=""):
    vision_calls.append((len(data), filename, description))
    return FAKE_VISION


real_analyze = vision.analyze_image
vision.analyze_image = fake_analyze

with env(RESOURCE_AI_MOCK="0", **{**KEYS_OFF, "GROQ_API_KEY": "test-key-not-real",
                                  "GROQ_VISION_MODEL": "fake-groq-vision"}):
    reset_ui()
    _common.init_state()
    base = counts()
    UPLOAD[0] = FakeUpload(jpeg_bytes(), "chair.jpg")
    add_resource.render()
    check(st.image.called, "a valid photo is previewed")
    check(button_call("add_analyse_photo").kwargs.get("disabled") is False,
          "Analyse photo is enabled for a valid photo")

    PRESSED.add("add_analyse_photo")
    add_resource.render()
    check(len(vision_calls) == 1 and vision_calls[0][1] == "chair.jpg", "photo analysis calls the vision layer once")
    an = st.session_state["analysis"]
    check(an["from_photo"] is True and an["name"] == "Wooden chair", "photo analysis pre-fills the form")
    check(an["quantity"] == 1.0 and an["location"] == K.DEFAULT_CITY, "photo analysis leaves quantity/city as placeholders")
    check(counts() == base, "photo analysis saves nothing")

    PRESSED.clear()
    add_resource.render()
    check(st.warning.called and "PLACEHOLDERS" in " ".join(str(c.args[0]) for c in st.warning.call_args_list),
          "review form warns that quantity, unit and city are placeholders")

    st.form_submit_button.return_value = True
    add_resource.render()
    check(counts()[0] == base[0] + 1 and counts()[1] == base[1], "saving a photo suggestion creates one resource, no exchange")
    row = database.list_resources(1)[0]
    check(row["name"] == "Wooden chair" and row["condition"] == "fair" and row["disposition"] == "repair",
          "saved resource carries the suggested values")
    check("photo" in (row["notes"] or "").lower(), "saved notes record that it came from a photo")

    # invalid file: no vision call, error shown
    reset_ui()
    _common.init_state()
    UPLOAD[0] = FakeUpload(b"not an image", "fake.jpg")
    PRESSED.add("add_analyse_photo")
    n_before = len(vision_calls)
    add_resource.render()
    check(st.error.called and len(vision_calls) == n_before and st.session_state["analysis"] is None,
          "invalid photo shows an error and never reaches the vision layer")

    # even if a click slipped through a disabled button, no bad image is analysed
    st.button.side_effect = lambda label="", *a, **k: k.get("key") in PRESSED
    for page, key in ((add_resource, "add_analyse_photo"), (chat, "chat_analyse_photo")):
        reset_ui()
        _common.init_state()
        UPLOAD[0] = FakeUpload(b"not an image", "fake.jpg")
        PRESSED.add(key)
        page.render()
        check(len(vision_calls) == n_before and st.session_state["analysis"] is None,
              f"{page.__name__}: a click without a valid image never reaches the vision layer")
    st.button.side_effect = _button

    # vision failure: readable error, no analysis
    def failing_analyze(data, filename="", description=""):
        raise vision.VisionError("All vision providers failed.\ngemini: 429 quota")

    vision.analyze_image = failing_analyze
    reset_ui()
    _common.init_state()
    UPLOAD[0] = FakeUpload(jpeg_bytes(), "chair.jpg")
    PRESSED.add("add_analyse_photo")
    add_resource.render()
    shown = " ".join(str(c.args[0]) for c in st.error.call_args_list)
    check("All vision providers failed" in shown and st.session_state["analysis"] is None,
          "vision failure (e.g. Gemini 429) is shown and nothing is pre-filled")
    vision.analyze_image = fake_analyze

# ------------------------------------------------------------- Chat page
class FakeResult:
    def __init__(self, answer="Here is my answer", error=False):
        self.answer = answer
        self.trace = [{"tool": "analyze_resource", "args": {"description": "x"}, "result": {}}]
        self.provider = "groq"
        self.error = error
        self.mock = False


class FakeAgent:
    def __init__(self):
        self.calls = []
        self.error = False

    def run(self, message):
        self.calls.append(message)
        return FakeResult("Sorry, that failed" if self.error else "Here is my answer", self.error)


agent = FakeAgent()
real_get_agent = _common.get_agent
_common.get_agent = lambda: agent

reset_ui()
_common.init_state()
chat.render()
check(st.chat_input.called and st.markdown.called is not None, "chat renders on an empty history")
check(agent.calls == [], "chat does not call the agent without a message")

st.chat_input.return_value = "I have 2 chairs in Noida"
chat.render()
check(agent.calls == ["I have 2 chairs in Noida"], "chat sends the message to the agent once")
msgs = st.session_state["chat"]
check(len(msgs) == 2 and msgs[0]["role"] == "user" and msgs[1]["role"] == "assistant",
      "chat stores the user message and the answer")
check(msgs[1]["provider"] == "groq" and msgs[1]["error"] is False and len(msgs[1]["trace"]) == 1,
      "chat keeps provider, error flag and tool trace")

st.chat_input.return_value = None
st.reset_mock()
chat.render()
check(st.code.called and st.caption.called, "chat history shows the tool trace and provider")

agent.error = True
st.chat_input.return_value = "trigger an error"
chat.render()
check(st.session_state["chat"][-1]["error"] is True, "chat stores an agent error")
st.chat_input.return_value = None
st.reset_mock()
chat.render()
check(st.error.called, "chat shows stored agent errors as errors")

# chat photo flow
with env(RESOURCE_AI_MOCK="0", **{**KEYS_OFF, "GROQ_API_KEY": "test-key-not-real",
                                  "GROQ_VISION_MODEL": "fake-groq-vision"}):
    reset_ui()
    _common.init_state()
    base = counts()
    n_before = len(vision_calls)
    UPLOAD[0] = FakeUpload(jpeg_bytes(), "table.jpg")
    PRESSED.add("chat_analyse_photo")
    chat.render()
    check(len(vision_calls) == n_before + 1, "chat photo analysis calls the vision layer once")
    msgs = st.session_state["chat"]
    check(len(msgs) == 2 and msgs[1].get("vision") is not None and "Photo analysis" in msgs[1]["content"],
          "chat stores the photo result as a message")
    check(st.session_state["photo_serial"] == 1, "chat clears the uploader after analysis")
    check(counts() == base, "chat photo analysis saves nothing")
    check(agent.calls[-1] == "trigger an error", "chat photo analysis does not call the agent")

    PRESSED.clear()
    UPLOAD[0] = None
    st.reset_mock()
    chat.render()
    use_btn = button_call("chat_use_vision_1")
    check(use_btn is not None and use_btn.kwargs.get("on_click") is add_resource.prefill_from_vision,
          "chat offers 'Use in Add Resource' for photo results")
    check("Photo analysis" in markdown_text(), "chat shows the photo result")

    # invalid chat photo
    reset_ui()
    _common.init_state()
    UPLOAD[0] = FakeUpload(b"junk", "x.png")
    PRESSED.add("chat_analyse_photo")
    n_before = len(vision_calls)
    chat.render()
    check(st.error.called and st.session_state["chat"] == [] and len(vision_calls) == n_before,
          "chat rejects an invalid photo without calling the vision layer")

    # vision failure in chat
    vision.analyze_image = failing_analyze
    reset_ui()
    _common.init_state()
    UPLOAD[0] = FakeUpload(jpeg_bytes(), "x.jpg")
    PRESSED.add("chat_analyse_photo")
    chat.render()
    check(st.error.called and st.session_state["chat"] == [],
          "chat shows a vision failure and adds no message")
    vision.analyze_image = fake_analyze

# prefill callback
reset_ui()
_common.init_state()
add_resource.prefill_from_vision(FAKE_VISION)
check(st.session_state["nav"] == "Add Resource" and st.session_state["analysis"]["from_photo"] is True,
      "prefill_from_vision loads the form and switches to Add Resource")
check(st.session_state["analysis_serial"] == 1, "prefill_from_vision refreshes the form")

# ---------------------------------------------- safeguards across pages
check(not approve_mock.called and not complete_mock.called and not reject_mock.called
      and not cancel_mock.called,
      "Dashboard, Add Resource and Chat never approve, reject, complete or cancel an exchange")
(tools.confirm_exchange_approval, tools.confirm_exchange_completion,
 tools.reject_exchange, tools.cancel_exchange) = real_user_actions
check(database.get_exchange(eid)["status"] == "pending", "the pending exchange is still pending")

_common.get_agent = real_get_agent
vision.analyze_image = real_analyze

print(f"\nALL VIEW TESTS PASSED ({PASSED} checks)")
