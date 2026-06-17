"""OAuth login/callback/logout routes and the /api/me identity endpoint.

Provider I/O is confined to _fetch_claims; the rest of the module is plain
request handling so the routes can be tested with _fetch_claims monkeypatched.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import urlencode

import httpx

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import RedirectResponse
from sqlalchemy.orm import Session

from db.database import Account, get_db
from core.user import User
from web.auth.identity import (
    Claims,
    BetaAccessDenied,
    NoExtensionAccount,
    resolve_or_provision_account,
    resolve_existing_account,
)
from web.auth.ext_token import (
    mint_token,
    profile_from_extension_token,
    resolve_token,
    revoke_token,
    _bearer,
)

router = APIRouter()

_PROVIDERS = ("google", "github")

oauth = OAuth()
oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    client_kwargs={"scope": "openid email profile"},
)
oauth.register(
    name="github",
    client_id=os.getenv("GITHUB_CLIENT_ID"),
    client_secret=os.getenv("GITHUB_CLIENT_SECRET"),
    access_token_url="https://github.com/login/oauth/access_token",
    authorize_url="https://github.com/login/oauth/authorize",
    api_base_url="https://api.github.com/",
    client_kwargs={"scope": "read:user user:email"},
)


def _allowed_ext_redirects() -> set[str]:
    """Return the set of permitted extension redirect URIs from env."""
    return {
        u.strip()
        for u in os.getenv("EXTENSION_REDIRECT_URLS", "").split(",")
        if u.strip()
    }


def _redirect_uri(request: Request, provider: str) -> str:
    return str(request.url_for("auth_callback", provider=provider))


# --- Stateless extension OAuth state (signed, no server session) ------------
#
# launchWebAuthFlow runs the OAuth round-trip in a context where the Starlette
# session cookie set by /auth/ext/login does not reliably survive back to the
# callback, so the extension flow cannot rely on it. Instead the redirect target
# is packed into the OAuth `state` parameter, HMAC-signed with SESSION_SECRET and
# echoed back by the provider. The callback verifies the signature, so no session
# is needed and the value cannot be tampered with.

_EXT_STATE_MAX_AGE = 600  # seconds


def _state_secret() -> bytes:
    return os.getenv("SESSION_SECRET", "").encode("utf-8")


def sign_ext_state(provider: str, redirect_uri: str) -> str:
    """Return a signed, URL-safe state token carrying the ext redirect target."""
    payload = {
        "ext": True,
        "provider": provider,
        "redirect_uri": redirect_uri,
        "ts": int(time.time()),
        "nonce": secrets.token_urlsafe(8),
    }
    raw = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    sig = hmac.new(_state_secret(), raw.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def verify_ext_state(state: str) -> dict | None:
    """Return the decoded ext-state payload if the signature/age are valid, else None."""
    if not state or "." not in state:
        return None
    raw, _, sig = state.rpartition(".")
    expected = hmac.new(
        _state_secret(), raw.encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(raw.encode("ascii")))
    except (ValueError, json.JSONDecodeError):
        return None
    if (
        not payload.get("ext")
        or time.time() - payload.get("ts", 0) > _EXT_STATE_MAX_AGE
    ):
        return None
    return payload


def _ext_authorize_url(provider: str, redirect_uri: str, state: str) -> str:
    """Build the provider authorize URL for the stateless extension flow."""
    if provider == "google":
        params = {
            "response_type": "code",
            "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
            "redirect_uri": redirect_uri,
            "scope": "openid email profile",
            "state": state,
        }
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    params = {
        "client_id": os.getenv("GITHUB_CLIENT_ID", ""),
        "redirect_uri": redirect_uri,
        "scope": "read:user user:email",
        "state": state,
    }
    return "https://github.com/login/oauth/authorize?" + urlencode(params)


async def _ext_fetch_claims(provider: str, code: str, redirect_uri: str) -> Claims:
    """Exchange an auth code for tokens and normalize provider data into Claims.

    Stateless equivalent of _fetch_claims for the extension flow: performs the
    token exchange manually (no Authlib session state). Isolated so tests can
    monkeypatch it.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        if provider == "google":
            tok = (
                await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "code": code,
                        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                        "redirect_uri": redirect_uri,
                        "grant_type": "authorization_code",
                    },
                )
            ).json()
            info = (
                await client.get(
                    "https://openidconnect.googleapis.com/v1/userinfo",
                    headers={"Authorization": f"Bearer {tok['access_token']}"},
                )
            ).json()
            return Claims(
                provider="google",
                subject=str(info["sub"]),
                email=info.get("email", ""),
                email_verified=bool(info.get("email_verified")),
            )
        tok = (
            await client.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": os.getenv("GITHUB_CLIENT_ID"),
                    "client_secret": os.getenv("GITHUB_CLIENT_SECRET"),
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            )
        ).json()
        access = tok["access_token"]
        headers = {
            "Authorization": f"Bearer {access}",
            "Accept": "application/vnd.github+json",
        }
        user = (await client.get("https://api.github.com/user", headers=headers)).json()
        emails = (
            await client.get("https://api.github.com/user/emails", headers=headers)
        ).json()
        primary = next(
            (e for e in emails if e.get("primary") and e.get("verified")), None
        )
        return Claims(
            provider="github",
            subject=str(user["id"]),
            email=(primary or {}).get("email", ""),
            email_verified=primary is not None,
        )


