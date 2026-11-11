"""SQLite storage: resources, organisations (sample data), exchanges, impact log."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from config import get_settings


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def _conn():
    path = Path(get_settings().db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def _row(cur) -> dict | None:
    r = cur.fetchone()
    return dict(r) if r else None


SCHEMA = """
CREATE TABLE IF NOT EXISTS resources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    material TEXT,
    condition TEXT NOT NULL,
    quantity REAL NOT NULL,
    unit TEXT NOT NULL,
    location TEXT,
    disposition TEXT,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'available',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS organizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    org_type TEXT NOT NULL,
    role TEXT NOT NULL,
    city TEXT NOT NULL,
    area TEXT,
    accepts TEXT NOT NULL,
    conditions TEXT NOT NULL,
    min_kg REAL,
    max_kg REAL,
    description TEXT
);
CREATE TABLE IF NOT EXISTS exchanges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id INTEGER NOT NULL,
    org_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS impact_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange_id INTEGER,
    resource_id INTEGER,
    category TEXT,
    action TEXT,
    kg_diverted REAL,
    co2e_avoided_kg REAL,
    is_estimate INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
"""

# SAMPLE DATA ONLY - fictional organisations for demo/testing.
# (name, org_type, role, city, area, accepts, conditions, min_kg, max_kg, description)
SEED_ORGS = [
    ("[Demo] Asha Community School", "school", "reuse", "Delhi", "Civil Lines",
     "books,paper,furniture,electronics", "new,good,fair", None, 200,
     "Primary school that accepts books, desks and working electronics."),
    ("[Demo] Seva Clothes Bank", "ngo", "reuse", "Delhi", "Karol Bagh",
     "textile", "new,good,fair", None, 150, "Distributes wearable clothes and blankets."),
    ("[Demo] Shelter Home Delhi", "ngo", "reuse", "Delhi", "Rohini",
     "furniture,textile,books", "new,good,fair", None, 300, "Furnishes shelter rooms for families."),
    ("[Demo] City Library Trust", "ngo", "reuse", "Delhi", "Daryaganj",
     "books,paper", "new,good,fair", None, 100, "Community lending library."),
    ("[Demo] Repair Cafe Collective", "community", "repair", "Delhi", "Hauz Khas",
     "electronics,furniture,textile", "fair,poor,broken", None, 100,
     "Volunteers who fix items for re-donation."),
    ("[Demo] Makers Studio Upcycle Lab", "makerspace", "repair", "Delhi", "Okhla",
     "wood,metal,glass,plastic,textile,paper,furniture", "good,fair,poor", None, 250,
     "Upcycling workshop that turns waste into products."),
    ("[Demo] Authorised E-Waste Recycler", "recycler", "recycle", "Delhi", "Mundka",
     "electronics", "fair,poor,broken", None, None, "Authorised e-waste dismantling unit."),
    ("[Demo] GreenLoop Plastic Recyclers", "recycler", "recycle", "Delhi", "Narela",
     "plastic,metal", "good,fair,poor,broken", 10, None, "Buys sorted plastic and metal; 10 kg minimum."),
    ("[Demo] Paper Collection Point", "recycler", "recycle", "Delhi", "Shahdara",
     "paper,books", "good,fair,poor,broken", 5, None, "Collects paper and cardboard for pulping."),
    ("[Demo] Metro Scrap Dealer", "recycler", "recycle", "Delhi", "Mayapuri",
     "metal", "good,fair,poor,broken", 5, None, "Metal scrap dealer."),
    ("[Demo] Kisan Compost Co-op", "coop", "recycle", "Gurugram", "Sector 56",
     "organic", "new,good,fair,poor,broken", None, 500, "Composts food and garden waste."),
    ("[Demo] Build Again Housing NGO", "ngo", "reuse", "Noida", "Sector 62",
     "construction,wood,metal", "new,good,fair", None, 2000, "Reuses building material for low-cost housing."),
    ("[Demo] Glass Recycling Unit", "recycler", "recycle", "Faridabad", "Sector 24",
     "glass", "good,fair,poor,broken", 10, None, "Glass cullet recycling."),
]


def init_db() -> None:
    """Create tables and insert sample organisations if the table is empty."""
    with _conn() as c:
        c.executescript(SCHEMA)
        if c.execute("SELECT COUNT(*) FROM organizations").fetchone()[0] == 0:
            c.executemany(
                "INSERT INTO organizations (name, org_type, role, city, area, accepts, "
                "conditions, min_kg, max_kg, description) VALUES (?,?,?,?,?,?,?,?,?,?)",
                SEED_ORGS,
            )


# ---------------------------------------------------------------- resources
def add_resource(name, category, material, condition, quantity, unit,
                 location, disposition, notes="") -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO resources (name, category, material, condition, quantity, unit, "
            "location, disposition, notes, status, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?, 'available', ?)",
            (name, category, material, condition, quantity, unit, location,
             disposition, notes, _now()),
        )
        return int(cur.lastrowid)


def get_resource(resource_id: int) -> dict | None:
    with _conn() as c:
        return _row(c.execute("SELECT * FROM resources WHERE id=?", (resource_id,)))


def list_resources(limit: int = 20) -> list[dict]:
    with _conn() as c:
        return _rows(c.execute("SELECT * FROM resources ORDER BY id DESC LIMIT ?", (limit,)))


def set_resource_status(resource_id: int, status: str) -> None:
    with _conn() as c:
        c.execute("UPDATE resources SET status=? WHERE id=?", (status, resource_id))


# ------------------------------------------------------------ organisations
def list_orgs() -> list[dict]:
    with _conn() as c:
        return _rows(c.execute("SELECT * FROM organizations ORDER BY id"))


def get_org(org_id: int) -> dict | None:
    with _conn() as c:
        return _row(c.execute("SELECT * FROM organizations WHERE id=?", (org_id,)))


# ---------------------------------------------------------------- exchanges
def create_exchange(resource_id: int, org_id: int, message: str = "") -> int:
    now = _now()
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO exchanges (resource_id, org_id, status, message, created_at, updated_at) "
            "VALUES (?,?, 'pending', ?, ?, ?)",
            (resource_id, org_id, message, now, now),
        )
        return int(cur.lastrowid)


def get_exchange(exchange_id: int) -> dict | None:
    with _conn() as c:
        return _row(c.execute("SELECT * FROM exchanges WHERE id=?", (exchange_id,)))


def set_exchange_status(exchange_id: int, status: str) -> None:
    now = _now()
    with _conn() as c:
        c.execute(
            "UPDATE exchanges SET status=?, updated_at=?, "
            "completed_at=CASE WHEN ?='completed' THEN ? ELSE completed_at END WHERE id=?",
            (status, now, status, now, exchange_id),
        )


def list_exchanges(limit: int = 20) -> list[dict]:
    with _conn() as c:
        return _rows(c.execute("SELECT * FROM exchanges ORDER BY id DESC LIMIT ?", (limit,)))


# ------------------------------------------------------------------- impact
def log_impact(exchange_id, resource_id, category, action, kg, co2e) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO impact_log (exchange_id, resource_id, category, action, kg_diverted, "
            "co2e_avoided_kg, is_estimate, created_at) VALUES (?,?,?,?,?,?,1,?)",
            (exchange_id, resource_id, category, action, kg, co2e, _now()),
        )
        return int(cur.lastrowid)


def impact_summary() -> dict:
    with _conn() as c:
        row = c.execute(
            "SELECT COUNT(*) AS transfers, COALESCE(SUM(kg_diverted),0) AS kg, "
            "COALESCE(SUM(co2e_avoided_kg),0) AS co2e FROM impact_log"
        ).fetchone()
    return {
        "completed_transfers": row["transfers"],
        "kg_diverted_estimate": round(row["kg"], 2),
        "co2e_avoided_kg_estimate": round(row["co2e"], 2),
        "note": "All totals are ESTIMATES from generic factors, not verified measurements.",
    }
    