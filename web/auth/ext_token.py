"""Browser-extension bearer tokens: mint, resolve, revoke, and FastAPI deps.

Tokens are opaque random strings; only their sha256 hash is stored. They are
long-lived and revocable (no expiry), invalidated by revoke or an account ban.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from db.database import Account, ExtensionToken, get_db
from web.tenancy import current_profile_id


def _now() -> str:
    """Return the current UTC timestamp as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def hash_token(raw: str) -> str:
    """Return the SHA256 hex digest of a raw token string."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def mint_token(db: Session, account_id: int) -> str:
    """Create and persist a token for an account; return the raw token once.

    Args:
        db: Database session.
        account_id: Account ID to mint token for.

    Returns:
        The raw token (random string); this is the only time it is returned.
    """
    raw = secrets.token_urlsafe(32)
    db.add(ExtensionToken(account_id=account_id, token_hash=hash_token(raw), created_at=_now()))
    db.commit()
    return raw


def resolve_token(db: Session, raw: str) -> Account | None:
    """Return the active account for a token, or None if invalid/revoked/banned.

    Bumps last_used_at on a valid token.

    Args:
        db: Database session.
        raw: Raw token string (from bearer header or similar).

    Returns:
        The Account row if the token is valid and active, else None.
    """
    if not raw:
        return None
    row = db.query(ExtensionToken).filter_by(token_hash=hash_token(raw), revoked=False).first()
    if row is None:
        return None
    acct = db.query(Account).filter_by(id=row.account_id).first()
    if acct is None or acct.banned:
        return None
    row.last_used_at = _now()
    db.commit()
    return acct


def revoke_token(db: Session, raw: str) -> None:
    """Mark a token as revoked.

    Args:
        db: Database session.
        raw: Raw token string to revoke.
    """
    row = db.query(ExtensionToken).filter_by(token_hash=hash_token(raw)).first()
    if row is not None:
        row.revoked = True
        db.commit()


def _bearer(request: Request) -> str:
    """Extract the bearer token from the Authorization header.

    Args:
        request: FastAPI request object.

    Returns:
        The token string (without "Bearer" prefix), or empty string if missing.
    """
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return ""


def profile_from_extension_token(request: Request, db: Session = Depends(get_db)) -> int:
    """FastAPI dependency: resolve a profile ID from an extension bearer token.

    Raises HTTPException(401) if the token is missing, invalid, revoked, or banned.

    Args:
        request: FastAPI request object.
        db: Database session (injected).

    Returns:
        The profile_id of the account that owns the token.

    Raises:
        HTTPException: 401 with detail={"error": "no_account"} if token is invalid.
    """
    acct = resolve_token(db, _bearer(request))
    if acct is None:
        raise HTTPException(status_code=401, detail={"error": "no_account"})
    return acct.profile_id


def bearer_or_session_profile(request: Request, db: Session = Depends(get_db)) -> int:
    """Resolve the tenant from an extension bearer token if present, else the
    session/dev-stub path (so local dev, tests, and the tray app keep working).

    Tries bearer token first; if missing or invalid, falls back to current_profile_id
    (which reads the session or dev stub).

    Args:
        request: FastAPI request object.
        db: Database session (injected).

    Returns:
        The profile_id of the authenticated account or session principal.

    Raises:
        HTTPException: 401 with detail={"error": "no_account"} if bearer is present
            but invalid; or whatever current_profile_id raises if no bearer.
    """
    raw = _bearer(request)
    if raw:
        acct = resolve_token(db, raw)
        if acct is None:
            raise HTTPException(status_code=401, detail={"error": "no_account"})
        return acct.profile_id
    return current_profile_id(request, db)
