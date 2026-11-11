"""Reusable Gemini backend for ReSource AI.

This is the ONLY module that imports Google's SDK. To change model/provider
later, edit this file (and GEMINI_MODEL in .env).
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from config import get_api_key, get_settings, redact


# ---------------------------------------------------------------- exceptions
class GeminiError(Exception):
    """Base class for all Gemini-related failures."""


class GeminiConfigError(GeminiError):
    """Missing/invalid API key or SDK not installed."""


class GeminiQuotaError(GeminiError):
    """Rate limit / free-tier quota exhausted (HTTP 429)."""


class GeminiResponseError(GeminiError):
    """Empty, blocked, or unparseable model output."""


# -------------------------------------------------------------------- client
_client = None


def is_configured() -> bool:
    return get_api_key() is not None


def use_mock() -> bool:
    """True when the app should run offline (no Gemini calls)."""
    mode = get_settings().mock_mode
    if mode == "always":
        return True
    if mode == "never":
        return False
    return not is_configured()  # "auto"


def _get_client():
    global _client
    if _client is not None:
        return _client
    key = get_api_key()
    if not key:
        raise GeminiConfigError(
            "GEMINI_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    try:
        from google import genai
    except ImportError as exc:
        raise GeminiConfigError(
            "Google Gen AI SDK missing. Run: pip install google-genai"
        ) from exc
    _client = genai.Client(
    api_key=key,
    http_options=genai.types.HttpOptions(timeout=30000)
)
    return _client


def reset_client() -> None:
    """Force re-creation of the client (e.g., after the key changes)."""
    global _client
    _client = None


# ------------------------------------------------------------------ core call
_RETRYABLE = {429, 500, 502, 503, 504}


def _call(contents: Any, config: Any):
    """generate_content with retries and friendly errors. Returns raw response."""
    from google.genai import errors

    settings = get_settings()
    client = _get_client()
    attempts = max(1, settings.max_retries)

    for attempt in range(attempts):
        is_last = attempt == attempts - 1
        try:
            return client.models.generate_content(
                model=settings.model, contents=contents, config=config
            )
        except errors.APIError as exc:
            code = getattr(exc, "code", None)
            msg = str(exc).lower()
            if code in (401, 403) or (code == 400 and "api key" in msg):
                raise GeminiConfigError(
                    "Gemini rejected the API key (invalid or no permission). "
                    "Check GEMINI_API_KEY."
                ) from exc
            if code in _RETRYABLE and not is_last:
                time.sleep(settings.retry_backoff_s * (2 ** attempt))
                continue
            if code == 429:
                raise GeminiQuotaError(
                    "Gemini quota/rate limit reached. Wait a minute and retry."
                ) from exc
            if code == 404:
                raise GeminiError(
                    f"Model '{settings.model}' not found. Set GEMINI_MODEL in .env "
                    "to a current model name from ai.google.dev."
                ) from exc
            raise GeminiError(redact(f"Gemini API error ({code}): {exc}")) from exc
        except Exception as exc:  # network errors etc.
            if not is_last:
                time.sleep(settings.retry_backoff_s * (2 ** attempt))
                continue
            raise GeminiError(redact(f"Gemini request failed: {exc}")) from exc

    raise GeminiError("Gemini request failed.")


def _extract_text(response: Any) -> str:
    try:
        return (response.text or "").strip()
    except Exception:
        return ""


def _generate(
    contents: Any,
    system: str | None,
    temperature: float,
    json_mode: bool,
    schema: Any = None,
) -> str:
    from google.genai import types

    settings = get_settings()
    config_kwargs: dict[str, Any] = {
        "temperature": temperature,
        "max_output_tokens": settings.max_tokens,
    }
    if system:
        config_kwargs["system_instruction"] = system
    if json_mode:
        config_kwargs["response_mime_type"] = "application/json"
        if schema is not None:
            config_kwargs["response_schema"] = schema
    config = types.GenerateContentConfig(**config_kwargs)

    response = _call(contents, config)
    text = _extract_text(response)
    if not text:
        raise GeminiResponseError(
            "Gemini returned an empty or blocked response. Try rephrasing."
        )
    return text


# -------------------------------------------------------------- public helpers
def generate_text(
    prompt: str, system: str | None = None, temperature: float = 0.4
) -> str:
    """Plain text answer."""
    return _generate(prompt, system, temperature, json_mode=False)


def _parse_json(text: str) -> Any:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", cleaned, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
    raise GeminiResponseError("Gemini did not return valid JSON.")


def generate_json(
    prompt: str,
    system: str | None = None,
    temperature: float = 0.2,
    schema: Any = None,
) -> Any:
    """Ask Gemini for structured JSON and return the parsed Python object."""
    text = _generate(prompt, system, temperature, json_mode=True, schema=schema)
    return _parse_json(text)


# ------------------------------------------------------- function calling API
def generate_with_tools(
    contents: list,
    system: str,
    tool_declarations: list[dict],
    temperature: float = 0.3,
):
    """One model round-trip with function calling. Returns the raw response.

    Automatic function calling is disabled: our agent loop executes tools itself.
    """
    from google.genai import types

    settings = get_settings()
    tool = types.Tool(
        function_declarations=[types.FunctionDeclaration(**d) for d in tool_declarations]
    )
    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=temperature,
        max_output_tokens=settings.max_tokens,
        tools=[tool],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    return _call(contents, config)


def make_content(role: str, text: str):
    """role is 'user' or 'model'."""
    from google.genai import types

    return types.Content(role=role, parts=[types.Part.from_text(text=text)])


def make_tool_response(results: list[tuple[str, dict]]):
    """Wrap tool results [(tool_name, result_dict), ...] as one user turn."""
    from google.genai import types

    parts = [
        types.Part.from_function_response(name=name, response=result)
        for name, result in results
    ]
    return types.Content(role="user", parts=parts)


def get_function_calls(response: Any) -> list[tuple[str, dict]]:
    calls = getattr(response, "function_calls", None) or []
    return [(c.name, dict(c.args or {})) for c in calls]


def get_model_content(response: Any):
    candidates = getattr(response, "candidates", None)
    if not candidates:
        return None
    return candidates[0].content


def get_text(response: Any) -> str:
    return _extract_text(response)


def health_check() -> tuple[bool, str]:
    """Small live call to verify key + model. Returns (ok, message)."""
    try:
        reply = generate_text("Reply with exactly one word: OK", temperature=0.0)
        return True, f"Gemini reachable (model reply: {reply[:40]!r})"
    except GeminiError as exc:
        return False, str(exc)