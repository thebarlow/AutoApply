"""Write-time tenant guard: every tenant-owned insert must carry profile_id."""
from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.orm import Session

# Tables that must always be tenant-stamped on insert.
_TENANT_TABLES = {"jobs", "documents", "skill_aliases"}
_registered = False


def register_tenant_guard() -> None:
    """Idempotently install the before_flush tenant assertion."""
    global _registered
    if _registered:
        return
    _registered = True

    @event.listens_for(Session, "before_flush")
    def _assert_tenant(session, flush_context, instances):  # noqa: ANN001
        for obj in session.new:
            table = getattr(obj, "__tablename__", None)
            if table in _TENANT_TABLES and getattr(obj, "profile_id", None) is None:
                raise ValueError(
                    f"Tenant-owned insert into '{table}' is missing profile_id "
                    f"(object={obj!r}). A write site forgot to scope by tenant."
                )
