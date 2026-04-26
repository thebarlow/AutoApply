from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from web.routers import jobs

app = FastAPI(title="Auto Apply")

_STATIC = Path(__file__).parent / "static"

app.include_router(jobs.router)
app.mount("/static", StaticFiles(directory=_STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(_STATIC / "index.html")
