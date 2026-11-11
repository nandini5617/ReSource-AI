
"""OpenRouter API client for ReSource AI."""

from __future__ import annotations

from openai import OpenAI

from config import (
    get_openrouter_api_key,
    get_settings,
    redact,
)


class OpenRouterError(Exception):
    pass


class OpenRouterConfigError(OpenRouterError):
    pass


class OpenRouterQuotaError(OpenRouterError):
    pass


_client = None


def is_configured() -> bool:
    return get_openrouter_api_key() is not None


def _get_client():
    global _client

    if _client is not None:
        return _client

    key = get_openrouter_api_key()

    if not key:
        raise OpenRouterConfigError(
            "OPENROUTER_API_KEY is not configured."
        )

    _client = OpenAI(
        api_key=key,
        base_url="https://openrouter.ai/api/v1",
        timeout=30.0,
    )

    return _client


def reset_client():
    global _client
    _client = None


def generate_text(
    prompt: str,
    system: str | None = None,
    temperature: float = 0.4,
) -> str:

    settings = get_settings()
    client = _get_client()

    messages = []

    if system:
        messages.append({
            "role": "system",
            "content": system,
        })

    messages.append({
        "role": "user",
        "content": prompt,
    })

    try:
        response = client.chat.completions.create(
            model=settings.openrouter_model,
            messages=messages,
            temperature=temperature,
            max_tokens=settings.max_tokens,
        )

        answer = response.choices[0].message.content

        if not answer:
            raise OpenRouterError(
                "OpenRouter returned an empty response."
            )

        return answer.strip()

    except Exception as exc:
        status = getattr(exc, "status_code", None)

        if status == 429:
            raise OpenRouterQuotaError(
                "OpenRouter rate limit or quota reached."
            ) from exc

        raise OpenRouterError(
            redact(f"OpenRouter API error: {exc}")
        ) from exc


def health_check() -> tuple[bool, str]:
    try:
        reply = generate_text(
            "Reply with exactly one word: OK",
            temperature=0.0,
        )

        return True, f"OpenRouter reachable: {reply[:40]!r}"

    except OpenRouterError as exc:
        return False, str(exc)

