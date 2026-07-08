"""Per-tenant config endpoints must not leak values across profiles.

Regression coverage for Task 4 of the config->profile_config tenancy split:
scoring/templates/sources/search/job_searches endpoints previously read/wrote
config via a global key, so all tenants shared one set of values.
"""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db, Base
from core.user import User
from web.main import app
from web.tenancy import current_profile_id


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def two_tenants(db_session):
    """Profile 1 has a parsed resume (the legacy migrated data); profile 2 is empty."""
    db_session.add(User(id=1, name="Admin", data=json.dumps({"skills": ["Python"]})))
    db_session.add(User(id=2, name="New User", data="{}"))
    db_session.commit()
    return db_session


def _client(db_session, caller_profile_id):
    # NOTE: app.dependency_overrides is global on the `app` object, not per
    # TestClient instance — the override is resolved at request time, not at
    # client-construction time. So each returned client re-applies its own
    # profile_id override immediately before issuing the request, letting two
    # "tenant" clients be interleaved safely within one test.
    class _TenantClient(TestClient):
        def request(self, *args, **kwargs):
            app.dependency_overrides[get_db] = lambda: db_session
            app.dependency_overrides[current_profile_id] = lambda: caller_profile_id
            return super().request(*args, **kwargs)

    return _TenantClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_scoring_is_per_tenant(two_tenants):
    c1 = _client(two_tenants, caller_profile_id=1)
    c2 = _client(two_tenants, caller_profile_id=2)
    c1.put("/api/config/scoring", json={
        "w1": 0.7, "w2": 0.3,
        "auto_reject_threshold": 0.2, "auto_approve_threshold": 0.9,
    })
    # Tenant 2 still sees defaults, not tenant 1's values.
    got = c2.get("/api/config/scoring").json()
    assert got["w1"] == 0.5
    assert got["auto_reject_threshold"] == 0.3  # PROFILE_CONFIG_DEFAULTS


def test_contact_links_are_per_tenant(two_tenants):
    c1 = _client(two_tenants, caller_profile_id=1)
    c2 = _client(two_tenants, caller_profile_id=2)
    c1.put("/api/config/templates", json={
        "resume_template_path": "generator/resume_template.html",
        "cover_template_path": "generator/cover_template.html",
        "resume_prompt_template": "", "cover_prompt_template": "",
        "github": "gh-tenant-1", "linkedin": "", "website": "",
    })
    assert c1.get("/api/config/templates").json()["github"] == "gh-tenant-1"
    assert c2.get("/api/config/templates").json()["github"] == ""
