import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import StreamingResponse

import web.auth.middleware as gate_mod

_REAL_ACCOUNT_STATE = gate_mod._account_state  # captured before autouse patching
from web.auth.middleware import AuthGateMiddleware


@pytest.fixture(autouse=True)
def _account_state(monkeypatch):
    """Hermetic account lookup: tests flip ``states[account_id]`` as needed."""
    states: dict = {}
    monkeypatch.setattr(gate_mod, "_account_state",
                        lambda aid: states.get(aid, gate_mod.OK))
    return states


def _app(monkeypatch, production: bool):
    if production:
        monkeypatch.setenv("APP_ENV", "production")
    else:
        monkeypatch.delenv("APP_ENV", raising=False)

    app = FastAPI()
    app.add_middleware(AuthGateMiddleware)
    app.add_middleware(SessionMiddleware, secret_key="test")  # outermost: runs first

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/secret")
    def secret():
        return {"ok": True}

    @app.get("/api/events")
    async def events():
        async def gen():
            yield "a"
            yield "b"
        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post("/login")
    def login(request: __import__("fastapi").Request):
        request.session["account_id"] = 1
        return {"ok": True}

    return app


def test_noop_when_not_production(monkeypatch):
    client = TestClient(_app(monkeypatch, production=False))
    assert client.get("/api/secret").status_code == 200


def test_blocks_unauthenticated_api_in_production(monkeypatch):
    client = TestClient(_app(monkeypatch, production=True))
    assert client.get("/api/secret").status_code == 401


def test_health_exempt_in_production(monkeypatch):
    client = TestClient(_app(monkeypatch, production=True))
    assert client.get("/health").status_code == 200


def test_authenticated_api_allowed(monkeypatch):
    client = TestClient(_app(monkeypatch, production=True))
    client.post("/login")
    assert client.get("/api/secret").status_code == 200


def test_sse_streams_for_authenticated_user(monkeypatch):
    client = TestClient(_app(monkeypatch, production=True))
    client.post("/login")
    r = client.get("/api/events")
    assert r.status_code == 200
    assert r.text == "ab"


def test_banned_session_rejected_and_cleared(monkeypatch, _account_state):
    client = TestClient(_app(monkeypatch, production=True))
    client.post("/login")
    assert client.get("/api/secret").status_code == 200
    _account_state[1] = gate_mod.BANNED
    r = client.get("/api/secret")
    assert r.status_code == 401
    assert r.json()["detail"] == "account suspended"
    # Session was cleared: un-banning does not resurrect the old cookie.
    _account_state[1] = gate_mod.OK
    assert client.get("/api/secret").status_code == 401


def test_missing_account_session_rejected(monkeypatch, _account_state):
    client = TestClient(_app(monkeypatch, production=True))
    client.post("/login")
    _account_state[1] = gate_mod.MISSING
    assert client.get("/api/secret").status_code == 401


def test_lookup_failure_fails_closed(monkeypatch):
    def boom(_aid):
        raise RuntimeError("db down")
    client = TestClient(_app(monkeypatch, production=True))
    client.post("/login")
    monkeypatch.setattr(gate_mod, "_account_state", boom)
    assert client.get("/api/secret").status_code == 503


def test_banned_session_passes_in_dev(monkeypatch, _account_state):
    _account_state[1] = gate_mod.BANNED
    client = TestClient(_app(monkeypatch, production=False))
    client.post("/login")
    assert client.get("/api/secret").status_code == 200


def test_account_state_reads_banned_column(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import db.database as dbmod
    from db.database import Account, Base

    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    for aid, banned in ((1, False), (2, True)):
        s.add(Account(id=aid, email=f"a{aid}@x.com", is_admin=False, profile_id=aid,
                      created_at="2026-01-01T00:00:00+00:00", credit_balance=0,
                      credit_rate=1.0, tier="standard", banned=banned))
    s.commit()
    s.close()
    monkeypatch.setattr(dbmod, "SessionLocal", Session)
    real = _REAL_ACCOUNT_STATE
    assert real(1) == gate_mod.OK
    assert real(2) == gate_mod.BANNED
    assert real(99) == gate_mod.MISSING
