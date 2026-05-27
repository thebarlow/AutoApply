import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db, Base
from web.main import app
from core.user import User


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


@pytest.fixture
def client(db_session, monkeypatch):
    app.dependency_overrides[get_db] = lambda: db_session
    # Stub render_pdf so the test doesn't need Playwright/pandoc
    def _fake_render_pdf(md_path, pdf_path, template_path, max_pages=None, meta=None):
        pdf_path.write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr("web.routers.config.render_pdf", _fake_render_pdf)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_export_master_returns_pdf(client, db_session):
    user = User(name="Test", data='{"first_name":"Jane","last_name":"Doe","email":"jane@example.com","skills":["Python"],"work_history":[],"education":[],"projects":[]}')
    db_session.add(user)
    db_session.commit()

    resp = client.post("/api/profile/export-master")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "master_resume.pdf" in resp.headers.get("content-disposition", "")


def test_export_master_no_profile_returns_404(client):
    resp = client.post("/api/profile/export-master")
    assert resp.status_code == 404
