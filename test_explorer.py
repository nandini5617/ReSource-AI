"""Run:  python test_explorer.py   (temporary database, no network, no API key)"""
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["RESOURCE_AI_DB"] = os.path.join(_tmp, "explorer_test.db")
os.environ["RESOURCE_AI_MOCK"] = "1"

from streamlit.testing.v1 import AppTest  # noqa: E402

import database  # noqa: E402
import tools  # noqa: E402

PASSED = 0


def check(condition: bool, label: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"FAILED: {label}")
    PASSED += 1
    print(f"  ok  {label}")


SCRIPT = "import views.explorer as page\npage.render()\n"


def run_page() -> AppTest:
    return AppTest.from_string(SCRIPT, default_timeout=30).run()


def button_labels(at) -> list[str]:
    return [b.label for b in at.button]


database.init_db()

# ---- empty database
at = run_page()
check(not at.exception, "empty database: page renders without exceptions")
check(any("No resources match" in m.value for m in at.markdown), "empty database: friendly message")

def add(name, category, condition="good", qty=2, unit="pieces", city="Delhi"):
    return tools.dispatch("save_resource", {
        "name": name, "category": category, "condition": condition,
        "quantity": qty, "unit": unit, "location": city})["resource_id"]


chair = add("Wooden chair", "furniture")
books = add("Old novels", "books", qty=10)
bottles = add("Plastic bottles", "plastic", "fair", 5, "kg")

# ---- cards and filters
at = run_page()
check(not at.exception, "with data: page renders without exceptions")
check(len([b for b in at.button if b.label == "View details"]) == 3, "three resource cards")
at.text_input(key="exp_query").set_value("chair").run()
check(len([b for b in at.button if b.label == "View details"]) == 1, "search narrows the cards")
at.text_input(key="exp_query").set_value("").run()
at.selectbox(key="exp_category").select("books").run()
check(len([b for b in at.button if b.label == "View details"]) == 1, "category filter works")
at.selectbox(key="exp_category").select("All").run()

# ---- details, matches, request
at.button(key=f"exp_view_{chair}").click().run()
check(not at.exception, "details panel renders without exceptions")
check(any("Recommended organisations" in m.value for m in at.markdown), "details show matches section")
req = [b for b in at.button if b.label == "Request exchange"]
check(len(req) > 0 and all(not b.disabled for b in req), "request buttons enabled for an available resource")

labels = " ".join(button_labels(at)).lower()
check("approve" not in labels and "complete" not in labels,
      "Explorer has no approve/complete controls")

req[0].click().run()
exchanges = database.list_exchanges()
check(len(exchanges) == 1 and exchanges[0]["status"] == "pending", "request creates exactly one PENDING exchange")
check(database.get_resource(chair)["status"] == "requested", "resource marked requested")
check(database.impact_summary()["completed_transfers"] == 0, "no impact recorded by a request")
check(any("created (pending)" in s.value for s in at.success), "success message shown")

# ---- a requested resource cannot be requested again from the UI
at = run_page()
at.button(key=f"exp_view_{chair}").click().run()
req = [b for b in at.button if b.label == "Request exchange"]
check(len(req) > 0 and all(b.disabled for b in req), "request buttons disabled once requested")
check(len(database.list_exchanges()) == 1, "still one exchange")

# ---- status filter and close
at.button(key="exp_close").click().run()
check("exp_selected" not in at.session_state, "close details clears the selection")
at.selectbox(key="exp_status").select("requested").run()
check(len([b for b in at.button if b.label == "View details"]) == 1, "status filter works")

print(f"\nALL EXPLORER TESTS PASSED ({PASSED} checks)")