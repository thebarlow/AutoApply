from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from web.routers import jobs
from web.routers import scraper
from web.routers import config

app = FastAPI(title="Auto Apply")

_STATIC = Path(__file__).parent / "static"

app.include_router(jobs.router)
app.include_router(scraper.router)
app.include_router(config.router)
app.mount("/static", StaticFiles(directory=_STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(_STATIC / "index.html")


@app.get("/config")
def config_page():
    return FileResponse(_STATIC / "config.html")
