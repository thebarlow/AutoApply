from __future__ import annotations

import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from db.database import init_db
from web.routers import jobs
from web.routers import scraper
from web.routers import config
from web.routers import events


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

    print("[startup] Open http://localhost:8080 in your browser")

    yield

    print("[shutdown] Waiting for background thread...")
    t.join(timeout=5)


app = FastAPI(title="Auto Apply", lifespan=lifespan)

_STATIC = Path(__file__).parent / "static"
_DIST = Path(__file__).parent.parent / "react-dashboard" / "dist"

app.include_router(jobs.router)
app.include_router(scraper.router)
app.include_router(config.router)
app.include_router(events.router)

# Serve legacy static assets (favicons, images)
app.mount("/static", StaticFiles(directory=_STATIC), name="static")

# Serve Vite-compiled JS/CSS bundles (only when built)
if (_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")


def _spa_index() -> FileResponse:
    return FileResponse(_DIST / "index.html")


@app.get("/")
def index():
    if (_DIST / "index.html").exists():
        return _spa_index()
    return FileResponse(_STATIC / "index.html")


@app.get("/config")
def config_page():
    if (_DIST / "index.html").exists():
        return _spa_index()
    return FileResponse(_STATIC / "config.html")


@app.get("/setup")
def setup_page():
    if (_DIST / "index.html").exists():
        return _spa_index()
    return FileResponse(_STATIC / "setup.html")


@app.get("/help")
def help_page():
    return FileResponse(Path(__file__).parent.parent / "docs" / "index.html")


@app.get("/{full_path:path}")
def spa_catchall(full_path: str):
    """Serve React SPA for any unmatched non-API route."""
    if (_DIST / "index.html").exists():
        return _spa_index()
    raise HTTPException(status_code=404)
