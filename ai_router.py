"""Provider-independent AI router for ReSource AI.

Supports:
    1. Groq
    2. Gemini
    3. OpenRouter

All providers use the same Python tool dispatcher.

Public helpers:
    run_agent(...)            tool-calling agent loop with automatic fallback
    route_json(...)           one-shot JSON generation with automatic fallback
    configured_providers()    providers that have an API key, in priority order

Guard against looping output: an answer that repeats the same word or phrase
over and over is treated as a provider failure, so the router falls back to
the next provider instead of showing garbage to the user.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from config import (
    get_api_key,
    get_groq_api_key,
    get_openrouter_api_key,
    get_settings,
    redact,
)

from gemini_client import (
    _parse_json,
    generate_json as _gemini_generate_json,
    generate_with_tools,
    get_function_calls,
    get_text,
    make_content,
)


class AIRouterError(Exception):
    """Raised when no configured AI provider can complete a request."""


_CLIENTS: dict[str, Any] = {}

# A provider that just failed is tried last for this many seconds.
_COOLDOWN_S = 60.0
_COOLDOWN_UNTIL: dict[str, float] = {}

# Chat answers are short; a smaller cap stops a runaway answer early.
_CHAT_MAX_TOKENS = 2048
_CHAT_TEMPERATURE = 0.4
_FREQUENCY_PENALTY = 0.3

_HISTORY_PLACEHOLDER = "(An earlier answer was unusable and has been omitted.)"

_THINK_CLOSED_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_THINK_OPEN_RE = re.compile(r"<think>.*$", re.DOTALL | re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z0-9']+")


# ------------------------------------------------------------ provider info
def _provider_order() -> list[str]:
    """Return providers starting with the configured primary provider."""
    primary = get_settings().primary_provider

    providers = ["groq", "gemini", "openrouter"]

    if primary in providers:
        providers.remove(primary)
        providers.insert(0, primary)

    return providers


def provider_order() -> list[str]:
    """Public: provider priority order."""
    return _provider_order()


def _is_configured(provider: str) -> bool:
    if provider == "groq":
        return bool(get_groq_api_key())
    if provider == "gemini":
        return bool(get_api_key())
    if provider == "openrouter":
        return bool(get_openrouter_api_key())
    return False


def configured_providers() -> list[str]:
    """Public: providers that have an API key set, in priority order."""
    return [p for p in _provider_order() if _is_configured(p)]


def _model_for(provider: str) -> str:
    settings = get_settings()
    if provider == "groq":
        return settings.groq_model
    if provider == "openrouter":
        return settings.openrouter_model
    return settings.gemini_model


# ----------------------------------------------------------------- cooldown
def _mark_failed(provider: str) -> None:
    _COOLDOWN_UNTIL[provider] = time.monotonic() + _COOLDOWN_S


def _mark_ok(provider: str) -> None:
    _COOLDOWN_UNTIL.pop(provider, None)


def _in_cooldown(provider: str) -> bool:
    return _COOLDOWN_UNTIL.get(provider, 0.0) > time.monotonic()


def _prefer_ready(order: list[str]) -> list[str]:
    """Providers not in cooldown first; cooling ones remain as a last resort."""
    ready = [p for p in order if not _in_cooldown(p)]
    cooling = [p for p in order if _in_cooldown(p)]
    return ready + cooling


# ------------------------------------------------------------------ clients
def _get_client(provider: str):
    """Create and cache an OpenAI-compatible provider client."""
    if provider in _CLIENTS:
        return _CLIENTS[provider]

    if provider == "groq":
        key = get_groq_api_key()
        if not key:
            raise AIRouterError("Groq API key is missing.")

        try:
            from groq import Groq
        except ImportError as exc:
            raise AIRouterError(
                "Groq SDK missing. Install it with: pip install groq"
            ) from exc

        client = Groq(api_key=key, timeout=30.0)

    elif provider == "openrouter":
        key = get_openrouter_api_key()
        if not key:
            raise AIRouterError("OpenRouter API key is missing.")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise AIRouterError(
                "OpenAI SDK missing. Install it with: pip install openai"
            ) from exc

        client = OpenAI(
            api_key=key,
            base_url="https://openrouter.ai/api/v1",
            timeout=30.0,
            default_headers={
                "X-Title": "ReSource AI",
            },
        )

    else:
        raise AIRouterError(f"Unsupported provider: {provider}")

    _CLIENTS[provider] = client
    return client


def reset_clients() -> None:
    """Clear cached clients and cooldowns, useful after changing API keys."""
    _CLIENTS.clear()
    _COOLDOWN_UNTIL.clear()


# ------------------------------------------------------------ text helpers
def _clean(text: str | None) -> str:
    """Remove <think>...</think> reasoning blocks some models emit."""
    text = _THINK_CLOSED_RE.sub("", text or "")
    text = _THINK_OPEN_RE.sub("", text)
    return text.strip()


def _looks_degenerate(text: str | None) -> bool:
    """True if text looks like a model stuck in a repetition loop.

    Flags: a word repeated 12+ times in a row, a 2-4 word phrase repeated 8+
    times in a row, or a long answer with very few distinct words.
    """
    words = _WORD_RE.findall((text or "").lower())
    count = len(words)
    if count < 16:
        return False
    if count >= 80 and len(set(words)) / count < 0.2:
        return True
    for period, repeats in ((1, 12), (2, 8), (3, 8), (4, 8)):
        needed = (repeats - 1) * period      # consecutive matching positions
        streak = 0
        for i in range(period, count):
            if words[i] == words[i - period]:
                streak += 1
                if streak >= needed:
                    return True
            else:
                streak = 0
    return False


def _reject_if_degenerate(provider: str, answer: str | None) -> None:
    if _looks_degenerate(answer):
        raise AIRouterError(
            f"{provider} produced a repetitive (looping) answer; it was discarded."
        )


def _convert_schema(schema: dict) -> dict:
    """Convert Gemini-style JSON schema types to OpenAI JSON schema types."""
    type_map = {
        "OBJECT": "object",
        "STRING": "string",
        "NUMBER": "number",
        "INTEGER": "integer",
        "BOOLEAN": "boolean",
        "ARRAY": "array",
    }

    result = {}

    for key, value in schema.items():
        if key == "type":
            result[key] = type_map.get(value, value)
        elif key == "properties":
            result[key] = {
                name: _convert_schema(prop)
                for name, prop in value.items()
            }
        elif key == "items" and isinstance(value, dict):
            result[key] = _convert_schema(value)
        elif key == "enum":
            result[key] = value
        elif key == "required":
            result[key] = value
        elif key == "description":
            result[key] = value
        elif key == "additionalProperties":
            result[key] = value

    return result


def _openai_tools(declarations: list[dict]) -> list[dict]:
    """Convert existing Gemini declarations to OpenAI-compatible tools."""
    converted = []

    for declaration in declarations:
        converted.append({
            "type": "function",
            "function": {
                "name": declaration["name"],
                "description": declaration.get("description", ""),
                "parameters": _convert_schema(
                    declaration.get("parameters", {})
                ),
            },
        })

    return converted


def _history_for_gemini(messages: list[dict]) -> list:
    """Convert neutral conversation history into Gemini Content objects."""
    contents = []

    for message in messages:
        role = message.get("role")
        content = message.get("content") or ""

        if role == "user":
            contents.append(make_content("user", str(content)))

        elif role == "assistant":
            if message.get("tool_calls"):
                descriptions = []
                for call in message["tool_calls"]:
                    function = call["function"]
                    descriptions.append(
                        f"{function['name']}({function['arguments']})"
                    )
                content = (
                    "I requested these tools: "
                    + "; ".join(descriptions)
                )

            if content:
                contents.append(make_content("model", str(content)))

        elif role == "tool":
            name = message.get("name", "tool")
            contents.append(make_content(
                "user",
                f"Result from {name}: {content}",
            ))

    return contents


# ------------------------------------------------------------ provider calls
def _call_gemini(
    messages: list[dict],
    system: str,
    declarations: list[dict],
) -> tuple[str | None, list, str]:
    """Call Gemini and extract its answer or function calls."""
    contents = _history_for_gemini(messages)

    response = generate_with_tools(
        contents,
        system,
        declarations,
    )

    calls = get_function_calls(response)
    answer = get_text(response) or ""
    _reject_if_degenerate("gemini", answer)

    return answer, calls, "gemini"


def _call_compatible(
    provider: str,
    messages: list[dict],
    system: str,
    declarations: list[dict],
) -> tuple[str | None, list, str]:
    """Call Groq or OpenRouter using the OpenAI-compatible API."""
    settings = get_settings()
    client = _get_client(provider)

    request_messages = [
        {"role": "system", "content": system},
        *messages,
    ]

    params = {
        "model": _model_for(provider),
        "messages": request_messages,
        "tools": _openai_tools(declarations),
        "tool_choice": "auto",
        "temperature": _CHAT_TEMPERATURE,
        "max_tokens": min(settings.max_tokens, _CHAT_MAX_TOKENS),
        "frequency_penalty": _FREQUENCY_PENALTY,
    }

    try:
        response = client.chat.completions.create(**params)
    except Exception as exc:  # noqa: BLE001
        # Some providers reject frequency_penalty: retry once without it.
        if "frequency_penalty" not in str(exc).lower():
            raise
        params.pop("frequency_penalty", None)
        response = client.chat.completions.create(**params)

    if not response.choices:
        raise AIRouterError(f"{provider} returned no choices.")

    message = response.choices[0].message
    answer = _clean(message.content)
    _reject_if_degenerate(provider, answer)

    calls = []

    for call in (message.tool_calls or []):
        function = call.function

        try:
            arguments = json.loads(function.arguments or "{}")
        except (TypeError, ValueError):
            arguments = {}

        if not isinstance(arguments, dict):
            arguments = {}

        calls.append({
            "id": call.id,
            "name": function.name,
            "args": arguments,
            "raw_arguments": function.arguments or "{}",
        })

    return answer, calls, provider


def _json_compatible(
    provider: str,
    prompt: str,
    system: str | None,
    temperature: float,
) -> Any:
    """One-shot JSON generation through Groq or OpenRouter."""
    settings = get_settings()
    client = _get_client(provider)

    system_text = (system or "You are a helpful assistant.") + (
        "\nReturn ONLY valid JSON. No markdown fences and no commentary."
    )

    response = client.chat.completions.create(
        model=_model_for(provider),
        messages=[
            {"role": "system", "content": system_text},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        max_tokens=settings.max_tokens,
    )

    if not response.choices:
        raise AIRouterError(f"{provider} returned no choices.")

    text = _clean(response.choices[0].message.content)
    if not text:
        raise AIRouterError(f"{provider} returned an empty response.")

    return _parse_json(text)


def route_json(
    prompt: str,
    system: str | None = None,
    temperature: float = 0.2,
) -> tuple[Any, str]:
    """Ask for JSON using automatic provider fallback.

    Returns (parsed_json, provider_used). Raises AIRouterError if every
    configured provider fails or none is configured.
    """
    order = configured_providers()
    if not order:
        raise AIRouterError(
            "No AI provider is configured. Add at least one valid API key."
        )

    failures: list[str] = []

    for provider in _prefer_ready(order):
        try:
            if provider == "gemini":
                data = _gemini_generate_json(
                    prompt, system=system, temperature=temperature
                )
            else:
                data = _json_compatible(provider, prompt, system, temperature)
        except Exception as exc:  # noqa: BLE001 - try the next provider
            _mark_failed(provider)
            failures.append(f"{provider}: {redact(str(exc))}")
            continue

        _mark_ok(provider)
        return data, provider

    raise AIRouterError("All configured AI providers failed.\n" + "\n".join(failures))


# --------------------------------------------------------------- agent loop
def run_agent(
    history: list[tuple[str, str]],
    user_message: str,
    system: str,
    tool_declarations: list[dict],
    dispatch,
    max_steps: int = 14,
    max_tool_calls: int = 30,
) -> tuple[str, list[dict], str]:
    """Run the agent using automatic provider fallback.

    Returns:
        (answer, trace, provider_used)

    dispatch must accept (tool_name, arguments) and return a dictionary.
    """
    messages: list[dict] = []

    for user_text, assistant_text in history:
        messages.append({
            "role": "user",
            "content": user_text,
        })
        # A looping answer stored earlier must not be fed back to the model.
        messages.append({
            "role": "assistant",
            "content": (
                _HISTORY_PLACEHOLDER
                if _looks_degenerate(assistant_text)
                else assistant_text
            ),
        })

    messages.append({
        "role": "user",
        "content": user_message,
    })

    providers = _provider_order()
    configured = [p for p in providers if _is_configured(p)]

    if not configured:
        raise AIRouterError(
            "No AI provider is configured. Add at least one valid API key."
        )

    trace: list[dict] = []
    tool_calls_used = 0
    last_provider = configured[0]

    for _ in range(max_steps):
        # Prefer the provider that succeeded in the previous step.
        start = (
            providers.index(last_provider)
            if last_provider in providers
            else 0
        )
        attempt_order = providers[start:] + providers[:start]
        attempt_order = _prefer_ready(
            [p for p in attempt_order if _is_configured(p)]
        )

        answer = ""
        calls = None
        selected_provider = None
        failures = []

        for provider in attempt_order:
            try:
                if provider == "gemini":
                    answer, calls, selected_provider = _call_gemini(
                        messages,
                        system,
                        tool_declarations,
                    )
                else:
                    answer, calls, selected_provider = _call_compatible(
                        provider,
                        messages,
                        system,
                        tool_declarations,
                    )

                _mark_ok(provider)
                break

            except Exception as exc:
                _mark_failed(provider)
                failures.append(
                    f"{provider}: {redact(str(exc))}"
                )

        if selected_provider is None:
            details = "\n".join(failures)
            raise AIRouterError(
                "All configured AI providers failed.\n" + details
            )

        last_provider = selected_provider

        # The model has finished and does not need another tool.
        if not calls:
            if answer.strip():
                return answer.strip(), trace, selected_provider

            return (
                "The AI provider returned an empty response. "
                "Please try again.",
                trace,
                selected_provider,
            )

        # Groq/OpenRouter function calls use the OpenAI message format.
        if selected_provider != "gemini":
            messages.append({
                "role": "assistant",
                "content": answer or None,
                "tool_calls": [
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {
                            "name": call["name"],
                            "arguments": call["raw_arguments"],
                        },
                    }
                    for call in calls
                ],
            })

            for call in calls:
                name = call["name"]
                args = call["args"]

                if tool_calls_used >= max_tool_calls:
                    result = {
                        "error": (
                            "Tool call limit reached. "
                            "Give your best final answer now."
                        )
                    }
                else:
                    result = dispatch(name, args)
                    tool_calls_used += 1

                trace.append({
                    "tool": name,
                    "args": args,
                    "result": result,
                })

                messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "name": name,
                    "content": json.dumps(result, default=str),
                })

        else:
            # Gemini calls do not use OpenAI tool-call IDs.
            descriptions = []

            for name, args in calls:
                descriptions.append(
                    f"{name}({json.dumps(args, default=str)})"
                )

            messages.append({
                "role": "assistant",
                "content": "I requested these tools: "
                           + "; ".join(descriptions),
            })

            results = []

            for name, args in calls:
                if tool_calls_used >= max_tool_calls:
                    result = {
                        "error": (
                            "Tool call limit reached. "
                            "Give your best final answer now."
                        )
                    }
                else:
                    result = dispatch(name, args)
                    tool_calls_used += 1

                trace.append({
                    "tool": name,
                    "args": args,
                    "result": result,
                })

                results.append({
                    "tool": name,
                    "result": result,
                })

            messages.append({
                "role": "user",
                "content": (
                    "Tool execution results:\n"
                    + json.dumps(results, indent=2, default=str)
                    + "\nUse these results to continue."
                ),
            })

    return (
        "I reached the step limit before finishing. "
        "Try a simpler or more specific request.",
        trace,
        last_provider,
    )