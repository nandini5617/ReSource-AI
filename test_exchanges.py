"""Run:  python test_exchanges.py   (temporary database, no network, no API key)"""
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["RESOURCE_AI_DB"] = os.path.join(_tmp, "exchanges_test.db")
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


SCRIPT = "import views.exchanges as page\npage.render()\n"


def run_page() -> AppTest:
    return AppTest.from_string(SCRIPT, default_timeout=30).run()


def new_exchange(name):
    rid = tools.dispatch("save_resource", {
        "name": name, "category": "furniture", "condition": "good",
        "quantity": 2, "unit": "pieces", "location": "Delhi"})["resource_id"]
    org_id = tools.dispatch("find_matches", {"resource_id": rid})["matches"][0]["org_id"]
    eid = tools.dispatch("create_exchange_request",
                         {"resource_id": rid, "org_id": org_id})["exchange_id"]
    return rid, eid


def status(eid):
    return database.get_exchange(eid)["status"]


database.init_db()

# ---- empty
at = run_page()
check(not at.exception, "empty: page renders")
check(len(at.button) == 0, "empty: no action buttons")

rid, eid = new_exchange("Study table")

# ---- pending: buttons locked until the checkbox is ticked
at = run_page()
check(not at.exception, "pending: page renders")
check(at.button(key=f"appr_{eid}").disabled, "Approve disabled before confirmation")
check(at.button(key=f"rej_{eid}").disabled, "Organisation declined disabled before confirmation")
check(not at.button(key=f"canc_{eid}").disabled, "Cancel available")
check(len([b for b in at.button if b.key == f"comp_{eid}"]) == 0,
      "no completion button while pending")

at.checkbox(key=f"ok_appr_{eid}").check().run()
check(not at.button(key=f"appr_{eid}").disabled, "Approve enabled after ticking the box")
check(status(eid) == "pending", "ticking the box alone changes nothing")

at.button(key=f"appr_{eid}").click().run()
check(status(eid) == "approved", "Approve button approves")
check(database.impact_summary()["completed_transfers"] == 0, "no impact at approval")
check(any("approved" in s.value for s in at.success), "success message shown")

# ---- approved: completion needs its own, separate confirmation
check(at.button(key=f"comp_{eid}").disabled, "Mark completed disabled before its own confirmation")
check(not any(b.key == f"appr_{eid}" for b in at.button), "no approve button once approved")
at.checkbox(key=f"ok_comp_{eid}").check().run()
check(status(eid) == "approved", "ticking the completion box alone changes nothing")
at.button(key=f"comp_{eid}").click().run()
check(status(eid) == "completed", "Mark completed completes")
check(database.impact_summary()["completed_transfers"] == 1, "impact recorded once")
check(database.get_resource(rid)["status"] == "transferred", "resource marked transferred")
check(any("Impact recorded" in i.value for i in at.info), "impact message shown (as estimate)")

# ---- completed: no controls, impact cannot repeat
at = run_page()
check(not any(b.key in (f"appr_{eid}", f"comp_{eid}", f"canc_{eid}", f"canc2_{eid}")
              for b in at.button), "completed exchange has no action buttons")
check(database.impact_summary()["completed_transfers"] == 1, "impact still exactly once")

# ---- reject and cancel paths
rid2, eid2 = new_exchange("Old bookshelf")
at = run_page()
at.checkbox(key=f"ok_appr_{eid2}").check().run()
at.button(key=f"rej_{eid2}").click().run()
check(status(eid2) == "rejected" and database.get_resource(rid2)["status"] == "available",
      "decline records rejection, resource available again")

rid3, eid3 = new_exchange("Spare desk")
at = run_page()
at.button(key=f"canc_{eid3}").click().run()
check(status(eid3) == "cancelled" and database.get_resource(rid3)["status"] == "available",
      "cancel works, resource available again")
check(database.impact_summary()["completed_transfers"] == 1, "rejecting/cancelling adds no impact")

# ---- filter
at = run_page()
at.selectbox(key="ex_filter").select("completed").run()
check(len(at.expander) == 1, "filter shows only completed exchanges")

print(f"\nALL EXCHANGES TESTS PASSED ({PASSED} checks)")