async def _fetch_claims(provider: str, request: Request) -> Claims:
    """Complete the OAuth exchange and normalize provider data into Claims.

    Isolated so tests can monkeypatch it; this is the only function that talks
    to a live provider.
    """
    client = oauth.create_client(provider)
    token = await client.authorize_access_token(request)
    if provider == "google":
        info = token.get("userinfo") or await client.userinfo(token=token)
        return Claims(
            provider="google",
            subject=str(info["sub"]),
            email=info.get("email", ""),
            email_verified=bool(info.get("email_verified")),
        )
    user = (await client.get("user", token=token)).json()
    emails = (await client.get("user/emails", token=token)).json()
    primary = next((e for e in emails if e.get("primary") and e.get("verified")), None)
    return Claims(
        provider="github",
        subject=str(user["id"]),
        email=(primary or {}).get("email", ""),
        email_verified=primary is not None,
    )


@router.get("/auth/ext/login/{provider}")
async def auth_ext_login(provider: str, request: Request, redirect_uri: str = ""):
    """Begin an extension OAuth flow for an existing account.

    Validates redirect_uri against EXTENSION_REDIRECT_URLS, stashes ext_mode and
    ext_redirect in the session, then redirects to the provider.

    Args:
        provider: OAuth provider name (google or github).
        request: FastAPI request.
        redirect_uri: The extension's registered redirect URI.

    Raises:
        HTTPException: 404 if provider unknown, 400 if redirect_uri not on allowlist.
    """
    if provider not in _PROVIDERS:
        raise HTTPException(status_code=404)
    if redirect_uri not in _allowed_ext_redirects():
        raise HTTPException(status_code=400, detail="redirect_uri not allowed")
    state = sign_ext_state(provider, redirect_uri)
    return RedirectResponse(
        url=_ext_authorize_url(provider, _redirect_uri(request, provider), state)
    )


@router.get("/auth/login/{provider}")
async def auth_login(provider: str, request: Request):
    if provider not in _PROVIDERS:
        raise HTTPException(status_code=404)
    return await oauth.create_client(provider).authorize_redirect(
        request, _redirect_uri(request, provider)
    )


@router.get("/auth/callback/{provider}", name="auth_callback")
async def auth_callback(provider: str, request: Request, db: Session = Depends(get_db)):
    """Handle the OAuth provider callback for both website and extension flows.

    Extension flow: reads ext_mode/ext_redirect from session (set by /auth/ext/login),
    resolves an EXISTING account, and redirects to ext_redirect with a bearer token or
    error fragment. Website flow (unchanged): provisions account, sets session cookie.

    Args:
        provider: OAuth provider name.
        request: FastAPI request.
        db: Database session.

    Raises:
        HTTPException: 404 if provider unknown.
    """
    if provider not in _PROVIDERS:
        raise HTTPException(status_code=404)
    # Extension flow: detected by a valid signed state (no session dependency).
    ext = verify_ext_state(request.query_params.get("state", ""))
    if ext:
        ext_redirect = ext["redirect_uri"]
        if ext_redirect not in _allowed_ext_redirects():
            return RedirectResponse(url=f"{ext_redirect}#error=auth")
        try:
            claims = await _ext_fetch_claims(
                provider,
                request.query_params.get("code", ""),
                _redirect_uri(request, provider),
            )
        except Exception:
            return RedirectResponse(url=f"{ext_redirect}#error=auth")
        try:
            acct = resolve_existing_account(db, claims)
        except NoExtensionAccount:
            return RedirectResponse(url=f"{ext_redirect}#error=no_account")
        token = mint_token(db, acct.id)
        return RedirectResponse(url=f"{ext_redirect}#token={token}")
    # --- existing website flow unchanged below ---
    try:
        claims = await _fetch_claims(provider, request)
    except Exception:
        return RedirectResponse(url="/?auth_error=1")
    try:
        acct = resolve_or_provision_account(db, claims)
    except BetaAccessDenied:
        return RedirectResponse(url="/?beta=closed")
    request.session["account_id"] = acct.id
    return RedirectResponse(url="/")


@router.post("/auth/ext/revoke")
def auth_ext_revoke(request: Request, db: Session = Depends(get_db)):
    """Revoke the extension bearer token presented in the Authorization header.

    Args:
        request: FastAPI request.
        db: Database session.

    Returns:
        JSON {"ok": true}.
    """
    revoke_token(db, _bearer(request))
    return {"ok": True}


@router.get("/api/ext/me")
def api_ext_me(
    request: Request,
    profile_id: int = Depends(profile_from_extension_token),
    db: Session = Depends(get_db),
):
    """Return the email of the account owning the presented bearer token.

    profile_from_extension_token raises 401 for invalid tokens, so this handler
    only runs when the token is valid.

    Args:
        request: FastAPI request.
        profile_id: Resolved from bearer token (injected by dependency).
        db: Database session.

    Returns:
        JSON {"email": ...}.
    """
    acct = resolve_token(db, _bearer(request))
    return {"email": acct.email}


@router.post("/auth/logout")
def auth_logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/api/me")
def api_me(request: Request, db: Session = Depends(get_db)):
    account_id = request.session.get("account_id")
    if not account_id:
        raise HTTPException(status_code=401)
    acct = db.query(Account).filter_by(id=account_id).first()
    if acct is None:
        request.session.clear()
        raise HTTPException(status_code=401)
    user = db.query(User).filter_by(id=acct.profile_id).first()
    impersonating = None
    if acct.is_admin:
        target_pid = request.session.get("impersonate_profile_id")
        if target_pid:
            try:
                pid = int(target_pid)
            except (ValueError, TypeError):
                pid = None
            target = (
                db.query(Account).filter_by(profile_id=pid).first()
                if pid is not None
                else None
            )
            if target is not None:
                impersonating = {"profile_id": target.profile_id, "email": target.email}
    return {
        "email": acct.email,
        "is_admin": acct.is_admin,
        "profile_name": user.name if user else "",
        "impersonating": impersonating,
    }
