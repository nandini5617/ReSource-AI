"""Run:  python test_app.py   (temporary database, offline mode, no network)"""
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["RESOURCE_AI_DB"] = os.path.join(_tmp, "app_test.db")
os.environ["RESOURCE_AI_MOCK"] = "1"

from streamlit.testing.v1 import AppTest  # noqa: E402

import database  # noqa: E402
import tools  # noqa: E402

PASSED = 0
PAGES = ["Dashboard", "AI Chat", "Add Resource", "Explorer", "Exchanges", "Impact"]


def check(condition: bool, label: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"FAILED: {label}")
    PASSED += 1
    print(f"  ok  {label}")


def fresh() -> AppTest:
    return AppTest.from_file("app.py", default_timeout=60).run()


def go(at: AppTest, page: str) -> AppTest:
    at.radio(key="nav").set_value(page).run()
    return at


database.init_db()

# ---- every page renders with an empty database
at = fresh()
check(not at.exception, "app starts without exceptions")
check(at.radio(key="nav").value == "Dashboard", "starts on the Dashboard")
for page in PAGES:
    go(at, page)
    check(not at.exception, f"{page}: renders (empty database)")
    check(not any("hit an error" in e.value for e in at.error), f"{page}: no page error banner")

# ---- text analysis -> save through the Add Resource page
go(at, "Add Resource")
at.text_area(key="add_description").set_value("3 good wooden chairs in Delhi").run()
at.button(key="add_analyse_text").click().run()
check(not at.exception, "Add Resource: analysis runs")
check(any("Review and save" in s.value for s in at.subheader), "Add Resource: review form appears")
saves = [b for b in at.get("form_submit_button")]
check(len(saves) == 1, "Add Resource: one Save button")
saves[0].click().run()
check(len(database.list_resources()) == 1, "Add Resource: resource saved once")
rid = database.list_resources()[0]["id"]

# ---- Explorer -> request exchange
go(at, "Explorer")
at.button(key=f"exp_view_{rid}").click().run()
req = [b for b in at.button if b.label == "Request exchange"]
check(len(req) > 0, "Explorer: request buttons shown")
req[0].click().run()
ex = database.list_exchanges()
check(len(ex) == 1 and ex[0]["status"] == "pending", "Explorer: one PENDING exchange created")
eid = ex[0]["id"]

# ---- Exchanges: safety flow through the real app
go(at, "Exchanges")
check(at.button(key=f"appr_{eid}").disabled, "Exchanges: Approve disabled before confirmation")
at.checkbox(key=f"ok_appr_{eid}").check().run()
at.button(key=f"appr_{eid}").click().run()
check(database.get_exchange(eid)["status"] == "approved", "Exchanges: approved after confirmation")
check(database.impact_summary()["completed_transfers"] == 0, "Exchanges: no impact at approval")
check(at.button(key=f"comp_{eid}").disabled, "Exchanges: completion needs its own confirmation")
at.checkbox(key=f"ok_comp_{eid}").check().run()
at.button(key=f"comp_{eid}").click().run()
check(database.get_exchange(eid)["status"] == "completed", "Exchanges: completed after confirmation")
check(database.impact_summary()["completed_transfers"] == 1, "impact recorded exactly once")

# ---- Dashboard and Impact reflect it; navigation buttons work
go(at, "Dashboard")
check(not at.exception, "Dashboard: renders with data")
go(at, "Impact")
check(not at.exception, "Impact: renders with data")
check(database.impact_summary()["completed_transfers"] == 1, "viewing pages adds no impact")

# ---- AI agent still cannot approve or complete
rid2 = tools.dispatch("save_resource", {"name": "Desk", "category": "furniture",
       "condition": "good", "quantity": 1, "unit": "pieces", "location": "Delhi"})["resource_id"]
org2 = tools.dispatch("find_matches", {"resource_id": rid2})["matches"][0]["org_id"]
eid2 = tools.dispatch("create_exchange_request", {"resource_id": rid2, "org_id": org2})["exchange_id"]
check("error" in tools.dispatch("update_exchange_status", {"exchange_id": eid2, "status": "approved"}),
      "AI cannot approve")
check("error" in tools.dispatch("update_exchange_status", {"exchange_id": eid2, "status": "completed"}),
      "AI cannot complete")
check(database.get_exchange(eid2)["status"] == "pending", "exchange still pending after AI attempts")

# ---- offline chat
at = fresh()
go(at, "AI Chat")
at.chat_input[0].set_value("I have 3 old wooden chairs in Delhi").run()
check(not at.exception, "AI Chat: offline message runs")
check(any("Offline demo mode" in m.value for m in at.markdown), "AI Chat: offline answer shown")

print(f"\nALL APP TESTS PASSED ({PASSED} checks)")