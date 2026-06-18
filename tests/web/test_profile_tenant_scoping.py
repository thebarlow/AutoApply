"""Profile endpoints must honor the tenancy seam (current_profile_id).

Regression tests for a live cross-tenant bug: `/api/setup-status` and the
`/api/config/profiles*` endpoints resolved the active profile via the legacy
`Config['dev_tenant_id']` dev stub / `User.first()` / raw URL id instead of the
logged-in account's tenant. In production every user was served profile 1's
data (no onboarding) and could read/edit/delete other tenants' profiles.
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
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[current_profile_id] = lambda: caller_profile_id
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_setup_status_uses_caller_profile_not_profile_one(two_tenants):
    """A new tenant (profile 2, empty) must see resume_parsed=False even though
    profile 1 has a parsed resume."""
    client = _client(two_tenants, caller_profile_id=2)
    r = client.get("/api/setup-status")
    assert r.status_code == 200
    assert r.json()["resume_parsed"] is False


def test_get_profile_denies_other_tenant(two_tenants):
    """Tenant 2 must not be able to read tenant 1's profile by URL id."""
    client = _client(two_tenants, caller_profile_id=2)
    r = client.get("/api/config/profiles/1")
    assert r.status_code == 404


def test_update_profile_denies_other_tenant(two_tenants):
    """Tenant 2 must not be able to overwrite tenant 1's profile."""
    client = _client(two_tenants, caller_profile_id=2)
    r = client.put(
        "/api/config/profiles/1",
        json={"name": "Hacked", "data": {"skills": []}},
    )
    assert r.status_code == 404
    assert two_tenants.query(User).filter_by(id=1).first().name == "Admin"


def test_delete_profile_denies_other_tenant(two_tenants):
    """Tenant 2 must not be able to delete tenant 1's profile."""
    client = _client(two_tenants, caller_profile_id=2)
    r = client.delete("/api/config/profiles/1")
    assert r.status_code == 404
    assert two_tenants.query(User).filter_by(id=1).first() is not None


def test_list_profiles_only_returns_caller_tenant(two_tenants):
    """The profile list must not leak other tenants' profiles."""
    client = _client(two_tenants, caller_profile_id=2)
    r = client.get("/api/config/profiles")
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()["profiles"]]
    assert ids == [2]


def test_serve_profile_file_denies_other_tenant(two_tenants, tmp_path):
    """Tenant 2 must not be able to download tenant 1's resume file.

    Give profile 1 a real, existing resume file so the endpoint would otherwise
    return 200 — proving the 404 comes from the tenant guard, not a missing file.
    """
    pdf = tmp_path / "resume.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    row = two_tenants.query(User).filter_by(id=1).first()
    row.data = json.dumps({"skills": ["Python"], "resume_path": str(pdf)})
    two_tenants.commit()

    client = _client(two_tenants, caller_profile_id=2)
    r = client.get("/api/config/profiles/1/file?type=pdf")
    assert r.status_code == 404


def test_parse_profile_denies_other_tenant(two_tenants):
    """Tenant 2 must not be able to parse (and mutate/charge) tenant 1's profile."""
    client = _client(two_tenants, caller_profile_id=2)
    r = client.post("/api/config/profiles/1/parse")
    assert r.status_code == 404


def test_get_prompt_denies_other_tenant(two_tenants):
    """Tenant 2 must not read tenant 1's prompt overrides."""
    client = _client(two_tenants, caller_profile_id=2)
    r = client.get("/api/prompts/1/scoring")
    assert r.status_code == 404


def test_put_prompt_denies_other_tenant(two_tenants):
    """Tenant 2 must not overwrite tenant 1's prompt overrides."""
    from db.database import Prompt
    client = _client(two_tenants, caller_profile_id=2)
    r = client.put("/api/prompts/1/scoring", json={"content": "pwned " * 20})
    assert r.status_code == 404
    assert two_tenants.query(Prompt).filter_by(profile_id=1, type_key="scoring").first() is None


def test_reset_prompt_denies_other_tenant(two_tenants):
    """Tenant 2 must not reset tenant 1's prompt overrides.

    Seed a prompt default so the endpoint would otherwise succeed — proving the
    404 comes from the tenant guard, not a missing default.
    """
    from db.database import PromptDefault
    two_tenants.add(PromptDefault(type_key="scoring", content="default scoring prompt"))
    two_tenants.commit()

    client = _client(two_tenants, caller_profile_id=2)
    r = client.post("/api/prompts/1/scoring/reset")
    assert r.status_code == 404


def test_reset_profile_denies_other_tenant(two_tenants):
    """Tenant 2 must not be able to reset tenant 1's profile."""
    client = _client(two_tenants, caller_profile_id=2)
    r = client.post("/api/config/profiles/1/reset")
    assert r.status_code == 404
    assert json.loads(two_tenants.query(User).filter_by(id=1).first().data) == {"skills": ["Python"]}
