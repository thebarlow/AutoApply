"""Admin-only operations: user invites (allowlist + email)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.email import send_invite
from db.database import Account, AllowedEmail, get_db
from web.routers.credits import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class InviteRequest(BaseModel):
    email: str


@router.post("/invite")
def invite_user(body: InviteRequest, db: Session = Depends(get_db),
                admin: Account = Depends(require_admin)):
    email = body.email.strip().lower()
    if "@" not in email or "." not in email:
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
