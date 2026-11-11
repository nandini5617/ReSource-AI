
"""Groq API client for ReSource AI."""

from __future__ import annotations

import time
from typing import Any

from config import get_groq_api_key, get_settings, redact


class GroqError(Exception):
    pass


class GroqConfigError(GroqError):
    pass


class GroqQuotaError(GroqError):
    pass


_client = None


def is_configured() -> bool:
    return get_groq_api_key() is not None


def _get_client():
    global _client

    if _client is not None:
        return _client

    key = get_groq_api_key()

    if not key:
        raise GroqConfigError("GROQ_API_KEY is not configured.")

    try:
        from groq import Groq
    except ImportError as exc:
        raise GroqConfigError(
            "Groq SDK missing. Run: pip install groq"
        ) from exc

    _client = Groq(api_key=key, timeout=30.0)
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
        messages.append({"role": "system", "content": system})

    messages.append({"role": "user", "content": prompt})

    try:
        response = client.chat.completions.create(
            model=settings.groq_model,
            messages=messages,
            temperature=temperature,
            max_tokens=settings.max_tokens,
        )

        answer = response.choices[0].message.content

        if not answer:
            raise GroqError("Groq returned an empty response.")

        return answer.strip()

    except Exception as exc:
        status = getattr(exc, "status_code", None)

        if status == 429:
            raise GroqQuotaError(
                "Groq rate limit or quota reached."
            ) from exc

        raise GroqError(redact(f"Groq API error: {exc}")) from exc


def health_check() -> tuple[bool, str]:
    try:
        reply = generate_text(
            "Reply with exactly one word: OK",
            temperature=0.0,
        )
        return True, f"Groq reachable: {reply[:40]!r}"

    except GroqError as exc:
        return False, str(exc)
