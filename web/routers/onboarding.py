from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.user import User
from db.database import get_db
from web.tenancy import current_profile_id

router = APIRouter()

_LEGAL = {"unstarted", "part1_done", "completed", "skipped"}
_TERMINAL = {"completed", "skipped"}


def _is_legal_transition(old: str, new: str) -> bool:
    """Reject moving out of a terminal state back to an in-progress one."""
    if old in _TERMINAL and new in {"unstarted", "part1_done"}:
        return False
    return True


class TourUpdate(BaseModel):
    state: str


@router.patch("/api/onboarding/tour")
def set_tour_state(
    body: TourUpdate,
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
) -> dict[str, str]:
    """Persist the caller's onboarding tour progress."""
    if body.state not in _LEGAL:
        raise HTTPException(status_code=422, detail=f"Unknown tour state: {body.state}")
    # A profile row is created at login in production, but the tour can finish
    # before one exists (e.g. a user skips the résumé wizard). Echo the state
    # without persisting rather than 500ing — there is nowhere to store it yet.
    if db.query(User).filter_by(id=profile_id).first() is None:
        return {"onboarding_tour": body.state}
    user = User.load(db, profile_id)
    if not _is_legal_transition(user.onboarding_tour, body.state):
        raise HTTPException(status_code=409, detail="Illegal tour state transition")
    user.onboarding_tour = body.state
    user.save(db)
    return {"onboarding_tour": user.onboarding_tour}
