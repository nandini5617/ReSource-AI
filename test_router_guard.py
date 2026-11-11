"""Run:  python test_router_guard.py   (no network, no API key, no database)"""
import os
from types import SimpleNamespace

import config  # noqa: F401  (loads .env first; we then override below)

os.environ["GROQ_API_KEY"] = "test-key-not-real"
os.environ["GEMINI_API_KEY"] = "test-key-not-real"
os.environ.pop("OPENROUTER_API_KEY", None)
os.environ["RESOURCE_AI_PRIMARY_PROVIDER"] = "groq"

import ai_router as router  # noqa: E402

PASSED = 0


def check(condition: bool, label: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"FAILED: {label}")
    PASSED += 1
    print(f"  ok  {label}")


LOOP = ("Shelter home Delhi (ngo, Rohini) - wait, Rohini - "
        + "Rohoni? " * 60)
GOOD = ("Here is the plan for your 15 wooden tables: reuse them. The best match is "
        "Asha Community School with a score of 100, because it accepts furniture in "
        "good condition. Estimated impact is a rough estimate, not a measurement. "
        "Next step: ask me to create an exchange request.")


def fake_client(content, calls_log, reject_penalty=False):
    def create(**kwargs):
        calls_log.append(kwargs)
        if reject_penalty and "frequency_penalty" in kwargs:
            raise RuntimeError("Unknown parameter: frequency_penalty")
        text = content(kwargs) if callable(content) else content
        message = SimpleNamespace(content=text, tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def run(history=None):
    return router.run_agent(history or [], "i have 15 wooden tables", "system", [],
                            lambda name, args: {})


real_get_client = router._get_client
real_gemini = router.generate_with_tools


def reset():
    router.reset_clients()
    router._get_client = real_get_client
    router.generate_with_tools = real_gemini


def fake_gemini(text, log=None):
    def fn(contents, system, declarations, *a, **k):
        if log is not None:
            log.append(contents)
        return SimpleNamespace(function_calls=[], text=text)
    return fn


# ---- detector
check(router._looks_degenerate(LOOP), "detector: flags the 'Rohoni?' loop from the screenshot")
check(router._looks_degenerate("go home now " * 30), "detector: flags a repeated 3-word phrase")
check(router._looks_degenerate("yes no " * 30), "detector: flags a repeated 2-word phrase")
check(not router._looks_degenerate(GOOD), "detector: normal answer is fine")
check(not router._looks_degenerate("Reuse, reuse, reuse is the best action."), "detector: short text is fine")
check(not router._looks_degenerate("") and not router._looks_degenerate(None), "detector: empty/None is fine")

# ---- looping Groq answer -> falls back to Gemini
reset()
groq_calls, gem_calls = [], []
router._get_client = lambda provider: fake_client(LOOP, groq_calls)
router.generate_with_tools = fake_gemini(GOOD, gem_calls)
answer, trace, provider = run()
check(provider == "gemini" and answer.startswith("Here is the plan"),
      "looping Groq answer is discarded and Gemini answers instead")
check(len(groq_calls) == 1 and len(gem_calls) == 1, "each provider was tried once")

# ---- every provider loops -> clear error, nothing returned
reset()
router._get_client = lambda provider: fake_client(LOOP, [])
router.generate_with_tools = fake_gemini(LOOP)
try:
    run()
    check(False, "all providers looping raises")
except router.AIRouterError as exc:
    check("looping" in str(exc), "all providers looping: AIRouterError mentions the loop")

# ---- good Groq answer is used directly
reset()
groq_calls = []
router._get_client = lambda provider: fake_client(GOOD, groq_calls)
router.generate_with_tools = fake_gemini(LOOP)
answer, _, provider = run()
check(provider == "groq" and answer.startswith("Here is the plan"), "good Groq answer is used")

# ---- sampling parameters and token cap
call = groq_calls[0]
check(call["max_tokens"] <= 2048, "text answer capped at 2048 tokens")
check(call["temperature"] == 0.4 and call.get("frequency_penalty") == 0.3,
      "temperature 0.4 and frequency_penalty 0.3 are sent")

# ---- provider that rejects frequency_penalty: retried without it
reset()
log = []
router._get_client = lambda provider: fake_client(GOOD, log, reject_penalty=True)
answer, _, provider = run()
check(provider == "groq" and len(log) == 2, "frequency_penalty rejection is retried once")
check("frequency_penalty" in log[0] and "frequency_penalty" not in log[1],
      "the retry omits frequency_penalty")

# ---- looping answer already in memory is not sent back to the model
reset()
seen = []
router._get_client = lambda provider: fake_client(
    lambda kwargs: (seen.append(kwargs["messages"]), GOOD)[1], [])
run(history=[("earlier question", LOOP)])
sent = " ".join(str(m.get("content")) for m in seen[0])
check("Rohoni?" not in sent and "omitted" in sent, "looping answer in history is replaced")

reset()
print(f"\nALL ROUTER GUARD TESTS PASSED ({PASSED} checks)")