from __future__ import annotations

from typing import Any

import openai
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


_NAMED_PROVIDER_BASE_URLS: dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
}


def _ping_provider(
    provider_type: str, api_key: str, model: str, base_url: str = ""
) -> tuple[bool, str | None]:
    """Test LLM connection by sending a minimal completion request.

    Args:
        provider_type: Provider name (anthropic, openai, openrouter, gemini)
        api_key: API key for the provider
        model: Model identifier
        base_url: Optional custom base URL; if empty, uses provider defaults

    Returns:
        (ok, error) tuple where ok is True if connection succeeded,
        error is None on success or an error message (truncated to 200 chars) on failure.
    """
    try:
        # Use provided base_url or look up by provider_type
        url = base_url or _NAMED_PROVIDER_BASE_URLS.get(provider_type.lower())
        if not url:
            return False, f"Unknown provider_type: {provider_type}"

        # Create client and test with minimal completion
        client = openai.OpenAI(api_key=api_key, base_url=url)
        response = client.chat.completions.create(
            model=model,
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )

        # If we got here, connection succeeded
        return True, None
    except Exception as e:
        # Catch any error and return truncated message
        error_msg = str(e)[:200]
        return False, error_msg


class TestConnectionRequest(BaseModel):
    provider_type: str
    api_key: str
    model: str
    base_url: str = ""


@router.post("/api/llm/test-connection")
def test_connection(body: TestConnectionRequest) -> dict[str, Any]:
    """Test LLM provider connection.

    Returns {ok: true} on success, {ok: false, error: "..."} on failure.
    HTTP status is always 200; errors are in the response body.
    """
    ok, error = _ping_provider(body.provider_type, body.api_key, body.model, body.base_url)

    if ok:
        return {"ok": True}
    else:
        return {"ok": False, "error": error or "Unknown error"}
