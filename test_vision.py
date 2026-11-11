"""Run:  python test_vision.py   (no API key, no network, no image leaves this machine)"""
import io
import os

os.environ["RESOURCE_AI_MOCK"] = "0"           # exercise the real routing code paths
os.environ["RESOURCE_AI_MAX_IMAGE_MB"] = "1"   # small limit so the oversize test is cheap

from PIL import Image  # noqa: E402

import config  # noqa: E402  (this loads .env)
import vision  # noqa: E402

# Make the test independent of the developer's .env: clear vision settings AFTER
# config has loaded it, so the defaults are what get tested.
for _k in ("GEMINI_VISION_MODEL", "GROQ_VISION_MODEL", "OPENROUTER_VISION_MODEL",
           "RESOURCE_AI_VISION_ORDER"):
    os.environ.pop(_k, None)

PASSED = 0


def check(condition: bool, label: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"FAILED: {label}")
    PASSED += 1
    print(f"  ok  {label}")


def make_image(fmt="JPEG", size=(64, 48), mode="RGB", color=(40, 140, 60)) -> bytes:
    buf = io.BytesIO()
    Image.new(mode, size, color).save(buf, format=fmt)
    return buf.getvalue()


def rejects(data, filename="photo.jpg") -> str | None:
    try:
        vision.validate_image(data, filename)
    except vision.VisionError as exc:
        return str(exc)
    return None


def set_keys(gemini=False, groq=False, openrouter=False):
    for name, on in (("GEMINI_API_KEY", gemini), ("GROQ_API_KEY", groq),
                     ("OPENROUTER_API_KEY", openrouter)):
        if on:
            os.environ[name] = "test-key-not-real"
        else:
            os.environ.pop(name, None)


# ---- validation: accepted formats
for fmt, fname in (("JPEG", "a.jpg"), ("JPEG", "a.jpeg"), ("PNG", "a.png"), ("WEBP", "a.webp")):
    info = vision.validate_image(make_image(fmt), fname)
    check(info["format"] == fmt, f"validation accepts {fname}")

# ---- validation: rejected inputs
check(rejects(b"") is not None, "empty file rejected")
check(rejects(b"x" * (2 * 1024 * 1024)) is not None, "oversize file rejected")
check("Unsupported file type" in (rejects(make_image("JPEG"), "photo.gif") or ""),
      "wrong extension rejected")
check(rejects(b"this is plain text, not an image", "fake.jpg") is not None,
      "text file renamed .jpg rejected")
check(rejects(b"\xff\xd8\xff corrupt bytes", "bad.jpg") is not None, "corrupt image rejected")
check("not JPG, PNG or WEBP" in (rejects(make_image("GIF", mode="P", color=1), "pic.png") or ""),
      "GIF disguised as .png rejected by real contents")

# ---- preparation
jpeg, mime = vision.prepare_image(make_image("PNG", (3000, 2000)), "big.png")
check(mime == "image/jpeg" and jpeg[:2] == b"\xff\xd8", "prepare_image outputs a JPEG")
with Image.open(io.BytesIO(jpeg)) as out:
    check(max(out.size) <= vision.MAX_SIDE, "large image downscaled")
jpeg, _ = vision.prepare_image(make_image("PNG", (50, 50), "RGBA", (10, 200, 10, 0)), "t.png")
check(jpeg[:2] == b"\xff\xd8", "transparent PNG converts to JPEG")

# ---- normalisation
r = vision.normalize_result(
    {"name": "Wooden chair", "category": "furniture", "visible_condition": "good",
     "disposition": "reuse", "hazardous": False, "ideas": ["Donate it", "Repaint it"],
     "reasoning": "Looks sturdy.", "confidence": "high"}, "gemini", "m")
check(r["category"] == "furniture" and r["confidence"] == "high" and len(r["ideas"]) == 2,
      "valid result kept")
check("weight" in r["limitations"] and "quantity" in r["limitations"],
      "result carries the photo limitations note")
r = vision.normalize_result(
    {"category": "spaceship", "visible_condition": "mint", "disposition": "burn",
     "confidence": "certain", "hazardous": "yes", "ideas": "not a list"}, "gemini", "m")
