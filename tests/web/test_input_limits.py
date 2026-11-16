"""Input-size caps (audit H3): oversize tenant input is refused with 413/422."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core import limits
from db.database import Base, get_db
from web.main import app


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session):
    from web.auth.ext_token import bearer_or_session_profile
    from web.tenancy import current_profile_id
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[current_profile_id] = lambda: 1
    app.dependency_overrides[bearer_or_session_profile] = lambda: 1
    yield TestClient(app)
    app.dependency_overrides.clear()


def _job(**kw):
    return {"source": "linkedin", "job_key": "k1", "title": "Eng", "company": "Acme",
            "url": "https://example.com/1", "description": "Do stuff.", **kw}


def _big(n: int) -> str:
    return "x" * (n + 1)


def test_stage_job_description_over_cap_is_422(client):
    r = client.post("/api/scraper/stage-job",
                    json=_job(description=_big(limits.MAX_JOB_DESCRIPTION)))
    assert r.status_code == 422


def test_scrape_selected_description_over_cap_is_422(client):
    r = client.post("/api/scraper/scrape-selected",
                    json={"jobs": [_job(description=_big(limits.MAX_JOB_DESCRIPTION))]})
    assert r.status_code == 422


def test_job_fields_patch_description_over_cap_is_422(client):
    r = client.patch("/api/jobs/k1/fields",
                     json={"description": _big(limits.MAX_JOB_DESCRIPTION)})
    assert r.status_code == 422


def test_prompt_content_over_cap_is_422(client):
    r = client.put("/api/prompts/1/resume",
                   json={"content": _big(limits.MAX_PROMPT_CONTENT)})
    assert r.status_code == 422


def test_profile_put_over_cap_is_413(client):
    r = client.put("/api/config/profiles/1",
                   json={"name": "x", "data": {"hero": _big(limits.MAX_PROFILE_JSON)}})
    assert r.status_code == 413
    assert r.json()["error"] == "payload_too_large"


def test_profile_tree_put_over_cap_is_413(client):
    r = client.put("/api/config/profiles/1/tree",
                   json={"tree": {"blob": _big(limits.MAX_PROFILE_JSON)}})
    assert r.status_code == 413


def test_document_put_over_cap_is_413(client):
    r = client.put("/api/jobs/k1/resume/document",
                   json={"blob": _big(limits.MAX_DOCUMENT_JSON)})
    assert r.status_code == 413


def test_feedback_note_over_cap_is_422(client):
    r = client.post("/api/jobs/k1/resume/feedback",
                    json={"notes": [{"section": "s", "note": _big(limits.MAX_FEEDBACK_NOTE)}]})
    assert r.status_code == 422


def test_feedback_too_many_notes_is_422(client):
    notes = [{"note": "n"}] * (limits.MAX_FEEDBACK_NOTES + 1)
    r = client.post("/api/jobs/k1/resume/feedback", json={"notes": notes})
    assert r.status_code == 422


def test_section_prompt_draft_over_cap_is_422(client):
    r = client.post("/api/config/section-prompt/draft",
                    json={"purpose": _big(limits.MAX_SECTION_PROMPT_FIELD)})
    assert r.status_code == 422


def test_application_plan_essay_label_over_cap_is_422(client):
    r = client.post("/api/scraper/jobs/k1/application-plan",
                    json={"enumerated_fields": [
                        {"field_id": "q1", "label": _big(limits.MAX_ESSAY_LABEL)}]})
    assert r.status_code == 422


def test_skills_over_cap_is_422(client):
    r = client.post("/api/skills/profile", json={"skills": [_big(limits.MAX_LABEL)]})
    assert r.status_code == 422


def test_body_over_content_length_cap_is_413(client):
    body = b"{" + b" " * limits.MAX_REQUEST_BODY_BYTES + b"}"
    r = client.post("/api/scraper/stage-job", content=body,
                    headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert r.json()["error"] == "payload_too_large"


def test_chunked_body_over_cap_is_413(client, monkeypatch):
    monkeypatch.setattr(limits, "MAX_REQUEST_BODY_BYTES", 1000)

    def gen():
        for _ in range(10):
            yield b" " * 500

    r = client.post("/api/scraper/stage-job", content=gen(),
                    headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_upload_over_cap_is_413_without_full_buffer(client, monkeypatch):
    # Shrink the file cap but keep the raw-body cap roomy so the endpoint's own
    # chunked read is what refuses it.
    monkeypatch.setattr(limits, "MAX_UPLOAD_BYTES", 100)
    monkeypatch.setattr(limits, "MULTIPART_OVERHEAD_BYTES", 10_000)
    r = client.post("/api/config/profile/upload",
                    files={"file": ("r.md", b"a" * 500, "text/markdown")})
    assert r.status_code == 413


def test_upload_body_over_raw_cap_is_413(client, monkeypatch):
    monkeypatch.setattr(limits, "MAX_UPLOAD_BYTES", 100)
    monkeypatch.setattr(limits, "MULTIPART_OVERHEAD_BYTES", 100)
    r = client.post("/api/config/profile/upload",
                    files={"file": ("r.md", b"a" * 5_000, "text/markdown")})
    assert r.status_code == 413


def test_upload_within_cap_succeeds(client, monkeypatch, tmp_path):
    import web.routers.config as cfg
    monkeypatch.setattr(cfg, "_PROFILES_DIR", tmp_path)
    r = client.post("/api/config/profile/upload",
                    files={"file": ("r.md", b"# Resume", "text/markdown")})
    assert r.status_code == 200
