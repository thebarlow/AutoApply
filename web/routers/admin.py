"""Admin-only operations: user invites (allowlist + email)."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.credits import grant_credits
from core.email import send_invite
from db.database import Account, AllowedEmail, Purchase, get_db
from web.routers.credits import openrouter_remaining, require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class InviteRequest(BaseModel):
    email: str


@router.post("/invite")
def invite_user(body: InviteRequest, db: Session = Depends(get_db),
                admin: Account = Depends(require_admin)):
    """Allowlist an email and send an invite. Idempotent: a repeat email is not
    re-inserted (no duplicate row) but the email is resent. Returns
    {email, already_invited, emailed}."""
    email = body.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="invalid email")
    existing = db.query(AllowedEmail).filter_by(email=email).first()
    already = existing is not None
    if not already:
        db.add(AllowedEmail(email=email, invited_by=admin.id, created_at=_now()))
        db.commit()
    emailed = send_invite(email)
    return {"email": email, "already_invited": already, "emailed": emailed}


@router.get("/invites")
def list_invites(db: Session = Depends(get_db),
                 admin: Account = Depends(require_admin)):
    rows = db.query(AllowedEmail).order_by(AllowedEmail.id.desc()).all()
    return [{"email": r.email, "created_at": r.created_at} for r in rows]


def require_real_admin(request: Request, db: Session = Depends(get_db)) -> Account:
    """Resolve the REAL logged-in account from the session and require admin.

    Unlike require_admin (which depends on current_profile_id and would resolve
    the *impersonated* tenant), this always authorizes the actual admin, so admin
    endpoints keep working -- and stay admin-gated -- while impersonating.
    Outside production there is no session login; fall back to the dev tenant's
    account so local/dev and tests behave.
    """
    account_id = request.session.get("account_id")
    acct = db.query(Account).filter_by(id=account_id).first() if account_id else None
    if acct is None:
        from web.tenancy import get_dev_tenant_id
        acct = db.query(Account).filter_by(profile_id=get_dev_tenant_id(db)).first()
    if acct is None or not acct.is_admin:
        raise HTTPException(status_code=403, detail="admin only")
    return acct


@router.get("/users")
def list_users(db: Session = Depends(get_db),
               admin: Account = Depends(require_real_admin)):
    rows = db.query(Account).order_by(Account.profile_id.asc()).all()
    return [{"profile_id": a.profile_id, "email": a.email, "tier": a.tier,
             "credits": a.credit_balance or 0, "is_admin": a.is_admin,
             "banned": a.banned}
            for a in rows]


class AccessRequest(BaseModel):
    banned: bool


@router.post("/users/{profile_id}/access")
def set_user_access(profile_id: int, body: AccessRequest,
                    db: Session = Depends(get_db),
                    admin: Account = Depends(require_real_admin)):
    target = db.query(Account).filter_by(profile_id=profile_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="profile not found")
    if target.is_admin:
        raise HTTPException(status_code=400, detail="cannot ban an admin")
    target.banned = body.banned
    if body.banned:
        row = db.query(AllowedEmail).filter_by(email=target.email.lower()).first()
        if row is not None:
            db.delete(row)
    db.commit()
    return {"profile_id": profile_id, "banned": target.banned}


@router.get("/users/{profile_id}/purchases")
def user_purchases(profile_id: int, db: Session = Depends(get_db),
                   admin: Account = Depends(require_real_admin)):
    if db.query(Account).filter_by(profile_id=profile_id).first() is None:
        raise HTTPException(status_code=404, detail="profile not found")
    rows = (db.query(Purchase).filter_by(profile_id=profile_id)
            .order_by(Purchase.id.desc()).limit(50).all())
    return [{"stripe_session_id": r.stripe_session_id, "credits": r.credits,
             "amount_usd": r.amount_usd, "status": r.status,
             "created_at": r.created_at} for r in rows]


class ImpersonateRequest(BaseModel):
    profile_id: int


@router.post("/impersonate/start")
def impersonate_start(body: ImpersonateRequest, request: Request,
                      db: Session = Depends(get_db),
                      admin: Account = Depends(require_real_admin)):
    target = db.query(Account).filter_by(profile_id=body.profile_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="profile not found")
    request.session["impersonate_profile_id"] = body.profile_id
    return {"ok": True}


CREDITS_PER_DOLLAR = 1000


def _grant_budget(db: Session) -> dict:
    remaining = openrouter_remaining()
    allocated = int(db.query(func.coalesce(func.sum(Account.credit_balance), 0))
                    .filter(Account.is_admin.is_(False)).scalar() or 0)
    if remaining is None:
        return {"system_credits": None, "allocated": allocated, "available": None}
    system_credits = round(remaining * CREDITS_PER_DOLLAR)
    return {"system_credits": system_credits, "allocated": allocated,
            "available": max(system_credits - allocated, 0)}


@router.get("/grant-budget")
def grant_budget(db: Session = Depends(get_db),
                 admin: Account = Depends(require_real_admin)):
    return _grant_budget(db)


class GrantRequest(BaseModel):
    amount: int


@router.post("/users/{profile_id}/grant")
def grant_to_user(profile_id: int, body: GrantRequest,
                  db: Session = Depends(get_db),
                  admin: Account = Depends(require_real_admin)):
    target = db.query(Account).filter_by(profile_id=profile_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="profile not found")
    if target.is_admin:
        raise HTTPException(status_code=400, detail="cannot grant to an admin")
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    budget = _grant_budget(db)
    if budget["available"] is None:
        raise HTTPException(status_code=409,
                            detail={"error": "system_balance_unavailable"})
    if body.amount > budget["available"]:
        raise HTTPException(status_code=400,
                            detail={"error": "exceeds_grant_budget",
                                    "available": budget["available"]})
    grant_credits(db, profile_id, body.amount, reason="admin_grant",
                  created_by=admin.id)
    bal = db.query(Account).filter_by(profile_id=profile_id).first().credit_balance
    return {"granted": body.amount, "balance": bal}


@router.post("/impersonate/stop")
def impersonate_stop(request: Request,
                     admin: Account = Depends(require_real_admin)):
    request.session.pop("impersonate_profile_id", None)
    return {"ok": True}
