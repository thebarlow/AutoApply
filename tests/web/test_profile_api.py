import io
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db
from db.models import Base, Config, UserProfileModel
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


EMPTY_DATA = json.dumps({
    "email": "", "phone": "", "location": "", "skills": [],
    "work_history": [], "education": [], "target_salary_min": None,
    "target_salary_max": None, "target_roles": [], "resume_path": "",
})


def test_get_profiles_empty(client):
    resp = client.get("/api/config/profiles")
    assert resp.status_code == 200
    data = resp.json()
    assert data["profiles"] == []
    assert data["active_id"] is None


def test_post_profile_creates_row(client, db_session):
    resp = client.post("/api/config/profiles", json={"name": "Software Engineer"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Software Engineer"
    assert "id" in data
    assert db_session.query(UserProfileModel).count() == 1


def test_get_profile_by_id(client, db_session):
    db_session.add(UserProfileModel(name="Data Engineer", data=EMPTY_DATA))
    db_session.commit()
    row = db_session.query(UserProfileModel).first()

    resp = client.get(f"/api/config/profiles/{row.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Data Engineer"
    assert "data" in data


def test_get_profile_by_id_not_found(client):
    resp = client.get("/api/config/profiles/999")
    assert resp.status_code == 404


def test_put_profile_updates_data(client, db_session):
    db_session.add(UserProfileModel(name="Old Name", data=EMPTY_DATA))
    db_session.commit()
    row = db_session.query(UserProfileModel).first()

    body = {
        "name": "New Name",
        "data": {
            "email": "new@example.com", "phone": "", "location": "",
            "skills": ["Python"], "work_history": [], "education": [],
            "target_salary_min": None, "target_salary_max": None,
            "target_roles": [], "resume_path": "",
        },
    }
    resp = client.put(f"/api/config/profiles/{row.id}", json=body)
    assert resp.status_code == 200

    db_session.refresh(row)
    assert row.name == "New Name"
    assert json.loads(row.data)["email"] == "new@example.com"


def test_delete_profile(client, db_session):
    db_session.add(UserProfileModel(name="To Delete", data=EMPTY_DATA))
    db_session.commit()
    row = db_session.query(UserProfileModel).first()

    resp = client.delete(f"/api/config/profiles/{row.id}")
    assert resp.status_code == 204
    assert db_session.query(UserProfileModel).count() == 0


def test_put_active_sets_config(client, db_session):
    db_session.add(UserProfileModel(name="Profile A", data=EMPTY_DATA))
    db_session.commit()
    row = db_session.query(UserProfileModel).first()

    resp = client.put("/api/config/profiles/active", json={"active_id": row.id})
    assert resp.status_code == 200

    cfg = db_session.query(Config).filter_by(key="active_profile_id").first()
    assert cfg is not None
    assert int(cfg.value) == row.id


def test_put_active_profile_not_found(client):
    resp = client.put("/api/config/profiles/active", json={"active_id": 999})
    assert resp.status_code == 404


def test_parse_endpoint_md_returns_profile_dict(client, monkeypatch):
    import core.profile_parser as pp
    monkeypatch.setattr(pp, "markdown_to_profile", lambda text: {
        "name": "Test User", "email": "t@t.com", "phone": "", "location": "",
        "skills": ["Python"], "work_history": [], "education": [],
        "target_salary_min": None, "target_salary_max": None,
        "target_roles": [], "resume_path": "",
    })

    resp = client.post(
        "/api/config/profile/parse",
        files={"file": ("resume.md", io.BytesIO(b"# Test"), "text/plain")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "t@t.com"
    assert data["skills"] == ["Python"]


def test_parse_endpoint_pdf_calls_pdf_to_markdown(client, monkeypatch):
    import core.profile_parser as pp
    pdf_calls = []

    def fake_pdf_to_md(b):
        pdf_calls.append(b)
        return "# Resume"

    monkeypatch.setattr(pp, "pdf_to_markdown", fake_pdf_to_md)
    monkeypatch.setattr(pp, "markdown_to_profile", lambda t: {
        "name": "", "email": "", "phone": "", "location": "",
        "skills": [], "work_history": [], "education": [],
        "target_salary_min": None, "target_salary_max": None,
        "target_roles": [], "resume_path": "",
    })

    resp = client.post(
        "/api/config/profile/parse",
        files={"file": ("resume.pdf", io.BytesIO(b"%PDF-fake"), "application/pdf")},
    )
    assert resp.status_code == 200
    assert len(pdf_calls) == 1


def test_serve_profile_file_pdf_not_set(client, db_session):
    from db.models import UserProfileModel
    data = {"resume_path": "", "md_path": ""}
    row = UserProfileModel(name="Test", data=json.dumps(data))
    db_session.add(row)
    db_session.commit()

    resp = client.get(f"/api/config/profiles/{row.id}/file?type=pdf")
    assert resp.status_code == 404


def test_serve_profile_file_md_not_set(client, db_session):
    from db.models import UserProfileModel
    data = {"resume_path": "", "md_path": ""}
    row = UserProfileModel(name="Test", data=json.dumps(data))
    db_session.add(row)
    db_session.commit()

    resp = client.get(f"/api/config/profiles/{row.id}/file?type=md")
    assert resp.status_code == 404


def test_serve_profile_file_pdf_missing_on_disk(client, db_session):
    from db.models import UserProfileModel
    data = {"resume_path": "/nonexistent/resume.pdf", "md_path": ""}
    row = UserProfileModel(name="Test", data=json.dumps(data))
    db_session.add(row)
    db_session.commit()

    resp = client.get(f"/api/config/profiles/{row.id}/file?type=pdf")
    assert resp.status_code == 404


def test_serve_profile_file_md_missing_on_disk(client, db_session):
    from db.models import UserProfileModel
    data = {"resume_path": "", "md_path": "/nonexistent/resume.md"}
    row = UserProfileModel(name="Test", data=json.dumps(data))
    db_session.add(row)
    db_session.commit()

    resp = client.get(f"/api/config/profiles/{row.id}/file?type=md")
    assert resp.status_code == 404


def test_serve_profile_file_profile_not_found(client, db_session):
    resp = client.get("/api/config/profiles/99999/file?type=pdf")
    assert resp.status_code == 404


def test_serve_profile_file_pdf_ok(client, db_session, tmp_path):
    from db.models import UserProfileModel
    pdf_file = tmp_path / "resume.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 fake")
    data = {"resume_path": str(pdf_file), "md_path": ""}
    row = UserProfileModel(name="Test", data=json.dumps(data))
    db_session.add(row)
    db_session.commit()

    resp = client.get(f"/api/config/profiles/{row.id}/file?type=pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"


def test_serve_profile_file_md_ok(client, db_session, tmp_path):
    from db.models import UserProfileModel
    md_file = tmp_path / "resume.md"
    md_file.write_text("# Resume\nHello", encoding="utf-8")
    data = {"resume_path": "", "md_path": str(md_file)}
    row = UserProfileModel(name="Test", data=json.dumps(data))
    db_session.add(row)
    db_session.commit()

    resp = client.get(f"/api/config/profiles/{row.id}/file?type=md")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]


def test_serve_profile_file_invalid_type(client, db_session):
    from db.models import UserProfileModel
    data = {"resume_path": "", "md_path": ""}
    row = UserProfileModel(name="Test", data=json.dumps(data))
    db_session.add(row)
    db_session.commit()

    resp = client.get(f"/api/config/profiles/{row.id}/file?type=xml")
    assert resp.status_code == 400
