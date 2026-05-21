from __future__ import annotations

import json as _json

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from core.job import Job
from db.database import get_db
from web.sse import broadcast as _broadcast

router = APIRouter()

_tray_ws: WebSocket | None = None


def _emit(job: Job) -> None:
    _broadcast(_json.dumps(job.serialize()))


@router.websocket("/ws/tray")
async def tray_ws(websocket: WebSocket):
    global _tray_ws
    if _tray_ws is not None:
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
def confirm_applied(job_key: str, db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    job.mark_applied(db)
    db.refresh(job)
    _emit(job)
    return job.serialize()


@router.post("/api/jobs/{job_key}/apply")
async def apply_job(job_key: str, db: Session = Depends(get_db)):
    global _tray_ws
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.resume_path or not job.cover_path:
        raise HTTPException(status_code=400, detail="resume_path and cover_path must both be set before applying")
    if _tray_ws is None:
        raise HTTPException(status_code=503, detail="Tray app not connected")

    payload = {
        "jobId": job_key,
        "role": job.role or "",
        "company": job.company or "",
        "resume_path": job.resume_path,
        "cover_path": job.cover_path,
    }
    await _tray_ws.send_text(_json.dumps(payload))
    return {"status": "queued"}
