from __future__ import annotations

import json as _json
import os

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from core.job import Job
from core.schemas import AtsReport
from db.database import get_db
from web.sse import send as _sse_send
from web.tenancy import current_profile_id

router = APIRouter()

_tray_ws: WebSocket | None = None


def _emit(job: Job) -> None:
    _sse_send("job", job.serialize(), profile_id=job.profile_id)


@router.websocket("/ws/tray")
async def tray_ws(websocket: WebSocket):
    global _tray_ws
    # The tray socket is a single unauthenticated process-global slot for the
    # local desktop app. On the hosted multi-tenant instance it would let any
    # internet client receive other tenants' apply payloads — refuse outright.
    if os.getenv("APP_ENV") == "production":
        await websocket.close(code=4003)
        return
    if _tray_ws is not None:
        await websocket.accept()
        await websocket.close(code=4009)
        return

    await websocket.accept()
    _tray_ws = websocket
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _tray_ws = None


@router.post("/api/jobs/{job_key}/confirm-applied")
def confirm_applied(
    job_key: str,
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
):
    job = Job.get(job_key, db, profile_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    # Trust the stored ATS report (produced automatically after generation/refine).
    # Missing or stale → block until a fresh check completes; failed → hard-block.
    if job.ats_report_json is None or job.ats_is_stale():
        raise HTTPException(
            status_code=422,
            detail="ATS check has not completed for the current résumé. "
            "Wait for it to finish or regenerate the résumé.",
        )
    report = AtsReport.model_validate_json(job.ats_report_json)
    if not report.passed:
        raise HTTPException(status_code=409, detail=report.model_dump())
    job.mark_applied(db)
    db.refresh(job)
    _emit(job)
    return job.serialize()


@router.post("/api/jobs/{job_key}/apply")
async def apply_job(
    job_key: str,
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
):
    job = Job.get(job_key, db, profile_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    ws = _tray_ws
    if ws is None:
        raise HTTPException(status_code=503, detail="Tray app not connected")

    payload = {
        "jobId": job_key,
        "role": job.title or "",
        "company": job.company or "",
        "resume_path": job.resume_path or "",
        "cover_path": job.cover_path or "",
    }
    try:
        await ws.send_text(_json.dumps(payload))
    except Exception:
        raise HTTPException(status_code=503, detail="Tray app disconnected before payload could be sent")
    return {"status": "queued"}
