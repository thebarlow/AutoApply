from __future__ import annotations

import json
import os
from dataclasses import dataclass

import openai
from sqlalchemy.orm import Session

from db.models import Config


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
    api_key = os.getenv(env_key)
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
