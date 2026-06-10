"""The multi-tenancy seam.

Every tenant-scoped read goes through ``scoped()``; every request resolves its
tenant through ``current_profile_id``. The dependency body is a DEV STUB — the
later Auth spec swaps it to read a session/JWT without changing any call site.
"""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from db.database import Config, get_db

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


def current_profile_id(db: Session = Depends(get_db)) -> int:
    """FastAPI dependency: the active tenant for this request.

    DEV STUB — returns the configured dev tenant. The Auth spec replaces this
    body with real session/JWT resolution; no call site changes.
    """
    return get_dev_tenant_id(db)


def scoped(db: Session, model, profile_id: int):
    """Return a query over ``model`` filtered to one tenant.

    All tenant-scoped reads of Job/Document/SkillAlias must go through this
    instead of a bare ``db.query(model)``.
    """
    return db.query(model).filter(model.profile_id == profile_id)
