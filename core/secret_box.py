"""Symmetric encryption for secrets stored at rest (user LLM API keys).

Uses Fernet (AES-128-CBC + HMAC-SHA256) keyed by the ``KEY_ENCRYPTION_KEY``
env var. The key lives only in the deployment environment, so a leaked DB dump
or backup does not expose usable provider keys. Losing or rotating the env key
makes previously stored ciphertexts undecryptable — callers treat that as
"no key stored" and the user re-enters it.
"""
from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken


class SecretBoxUnavailable(RuntimeError):
    """Raised when ``KEY_ENCRYPTION_KEY`` is missing or malformed."""


def _fernet() -> Fernet:
    key = os.getenv("KEY_ENCRYPTION_KEY", "").strip()
    if not key:
        raise SecretBoxUnavailable("KEY_ENCRYPTION_KEY is not set; cannot store API keys.")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise SecretBoxUnavailable("KEY_ENCRYPTION_KEY is not a valid Fernet key.") from exc


def is_available() -> bool:
    """True when secrets can be encrypted/decrypted in this environment."""
    try:
        _fernet()
    except SecretBoxUnavailable:
        return False
    return True


def encrypt(plaintext: str) -> str:
    """Encrypt ``plaintext`` and return a URL-safe ASCII token."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str | None:
    """Decrypt ``token``; return None if it was made with a different key or is corrupt."""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None


def generate_key() -> str:
    """Return a fresh Fernet key (for provisioning ``KEY_ENCRYPTION_KEY``)."""
    return Fernet.generate_key().decode()
