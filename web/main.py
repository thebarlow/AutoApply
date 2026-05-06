from __future__ import annotations

import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from db.database import init_db
from web.routers import jobs
from web.routers import scraper
from web.routers import config


def _timed(label: str, fn):
    t = time.perf_counter()
    result = fn()
    print(f"  [startup] {label} — {time.perf_counter() - t:.1f}s")
    return result


def _warm_lazy_imports() -> None:
    """Import heavy modules in the background so the first real request isn't slow."""
    print("[startup] Warming lazy imports in background...")
    _timed("openai", lambda: __import__("openai"))
    _timed("pdfplumber", lambda: __import__("pdfplumber"))
    print("[startup] Background warm-up complete — all imports ready.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[startup] Initialising database...")
    _timed("init_db", init_db)

    t = threading.Thread(target=_warm_lazy_imports, daemon=True)
    t.start()

    yield  # server is live from here

    print("[shutdown] Waiting for background thread...")
    t.join(timeout=5)


app = FastAPI(title="Auto Apply", lifespan=lifespan)

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


@app.get("/setup")
def setup_page():
    return FileResponse(_STATIC / "setup.html")
