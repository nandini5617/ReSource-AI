"""Image-based resource recognition for ReSource AI.

Privacy: image bytes are processed in memory only. Nothing is written to disk,
the database or logs. The image is re-encoded as JPEG (this drops metadata
such as GPS) and downscaled before it is sent to a cloud vision provider.

Images are sent ONLY to providers that have a vision model configured
(see config.get_vision_providers). Text-only models are never used.
"""
from __future__ import annotations

import base64
import io
import json
import re
import time
from typing import Any

import knowledge as K
from config import (
    get_api_key,
    get_groq_api_key,
    get_openrouter_api_key,
    get_settings,
    get_vision_model,
    get_vision_providers,
    is_mock_mode,
    redact,
)

ALLOWED_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
ALLOWED_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
MAX_PIXELS = 40_000_000          # reject decompression-bomb style images
MAX_SIDE = 1280                  # downscale long side to this before sending
CALL_TIMEOUT_S = 45.0

LIMITATIONS_NOTE = (
    "This is a suggestion based on how the item LOOKS in the photo. A photo cannot "
    "show weight, exact quantity, material composition or hidden defects. Please "
    "confirm quantity, unit, city and condition yourself before saving."
)


class VisionError(Exception):
    """A user-readable problem with an image or the vision providers."""


# ---------------------------------------------------------------- validation
def validate_image(data: bytes, filename: str = "") -> dict:
    """Check type, size and contents. Returns info or raises VisionError."""
    if not data:
        raise VisionError("The image file is empty.")
    max_bytes = int(get_settings().max_image_mb * 1024 * 1024)
    if len(data) > max_bytes:
        raise VisionError(
            f"The image is {len(data) / 1048576:.1f} MB; the limit is "
            f"{get_settings().max_image_mb:g} MB."
        )
    name = (filename or "").lower()
    if name and not name.endswith(ALLOWED_EXTENSIONS):
        raise VisionError("Unsupported file type. Use JPG, JPEG, PNG or WEBP.")

    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:
        raise VisionError("Pillow is missing. Run: python -m pip install pillow") from exc

    try:
        with Image.open(io.BytesIO(data)) as img:
            fmt = (img.format or "").upper()
            width, height = img.size
            img.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise VisionError("This file is not a readable image (it may be corrupt).") from None
    except Image.DecompressionBombError:
        raise VisionError("The image dimensions are too large.") from None

    if fmt not in ALLOWED_FORMATS:
        raise VisionError(
            f"The file contents are {fmt or 'unknown'}, not JPG, PNG or WEBP."
        )
    if width * height > MAX_PIXELS:
        raise VisionError("The image dimensions are too large.")
    return {"format": fmt, "width": width, "height": height, "size_bytes": len(data)}


def prepare_image(data: bytes, filename: str = "") -> tuple[bytes, str]:
    """Validate, then return (jpeg_bytes, 'image/jpeg'): downscaled, metadata removed."""
    validate_image(data, filename)
    from PIL import Image, ImageOps

    try:
        with Image.open(io.BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode != "RGB":
                background = Image.new("RGB", img.size, (255, 255, 255))
                rgba = img.convert("RGBA")
                background.paste(rgba, mask=rgba.split()[-1])
                img = background
            img.thumbnail((MAX_SIDE, MAX_SIDE))
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=85)
    except Exception as exc:  # noqa: BLE001
        raise VisionError("The image could not be processed.") from exc
    return out.getvalue(), "image/jpeg"


# -------------------------------------------------------------------- prompt
_PROMPT = """You are a circular-economy assistant. Look at the photo of a discarded, unused or surplus item.
{extra}
Return ONLY a JSON object with exactly these keys:
"name" (short likely item name),
"category" (one of: {categories}),
"visible_condition" (one of: {conditions}; judge only what is visible),
"disposition" (best action, one of: {dispositions}; prefer reuse > repair > recycle > dispose),
"hazardous" (true or false),
"ideas" (list of 2-4 short reuse or repair ideas),
"reasoning" (1-2 sentences describing what you see and why),
"confidence" ("low", "medium" or "high").
Do NOT guess weight, exact quantity, material composition or hidden defects."""


def _build_prompt(description: str) -> str:
    extra = ""
    if description.strip():
        extra = f"The user also says: {description.strip()[:500]}\n"
    return _PROMPT.format(
        extra=extra,
        categories=", ".join(K.CATEGORIES),
        conditions=", ".join(K.CONDITIONS),
        dispositions=", ".join(K.DISPOSITIONS),
    )


# -------------------------------------------------------------- normalisation
def _parse_json(text: str) -> Any:
    cleaned = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned.strip(), flags=re.IGNORECASE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    raise VisionError("The vision model did not return valid JSON.")


