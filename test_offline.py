"""Run:  python test_offline.py   (no API key, no network needed)"""
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["RESOURCE_AI_DB"] = os.path.join(_tmp, "test.db")
os.environ["RESOURCE_AI_MOCK"] = "1"

import analysis  # noqa: E402
import database  # noqa: E402
import impact  # noqa: E402
import matching  # noqa: E402
import tools  # noqa: E402
from agent import ResourceAgent  # noqa: E402

PASSED = 0


def check(condition: bool, label: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"FAILED: {label}")
    PASSED += 1
    print(f"  ok  {label}")


database.init_db()
check(len(database.list_orgs()) >= 10, "database seeded with sample organisations")

# ---- analysis
a = analysis.analyze_resource("5 kg of old plastic bottles in Delhi")
check(a["category"] == "plastic" and a["quantity"] == 5 and a["unit"] == "kg", "analysis: plastic 5 kg")
a = analysis.analyze_resource("broken laptop with dead battery")
check(a["category"] == "electronics" and a["condition"] == "broken", "analysis: broken electronics")
check(a["disposition"] == "recycle", "analysis: broken laptop -> recycle")
a = analysis.analyze_resource("3 good wooden chairs")
check(a["category"] == "furniture" and a["disposition"] == "reuse" and a["quantity"] == 3, "analysis: chairs -> reuse")

# ---- matching
m = matching.find_matches("furniture", 3, "pieces", "good", "Delhi", "reuse")
check(len(m) > 0, "matching: furniture has matches")
check(all(m[i]["score"] >= m[i + 1]["score"] for i in range(len(m) - 1)), "matching: sorted by score")
check(m[0]["role"] == "reuse", "matching: reuse organisation ranked first")
check(matching.find_matches("organic", 1, "kg", "broken", "Delhi") != [], "matching: organic accepted any condition")

# ---- impact
e = impact.estimate("plastic", 5, "kg", "recycle")
check(abs(e["co2e_avoided_kg"] - 3.75) < 0.01 and e["is_estimate"], "impact: plastic recycle = 3.75 (estimate)")
check(impact.estimate("plastic", 5, "kg", "dispose")["co2e_avoided_kg"] == 0, "impact: disposal avoids nothing")

# ---- tools: basic validation
check("error" in tools.dispatch("nonexistent", {}), "tools: unknown tool returns error")
check("error" in tools.dispatch("save_resource", {"name": "x", "category": "spaceship",
      "condition": "good", "quantity": 1, "unit": "pieces"}), "tools: invalid category rejected")

# ---- exchange lifecycle with human confirmation
saved = tools.dispatch("save_resource", {"name": "Study table", "category": "furniture",
                       "condition": "good", "quantity": 2.0, "unit": "pieces", "location": "Delhi"})
rid = saved["resource_id"]
org_id = tools.dispatch("find_matches", {"resource_id": float(rid)})["matches"][0]["org_id"]
ex = tools.dispatch("create_exchange_request", {"resource_id": rid, "org_id": org_id})
eid = ex["exchange_id"]


def ex_status():
    return database.get_exchange(eid)["status"]


def ai_set(new_status):
    return tools.dispatch("update_exchange_status", {"exchange_id": eid, "status": new_status})


check(ex["status"] == "pending", "exchange: created as pending")

# The AI cannot approve or complete a pending exchange
r = ai_set("approved")
check("error" in r and "explicit confirmation" in r["error"], "exchange: AI approval is blocked")
check(ex_status() == "pending", "exchange: still pending after AI approval attempt")
check("error" in ai_set("completed"), "exchange: AI completion of a pending exchange is blocked")
check(ex_status() == "pending", "exchange: still pending after AI completion attempt")

# User path: approval needs an explicit True
check("error" in tools.confirm_exchange_approval(eid, False), "exchange: user approval refused without confirmation")
check(ex_status() == "pending", "exchange: still pending after unconfirmed approval")
check("error" in tools.confirm_exchange_completion(eid, True),
      "exchange: user completion blocked while still pending")

# User approves (trusted function only)
r = tools.confirm_exchange_approval(eid, True)
check(r.get("status") == "approved" and ex_status() == "approved", "exchange: approved via user confirmation")
check(database.impact_summary()["completed_transfers"] == 0, "impact: nothing logged at approval")

# The AI still cannot complete an approved exchange
r = ai_set("completed")
check("error" in r and ex_status() == "approved", "exchange: AI completion of an approved exchange is blocked")
check(database.impact_summary()["completed_transfers"] == 0, "impact: nothing logged after AI completion attempt")

# User completes (separate confirmation)
check("error" in tools.confirm_exchange_completion(eid, False),
      "exchange: user completion refused without confirmation")
check(ex_status() == "approved", "exchange: still approved after unconfirmed completion")
done = tools.confirm_exchange_completion(eid, True)
check(done.get("status") == "completed" and "impact_logged" in done,
      "exchange: completed via separate user confirmation, impact logged")
check(database.get_resource(rid)["status"] == "transferred", "exchange: resource marked transferred")
check(database.impact_summary()["completed_transfers"] == 1, "impact: recorded exactly once")

# Impact cannot be recorded a second time
check("error" in tools.confirm_exchange_completion(eid, True), "exchange: second completion blocked")
check(database.impact_summary()["completed_transfers"] == 1, "impact: still exactly one record after retry")

# ---- agent (offline pipeline) + memory
agent = ResourceAgent()
res = agent.run("I have 3 good wooden chairs in Delhi")
names = [t["tool"] for t in res.trace]
check(not res.error and res.mock, "agent: offline run succeeds")
check({"analyze_resource", "find_matches", "estimate_impact"} <= set(names), "agent: used the expected tools")
check("ESTIMATE" in res.answer, "agent: impact labelled as estimate")
check(len(agent.memory.resource_ids) == 1 and "chairs" in agent.memory.context_summary().lower(),
      "memory: resource remembered in session")
check(agent.run("").error, "agent: empty input handled")

print(f"\nALL OFFLINE TESTS PASSED ({PASSED} checks)")