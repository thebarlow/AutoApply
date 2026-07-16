from __future__ import annotations

import os

from fastapi import APIRouter, Request
from sqlalchemy.orm import Session
from fastapi import Depends

from core import session_cost
from db.database import Account, get_db

router = APIRouter(prefix="/api")


@router.get("/session-cost")
def get_session_cost(request: Request, db: Session = Depends(get_db)) -> dict:
    """Process-wide LLM spend since boot.

    The total is platform-global (all tenants), so on the hosted instance only
    admins see the real figure; other users get 0.0. The frontend also uses
    this endpoint as a liveness heartbeat, so it must return 200 for everyone.
    """
    if os.getenv("APP_ENV") == "production":
        account_id = request.session.get("account_id")
        acct = (
            db.query(Account).filter_by(id=account_id).first()
            if account_id
            else None
        )
        if acct is None or not acct.is_admin:
            return {"total": 0.0}
    return {"total": session_cost.get_total()}
