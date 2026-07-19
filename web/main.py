from __future__ import annotations

import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from core.logging_config import setup_logging

setup_logging()

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
from web.routers import setup_status
from web.routers import onboarding
from web.routers import docs_router
from web.routers import session_cost_router
from web.routers import stats as stats_router
from web.routers import skills as skills_router
from web.routers import credits as credits_router
from web.routers import payments as payments_router
from web.routers import admin as admin_router
from web.routers import extension as extension_router
from web.routers import dev as dev_router
from web.routers import output_formats as output_formats_router
from web.routers import themes as themes_router
from web.auth import routes as auth_routes
from core.credits import InsufficientCredits
from fastapi.responses import JSONResponse
from web.auth.middleware import AuthGateMiddleware
from web.middleware_impersonation import ImpersonationReadOnlyMiddleware


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


def _purge_deleted_jobs(context: str = "startup") -> int:
    """Permanently remove all jobs in state='deleted'. Returns the count purged.

    Global purge across tenants — maintenance, not request-scoped. Runs at startup
    and on the daily scheduler.
    """
    from db.database import SessionLocal
    from core.job import Job

    db = SessionLocal()
    try:
        count = (
            db.query(Job)
            .filter(Job.state == "deleted")
            .delete(synchronize_session=False)
        )
        db.commit()
        if count:
            print(f"[{context}] Purged {count} deleted job(s).")
        return count
    finally:
        db.close()


# Deleted jobs are purged daily at 23:59 America/New_York (Eastern, DST-aware) —
# replaces the old "cleared on a fresh session" behavior, which effectively never
# fired once the app became an always-on hosted service.
_PURGE_TZ = ZoneInfo("America/New_York")


def _seconds_until_next_purge(now: datetime | None = None) -> float:
    """Seconds from now until the next 23:59 in the purge timezone."""
    now = now or datetime.now(_PURGE_TZ)
    target = now.replace(hour=23, minute=59, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _daily_purge_loop(stop_event: threading.Event) -> None:
    """Sleep until the next 23:59 ET, purge deleted jobs, repeat until stopped."""
    while not stop_event.wait(_seconds_until_next_purge()):
        try:
            _purge_deleted_jobs(context="daily-purge")
        except Exception as exc:  # never let a transient DB error kill the loop
            print(f"[daily-purge] error: {exc}")


def _warn_if_billing_disabled() -> None:
    """Loudly flag a production start with a zero default credit rate.

    meter_action bills nothing for accounts with credit_rate == 0, so a zero
    CREDIT_DEFAULT_RATE (env typo, bad migration) silently gives every new
    signup free LLM usage. Warn rather than crash: an admin may legitimately
    run a free period, but it must never happen unnoticed.
    """
    if os.getenv("APP_ENV") != "production":
        return
    from core.credits import default_rate

    if default_rate() <= 0:
        import logging

        logging.getLogger(__name__).warning(
            "CREDIT_DEFAULT_RATE resolves to %s in production — new accounts "
            "will NOT be billed for LLM actions", default_rate()
        )
        print("[startup] WARNING: billing disabled (CREDIT_DEFAULT_RATE <= 0)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[startup] Initialising database...")
    _warn_if_billing_disabled()
    _timed("init_db", init_db)
    _timed("purge_deleted", _purge_deleted_jobs)

    t = threading.Thread(target=_warm_lazy_imports, daemon=True)
    t.start()

    purge_stop = threading.Event()
    purge_thread = threading.Thread(
        target=_daily_purge_loop, args=(purge_stop,), daemon=True
    )
    purge_thread.start()

    print("[startup] Open http://localhost:8080 in your browser")

    yield

    print("[shutdown] Waiting for background threads...")
    purge_stop.set()
    t.join(timeout=5)
    purge_thread.join(timeout=5)


_DEV_SESSION_SECRET = "dev-insecure-session-secret"


def _session_secret() -> str:
    """Resolve the session-signing secret, refusing the insecure dev default in
    production. A weak/known secret lets anyone forge a session cookie and bypass
    auth entirely, so fail fast at startup rather than ship a guessable key."""
    secret = os.getenv("SESSION_SECRET")
    if os.getenv("APP_ENV") == "production":
        if not secret or secret == _DEV_SESSION_SECRET:
            raise RuntimeError(
                "SESSION_SECRET must be set to a strong random value in production"
            )
        return secret
    return secret or _DEV_SESSION_SECRET


app = FastAPI(
    title="Auto Apply", lifespan=lifespan, docs_url="/endpoints", redoc_url=None
)
# SessionMiddleware is registered LAST in this block on purpose: Starlette runs
# the most-recently-added middleware outermost, so the session is populated on
# the request scope before AuthGateMiddleware inspects it.
app.add_middleware(AuthGateMiddleware)
app.add_middleware(ImpersonationReadOnlyMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret(),
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
app.include_router(setup_status.router)
app.include_router(onboarding.router)
app.include_router(docs_router.router)
app.include_router(session_cost_router.router)
app.include_router(stats_router.router)
app.include_router(skills_router.router)
app.include_router(credits_router.router)
app.include_router(payments_router.router)
app.include_router(admin_router.router)
app.include_router(extension_router.router)
app.include_router(dev_router.router)
app.include_router(output_formats_router.router)
app.include_router(themes_router.router)
app.include_router(auth_routes.router)


@app.exception_handler(InsufficientCredits)
async def _insufficient_credits_handler(request, exc: InsufficientCredits):
    return JSONResponse(
        status_code=402,
        content={
            "error": "insufficient_credits",
            "balance": exc.balance,
            "price": exc.price,
            "action": exc.action,
        },
    )


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