check(r["category"] == "other" and r["visible_condition"] == "fair" and r["disposition"] == "reuse",
      "invalid category/condition/disposition fall back to safe values")
check(r["confidence"] == "low" and r["hazardous"] is False and r["ideas"] == [] and r["name"],
      "invalid confidence/hazardous/ideas handled")
try:
    vision.normalize_result(["not", "a", "dict"], "gemini", "m")
    check(False, "non-dict reply rejected")
except vision.VisionError:
    check(True, "non-dict reply rejected")

# ---- JSON parsing
check(vision._parse_json('```json\n{"a": 1}\n```') == {"a": 1}, "fenced JSON parsed")
check(vision._parse_json('<think>hmm</think>{"a": 2}') == {"a": 2}, "<think> block stripped")
try:
    vision._parse_json("no json here")
    check(False, "garbage reply rejected")
except vision.VisionError:
    check(True, "garbage reply rejected")

# ---- provider selection rules (default order is groq, gemini, openrouter)
set_keys(gemini=True, groq=True, openrouter=True)
check(config.get_vision_providers() == ["gemini"],
      "only providers with a vision model are eligible (text-only never used)")
os.environ["GROQ_VISION_MODEL"] = "fake-groq-vision"
check(config.get_vision_providers() == ["groq", "gemini"],
      "setting a vision model enables that provider (default order: groq first)")
os.environ["RESOURCE_AI_VISION_ORDER"] = "gemini,groq"
check(config.get_vision_providers() == ["gemini", "groq"], "vision order is respected")
os.environ.pop("RESOURCE_AI_VISION_ORDER")
os.environ.pop("GROQ_VISION_MODEL")

set_keys()                                   # no keys at all
try:
    vision.analyze_image(make_image(), "a.jpg")
    check(False, "no provider configured raises")
except vision.VisionError as exc:
    check("never" in str(exc).lower(),
          "no vision provider: clear error, nothing sent")

# ---- mock mode (no network)
os.environ["RESOURCE_AI_MOCK"] = "1"
m = vision.analyze_image(make_image(), "a.jpg", "old lamp")
check(m["provider"] == "offline demo" and "NOT analysed" in " ".join(m["ideas"]),
      "mock mode is honest: image not analysed")
check(m["name"] == "old lamp", "mock mode uses the user's description")
try:
    vision.analyze_image(b"junk", "a.jpg")
    check(False, "mock mode still validates")
except vision.VisionError:
    check(True, "mock mode still validates the image")
os.environ["RESOURCE_AI_MOCK"] = "0"

# ---- failure handling and fallback (fake providers, no network)
set_keys(gemini=True, groq=True)
os.environ["GROQ_VISION_MODEL"] = "fake-groq-vision"
os.environ["RESOURCE_AI_VISION_ORDER"] = "gemini,groq"   # explicit: gemini fails first
calls = []
good = {"name": "Lamp", "category": "electronics", "visible_condition": "good",
        "disposition": "repair", "ideas": ["Rewire it"], "confidence": "medium"}


def fake_call(provider, jpeg, mime, prompt):
    calls.append(provider)
    if provider == "gemini":
        raise RuntimeError("504 DEADLINE_EXCEEDED simulated")
    return vision.normalize_result(good, provider, "fake")


real_call = vision._call_provider
vision._call_provider = fake_call
res = vision.analyze_image(make_image(), "a.jpg")
check(calls == ["gemini", "groq"] and res["provider"] == "groq",
      "vision falls back to the next provider when one fails")


def always_fail(provider, jpeg, mime, prompt):
    raise RuntimeError("boom with key test-key-not-real inside")


vision._call_provider = always_fail
try:
    vision.analyze_image(make_image(), "a.jpg")
    check(False, "all providers failing raises")
except vision.VisionError as exc:
    msg = str(exc)
    check("All vision providers failed" in msg and "gemini" in msg and "groq" in msg,
          "all failing: readable error naming each provider")
    check("test-key-not-real" not in msg, "error message does not leak key text")
vision._call_provider = real_call
os.environ.pop("RESOURCE_AI_VISION_ORDER", None)

check(vision._call_provider.__name__ == "_call_provider", "real provider function restored")

print(f"\nALL VISION TESTS PASSED ({PASSED} checks)")