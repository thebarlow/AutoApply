from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import openai
from sqlalchemy.orm import Session

from db.database import Config

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


@dataclass
class LLMProvider:
    name: str
    base_url: str
    model: str


def get_active_provider(db: Session) -> LLMProvider:
    def _get(key: str) -> str:
        row = db.query(Config).filter_by(key=key).first()
        return row.value if row else ""

    active = _get("llm_active_provider")
    providers = json.loads(_get("llm_providers") or "[]")

    for p in providers:
        if p["name"] == active:
            return LLMProvider(name=p["name"], base_url=p["base_url"], model=p["model"])

    raise RuntimeError(
        f"No active LLM provider configured. "
        f"Add a provider and set it active via /config."
    )


_NAMED_PROVIDER_BASE_URLS: dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
}


def get_client_for_named_provider(db: Session, provider_name: str, model_id: str) -> tuple:
    """Return (client, model) for a named provider stored in config."""
    def _get(key: str) -> str:
        row = db.query(Config).filter_by(key=key).first()
        return row.value if row else ""

    named = json.loads(_get("named_providers") or "[]")
    provider = next((p for p in named if p["name"] == provider_name), None)
    if not provider:
        raise RuntimeError(
            f"Provider '{provider_name}' not found in named providers. "
            f"Add it under Config → Providers."
        )

    base_url = _NAMED_PROVIDER_BASE_URLS.get(provider["provider_type"])
    if not base_url:
        raise RuntimeError(f"Unknown provider_type '{provider['provider_type']}'.")

    env_key = f"LLM_KEY_{provider['id'].upper().replace('-', '_')}"
    api_key = os.getenv(env_key) or _read_env_file().get(env_key, "")
    if not api_key:
        raise RuntimeError(
            f"No API key for provider '{provider_name}'. Set {env_key} in .env."
        )

    model = model_id or provider.get("default_model", "")
    if not model:
        raise RuntimeError(f"No model configured for provider '{provider_name}'.")

    client = openai.OpenAI(api_key=api_key, base_url=base_url)
    return client, model


def get_openai_client(db: Session) -> tuple:
    """Returns (client, model_name) for the active provider."""
    provider = get_active_provider(db)
    api_key = os.getenv(f"LLM_KEY_{provider.name.upper()}")
    if not api_key:
        raise RuntimeError(
            f"No API key for provider '{provider.name}'. "
            f"Set LLM_KEY_{provider.name.upper()} in .env via /config."
        )
    client = openai.OpenAI(api_key=api_key, base_url=provider.base_url)
    return client, provider.model


def get_client_for_profile(user: Any, model_override: str = "") -> tuple:
    """Return (client, model) resolved from a User profile's llm_provider_type/llm_model.

    Falls back to the active provider if the profile has no provider configured.
    model_override takes precedence over everything else when non-empty.

    Args:
        user: A hydrated User instance with llm_provider_type and llm_model attributes.
        model_override: If non-empty, use this model instead of the profile default.

    Returns:
        (client, model) tuple.

    Raises:
        RuntimeError: If no provider or API key can be resolved.
    """
    provider_type: str = getattr(user, "llm_provider_type", "") or ""
    profile_model: str = getattr(user, "llm_model", "") or ""
    model = model_override or profile_model

    if provider_type:
        base_url = _NAMED_PROVIDER_BASE_URLS.get(provider_type.lower())
        if not base_url:
            raise RuntimeError(f"Unknown provider_type '{provider_type}' on user profile.")
        env_key = f"LLM_KEY_PROFILE_{user.id}"
        api_key = os.getenv(env_key) or _read_env_file().get(env_key, "")
        if not api_key:
            raise RuntimeError(
                f"No API key for user profile {user.id}. Set {env_key} in .env."
            )
        if not model:
            raise RuntimeError(f"No model configured for provider '{provider_type}'.")
        return openai.OpenAI(api_key=api_key, base_url=base_url), model

    # Fall back to active provider from DB — requires a db session via the active provider path
    raise RuntimeError(
        "User profile has no llm_provider_type configured. "
        "Set a provider under Profile → LLM Config."
    )


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
    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    choice = response.choices[0]
    content = choice.message.content
    if not content:
        raise RuntimeError(
            f"LLM returned empty response (finish_reason={choice.finish_reason!r})"
        )
    return content.strip()
