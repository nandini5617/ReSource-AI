"""Run:  python test_exchange_safeguards.py   (no API key, no network)"""
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["RESOURCE_AI_DB"] = os.path.join(_tmp, "safeguard_test.db")
os.environ["RESOURCE_AI_MOCK"] = "1"

import database  # noqa: E402
import tools  # noqa: E402

PASSED = 0


def check(condition: bool, label: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"FAILED: {label}")
    PASSED += 1
    print(f"  ok  {label}")


def new_exchange(name="Study table"):
    saved = tools.dispatch("save_resource", {
        "name": name, "category": "furniture", "condition": "good",
        "quantity": 2, "unit": "pieces", "location": "Delhi"})
    rid = saved["resource_id"]
    org_id = tools.dispatch("find_matches", {"resource_id": rid})["matches"][0]["org_id"]
    ex = tools.dispatch("create_exchange_request", {"resource_id": rid, "org_id": org_id})
    return rid, org_id, ex["exchange_id"]


def status(eid):
    return database.get_exchange(eid)["status"]


def ai(eid, new_status):
    return tools.dispatch("update_exchange_status", {"exchange_id": eid, "status": new_status})


database.init_db()
rid, org_id, eid = new_exchange()
check(status(eid) == "pending" and database.get_resource(rid)["status"] == "requested",
      "request created as pending, resource 'requested'")

# ---- the AI cannot approve / complete / reject
r = ai(eid, "approved")
check("error" in r and "explicit confirmation" in r["error"], "AI approval blocked (original message kept)")
check(status(eid) == "pending", "exchange still pending after AI approval attempt")
check("error" in ai(eid, "completed"), "AI completion of a pending exchange blocked")
check("error" in ai(eid, "rejected") and status(eid) == "pending", "AI cannot reject")

# ---- user path needs a real True
for bad in (False, None, "yes", 1):
    check("error" in tools.confirm_exchange_approval(eid, bad), f"approval refused for confirmed={bad!r}")
check(status(eid) == "pending", "still pending after refused approvals")
check("error" in tools.confirm_exchange_completion(eid, True), "completion without approval blocked (user path)")

# ---- approval by the user
r = tools.confirm_exchange_approval(eid, True)
check(r.get("status") == "approved" and status(eid) == "approved", "user approval works")
check(database.impact_summary()["completed_transfers"] == 0, "no impact logged at approval")

# ---- the AI still cannot complete an APPROVED exchange
r = ai(eid, "completed")
check("error" in r and status(eid) == "approved", "AI cannot complete an approved exchange")
check(database.impact_summary()["completed_transfers"] == 0, "no impact logged after AI attempt")

# ---- completion by the user (separate confirmation)
check("error" in tools.confirm_exchange_completion(eid, False), "completion refused without confirmation")
check(status(eid) == "approved", "still approved")
done = tools.confirm_exchange_completion(eid, True)
check(done.get("status") == "completed" and "impact_logged" in done, "user completion works and logs impact")
check(database.get_resource(rid)["status"] == "transferred", "resource marked transferred")
check(database.impact_summary()["completed_transfers"] == 1, "impact recorded once")

# ---- impact cannot be recorded twice
check("error" in tools.confirm_exchange_completion(eid, True), "second completion blocked")
check("error" in tools.confirm_exchange_approval(eid, True), "approval of a completed exchange blocked")
check(database.impact_summary()["completed_transfers"] == 1, "impact still recorded exactly once")

# ---- consistency guards
r = tools.dispatch("create_exchange_request", {"resource_id": rid, "org_id": org_id})
check("error" in r, "transferred resource cannot be requested again")

rid2, org2, eid2 = new_exchange("Old bookshelf")
r = tools.dispatch("create_exchange_request", {"resource_id": rid2, "org_id": org2})
check("error" in r, "second active request for the same resource blocked")

# ---- cancel / reject restore availability
r = ai(eid2, "cancelled")
check(r.get("status") == "cancelled" and database.get_resource(rid2)["status"] == "available",
      "AI can cancel; resource available again")
check("exchange_id" in tools.dispatch("create_exchange_request", {"resource_id": rid2, "org_id": org2}),
      "resource can be requested again after cancellation")

rid3, org3, eid3 = new_exchange("Spare desk")
r = tools.reject_exchange(eid3, True)
check(r.get("status") == "rejected" and database.get_resource(rid3)["status"] == "available",
      "user rejection works; resource available again")
check("error" in tools.reject_exchange(eid3, True), "rejected is a final state")

# ---- the AI cannot see the user-only actions
declared = {d["name"] for d in tools.TOOL_DECLARATIONS}
check(not any(n.startswith(("confirm_", "reject_", "cancel_exchange")) for n in declared | set(tools._HANDLERS)),
      "user-only functions are not exposed to the AI")
upd = next(d for d in tools.TOOL_DECLARATIONS if d["name"] == "update_exchange_status")
check(upd["parameters"]["properties"]["status"]["enum"] == ["cancelled"],
      "AI declaration only offers 'cancelled'")

print(f"\nALL SAFEGUARD TESTS PASSED ({PASSED} checks)")