"""Run:  python test_vision_providers.py

LIVE probe: sends ONE small generated test image to each vision provider that has
an API key and a vision model configured. Uses a little free-tier quota.
PASS = the provider accepted the image and returned a valid structured reply.
It does not prove the recognition is accurate; read the printed reply yourself.
"""
import io
import os
import time

os.environ["RESOURCE_AI_MOCK"] = "0"

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import config  # noqa: E402
import vision  # noqa: E402


def make_probe_image() -> bytes:
    img = Image.new("RGB", (480, 320), (245, 245, 240))
    draw = ImageDraw.Draw(img)
    draw.rectangle((140, 110, 340, 250), fill=(150, 100, 50), outline=(60, 40, 20), width=4)
    draw.rectangle((140, 60, 340, 110), fill=(170, 120, 70), outline=(60, 40, 20), width=4)
    for x in (150, 320):
        draw.rectangle((x, 250, x + 14, 300), fill=(90, 60, 30))
    try:
        font = ImageFont.load_default(size=28)
    except TypeError:
        font = ImageFont.load_default()
    draw.text((20, 15), "PROBE IMAGE", fill=(20, 20, 20), font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def key_present(provider: str) -> bool:
    return {
        "gemini": bool(config.get_api_key()),
        "groq": bool(config.get_groq_api_key()),
        "openrouter": bool(config.get_openrouter_api_key()),
    }[provider]


jpeg, mime = vision.prepare_image(make_probe_image(), "probe.png")
prompt = vision._build_prompt("")
eligible = config.get_vision_providers()
results = {}

print("Vision provider probe (one request per provider)\n")
for provider in ("gemini", "groq", "openrouter"):
    model = config.get_vision_model(provider)
    if not key_present(provider):
        results[provider] = "SKIPPED"
        print(f"  [SKIPPED] {provider}: no API key set")
        continue
    if provider not in eligible:
        results[provider] = "SKIPPED"
        print(f"  [SKIPPED] {provider}: no vision model set "
              f"(set {provider.upper()}_VISION_MODEL in .env to test it)")
        continue
    start = time.monotonic()
    try:
        out = vision._call_provider(provider, jpeg, mime, prompt)
        secs = time.monotonic() - start
        results[provider] = "PASS"
        print(f"  [PASS]    {provider} ({model}) in {secs:.1f}s")
        print(f"            reply -> name: {out['name']!r}, category: {out['category']}, "
              f"condition: {out['visible_condition']}, action: {out['disposition']}, "
              f"confidence: {out['confidence']}")
    except Exception as exc:  # noqa: BLE001
        secs = time.monotonic() - start
        results[provider] = "FAIL"
        print(f"  [FAIL]    {provider} ({model}) after {secs:.1f}s: "
              f"{config.redact(str(exc))[:300]}")

print("\nSummary:", ", ".join(f"{p}={s}" for p, s in results.items()))
if "PASS" not in results.values():
    print("No vision provider passed. Image analysis will not work until one does.")