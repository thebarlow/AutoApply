from __future__ import annotations

from fastapi import APIRouter

from core import session_cost

router = APIRouter(prefix="/api")


@router.get("/session-cost")
def get_session_cost() -> dict:
    return {"total": session_cost.get_total()}
