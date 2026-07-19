"""Credit balance, admin grants, and the dev system-balance view."""
from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from db.database import Account, CreditLedger, get_db
from core.credits import grant_credits
from core import payments
from web.tenancy import current_profile_id

router = APIRouter(prefix="/api", tags=["credits"])

logger = logging.getLogger(__name__)


def require_real_admin(request: Request, db: Session = Depends(get_db)) -> Account:
    """Resolve the REAL logged-in account from the session and require admin.

    Authorizes the actual admin, never an impersonated tenant: it reads the
    session's ``account_id`` directly instead of going through
    ``current_profile_id`` (which resolves the *impersonated* profile while an
    admin is impersonating). So admin endpoints stay admin-gated even
    mid-impersonation. Outside production there is no session login; fall back to
    the dev tenant's account so local/dev and tests behave.

    Reads the session off ``request.scope`` (not ``request.session``) so it does
    not hard-require SessionMiddleware to be mounted — a missing session is
    treated as "not logged in" and routed to the dev fallback rather than 500ing.
    """
    from web.tenancy import get_dev_tenant_id
    session = request.scope.get("session") or {}
    account_id = session.get("account_id")
    acct = db.query(Account).filter_by(id=account_id).first() if account_id else None
    # The dev-tenant fallback must never apply in production: the outer auth
    # gate already 401s unauthenticated /api/*, but if it were bypassed (new
    # exempt path, middleware reorder) this would otherwise grant admin.
    if acct is None and os.getenv("APP_ENV") != "production":
        acct = db.query(Account).filter_by(profile_id=get_dev_tenant_id(db)).first()
    if acct is None or not acct.is_admin:
        raise HTTPException(status_code=403, detail="admin only")
    return acct


@router.get("/credits")
def get_credits(db: Session = Depends(get_db), profile_id: int = Depends(current_profile_id)):
    acct = db.query(Account).filter_by(profile_id=profile_id).first()
    if acct is None:
        return {"balance": 0, "rate": 0.0, "recent": []}
    recent = (db.query(CreditLedger).filter_by(profile_id=profile_id)
              .order_by(CreditLedger.id.desc()).limit(20).all())
    return {
        "balance": acct.credit_balance or 0,
        "rate": acct.credit_rate or 0.0,
        "recent": [
            {"delta": r.delta, "reason": r.reason, "action": r.action,
             "job_key": r.job_key, "created_at": r.created_at}
            for r in recent
        ],
    }


class GrantRequest(BaseModel):
    profile_id: int | None = None
    email: str | None = None
    amount: int
    note: str | None = None


@router.post("/admin/credits/grant")
def admin_grant(body: GrantRequest, db: Session = Depends(get_db),
                admin: Account = Depends(require_real_admin)):
    target_pid = body.profile_id
    if target_pid is None and body.email:
        tgt = (db.query(Account)
               .filter(func.lower(Account.email) == body.email.strip().lower())
               .first())
        if tgt is None:
            raise HTTPException(status_code=404, detail="account not found")
        target_pid = tgt.profile_id
    if target_pid is None:
        raise HTTPException(status_code=400, detail="profile_id or email required")
    row = grant_credits(db, target_pid, body.amount, reason="admin_grant",
                        created_by=admin.id, note=body.note)
    if row is None:
        raise HTTPException(status_code=404, detail="target account not found")
    bal = db.query(Account).filter_by(profile_id=target_pid).first().credit_balance
    return {"granted": body.amount, "balance": bal}


class SetTierRequest(BaseModel):
    profile_id: int | None = None
    email: str | None = None
    tier: str


@router.post("/admin/credits/tier")
def admin_set_tier(body: SetTierRequest, db: Session = Depends(get_db),
                   admin: Account = Depends(require_real_admin)):
    """Set a profile's pricing tier (admin only)."""
    if body.tier not in payments.tier_multipliers():
        raise HTTPException(status_code=400, detail="unknown tier")
    target = None
    if body.profile_id is not None:
        target = db.query(Account).filter_by(profile_id=body.profile_id).first()
    elif body.email:
        target = (db.query(Account)
                  .filter(func.lower(Account.email) == body.email.strip().lower())
                  .first())
    if target is None:
        raise HTTPException(status_code=404, detail="account not found")
    target.tier = body.tier
    db.commit()
    return {"profile_id": target.profile_id, "tier": target.tier}


def openrouter_remaining() -> float | None:
    """Remaining USD on the platform OpenRouter key, or None if unset/unreachable."""
    key = os.getenv("LLM_API_KEY", "")
    if not key:
        return None
    try:
        resp = httpx.get("https://openrouter.ai/api/v1/credits",
                         headers={"Authorization": f"Bearer {key}"}, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        return float(data.get("total_credits", 0)) - float(data.get("total_usage", 0))
    except httpx.HTTPError:
        logger.exception("openrouter_remaining: request failed")
        return None


@router.get("/admin/system-balance")
def system_balance(admin: Account = Depends(require_real_admin)):
    """Remaining balance on the platform OpenRouter key (money in the system)."""
    if not os.getenv("LLM_API_KEY", ""):
        raise HTTPException(status_code=503, detail="no platform key")
    remaining = openrouter_remaining()
    if remaining is None:
        raise HTTPException(status_code=502, detail="failed to reach OpenRouter")
    return {"remaining": remaining}
