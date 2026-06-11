from __future__ import annotations

import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from db.database import init_db
from web.routers import jobs
from web.routers import scraper
from web.routers import config
from web.routers import events
from web.routers import tray
from web.routers import prompts
from web.routers import llm_status_router
from web.routers import llm_test
from web.routers import setup_status
from web.routers import docs_router
from web.routers import session_cost_router
from web.routers import shutdown as shutdown_router
from web.routers import stats as stats_router
from web.routers import skills as skills_router
from web.auth import routes as auth_routes
from web.auth.middleware import AuthGateMiddleware


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


def _purge_deleted_jobs() -> None:
    """Permanently remove any jobs left in state='deleted' from a prior session."""
    # global purge across tenants — startup maintenance, not request-scoped
    from db.database import SessionLocal
    from core.job import Job
    db = SessionLocal()
    try:
        count = db.query(Job).filter(Job.state == "deleted").delete(synchronize_session=False)
        db.commit()
        if count:
            print(f"[startup] Purged {count} deleted job(s) from prior session.")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[startup] Initialising database...")
    _timed("init_db", init_db)
    _timed("purge_deleted", _purge_deleted_jobs)

    t = threading.Thread(target=_warm_lazy_imports, daemon=True)
    t.start()

    print("[startup] Open http://localhost:8080 in your browser")

    yield

    print("[shutdown] Waiting for background thread...")
    t.join(timeout=5)


app = FastAPI(title="Auto Apply", lifespan=lifespan, docs_url="/endpoints", redoc_url=None)
# SessionMiddleware is registered LAST in this block on purpose: Starlette runs
# the most-recently-added middleware outermost, so the session is populated on
# the request scope before AuthGateMiddleware inspects it.
app.add_middleware(AuthGateMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "dev-insecure-session-secret"),
    https_only=os.getenv("APP_ENV") == "production",
    same_site="lax",
)

_STATIC = Path(__file__).parent / "static"
_DIST = Path(__file__).parent.parent / "react-dashboard" / "dist"

app.include_router(jobs.router)
app.include_router(scraper.router)
app.include_router(config.router)
app.include_router(events.router)
app.include_router(tray.router)
app.include_router(prompts.router)
app.include_router(llm_status_router.router)
app.include_router(llm_test.router)
app.include_router(setup_status.router)
app.include_router(docs_router.router)
app.include_router(session_cost_router.router)
app.include_router(shutdown_router.router)
app.include_router(stats_router.router)
app.include_router(skills_router.router)
app.include_router(auth_routes.router)

# Serve legacy static assets (favicons, images)
app.mount("/static", StaticFiles(directory=_STATIC), name="static")

# Serve Vite-compiled JS/CSS bundles (only when built)
if (_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")


def _spa_index() -> FileResponse:
    return FileResponse(_DIST / "index.html")


@app.get("/")
def index():
    return _spa_index()


@app.get("/config")
def config_page():
    return _spa_index()


@app.get("/setup")
def setup_page():
    return _spa_index()


@app.get("/help")
def help_page():
    return FileResponse(Path(__file__).parent.parent / "docs" / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/{full_path:path}")
def spa_catchall(full_path: str):
    """Serve React SPA for any unmatched non-API route."""
    if (_DIST / "index.html").exists():
        return _spa_index()
    raise HTTPException(status_code=404)
