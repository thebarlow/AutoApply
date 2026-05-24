from __future__ import annotations

from fastapi import APIRouter

from web import llm_status


router = APIRouter(prefix="/api")


@router.get("/llm-status")
def get_llm_status() -> dict[str, list[str]]:
    """Return job_keys currently in an in-flight LLM op."""
    return {"processing": llm_status.snapshot()}
