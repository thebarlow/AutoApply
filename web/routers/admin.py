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
from core.payments import tier_margins
from db.database import Account, AllowedEmail, Purchase, get_db
from web.routers.credits import openrouter_remaining, require_real_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class InviteRequest(BaseModel):
    email: str
    tier: str = "standard"
    is_admin: bool = False


@router.post("/invite")
def invite_user(body: InviteRequest, db: Session = Depends(get_db),
                admin: Account = Depends(require_real_admin)):
    """Allowlist an email (with an intended user type) and send an invite.

    Idempotent: a repeat email is not re-inserted, but its tier/is_admin are
    updated to the latest request and the email is resent. The type is applied
    to the Account when it is provisioned at first login. Returns
    {email, already_invited, emailed}."""
    email = body.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="invalid email")
    if body.tier not in tier_margins():
        raise HTTPException(status_code=400, detail="invalid tier")
    existing = db.query(AllowedEmail).filter_by(email=email).first()
    already = existing is not None
    if already:
        existing.tier = body.tier
        existing.is_admin = body.is_admin
    else:
        db.add(AllowedEmail(email=email, invited_by=admin.id, created_at=_now(),
                            tier=body.tier, is_admin=body.is_admin))
    db.commit()
    # The allowlist row is already committed, so a mail failure must not 500 the
    # request (the user is still invited). Capture and surface the real reason so
    # the admin sees *why* delivery failed instead of a generic error.
    emailed = False
    email_error = None
    try:
        emailed = send_invite(email)
    except Exception as exc:  # noqa: BLE001 - report any SMTP/connection failure
        logger.exception("send_invite failed for %s", email)
        email_error = f"{type(exc).__name__}: {exc}"
    return {"email": email, "already_invited": already, "emailed": emailed,
            "email_error": email_error}


@router.get("/invites")
def list_invites(db: Session = Depends(get_db),
                 admin: Account = Depends(require_real_admin)):
    rows = db.query(AllowedEmail).order_by(AllowedEmail.id.desc()).all()
    return [{"email": r.email, "created_at": r.created_at,
             "tier": r.tier, "is_admin": r.is_admin} for r in rows]


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
    if target.banned:
        raise HTTPException(status_code=400, detail="cannot impersonate a banned user")
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
    if target.banned:
        raise HTTPException(status_code=400, detail="cannot grant to a banned user")
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
    return {"granted": body.amount, "balance": target.credit_balance}


@router.post("/impersonate/stop")
def impersonate_stop(request: Request,
                     admin: Account = Depends(require_real_admin)):
    request.session.pop("impersonate_profile_id", None)
    return {"ok": True}
