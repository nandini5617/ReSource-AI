"""Resource understanding: classify a description and suggest reuse ideas.

Uses the AI router (Groq -> Gemini -> OpenRouter) when cloud AI is available;
falls back to keyword heuristics (offline/mock mode or if every provider
fails) so the app always returns something usable.
"""
from __future__ import annotations

import re

import knowledge as K
from ai_router import AIRouterError, route_json
from config import is_mock_mode, redact


# ----------------------------------------------------------- heuristic engine
def _detect_category(text: str) -> str:
    for category, words in K.KEYWORDS.items():
        if any(re.search(r"\b" + re.escape(w), text) for w in words):
            return category
    return "other"


def _detect_condition(text: str) -> str:
    if re.search(r"broken|not working|dead|faulty|non-functional", text):
        return "broken"
    if re.search(r"damaged|cracked|torn|rust|worn|leaking", text):
        return "poor"
    if re.search(r"brand new|unused|sealed|unopened|\bnew\b", text):
        return "new"
    if re.search(r"\bgood\b|working|excellent|like new|clean", text):
        return "good"
    return "fair"


def _detect_quantity(text: str) -> tuple[float, str]:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(kg|kgs|kilograms?|grams?|g|tonnes?|tons?)\b", text)
    if m:
        value, unit = float(m.group(1)), m.group(2)
        if unit.startswith("g"):
            return value / 1000.0, "kg"
        if unit.startswith("t"):
            return value * 1000.0, "kg"
        return value, "kg"
    m = re.search(r"\b(\d{1,5})\b", text)
    if m:
        return float(m.group(1)), "pieces"
    return 1.0, "pieces"


def _detect_location(text: str) -> str:
    for city in K.KNOWN_CITIES:
        if city in text:
            return "Delhi" if city == "new delhi" else city.title()
    return K.DEFAULT_CITY


def decide_disposition(category: str, condition: str, hazardous: bool) -> str:
    if hazardous:
        return "dispose"
    if condition in ("new", "good", "fair"):
        return "reuse"
    if condition == "poor":
        return "repair" if category in K.REPAIRABLE else "recycle"
    # broken
    return "repair" if category in ("furniture", "textile") else "recycle"


def _heuristic(description: str) -> dict:
    text = description.lower()
    category = _detect_category(text)
    condition = _detect_condition(text)
    quantity, unit = _detect_quantity(text)
    hazardous = any(w in text for w in K.HAZARD_KEYWORDS)
    disposition = decide_disposition(category, condition, hazardous)
    reasoning = (
        f"Keyword analysis: looks like {category} in {condition} condition, "
        f"so the best action is '{disposition}'."
    )
    if hazardous:
        reasoning += " Possible hazardous material: use an authorised hazardous-waste channel."
    return {
        "name": description.strip()[:60],
        "category": category,
        "material": category,
        "condition": condition,
        "quantity": quantity,
        "unit": unit,
        "location": _detect_location(text),
        "disposition": disposition,
        "hazardous": hazardous,
        "reasoning": reasoning,
        "source": "heuristic",
    }


# ------------------------------------------------------------- cloud AI engine
_ANALYZE_PROMPT = """Analyse this description of a discarded, unused or surplus resource.
Return a JSON object with exactly these keys:
"name" (short item name),
"category" (one of: {categories}),
"material" (main material, e.g. "PET plastic", "teak wood"),
"condition" (one of: {conditions}),
"quantity" (number; use 1 if not stated),
"unit" ("kg" or "pieces"),
"location" (city if stated, otherwise "{city}"),
"disposition" (best action, one of: {dispositions}; prefer reuse > repair > recycle > dispose),
"hazardous" (true or false),
"reasoning" (1-2 sentences explaining the disposition).

Description: {description}"""


def _normalize(data: dict, description: str, provider: str) -> dict:
    base = _heuristic(description)  # safe defaults for anything missing/invalid
    category = str(data.get("category", "")).lower()
    condition = str(data.get("condition", "")).lower()
    unit = str(data.get("unit", "")).lower()
    disposition = str(data.get("disposition", "")).lower()
    try:
        quantity = float(data.get("quantity", 1))
        if quantity <= 0:
            quantity = 1.0
    except (TypeError, ValueError):
        quantity = base["quantity"]
    return {
        "name": str(data.get("name") or base["name"])[:80],
        "category": category if category in K.CATEGORIES else base["category"],
        "material": str(data.get("material") or base["material"])[:60],
        "condition": condition if condition in K.CONDITIONS else base["condition"],
        "quantity": quantity,
        "unit": unit if unit in K.UNITS else base["unit"],
        "location": str(data.get("location") or K.DEFAULT_CITY)[:40],
        "disposition": disposition if disposition in K.DISPOSITIONS else base["disposition"],
        "hazardous": bool(data.get("hazardous", False)),
        "reasoning": str(data.get("reasoning") or base["reasoning"]),
        "source": provider,
    }


def analyze_resource(description: str) -> dict:
    description = (description or "").strip()
    if not description:
        raise ValueError("Please describe the resource.")
    if is_mock_mode():
        return _heuristic(description)
    prompt = _ANALYZE_PROMPT.format(
        categories=", ".join(K.CATEGORIES),
        conditions=", ".join(K.CONDITIONS),
        dispositions=", ".join(K.DISPOSITIONS),
        city=K.DEFAULT_CITY,
        description=description,
    )
    try:
        data, provider = route_json(
            prompt, system="You are a circular-economy expert. Return only JSON."
        )
        if not isinstance(data, dict):
            raise AIRouterError("Unexpected JSON shape.")
        return _normalize(data, description, provider)
    except Exception as exc:  # noqa: BLE001 - always fall back to keyword rules
        result = _heuristic(description)
        result["source"] = f"heuristic (AI unavailable: {redact(str(exc))[:150]})"
        return result


# ---------------------------------------------------------------- reuse ideas
_IDEAS_PROMPT = """Suggest {n} practical reuse / upcycling / recycling ideas for this item.
Item: {name}. Category: {category}. Material: {material}. Condition: {condition}.
Return a JSON list; each element has keys "idea", "effort" (low|medium|high), "why"
(one sentence on practicality and environmental benefit). Order from best to worst
following the waste hierarchy (reuse > repair > upcycle > recycle). Be realistic for India."""


def _norm_ideas(raw, limit: int) -> list[dict]:
    if isinstance(raw, dict):
        raw = raw.get("ideas") or raw.get("suggestions") or []
    out: list[dict] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item.get("idea"):
                out.append({
                    "idea": str(item["idea"]),
                    "effort": str(item.get("effort", "medium")).lower(),
                    "why": str(item.get("why", "")),
                })
            elif isinstance(item, str):
                out.append({"idea": item, "effort": "medium", "why": ""})
    return out[:limit]


def generate_reuse_ideas(name: str, category: str, material: str = "",
                         condition: str = "fair", n: int = 4) -> dict:
    category = category if category in K.CATEGORIES else "other"
    fallback = K.FALLBACK_IDEAS.get(category, K.FALLBACK_IDEAS["other"])[:n]
    if is_mock_mode():
        return {"ideas": fallback, "source": "built-in knowledge base"}
    prompt = _IDEAS_PROMPT.format(
        n=n, name=name, category=category, material=material or category, condition=condition
    )
    try:
        raw, provider = route_json(prompt, system="Return only JSON.")
        ideas = _norm_ideas(raw, n)
        if ideas:
            return {"ideas": ideas, "source": provider}
    except Exception:  # noqa: BLE001 - fall back to the built-in knowledge base
        pass
    return {"ideas": fallback, "source": "built-in knowledge base (AI unavailable)"}