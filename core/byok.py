"""Bring-your-own-key (BYOK): per-account LLM provider keys.

An account that stores its own provider key runs every LLM action on that key,
unmetered and free. Accounts without one fall back to the platform key and the
prepaid credit system (``core/metering.py``).

The decrypted key never leaves the server: API responses only carry the
provider, the last four characters, and the chosen default model.
"""
from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session

from core import secret_box

logger = logging.getLogger(__name__)

PROVIDERS: dict[str, dict[str, str]] = {
    "openrouter": {"label": "OpenRouter", "base_url": "https://openrouter.ai/api/v1"},
    "openai": {"label": "OpenAI", "base_url": "https://api.openai.com/v1"},
    "anthropic": {"label": "Anthropic", "base_url": "https://api.anthropic.com/v1"},
    "gemini": {"label": "Google Gemini",
               "base_url": "https://generativelanguage.googleapis.com/v1beta/openai"},
}

_LIST_TIMEOUT = 15.0


@dataclass(frozen=True)
class ByokConfig:
    """A resolved, decrypted BYOK credential for one account."""

    provider: str
    api_key: str
    default_model: str

    @property
    def base_url(self) -> str:
        return PROVIDERS[self.provider]["base_url"]


# Snapshot of the acting account's BYOK config for the duration of one metered
# action. ``meter_action`` decides "free vs. charged" once, up front; pinning the
# credential here stops a user who deletes their key mid-action from having the
# rest of that (unbilled) action fall through to the platform key.
_active: ContextVar[ByokConfig | None] = ContextVar("_byok_active", default=None)


def active() -> ByokConfig | None:
    return _active.get()


def set_active(cfg: ByokConfig | None):
    return _active.set(cfg)


def reset_active(token) -> None:
    _active.reset(token)


def has_key(account) -> bool:
    """Cheap check (no decryption) for whether an account has a stored key."""
    return bool(account is not None and getattr(account, "llm_api_key_enc", None)
                and getattr(account, "llm_provider", None) in PROVIDERS)


def config_for_account(account) -> ByokConfig | None:
    """Decrypt an account's stored key; None if absent or undecryptable."""
    if not has_key(account):
        return None
    try:
        key = secret_box.decrypt(account.llm_api_key_enc)
    except secret_box.SecretBoxUnavailable:
        logger.error("BYOK key stored for account %s but KEY_ENCRYPTION_KEY is unavailable",
                     account.id)
        return None
    if not key:
        logger.warning("BYOK key for account %s could not be decrypted (key rotated?)",
                       account.id)
        return None
    return ByokConfig(account.llm_provider, key, account.llm_default_model or "")


def config_for_profile(db: Session, profile_id: int) -> ByokConfig | None:
    from core.credits import get_account_for_profile
    return config_for_account(get_account_for_profile(db, profile_id))


def config_for_profile_id(profile_id: int | None) -> ByokConfig | None:
    """Resolve BYOK config with a short-lived session (for callers without one)."""
    if profile_id is None:
        return None
    from db.database import SessionLocal
    db = SessionLocal()
    try:
        return config_for_profile(db, profile_id)
    finally:
        db.close()


def mask(last4: str | None) -> str:
    return f"••••{last4}" if last4 else ""


# ---------------------------------------------------------------------------
# Model listing (also serves as key validation: a bad key fails the list call)
# ---------------------------------------------------------------------------

class KeyValidationError(Exception):
    """The provider rejected the key, or could not be reached."""


_OPENAI_NON_TEXT = ("audio", "realtime", "tts", "transcribe", "whisper", "dall-e",
                    "image", "embedding", "moderation", "search", "davinci", "babbage",
                    "computer-use", "codex-mini")
_GEMINI_NON_TEXT = ("embedding", "imagen", "veo", "tts", "aqa", "image", "live",
                    "native-audio", "learnlm")


def _is_text_model(provider: str, model: dict) -> bool:
    mid = (model.get("id") or "").lower()
    if provider == "openrouter":
        arch = model.get("architecture") or {}
        outputs = arch.get("output_modalities")
        if outputs is not None:
            return outputs == ["text"]
        return (arch.get("modality") or "text->text").endswith("->text")
    if provider == "openai":
        if not mid.startswith(("gpt-", "o1", "o3", "o4", "chatgpt-")):
            return False
        return not any(tok in mid for tok in _OPENAI_NON_TEXT)
    if provider == "gemini":
        return mid.startswith("gemini") and not any(tok in mid for tok in _GEMINI_NON_TEXT)
    if provider == "anthropic":
        return mid.startswith("claude")
    return False


def _fetch_models(provider: str, api_key: str) -> list[dict]:
    base = PROVIDERS[provider]["base_url"]
    if provider == "anthropic":
        # Anthropic's model list is a native endpoint; it authenticates with
        # x-api-key rather than the OpenAI-style bearer header.
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
        url, params = f"{base}/models", {"limit": 1000}
    else:
        headers = {"Authorization": f"Bearer {api_key}"}
        url, params = f"{base}/models", None
    if provider == "openrouter":
        # OpenRouter's /models is public; /key is the authenticated probe.
        try:
            probe = httpx.get(f"{base}/key", headers=headers, timeout=_LIST_TIMEOUT)
            if probe.status_code == 404:  # older route name
                probe = httpx.get(f"{base}/auth/key", headers=headers, timeout=_LIST_TIMEOUT)
        except httpx.HTTPError as exc:
            raise KeyValidationError("Could not reach OpenRouter. Try again.") from exc
        if probe.status_code in (401, 403):
            raise KeyValidationError("OpenRouter rejected this key.")
    try:
        resp = httpx.get(url, headers=headers, params=params, timeout=_LIST_TIMEOUT)
    except httpx.HTTPError as exc:
        raise KeyValidationError(f"Could not reach {PROVIDERS[provider]['label']}. Try again.") from exc
    if resp.status_code in (400, 401, 403):
        raise KeyValidationError(f"{PROVIDERS[provider]['label']} rejected this key.")
    if resp.status_code >= 400:
        raise KeyValidationError(
            f"{PROVIDERS[provider]['label']} returned an error ({resp.status_code}). Try again.")
    data = resp.json().get("data") or []
    if provider == "gemini":
        for m in data:  # Gemini's compat layer prefixes ids with "models/"
            if isinstance(m.get("id"), str) and m["id"].startswith("models/"):
                m["id"] = m["id"][len("models/"):]
    return data


def list_text_models(provider: str, api_key: str) -> list[dict]:
    """Validate ``api_key`` against ``provider`` and return its text-output models.

    Returns ``[{"id": ..., "name": ...}]`` sorted by id.

    Raises:
        ValueError: Unknown provider.
        KeyValidationError: Key rejected or provider unreachable.
    """
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}")
    models = [m for m in _fetch_models(provider, api_key) if _is_text_model(provider, m)]
    out = [{"id": m["id"], "name": m.get("name") or m.get("display_name") or m["id"]}
           for m in models if m.get("id")]
    return sorted(out, key=lambda m: m["id"])
