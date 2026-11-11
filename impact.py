"""Sustainability impact estimation.

IMPORTANT: every number here is an ESTIMATE based on rough, generic factors.
They are placeholders for demo purposes and are NOT verified measurements.
Replace EMISSION_FACTORS with values from a published life-cycle database
(and cite the source) before presenting results as scientific.
"""
from __future__ import annotations

ESTIMATE_LABEL = "ESTIMATE based on generic factors - not a verified measurement"

# Rough kg CO2e avoided per kg of material kept in use (illustrative only).
EMISSION_FACTORS = {
    "plastic": 1.5, "paper": 1.0, "metal": 2.0, "glass": 0.6, "textile": 8.0,
    "electronics": 12.0, "furniture": 1.5, "wood": 0.7, "organic": 0.4,
    "construction": 0.2, "books": 1.0, "other": 0.5,
}

# Typical weight of one piece, used when the quantity is given in pieces.
AVG_ITEM_KG = {
    "plastic": 0.05, "paper": 0.2, "metal": 0.5, "glass": 0.4, "textile": 0.4,
    "electronics": 2.5, "furniture": 12.0, "wood": 3.0, "organic": 0.5,
    "construction": 2.0, "books": 0.4, "other": 1.0,
}

# Reuse avoids most of the footprint; recycling avoids less; disposal avoids none.
ACTION_FACTOR = {"reuse": 1.0, "repair": 0.8, "recycle": 0.5, "dispose": 0.0}


def to_kg(quantity: float, unit: str, category: str) -> float:
    unit = (unit or "pieces").strip().lower()
    if unit in ("kg", "kgs", "kilogram", "kilograms"):
        return float(quantity)
    if unit in ("g", "gram", "grams"):
        return float(quantity) / 1000.0
    if unit in ("tonne", "tonnes", "ton", "tons"):
        return float(quantity) * 1000.0
    return float(quantity) * AVG_ITEM_KG.get(category, AVG_ITEM_KG["other"])


def estimate(category: str, quantity: float, unit: str, action: str) -> dict:
    category = category if category in EMISSION_FACTORS else "other"
    action = action if action in ACTION_FACTOR else "recycle"
    kg = to_kg(quantity, unit, category)
    diverted = kg if action != "dispose" else 0.0
    co2e = kg * EMISSION_FACTORS[category] * ACTION_FACTOR[action]

    assumptions = [f"Emission factor for {category}: {EMISSION_FACTORS[category]} kg CO2e per kg (illustrative)."]
    if (unit or "").lower() not in ("kg", "kgs", "g", "tonne", "tonnes"):
        assumptions.append(
            f"Weight estimated from pieces at ~{AVG_ITEM_KG.get(category, 1.0)} kg per item."
        )
    assumptions.append(f"Action '{action}' counts for {int(ACTION_FACTOR[action] * 100)}% of the footprint.")

    return {
        "category": category,
        "action": action,
        "kg_diverted": round(diverted, 2),
        "co2e_avoided_kg": round(co2e, 2),
        "is_estimate": True,
        "label": ESTIMATE_LABEL,
        "assumptions": assumptions,
    }