"""Run:  python test_impact.py   (temporary database, no network, no API key)"""
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["RESOURCE_AI_DB"] = os.path.join(_tmp, "impact_test.db")
os.environ["RESOURCE_AI_MOCK"] = "1"

from streamlit.testing.v1 import AppTest  # noqa: E402

import database  # noqa: E402
import tools  # noqa: E402
from views import impact as page  # noqa: E402

PASSED = 0


def check(condition: bool, label: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"FAILED: {label}")
    PASSED += 1
    print(f"  ok  {label}")


def run_page() -> AppTest:
    return AppTest.from_string("import views.impact as p\np.render()\n",
                               default_timeout=30).run()


# ---- pure helpers
check(page.csv_safe("=SUM(A1)") == "'=SUM(A1)", "csv_safe neutralises formulas")
check(page.csv_safe("@cmd") == "'@cmd" and page.csv_safe("+1") == "'+1", "csv_safe handles @ and +")
check(page.csv_safe("Chair") == "Chair" and page.csv_safe(3.5) == 3.5 and page.csv_safe(None) == "",
      "csv_safe leaves normal values alone")
text = page.build_csv([{"record": 1, "exchange_id": 2, "resource": "=evil()", "category": "furniture",
                        "action": "reuse", "organisation": "Org", "kg_diverted": 24.0,
                        "co2e_avoided_kg": 36.0, "created_at": "2026-01-01T10:00:00"}])
check("ESTIMATE" in text.splitlines()[0] and "'=evil()" in text, "CSV header labels estimates, cells are safe")
rows = page.trend_rows([{"day": "d1", "co2e": 2.0}, {"day": "d2", "co2e": 3.5}])
check(rows[-1]["cumulative_co2e"] == 5.5, "trend adds a cumulative total")
md = page.build_report_md({"completed_exchanges": 0, "kg_diverted_estimate": 0,
                           "co2e_avoided_kg_estimate": 0}, [], "now")
check("ESTIMATES" in md and "(none yet)" in md, "report states estimates and handles no data")

# ---- page: empty
database.init_db()
at = run_page()
check(not at.exception, "empty: page renders")
check(any("No impact recorded yet" in m.value for m in at.markdown), "empty: friendly message")

# ---- page: after one confirmed completion
rid = tools.dispatch("save_resource", {"name": "Wooden chair", "category": "furniture",
      "condition": "good", "quantity": 2, "unit": "pieces", "location": "Delhi"})["resource_id"]
org = tools.dispatch("find_matches", {"resource_id": rid})["matches"][0]["org_id"]
eid = tools.dispatch("create_exchange_request", {"resource_id": rid, "org_id": org})["exchange_id"]
tools.confirm_exchange_approval(eid, True)
tools.confirm_exchange_completion(eid, True)

at = run_page()
check(not at.exception, "with data: page renders")
check(any("Completed exchanges" in m.value for m in at.markdown), "with data: metrics shown")
check(any("ESTIMATE" in m.value for m in at.markdown), "with data: estimate label shown")
check(database.impact_summary()["completed_transfers"] == 1, "page is read-only: impact still one record")

print(f"\nALL IMPACT TESTS PASSED ({PASSED} checks)")