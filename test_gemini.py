"""Run:  python test_gemini.py"""
from gemini_client import generate_json, health_check, is_configured

if not is_configured():
    print("FAIL: GEMINI_API_KEY not set. Create .env from .env.example first.")
    raise SystemExit(1)

ok, msg = health_check()
print("Health check:", "PASS" if ok else "FAIL", "-", msg)
if not ok:
    raise SystemExit(1)

data = generate_json(
    "Classify this item: 'old wooden study table with a broken leg'. "
    'Return JSON with keys: "category", "action" (reuse|recycle|repair|dispose), "reason".',
    system="You are a resource-recovery expert. Return only JSON.",
)
print("Structured output:", data)
