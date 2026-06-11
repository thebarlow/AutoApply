from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import openai

_ENV_PATH = Path(__file__).parent.parent / ".env"


def _read_env_file() -> dict[str, str]:
    """Read .env file directly — needed for keys saved at runtime after startup."""
    if not _ENV_PATH.exists():
        return {}
    result: dict[str, str] = {}
    for line in _ENV_PATH.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


_PROVIDER_BASE_URLS: dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
}


def get_client_for_profile(user: Any = None, model_override: str = "") -> tuple:
    """Return (client, model) for the platform LLM provider, resolved from env.

    The platform owns LLM keys server-side; ``user`` is accepted for call-site
    compatibility but no longer influences provider selection. ``model_override``
    takes precedence over ``LLM_DEFAULT_MODEL`` when non-empty.

    Raises:
        RuntimeError: If provider type, API key, or model cannot be resolved.
    """
    provider_type = (os.getenv("LLM_PROVIDER_TYPE") or "openrouter").lower()
    base_url = _PROVIDER_BASE_URLS.get(provider_type)
    if not base_url:
        raise RuntimeError(
            f"Unknown LLM_PROVIDER_TYPE {provider_type!r}. "
            f"Expected one of {sorted(_PROVIDER_BASE_URLS)}."
        )
    api_key = os.getenv("LLM_API_KEY") or _read_env_file().get("LLM_API_KEY", "")
    if not api_key:
        raise RuntimeError("No platform LLM key. Set LLM_API_KEY in .env.")
    model = model_override or os.getenv("LLM_DEFAULT_MODEL") or _read_env_file().get("LLM_DEFAULT_MODEL", "")
    if not model:
        raise RuntimeError("No model resolved. Set LLM_DEFAULT_MODEL in .env or pass model_override.")
    return openai.OpenAI(api_key=api_key, base_url=base_url), model


def call_llm(prompt: str, client: Any, model: str, max_tokens: int = 8192) -> str:
    """Send a single-turn prompt to the LLM and return the response text.

    Args:
        prompt: The user message to send.
        client: An OpenAI-compatible client instance.
        model: Model identifier string.
        max_tokens: Maximum tokens in the response.

    Returns:
        Stripped response content string.

    Raises:
        RuntimeError: If the LLM returns an empty response.
    """
    from core import session_cost

    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    usage = getattr(response, "usage", None)
    if usage is not None:
        session_cost.add_cost(float(getattr(usage, "cost", None) or 0.0))
    choice = response.choices[0]
    content = choice.message.content
    if not content:
        if choice.finish_reason == "length":
            # Input context likely too long; return empty and let callers handle it.
            return ""
        raise RuntimeError(
            f"LLM returned empty response (finish_reason={choice.finish_reason!r})"
        )
    return content.strip()
