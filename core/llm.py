from __future__ import annotations

import contextlib
import contextvars
import os
from pathlib import Path
from typing import Any, Generator

import openai

_ENV_PATH = Path(__file__).parent.parent / ".env"

# Per-request label propagated to the LLM provider (e.g. OpenRouter) via the
# OpenAI ``user`` field, which surfaces in the provider's activity logs. Set it
# around a high-level operation with ``llm_label(...)``; every ``create`` call
# made through a client from ``get_client_for_profile`` picks it up.
_llm_label: contextvars.ContextVar[str] = contextvars.ContextVar("_llm_label", default="")


@contextlib.contextmanager
def llm_label(label: str) -> Generator[None]:
    """Tag all LLM requests made within this block with ``label`` (for log readability)."""
    token = _llm_label.set(label)
    try:
        yield
    finally:
        _llm_label.reset(token)


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


def allowed_models() -> set[str] | None:
    """Models tenants may select for prompt slots; None means unrestricted.

    ``LLM_ALLOWED_MODELS`` (comma-separated) is the explicit allowlist. When it
    is unset, production fails safe to {LLM_DEFAULT_MODEL} — the platform pays
    for every call with its own key, so an unrestricted free-text model field
    would let a flat-priced action run on an arbitrarily expensive model.
    Local/self-hosted (non-production) stays unrestricted.
    """
    raw = os.getenv("LLM_ALLOWED_MODELS", "").strip()
    if raw:
        return {m.strip() for m in raw.split(",") if m.strip()}
    if os.getenv("APP_ENV") == "production":
        default = (os.getenv("LLM_DEFAULT_MODEL")
                   or _read_env_file().get("LLM_DEFAULT_MODEL", "")).strip()
        return {default} if default else set()
    return None


def model_allowed(model: str) -> bool:
    """True if ``model`` may be used for tenant-selected prompt slots."""
    allowed = allowed_models()
    return allowed is None or model in allowed


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
    # Defense-in-depth: Prompt rows written before the allowlist existed (or via
    # any path that skips PUT validation) must not reach the platform key with a
    # disallowed model — fall back to the platform default instead of erroring.
    if model_override and not model_allowed(model_override):
        model_override = ""
    model = model_override or os.getenv("LLM_DEFAULT_MODEL") or _read_env_file().get("LLM_DEFAULT_MODEL", "")
    if not model:
        raise RuntimeError("No model resolved. Set LLM_DEFAULT_MODEL in .env or pass model_override.")
    client = openai.OpenAI(api_key=api_key, base_url=base_url)
    _install_request_labeling(client)
    return client, model


def _install_request_labeling(client: Any) -> Any:
    """Wrap ``client.chat.completions.create`` to attach the current ``llm_label``.

    The label is sent as the OpenAI ``user`` field, which OpenRouter records and
    displays per-request in its activity logs. No-op when no label is set.
    """
    completions = client.chat.completions
    original = completions.create

    def create(*args: Any, **kwargs: Any) -> Any:
        label = _llm_label.get()
        if label and "user" not in kwargs:
            extra_body = dict(kwargs.get("extra_body") or {})
            extra_body.setdefault("user", label)
            kwargs["extra_body"] = extra_body
        return original(*args, **kwargs)

    completions.create = create  # type: ignore[method-assign]
    return client


def record_usage(response: Any, model: str) -> None:
    """Record an LLM response's usage into session cost and the active meter.

    Call this once after any direct ``client.chat.completions.create`` that runs
    outside ``call_llm`` so its cost still counts toward the session total and the
    per-action credit debit. Both sinks are no-ops outside their contexts (no
    session accumulator / no active ``meter_action``), so this is safe anywhere.

    Args:
        response: The OpenAI-compatible completion response.
        model: The model id used for the call (recorded on the meter row).
    """
    from core import session_cost, metering

    usage = getattr(response, "usage", None)
    if usage is None:
        return
    cost = float(getattr(usage, "cost", None) or 0.0)
    session_cost.add_cost(cost)
    metering.record_call(
        cost, model,
        int(getattr(usage, "prompt_tokens", 0) or 0),
        int(getattr(usage, "completion_tokens", 0) or 0),
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
    record_usage(response, model)
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
