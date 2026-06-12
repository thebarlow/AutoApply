"""Credit balance, admin grants, and the dev system-balance view."""
from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import Account, CreditLedger, get_db
from core.credits import grant_credits
from web.tenancy import current_profile_id

router = APIRouter(prefix="/api", tags=["credits"])

logger = logging.getLogger(__name__)


def require_admin(request: Request, db: Session = Depends(get_db),
                  profile_id: int = Depends(current_profile_id)) -> Account:
    """Resolve the active account and ensure it is an admin."""
    acct = db.query(Account).filter_by(profile_id=profile_id).first()
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
                admin: Account = Depends(require_admin)):
    target_pid = body.profile_id
    if target_pid is None and body.email:
        tgt = db.query(Account).filter_by(email=body.email).first()
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


@router.get("/admin/system-balance")
def system_balance(admin: Account = Depends(require_admin)):
    """Remaining balance on the platform OpenRouter key (money in the system)."""
    key = os.getenv("LLM_API_KEY", "")
    if not key:
        raise HTTPException(status_code=503, detail="no platform key")
    try:
        resp = httpx.get("https://openrouter.ai/api/v1/credits",
                         headers={"Authorization": f"Bearer {key}"}, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        total = float(data.get("total_credits", 0))
        used = float(data.get("total_usage", 0))
        return {"total": total, "used": used, "remaining": total - used}
    except httpx.HTTPError:
        logger.exception("system-balance: OpenRouter request failed")
        raise HTTPException(status_code=502, detail="failed to reach OpenRouter")
