"""Read-only statistics and queries for the ReSource AI dashboard.

Nothing in this module writes to the database. All writes (saving resources,
exchange changes, impact logging) stay in tools.py and database.py, so the
exchange safeguards cannot be affected by the UI.
"""
from __future__ import annotations

import database


def _all(sql: str, params: tuple = ()) -> list[dict]:
    with database._conn() as conn:
        return database._rows(conn.execute(sql, params))


# ---------------------------------------------------------------- dashboard
def dashboard_counts() -> dict:
    resources = {r["status"]: r["n"] for r in
                 _all("SELECT status, COUNT(*) AS n FROM resources GROUP BY status")}
    exchanges = {r["status"]: r["n"] for r in
                 _all("SELECT status, COUNT(*) AS n FROM exchanges GROUP BY status")}
    summary = database.impact_summary()
    return {
        "total_resources": sum(resources.values()),
        "available_resources": resources.get("available", 0),
        "requested_resources": resources.get("requested", 0),
        "transferred_resources": resources.get("transferred", 0),
        "pending_exchanges": exchanges.get("pending", 0),
        "approved_exchanges": exchanges.get("approved", 0),
        "completed_exchanges": exchanges.get("completed", 0),
        "closed_exchanges": exchanges.get("rejected", 0) + exchanges.get("cancelled", 0),
        "kg_diverted_estimate": summary["kg_diverted_estimate"],
        "co2e_avoided_kg_estimate": summary["co2e_avoided_kg_estimate"],
    }


def category_distribution() -> list[dict]:
    return _all("SELECT category, COUNT(*) AS count FROM resources "
                "GROUP BY category ORDER BY count DESC, category")


def recent_resources(limit: int = 6) -> list[dict]:
    return _all("SELECT id, name, category, condition, quantity, unit, status, created_at "
                "FROM resources ORDER BY id DESC LIMIT ?", (limit,))


def recent_exchanges(limit: int = 6) -> list[dict]:
    return _all(
        "SELECT e.id, e.status, e.created_at, e.updated_at, "
        "r.name AS resource, o.name AS organisation "
        "FROM exchanges e "
        "LEFT JOIN resources r ON r.id = e.resource_id "
        "LEFT JOIN organizations o ON o.id = e.org_id "
        "ORDER BY e.id DESC LIMIT ?", (limit,))


# ------------------------------------------------------------------- impact
def impact_by_category() -> list[dict]:
    return _all("SELECT category, COUNT(*) AS transfers, "
                "ROUND(SUM(kg_diverted), 2) AS kg, "
                "ROUND(SUM(co2e_avoided_kg), 2) AS co2e "
                "FROM impact_log GROUP BY category ORDER BY co2e DESC")


def impact_by_date() -> list[dict]:
    return _all("SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS transfers, "
                "ROUND(SUM(kg_diverted), 2) AS kg, "
                "ROUND(SUM(co2e_avoided_kg), 2) AS co2e "
                "FROM impact_log GROUP BY day ORDER BY day")


def impact_report_rows() -> list[dict]:
    """One row per recorded transfer, for the downloadable report."""
    return _all(
        "SELECT i.id AS record, i.exchange_id, i.resource_id, "
        "r.name AS resource, i.category, i.action, i.kg_diverted, "
        "i.co2e_avoided_kg, o.name AS organisation, i.created_at "
        "FROM impact_log i "
        "LEFT JOIN resources r ON r.id = i.resource_id "
        "LEFT JOIN exchanges e ON e.id = i.exchange_id "
        "LEFT JOIN organizations o ON o.id = e.org_id "
        "ORDER BY i.id")


# ----------------------------------------------------------------- explorer
def search_resources(query: str = "", category: str | None = None,
                     condition: str | None = None, status: str | None = None,
                     limit: int = 200) -> list[dict]:
    sql = "SELECT * FROM resources WHERE 1=1"
    params: list = []
    query = (query or "").strip().lower()
    if query:
        sql += (" AND (lower(name) LIKE ? OR lower(material) LIKE ? "
                "OR lower(notes) LIKE ? OR lower(location) LIKE ?)")
        like = f"%{query}%"
        params += [like, like, like, like]
    for column, value in (("category", category), ("condition", condition),
                          ("status", status)):
        if value:
            sql += f" AND {column} = ?"
            params.append(value)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(int(limit))
    return _all(sql, tuple(params))


# ----------------------------------------------------------------- timeline
def exchange_timeline(exchange: dict) -> list[dict]:
    """Events for one exchange, using only timestamps that are really stored."""
    status = exchange.get("status")
    events = [{"event": "Request created", "time": exchange.get("created_at"), "note": ""}]
    if status in ("approved", "completed"):
        events.append({"event": "Organisation acceptance confirmed by user",
                       "time": None, "note": "time not recorded"})
    if status == "completed":
        events.append({"event": "Physical hand-over confirmed by user",
                       "time": exchange.get("completed_at"), "note": ""})
    elif status == "rejected":
        events.append({"event": "Organisation declined (recorded by user)",
                       "time": exchange.get("updated_at"), "note": ""})
    elif status == "cancelled":
        events.append({"event": "Request cancelled",
                       "time": exchange.get("updated_at"), "note": ""})
    return events