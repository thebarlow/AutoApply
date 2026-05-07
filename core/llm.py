from __future__ import annotations

import json
import os
from dataclasses import dataclass

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


def get_openai_client(db: Session) -> tuple:
    """Returns (client, model_name) for the active provider."""
    import openai  # lazy — openai adds ~10s to startup on WSL2
    provider = get_active_provider(db)
    api_key = os.getenv(f"LLM_KEY_{provider.name.upper()}")
    if not api_key:
        raise RuntimeError(
            f"No API key for provider '{provider.name}'. "
            f"Set LLM_KEY_{provider.name.upper()} in .env via /config."
        )
    client = openai.OpenAI(api_key=api_key, base_url=provider.base_url)
    return client, provider.model
