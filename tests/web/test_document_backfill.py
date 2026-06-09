import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db, Base, Document
from core.job import Job, JobState
import core.user  # noqa: F401


@pytest.fixture
def db_session():
    import core.job  # noqa: F401
    import core.user  # noqa: F401
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
    from web.main import app
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _job(db, key="bf1"):
    j = Job(job_key=key, source="x", title="t", company="Acme", url=f"u/{key}", state=JobState.NEW.value)
    db.add(j)
    db.commit()
    return j


def test_get_document_backfills_from_markdown(client, db_session, tmp_path, monkeypatch):
    import web.routers.jobs as jobs_mod
    out_dir = tmp_path
    monkeypatch.setattr(jobs_mod, "_OUTPUTS_DIR", out_dir, raising=False)
    (out_dir / "bf1_resume.md").write_text(
        "---\nname: Jane Doe\nemail: jane@x.com\n---\n## Profile\n\nEngineer who ships.\n",
        encoding="utf-8",
    )
    _job(db_session)
    assert Document.fetch(db_session, "bf1", "resume") is None

    r = client.get("/api/jobs/bf1/resume/document")
    assert r.status_code == 200
    assert r.json()["profile_summary"] == "Engineer who ships."
    assert r.json()["header"]["name"] == "Jane Doe"
    assert Document.fetch(db_session, "bf1", "resume") is not None


def test_get_document_404_when_no_row_and_no_markdown(client, db_session, tmp_path, monkeypatch):
    import web.routers.jobs as jobs_mod
    monkeypatch.setattr(jobs_mod, "_OUTPUTS_DIR", tmp_path, raising=False)
    _job(db_session, key="bf2")
    assert client.get("/api/jobs/bf2/resume/document").status_code == 404
