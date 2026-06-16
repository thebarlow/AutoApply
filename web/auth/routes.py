"""OAuth login/callback/logout routes and the /api/me identity endpoint.

Provider I/O is confined to _fetch_claims; the rest of the module is plain
request handling so the routes can be tested with _fetch_claims monkeypatched.
"""
from __future__ import annotations

import os

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import RedirectResponse
from sqlalchemy.orm import Session

from db.database import Account, get_db
from core.user import User
from web.auth.identity import Claims, BetaAccessDenied, resolve_or_provision_account

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


def _redirect_uri(request: Request, provider: str) -> str:
    return str(request.url_for("auth_callback", provider=provider))


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


@router.get("/auth/login/{provider}")
async def auth_login(provider: str, request: Request):
    if provider not in _PROVIDERS:
        raise HTTPException(status_code=404)
    return await oauth.create_client(provider).authorize_redirect(
        request, _redirect_uri(request, provider)
    )


@router.get("/auth/callback/{provider}", name="auth_callback")
async def auth_callback(provider: str, request: Request, db: Session = Depends(get_db)):
    if provider not in _PROVIDERS:
        raise HTTPException(status_code=404)
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
            target = (db.query(Account).filter_by(profile_id=pid).first()
                      if pid is not None else None)
            if target is not None:
                impersonating = {"profile_id": target.profile_id, "email": target.email}
    return {
        "email": acct.email,
        "is_admin": acct.is_admin,
        "profile_name": user.name if user else "",
        "impersonating": impersonating,
    }
