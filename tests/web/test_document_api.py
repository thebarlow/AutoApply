import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db, Base, Document
from core.job import Job, JobState
import core.user  # noqa: F401


@pytest.fixture
def db_session():
    import core.job   # noqa: F401
    import core.user  # noqa: F401
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session):
    from web.main import app
    from web.tenancy import current_profile_id
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[current_profile_id] = lambda: 1
    yield TestClient(app)
    app.dependency_overrides.clear()


def _job(db, key="k1"):
    j = Job(job_key=key, profile_id=1, source="x", title="t", company="Acme", url=f"u/{key}", state=JobState.NEW.value)
    db.add(j)
    db.commit()
    return j


def _resume_payload():
    return {
        "header": {"name": "Jane Doe", "email": "j@x.com"},
        "education": [],
        "profile_summary": "hi",
        "experience": [{"company": "Acme", "title": "Eng", "start": "2020", "end": "2024", "description": "- x"}],
        "projects": [],
        "skills": [{"category": "Lang", "items": ["Python"]}],
        "section_order": [],
    }


def test_get_document_404_when_absent(client, db_session):
    _job(db_session)
    assert client.get("/api/jobs/k1/resume/document").status_code == 404


def test_put_document_persists_and_returns(client, db_session, monkeypatch):
    import core.job as jobmod
    monkeypatch.setattr(jobmod.Job, "generate_resume_pdf", lambda self, t, db, max_pages=1: None)
    monkeypatch.setattr(jobmod.Job, "write_resume_markdown", lambda self, doc: None)
    _job(db_session)
    r = client.put("/api/jobs/k1/resume/document", json=_resume_payload())
    assert r.status_code == 200
    assert r.json()["profile_summary"] == "hi"
    assert r.json()["section_order"][0] == "Profile"        # recomputed
    row = Document.fetch(db_session, "k1", "resume", profile_id=1)
    assert row is not None and '"hi"' in row.structured_json


def test_get_document_after_put(client, db_session, monkeypatch):
    import core.job as jobmod
    monkeypatch.setattr(jobmod.Job, "generate_resume_pdf", lambda self, t, db, max_pages=1: None)
    monkeypatch.setattr(jobmod.Job, "write_resume_markdown", lambda self, doc: None)
    _job(db_session)
    client.put("/api/jobs/k1/resume/document", json=_resume_payload())
    g = client.get("/api/jobs/k1/resume/document")
    assert g.status_code == 200 and g.json()["experience"][0]["company"] == "Acme"


def test_put_document_rejects_malformed(client, db_session):
    _job(db_session)
    bad = {"experience": "not-a-list"}
    assert client.put("/api/jobs/k1/resume/document", json=bad).status_code == 400


def test_markdown_put_route_is_gone(client, db_session):
    # 405 because the GET .../markdown route still exists; only the PUT handler was removed.
    _job(db_session)
    assert client.put("/api/jobs/k1/resume/markdown", content=b"# x").status_code == 405


def test_put_cover_document_persists(client, db_session, monkeypatch):
    import core.job as jobmod
    monkeypatch.setattr(jobmod.Job, "write_cover_markdown", lambda self, doc: None)
    monkeypatch.setattr(jobmod.Job, "generate_cover_pdf", lambda self, t, db: None)
    _job(db_session, key="kc")
    payload = {"header": {"name": "Jane Doe", "email": "j@x.com"}, "body": "Cover body text.", "signoff": {}}
    r = client.put("/api/jobs/kc/cover/document", json=payload)
    assert r.status_code == 200
    assert r.json()["body"] == "Cover body text."
    row = Document.fetch(db_session, "kc", "cover", profile_id=1)
    assert row is not None and "Cover body text." in row.structured_json


def test_put_resume_tree_v1_roundtrip(client, db_session, monkeypatch):
    import core.job as jobmod
    monkeypatch.setattr(jobmod.Job, "generate_resume_pdf", lambda self, t, db, max_pages=1: None)
    monkeypatch.setattr(jobmod.Job, "write_resume_markdown", lambda self, doc: None)
    _job(db_session)
    payload = {
        "schema": "tree-v1", "type": "root", "id": "r",
        "children": [
            {"type": "section", "id": "s1", "name": "Summary", "role": "summary",
             "order": 0, "visible": True, "locked": False, "children": [
                {"type": "field", "id": "f1", "name": "Summary", "key": "summary",
                 "order": 0, "visible": True, "kind": "markdown",
                 "value": "Edited summary text.", "llm_output": True}]},
        ],
    }
    r = client.put("/api/jobs/k1/resume/document", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body.get("schema") == "tree-v1"
    row = Document.fetch(db_session, "k1", "resume", profile_id=1)
    assert row is not None
    from core.resume_document_io import is_tree_v1
    assert is_tree_v1(row.structured_json)
    assert "Edited summary text." in row.structured_json
