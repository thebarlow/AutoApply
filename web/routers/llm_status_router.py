from __future__ import annotations

from fastapi import APIRouter

from web import llm_status


router = APIRouter(prefix="/api")


@router.get("/llm-status")
def get_llm_status() -> dict:
    """Return processing snapshot: job-level keys and per-action map."""
    return {
        "processing": llm_status.snapshot(),
        "actions": llm_status.action_snapshot(),
    }
