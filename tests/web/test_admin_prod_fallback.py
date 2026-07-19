"""The require_real_admin dev-tenant fallback must never apply in production.

Defense-in-depth behind the auth gate: if an unauthenticated request ever
reaches an admin endpoint in production (new exempt path, middleware reorder),
the sessionless fallback to the dev-tenant admin account must not grant access.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Account, Base
import core.user  # noqa: F401 — registers the user_profile table on Base
from web.routers.credits import require_real_admin


class _FakeRequest:
    def __init__(self, session: dict | None = None):
        self.scope = {"session": session} if session is not None else {}


@pytest.fixture
def db_session():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    # Dev tenant (profile 1) is an admin account — the fallback target.
    s.add(Account(id=1, email="admin@x.c", is_admin=True, profile_id=1,
                  created_at="now", credit_balance=0, credit_rate=0.0))
    s.commit()
    yield s
    s.close()


def test_dev_fallback_grants_admin_outside_production(monkeypatch, db_session):
    monkeypatch.delenv("APP_ENV", raising=False)
    acct = require_real_admin(_FakeRequest(), db_session)
    assert acct.is_admin


def test_no_session_in_production_is_403(monkeypatch, db_session):
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(HTTPException) as exc:
        require_real_admin(_FakeRequest(), db_session)
    assert exc.value.status_code == 403


def test_real_admin_session_still_works_in_production(monkeypatch, db_session):
    monkeypatch.setenv("APP_ENV", "production")
    acct = require_real_admin(_FakeRequest({"account_id": 1}), db_session)
    assert acct.is_admin
