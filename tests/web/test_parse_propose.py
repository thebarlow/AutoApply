"""Tests for POST /api/config/profiles/{id}/parse/propose (Task 5).

The test monkeypatches User.from_markdown / User.from_pdf so no real LLM runs.
"""
from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db, Base
from core.user import User as UserProfileModel
from web.main import app


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def a_profile_with_resume(client, db_session, tmp_path):
    """Create a profile row whose data references a tmp .md file.

    Returns the profile id (will be 1 in a fresh in-memory db, which matches
    the dev auth stub's current_profile_id → 1).
    """
    md_file = tmp_path / "resume.md"
    md_file.write_text("# Ada Resume\nPython developer.", encoding="utf-8")
    resp = client.post("/api/config/profiles", json={"name": "Ada"})
    assert resp.status_code == 200
    profile_id = resp.json()["id"]
    # Write resume_path into the profile's data column directly.
    row = db_session.query(UserProfileModel).filter_by(id=profile_id).first()
    existing = json.loads(row.data) if row.data else {}
    existing["resume_path"] = str(md_file)
    row.data = json.dumps(existing)
    db_session.commit()
    return profile_id


def _profile_tree_section_names(db_session, profile_id: int) -> list[str]:
    """Return the names of all sections currently in the stored profile tree."""
    row = db_session.query(UserProfileModel).filter_by(id=profile_id).first()
    if not row or not row.data:
        return []
    data = json.loads(row.data)
    tree_raw = data.get("profile_tree")
    if not tree_raw:
        return []
    from core.profile_tree import RootNode
    root = RootNode.model_validate(tree_raw)
    return [s.name for s in root.children]


# ---------------------------------------------------------------------------
# Fake parse dict used by monkeypatched from_markdown / from_pdf
# ---------------------------------------------------------------------------

_FAKE_PARSE = {
    "first_name": "Ada",
    "last_name": "Lovelace",
    "skills": ["Python", "Math"],
    "work_history": [{"company": "Acme", "title": "Eng", "start": "", "end": "", "summary": ""}],
    "extra_sections": [
        {
            "name": "Certifications",
            "kind": "list",
            "entries": [{"fields": [{"label": "Name", "value": "AWS"}]}],
        },
    ],
}


def test_propose_returns_builtin_and_novel(client, db_session, monkeypatch, a_profile_with_resume):
    """Endpoint returns sections of both origins and doesn't persist anything."""
    monkeypatch.setattr(
        "core.user.User.from_pdf",
        classmethod(lambda cls, b, db, profile_id=None: _FAKE_PARSE),
    )
    monkeypatch.setattr(
        "core.user.User.from_markdown",
        classmethod(lambda cls, t, db, profile_id=None: _FAKE_PARSE),
    )
    r = client.post(f"/api/config/profiles/{a_profile_with_resume}/parse/propose")
    assert r.status_code == 200, r.text
    body = r.json()

    origins = {s["origin"] for s in body["sections"]}
    assert origins == {"builtin", "novel"}

    novel_sections = [s for s in body["sections"] if s["origin"] == "novel"]
    assert len(novel_sections) == 1
    novel = novel_sections[0]
    assert novel["name"] == "Certifications"
    assert novel["kind"] == "list"
    assert "add" in novel["allowed_actions"]
    assert "merge" in novel["allowed_actions"]

    # Nothing persisted — Certifications must NOT appear in the stored tree.
    assert _profile_tree_section_names(db_session, a_profile_with_resume).count("Certifications") == 0


def test_propose_onboarding_flag(client, db_session, monkeypatch, a_profile_with_resume):
    """is_onboarding=True when the stored profile has no populated built-in sections."""
    monkeypatch.setattr(
        "core.user.User.from_markdown",
        classmethod(lambda cls, t, db, profile_id=None: _FAKE_PARSE),
    )
    monkeypatch.setattr(
        "core.user.User.from_pdf",
        classmethod(lambda cls, b, db, profile_id=None: _FAKE_PARSE),
    )
    r = client.post(f"/api/config/profiles/{a_profile_with_resume}/parse/propose")
    assert r.status_code == 200
    assert r.json()["is_onboarding"] is True


def test_propose_404_wrong_profile(client, db_session, a_profile_with_resume):
    """A profile id that doesn't match the caller returns 404."""
    r = client.post("/api/config/profiles/9999/parse/propose")
    assert r.status_code == 404


def test_propose_400_no_resume(client, db_session):
    """A profile with no resume_path returns 400."""
    resp = client.post("/api/config/profiles", json={"name": "Empty"})
    assert resp.status_code == 200
    profile_id = resp.json()["id"]
    r = client.post(f"/api/config/profiles/{profile_id}/parse/propose")
    assert r.status_code == 400


# Fake parse dict that includes both work_history (→ experience) and education
_FAKE_PARSE_WITH_EDU = {
    "first_name": "Ada",
    "last_name": "Lovelace",
    "skills": ["Python", "Math"],
    "work_history": [{"company": "Acme", "title": "Eng", "start": "", "end": "", "summary": ""}],
    "education": [{"institution": "MIT", "degree": "BS", "field": "CS", "start": "", "end": ""}],
    "extra_sections": [],
}


def test_propose_prechecks_tailored_roles(client, db_session, monkeypatch, a_profile_with_resume):
    """Experience row has customize=True + non-empty prompt; education has customize=False."""
    monkeypatch.setattr(
        "core.user.User.from_pdf",
        classmethod(lambda cls, b, db, profile_id=None: _FAKE_PARSE_WITH_EDU),
    )
    monkeypatch.setattr(
        "core.user.User.from_markdown",
        classmethod(lambda cls, t, db, profile_id=None: _FAKE_PARSE_WITH_EDU),
    )
    r = client.post(f"/api/config/profiles/{a_profile_with_resume}/parse/propose")
    assert r.status_code == 200, r.text
    rows = {s["builtin_role"]: s for s in r.json()["sections"] if s["origin"] == "builtin"}

    assert "experience" in rows, "expected experience row"
    assert rows["experience"]["customize"] is True
    assert rows["experience"]["prompt"], "expected non-empty prompt for experience"

    assert "education" in rows, "expected education row"
    assert rows["education"]["customize"] is False
