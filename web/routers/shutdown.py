from __future__ import annotations

import os
import threading
import time

from fastapi import APIRouter, HTTPException

from web import llm_status

router = APIRouter(prefix="/api")


def _exit_process() -> None:
    os._exit(0)


def _delayed_exit(delay: float = 0.3) -> None:
    def _run():
        time.sleep(delay)
        _exit_process()
    threading.Thread(target=_run, daemon=True).start()


def _wait_and_exit() -> None:
    def _run():
        while llm_status.snapshot():
            time.sleep(1)
        _exit_process()
    threading.Thread(target=_run, daemon=True).start()


@router.post("/shutdown")
def shutdown(mode: str = "immediate") -> dict:
    if mode not in ("immediate", "wait"):
        raise HTTPException(status_code=422, detail=f"Unknown mode: {mode!r}")
    if mode == "wait":
        _wait_and_exit()
        return {"ok": True, "mode": "wait"}
    _delayed_exit()
    return {"ok": True, "mode": "immediate"}
