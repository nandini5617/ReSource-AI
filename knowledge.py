"""Constants and fallback knowledge shared across ReSource AI modules."""
from __future__ import annotations

CATEGORIES = [
    "plastic", "paper", "metal", "glass", "textile", "electronics",
    "furniture", "wood", "organic", "construction", "books", "other",
]
CONDITIONS = ["new", "good", "fair", "poor", "broken"]
DISPOSITIONS = ["reuse", "repair", "recycle", "dispose"]
UNITS = ["kg", "pieces"]

EXCHANGE_STATUSES = ["pending", "approved", "rejected", "completed", "cancelled"]
ALLOWED_TRANSITIONS = {
    "pending": {"approved", "rejected", "cancelled"},
    "approved": {"completed", "cancelled"},
    "rejected": set(),
    "completed": set(),
    "cancelled": set(),
}

# Order matters: the first category whose keyword matches wins.
KEYWORDS = {
    "electronics": ["laptop", "phone", "mobile", "charger", "tv", "television", "monitor",
                    "computer", "keyboard", "battery", "batteries", "cable", "circuit",
                    "printer", "electronic", "router", "fan", "speaker"],
    "furniture": ["table", "chair", "sofa", "desk", "bed", "cupboard", "almirah",
                  "wardrobe", "shelf", "shelves", "furniture", "couch", "mattress", "bench"],
    "books": ["book", "novel", "textbook", "notebook", "magazine"],
    "textile": ["cloth", "shirt", "jeans", "saree", "fabric", "curtain", "blanket",
                "textile", "jacket", "shoe", "bedsheet", "garment"],
    "plastic": ["plastic", "pet bottle", "bottle", "bucket", "container", "polythene", "packaging"],
    "paper": ["paper", "cardboard", "carton", "newspaper", "box"],
    "metal": ["metal", "steel", "iron", "aluminium", "aluminum", "copper", "scrap", "utensil", "tin can"],
    "glass": ["glass", "jar", "window pane"],
    "wood": ["wood", "plank", "pallet", "timber", "plywood"],
    "construction": ["brick", "cement", "tile", "rubble", "sand", "pipe"],
    "organic": ["food", "vegetable", "peel", "leaves", "kitchen waste", "compost", "garden waste"],
}

HAZARD_KEYWORDS = ["paint", "chemical", "pesticide", "asbestos", "syringe",
                   "medical waste", "mercury", "tube light", "cfl"]

KNOWN_CITIES = ["new delhi", "delhi", "gurugram", "gurgaon", "noida", "faridabad", "ghaziabad"]
DEFAULT_CITY = "Delhi"

REPAIRABLE = {"electronics", "furniture", "textile", "wood"}

# Used when Gemini is unavailable or in offline/mock mode.
FALLBACK_IDEAS = {
    "plastic": [
        {"idea": "Cut bottles into self-watering planters or seed trays", "effort": "low", "why": "Needs only scissors; keeps plastic out of landfill."},
        {"idea": "Donate clean containers to a school art or science class", "effort": "low", "why": "Direct reuse without reprocessing."},
        {"idea": "Send sorted plastic to an authorised recycler", "effort": "low", "why": "Closes the loop for items that cannot be reused."},
    ],
    "paper": [
        {"idea": "Reuse clean sides for rough notes or craft", "effort": "low", "why": "Extends paper life before recycling."},
        {"idea": "Make seed paper or paper-bag packaging", "effort": "medium", "why": "Turns waste into a sellable product."},
        {"idea": "Give to a paper-collection point for recycling", "effort": "low", "why": "Recycled paper uses less energy than virgin pulp."},
    ],
    "metal": [
        {"idea": "Give to a maker space for upcycled art or tools", "effort": "medium", "why": "Metal keeps its value when reused whole."},
        {"idea": "Sell sorted scrap to a metal dealer", "effort": "low", "why": "Metals are highly recyclable."},
        {"idea": "Repurpose cans/utensils as planters or organisers", "effort": "low", "why": "Quick household reuse."},
    ],
    "glass": [
        {"idea": "Reuse jars for storage or candles", "effort": "low", "why": "Glass is durable and easy to clean."},
        {"idea": "Send broken glass to a glass recycling unit (wrapped safely)", "effort": "low", "why": "Glass can be recycled repeatedly."},
    ],
    "textile": [
        {"idea": "Donate wearable clothes to a clothes bank or shelter", "effort": "low", "why": "Highest-value reuse for textiles."},
        {"idea": "Turn worn fabric into cleaning rags, bags or quilts", "effort": "medium", "why": "Gives a second life to unwearable cloth."},
    ],
    "electronics": [
        {"idea": "Repair or refurbish at a repair cafe, then donate", "effort": "medium", "why": "Electronics have the highest embodied carbon per kg."},
        {"idea": "Harvest working parts (screens, cables, drives)", "effort": "medium", "why": "Parts can fix other devices."},
        {"idea": "Hand dead devices to an authorised e-waste recycler", "effort": "low", "why": "Safe recovery of metals; avoids toxic leakage."},
    ],
    "furniture": [
        {"idea": "Donate usable pieces to a shelter, school or furniture bank", "effort": "low", "why": "Direct reuse is the best outcome."},
        {"idea": "Repair joints/legs and refinish", "effort": "medium", "why": "Small repairs often restore full function."},
        {"idea": "Upcycle into shelves, planters or kids' furniture", "effort": "medium", "why": "Reuses solid wood and hardware."},
    ],
    "wood": [
        {"idea": "Reuse planks/pallets for shelves, planters or compost bins", "effort": "medium", "why": "Solid wood is easy to repurpose."},
        {"idea": "Offer to a maker space or housing NGO", "effort": "low", "why": "Others can use offcuts."},
    ],
    "organic": [
        {"idea": "Compost at home or give to a compost co-op", "effort": "low", "why": "Returns nutrients to soil and avoids methane from landfill."},
        {"idea": "Use peels/leaves for natural cleaners or mulch", "effort": "low", "why": "Reuse before composting."},
    ],
    "construction": [
        {"idea": "Offer bricks/tiles to a housing NGO or builder", "effort": "low", "why": "Reuse saves cement and fired-clay emissions."},
        {"idea": "Use rubble as filler or garden paths", "effort": "medium", "why": "Keeps heavy waste out of landfill."},
    ],
    "books": [
        {"idea": "Donate to a library trust or school", "effort": "low", "why": "Books reach new readers."},
        {"idea": "Swap at a community book exchange", "effort": "low", "why": "Zero-cost reuse."},
    ],
    "other": [
        {"idea": "List it with a local reuse group or donate to a charity shop", "effort": "low", "why": "Someone nearby may need it."},
        {"idea": "Check if it can be taken apart and sorted by material", "effort": "medium", "why": "Sorted materials are easier to recycle."},
    ],
}