"""Admin-only operations: user invites (allowlist + email)."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.email import send_invite
from db.database import Account, AllowedEmail, get_db
from web.routers.credits import require_admin

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
