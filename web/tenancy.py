"""The multi-tenancy seam.

Every tenant-scoped read goes through ``scoped()``; every request resolves its
tenant through ``current_profile_id``. The dependency body is a DEV STUB — the
later Auth spec swaps it to read a session/JWT without changing any call site.
"""
from __future__ import annotations

import os

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from db.database import Account, Config, get_db

# Seed/dev tenant. Never 0 (falsy — would break `if profile_id:` guards).
DEFAULT_TENANT_ID = 1


def get_dev_tenant_id(db: Session) -> int:
    """Resolve the dev tenant from Config['dev_tenant_id'], defaulting to 1."""
    row = db.query(Config).filter_by(key="dev_tenant_id").first()
    if row and row.value:
        try:
            return int(row.value)
        except (ValueError, TypeError):
            pass
    return DEFAULT_TENANT_ID


def current_profile_id(request: Request, db: Session = Depends(get_db)) -> int:
    """FastAPI dependency: the active tenant for this request.

    In production the tenant is the logged-in account's profile (session-backed).
    Outside production the dev stub returns the configured dev tenant so local
    dev and the test suite need no login.
    """
    if os.getenv("APP_ENV") == "production":
        account_id = request.session.get("account_id")
        if not account_id:
            raise HTTPException(status_code=401, detail="Not authenticated")
        acct = db.query(Account).filter_by(id=account_id).first()
        if acct is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return acct.profile_id
    return get_dev_tenant_id(db)


def scoped(db: Session, model, profile_id: int):
    """Return a query over ``model`` filtered to one tenant.

    All tenant-scoped reads of Job/Document/SkillAlias must go through this
    instead of a bare ``db.query(model)``.
    """
    return db.query(model).filter(model.profile_id == profile_id)
