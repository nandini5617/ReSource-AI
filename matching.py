"""Deterministic, explainable resource-to-organisation matching."""
from __future__ import annotations

import database
import impact

_CITY_ALIASES = {"new delhi": "delhi", "gurgaon": "gurugram"}


def _city(value: str | None) -> str:
    v = (value or "").strip().lower()
    return _CITY_ALIASES.get(v, v)


def _split(value: str | None) -> list[str]:
    return [p.strip() for p in (value or "").split(",") if p.strip()]


def find_matches(category: str, quantity: float, unit: str, condition: str,
                 location: str, disposition: str | None = None, limit: int = 5) -> list[dict]:
    kg = impact.to_kg(quantity, unit, category)
    results: list[dict] = []

    for org in database.list_orgs():
        if category not in _split(org["accepts"]):
            continue
        if condition not in _split(org["conditions"]):
            continue

        score = 70  # 50 for category + 20 for condition
        reasons = [f"Accepts {category}", f"Accepts items in '{condition}' condition"]

        if location and _city(org["city"]) == _city(location):
            score += 20
            reasons.append(f"Located in {org['city']} ({org['area']}), same city as the item")
        else:
            reasons.append(f"Located in {org['city']}, outside {location or 'your area'}")

        min_kg, max_kg = org["min_kg"], org["max_kg"]
        if min_kg and kg < min_kg:
            score -= 10
            reasons.append(f"Usually wants at least {min_kg:g} kg; this is about {kg:.1f} kg (estimated)")
        elif max_kg and kg > max_kg:
            score -= 10
            reasons.append(f"Limited capacity (max {max_kg:g} kg); this is about {kg:.1f} kg (estimated)")
        else:
            score += 10
            reasons.append(f"Quantity (~{kg:.1f} kg) fits their capacity")

        if disposition and org["role"] == disposition:
            score += 10
            reasons.append(f"Matches the recommended action: {disposition}")

        results.append({
            "org_id": org["id"],
            "name": org["name"],
            "type": org["org_type"],
            "role": org["role"],
            "city": org["city"],
            "area": org["area"],
            "score": max(0, min(100, score)),
            "reasons": reasons,
        })

    results.sort(key=lambda r: (-r["score"], r["name"]))
    return results[:limit]
    