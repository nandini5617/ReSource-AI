from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Default AI models (text).
# NOTE: gemini-2.5-flash is retired for new users; Google's error message
# recommended gemini-3.8-flash. Override any of these in .env.
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
DEFAULT_GROQ_MODEL = "qwen/qwen3.8-27b"
DEFAULT_OPENROUTER_MODEL = "openai/gpt-oss-20b:free"

# Default order in which vision-capable providers are tried.
# Groq first: it is the only vision provider verified by the live probe.
DEFAULT_VISION_ORDER = "groq,gemini,openrouter"


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(BASE_DIR / ".env", override=False)
    except Exception:
        pass


_load_dotenv()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    db_path: str
    upload_dir: str
    output_dir: str
    model: str
    max_agent_steps: int
    max_tool_calls: int
    max_tokens: int
    max_upload_mb: float
    mock_mode: str
    currency: str
    retry_backoff_s: float
    max_retries: int

    # Multi-provider settings
    primary_provider: str = "groq"
    gemini_model: str = DEFAULT_GEMINI_MODEL
    groq_model: str = DEFAULT_GROQ_MODEL
    openrouter_model: str = DEFAULT_OPENROUTER_MODEL

    # Vision (image input) settings. A provider is used for images ONLY if it
    # has a vision model configured here AND an API key. Text models are never
    # assumed to accept images.
    gemini_vision_model: str = DEFAULT_GEMINI_MODEL
    groq_vision_model: str = ""
    openrouter_vision_model: str = ""
    vision_order: str = DEFAULT_VISION_ORDER
    max_image_mb: float = 5.0


def get_settings() -> Settings:
    """Read settings from environment on every call."""
    return Settings(
        db_path=os.environ.get(
            "RESOURCE_AI_DB",
            str(BASE_DIR / "data" / "resource_ai.db")
        ),
        upload_dir=os.environ.get(
            "RESOURCE_AI_UPLOAD_DIR",
            str(BASE_DIR / "uploads")
        ),
        output_dir=os.environ.get(
            "RESOURCE_AI_OUTPUT_DIR",
            str(BASE_DIR / "outputs")
        ),
        model=os.environ.get(
            "GEMINI_MODEL", DEFAULT_GEMINI_MODEL
        ).strip() or DEFAULT_GEMINI_MODEL,

        max_agent_steps=_env_int("RESOURCE_AI_MAX_STEPS", 14),
        max_tool_calls=_env_int("RESOURCE_AI_MAX_TOOL_CALLS", 30),
        max_tokens=_env_int("RESOURCE_AI_MAX_TOKENS", 8192),
        max_upload_mb=_env_float("RESOURCE_AI_MAX_UPLOAD_MB", 5.0),
        mock_mode=os.environ.get(
            "RESOURCE_AI_MOCK", "auto"
        ).strip().lower(),
        currency=os.environ.get("RESOURCE_AI_CURRENCY", "INR"),
        retry_backoff_s=_env_float("RESOURCE_AI_RETRY_BACKOFF", 1.0),
        max_retries=_env_int("RESOURCE_AI_MAX_RETRIES", 3),

        # Multi-provider configuration
        primary_provider=os.environ.get(
            "RESOURCE_AI_PRIMARY_PROVIDER", "groq"
        ).strip().lower(),

        gemini_model=os.environ.get(
            "GEMINI_MODEL", DEFAULT_GEMINI_MODEL
        ).strip() or DEFAULT_GEMINI_MODEL,

        groq_model=os.environ.get(
            "GROQ_MODEL", DEFAULT_GROQ_MODEL
        ).strip() or DEFAULT_GROQ_MODEL,

        openrouter_model=os.environ.get(
            "OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL
        ).strip() or DEFAULT_OPENROUTER_MODEL,

        # Vision configuration
        gemini_vision_model=os.environ.get(
            "GEMINI_VISION_MODEL", DEFAULT_GEMINI_MODEL
        ).strip() or DEFAULT_GEMINI_MODEL,
        groq_vision_model=os.environ.get("GROQ_VISION_MODEL", "").strip(),
        openrouter_vision_model=os.environ.get(
            "OPENROUTER_VISION_MODEL", ""
        ).strip(),
        vision_order=os.environ.get(
            "RESOURCE_AI_VISION_ORDER", DEFAULT_VISION_ORDER
        ).strip().lower() or DEFAULT_VISION_ORDER,
        max_image_mb=_env_float(
            "RESOURCE_AI_MAX_IMAGE_MB",
            _env_float("RESOURCE_AI_MAX_UPLOAD_MB", 5.0),
        ),
    )


def get_api_key() -> str | None:
    """Return the Gemini API key."""
    return os.environ.get("GEMINI_API_KEY", "").strip() or None


def get_groq_api_key() -> str | None:
    """Return the Groq API key."""
    return os.environ.get("GROQ_API_KEY", "").strip() or None


def get_openrouter_api_key() -> str | None:
    """Return the OpenRouter API key."""
    return os.environ.get("OPENROUTER_API_KEY", "").strip() or None


def is_mock_mode() -> bool:
    """Single source of truth: should the app run offline (no cloud AI calls)?

    RESOURCE_AI_MOCK accepts:
      on : 1, true, yes, on, always
      off: 0, false, no, off, never
      auto (default): offline only when NO provider key is configured
    """
    mode = get_settings().mock_mode
    if mode in ("1", "true", "yes", "on", "always"):
        return True
    if mode in ("0", "false", "no", "off", "never"):
        return False
    return not any((
        get_groq_api_key(),
        get_api_key(),
        get_openrouter_api_key(),
    ))


# ----------------------------------------------------------------- vision
def _has_key(provider: str) -> bool:
    if provider == "gemini":
        return bool(get_api_key())
    if provider == "groq":
        return bool(get_groq_api_key())
    if provider == "openrouter":
        return bool(get_openrouter_api_key())
    return False


def get_vision_model(provider: str) -> str:
    """Vision model configured for a provider ('' means: no image support set up)."""
    s = get_settings()
    return {
        "gemini": s.gemini_vision_model,
        "groq": s.groq_vision_model,
        "openrouter": s.openrouter_vision_model,
    }.get(provider, "")


def get_vision_providers() -> list[str]:
    """Providers allowed to receive images, in priority order.

    A provider qualifies only if it has an API key AND a vision model set.
    Text-only models are never used for images.
    """
    wanted = [p.strip() for p in get_settings().vision_order.split(",") if p.strip()]
    order: list[str] = []
    for p in wanted + ["groq", "gemini", "openrouter"]:
        if p in ("gemini", "groq", "openrouter") and p not in order:
            order.append(p)
    return [p for p in order if _has_key(p) and get_vision_model(p)]


# Patterns used to redact API keys from logs and error messages.
_SECRET_RE = re.compile(
    r"AIza[0-9A-Za-z_\-]{20,}"
    r"|sk-ant-[A-Za-z0-9_\-]{8,}"
    r"|sk-or-v1-[A-Za-z0-9]+"
    r"|gsk_[A-Za-z0-9]+"
)


def redact(text: str) -> str:
    """Remove API keys from displayed text and logs."""
    text = _SECRET_RE.sub("[REDACTED]", str(text))

    # Also redact keys loaded from environment variables.
    for name in (
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "OPENROUTER_API_KEY",
    ):
        key = os.environ.get(name, "").strip()
        if key:
            text = text.replace(key, "[REDACTED]")

    return text