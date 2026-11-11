"""Run:  python test_stats.py   (temporary database, no network, no API key)"""
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["RESOURCE_AI_DB"] = os.path.join(_tmp, "stats_test.db")
os.environ["RESOURCE_AI_MOCK"] = "1"

import database  # noqa: E402
import stats  # noqa: E402
import tools  # noqa: E402

PASSED = 0


def check(condition: bool, label: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"FAILED: {label}")
    PASSED += 1
    print(f"  ok  {label}")


database.init_db()

# ---- empty database
c = stats.dashboard_counts()
check(c["total_resources"] == 0 and c["completed_exchanges"] == 0, "empty database: zero counts")
check(stats.category_distribution() == [] and stats.impact_by_date() == [], "empty database: empty charts")

# ---- add data through the normal tool path
def add(name, category, condition="good", qty=2, unit="pieces", city="Delhi"):
    r = tools.dispatch("save_resource", {"name": name, "category": category,
                       "condition": condition, "quantity": qty, "unit": unit, "location": city})
    return r["resource_id"]


chair = add("Wooden chair", "furniture")
add("Old novels", "books", qty=10)
add("Plastic bottles", "plastic", "fair", 5, "kg")
c = stats.dashboard_counts()
check(c["total_resources"] == 3 and c["available_resources"] == 3, "counts: 3 resources, all available")
dist = {d["category"]: d["count"] for d in stats.category_distribution()}
check(dist == {"furniture": 1, "books": 1, "plastic": 1}, "category distribution")
check(len(stats.recent_resources(2)) == 2, "recent resources respects the limit")

# ---- search and filters
check(len(stats.search_resources("chair")) == 1, "search by name")
check(len(stats.search_resources("", category="books")) == 1, "filter by category")
check(len(stats.search_resources("", condition="fair")) == 1, "filter by condition")
check(len(stats.search_resources("zzz-nothing")) == 0, "search with no result")
check(len(stats.search_resources("", status="available")) == 3, "filter by status")

# ---- exchange flow, counted by the stats
org_id = tools.dispatch("find_matches", {"resource_id": chair})["matches"][0]["org_id"]
eid = tools.dispatch("create_exchange_request", {"resource_id": chair, "org_id": org_id})["exchange_id"]
c = stats.dashboard_counts()
check(c["pending_exchanges"] == 1 and c["requested_resources"] == 1 and c["available_resources"] == 2,
      "counts after request")
check(stats.recent_exchanges(1)[0]["resource"] == "Wooden chair", "recent exchange shows resource name")
check(stats.recent_exchanges(1)[0]["organisation"], "recent exchange shows organisation name")

tools.confirm_exchange_approval(eid, True)
c = stats.dashboard_counts()
check(c["approved_exchanges"] == 1 and c["kg_diverted_estimate"] == 0, "approved: no impact yet")

tools.confirm_exchange_completion(eid, True)
c = stats.dashboard_counts()
check(c["completed_exchanges"] == 1 and c["transferred_resources"] == 1, "completed counts")
check(c["kg_diverted_estimate"] > 0 and c["co2e_avoided_kg_estimate"] > 0, "impact totals above zero")

# ---- impact queries
by_cat = stats.impact_by_category()
check(len(by_cat) == 1 and by_cat[0]["category"] == "furniture" and by_cat[0]["transfers"] == 1,
      "impact by category")
check(len(stats.impact_by_date()) == 1 and stats.impact_by_date()[0]["transfers"] == 1,
      "impact by date")
rows = stats.impact_report_rows()
check(len(rows) == 1 and rows[0]["resource"] == "Wooden chair" and rows[0]["organisation"],
      "report rows: one per completed transfer")

# ---- completing again cannot add a second record
tools.confirm_exchange_completion(eid, True)
check(len(stats.impact_report_rows()) == 1, "impact still recorded exactly once")

# ---- timeline
ex = database.get_exchange(eid)
events = stats.exchange_timeline(ex)
names = [e["event"] for e in events]
check(names[0] == "Request created" and any("hand-over" in n for n in names), "timeline: completed exchange")
check(any(e["note"] == "time not recorded" for e in events), "timeline: approval time honestly unrecorded")
pending = {"status": "pending", "created_at": "2026-01-01T10:00:00"}
check(len(stats.exchange_timeline(pending)) == 1, "timeline: pending has one event")

print(f"\nALL STATS TESTS PASSED ({PASSED} checks)")