def normalize_result(data: Any, provider: str, model: str) -> dict:
    """Coerce a model reply into safe, validated fields."""
    if not isinstance(data, dict):
        raise VisionError("The vision model returned an unexpected format.")
    category = str(data.get("category", "")).strip().lower()
    condition = str(data.get("visible_condition") or data.get("condition") or "").strip().lower()
    disposition = str(data.get("disposition", "")).strip().lower()
    ideas_raw = data.get("ideas") or []
    ideas = [str(i)[:200] for i in ideas_raw if str(i).strip()][:4] if isinstance(ideas_raw, list) else []
    confidence = str(data.get("confidence", "low")).strip().lower()
    return {
        "name": (str(data.get("name") or "").strip() or "Unidentified item")[:80],
        "category": category if category in K.CATEGORIES else "other",
        "visible_condition": condition if condition in K.CONDITIONS else "fair",
        "disposition": disposition if disposition in K.DISPOSITIONS else "reuse",
        "hazardous": data.get("hazardous") is True,
        "ideas": ideas,
        "reasoning": str(data.get("reasoning") or "")[:500],
        "confidence": confidence if confidence in ("low", "medium", "high") else "low",
        "provider": provider,
        "model": model,
        "limitations": LIMITATIONS_NOTE,
    }


# ----------------------------------------------------------------- providers
def _call_gemini(jpeg: bytes, mime: str, prompt: str, model: str) -> str:
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise VisionError("Google Gen AI SDK missing. Run: pip install google-genai") from exc
    client = genai.Client(
        api_key=get_api_key(),
        http_options=types.HttpOptions(timeout=int(CALL_TIMEOUT_S * 1000)),
    )
    response = client.models.generate_content(
        model=model,
        contents=[types.Part.from_bytes(data=jpeg, mime_type=mime), prompt],
        config=types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=get_settings().max_tokens,
            response_mime_type="application/json",
        ),
    )
    return (response.text or "").strip()


def _call_openai_style(provider: str, jpeg: bytes, mime: str, prompt: str, model: str) -> str:
    """Groq / OpenRouter chat API with an image_url data URI (UNTESTED until probed)."""
    if provider == "groq":
        try:
            from groq import Groq
        except ImportError as exc:
            raise VisionError("Groq SDK missing. Run: pip install groq") from exc
        client = Groq(api_key=get_groq_api_key(), timeout=CALL_TIMEOUT_S)
    else:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise VisionError("OpenAI SDK missing. Run: pip install openai") from exc
        client = OpenAI(
            api_key=get_openrouter_api_key(),
            base_url="https://openrouter.ai/api/v1",
            timeout=CALL_TIMEOUT_S,
            default_headers={"X-Title": "ReSource AI"},
        )
    data_uri = f"data:{mime};base64,{base64.b64encode(jpeg).decode('ascii')}"
    response = client.chat.completions.create(
        model=model,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ],
        }],
        temperature=0.2,
        max_tokens=get_settings().max_tokens,
    )
    if not response.choices:
        raise VisionError(f"{provider} returned no choices.")
    return (response.choices[0].message.content or "").strip()


def _call_provider(provider: str, jpeg: bytes, mime: str, prompt: str) -> dict:
    model = get_vision_model(provider)
    if not model:
        raise VisionError(f"No vision model is configured for {provider}.")
    if provider == "gemini":
        text = _call_gemini(jpeg, mime, prompt, model)
    else:
        text = _call_openai_style(provider, jpeg, mime, prompt, model)
    if not text:
        raise VisionError(f"{provider} returned an empty response.")
    return normalize_result(_parse_json(text), provider, model)


# ------------------------------------------------------------------- public
def mock_result(description: str = "") -> dict:
    """Offline placeholder. Makes NO guess about the image; clearly labelled."""
    return {
        "name": (description.strip()[:80] or "Item (offline demo)"),
        "category": "other",
        "visible_condition": "fair",
        "disposition": "reuse",
        "hazardous": False,
        "ideas": ["Offline demo mode: the image was NOT analysed."],
        "reasoning": "Offline demo mode. No vision model was called, so nothing "
                     "was recognised from the photo.",
        "confidence": "low",
        "provider": "offline demo",
        "model": "",
        "limitations": LIMITATIONS_NOTE,
    }


def analyze_image(data: bytes, filename: str = "", description: str = "") -> dict:
    """Validate an image and describe it with the first working vision provider.

    Raises VisionError with a readable message. Never returns image bytes.
    """
    jpeg, mime = prepare_image(data, filename)      # validation errors surface here
    if is_mock_mode():
        return mock_result(description)

    providers = get_vision_providers()
    if not providers:
        raise VisionError(
            "No vision-capable provider is configured. Set a *_VISION_MODEL in .env "
            "(Gemini is on by default when GEMINI_API_KEY is set). Images are never "
            "sent to text-only models."
        )

    prompt = _build_prompt(description)
    failures: list[str] = []
    for provider in providers:
        try:
            return _call_provider(provider, jpeg, mime, prompt)
        except Exception as exc:  # noqa: BLE001 - try the next vision provider
            failures.append(f"{provider}: {redact(str(exc))[:200]}")
            time.sleep(0.2)
    raise VisionError("All vision providers failed.\n" + "\n".join(failures))