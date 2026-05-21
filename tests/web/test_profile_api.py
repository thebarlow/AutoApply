import io
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db
from db.database import Base, Config
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
    from core.user import User
    monkeypatch.setattr(User, "from_markdown", classmethod(lambda cls, text, db: {
        "name": "Test User", "email": "t@t.com", "phone": "", "location": "",
        "skills": ["Python"], "work_history": [], "education": [],
        "target_salary_min": None, "target_salary_max": None,
        "target_roles": [], "resume_path": "", "md_path": "",
    }))

    resp = client.post(
        "/api/config/profile/parse",
        files={"file": ("resume.md", io.BytesIO(b"# Test"), "text/plain")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "t@t.com"
    assert data["skills"] == ["Python"]


def test_parse_endpoint_pdf_calls_pdf_to_markdown(client, monkeypatch):
    from core.user import User
    pdf_calls = []

    def fake_from_pdf(cls, b, db):
        pdf_calls.append(b)
        return {
            "name": "", "email": "", "phone": "", "location": "",
            "skills": [], "work_history": [], "education": [],
            "target_salary_min": None, "target_salary_max": None,
            "target_roles": [], "resume_path": "", "md_path": "",
        }

    monkeypatch.setattr(User, "from_pdf", classmethod(fake_from_pdf))

    resp = client.post(
        "/api/config/profile/parse",
        files={"file": ("resume.pdf", io.BytesIO(b"%PDF-fake"), "application/pdf")},
    )
    assert resp.status_code == 200
    assert len(pdf_calls) == 1


def test_serve_profile_file_pdf_not_set(client, db_session):
    from core.user import User as UserProfileModel
    data = {"resume_path": "", "md_path": ""}
    row = UserProfileModel(name="Test", data=json.dumps(data))
    db_session.add(row)
    db_session.commit()

    resp = client.get(f"/api/config/profiles/{row.id}/file?type=pdf")
    assert resp.status_code == 404


def test_serve_profile_file_md_not_set(client, db_session):
    from core.user import User as UserProfileModel
    data = {"resume_path": "", "md_path": ""}
    row = UserProfileModel(name="Test", data=json.dumps(data))
    db_session.add(row)
    db_session.commit()

    resp = client.get(f"/api/config/profiles/{row.id}/file?type=md")
    assert resp.status_code == 404


def test_serve_profile_file_pdf_missing_on_disk(client, db_session):
    from core.user import User as UserProfileModel
    data = {"resume_path": "/nonexistent/resume.pdf", "md_path": ""}
    row = UserProfileModel(name="Test", data=json.dumps(data))
    db_session.add(row)
    db_session.commit()

    resp = client.get(f"/api/config/profiles/{row.id}/file?type=pdf")
    assert resp.status_code == 404


def test_serve_profile_file_md_missing_on_disk(client, db_session):
    from core.user import User as UserProfileModel
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
    from core.user import User as UserProfileModel
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
    from core.user import User as UserProfileModel
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
    from core.user import User as UserProfileModel
    data = {"resume_path": "", "md_path": ""}
    row = UserProfileModel(name="Test", data=json.dumps(data))
    db_session.add(row)
    db_session.commit()

    resp = client.get(f"/api/config/profiles/{row.id}/file?type=xml")
    assert resp.status_code == 400


def test_parse_endpoint_surfaces_no_provider_error(client, monkeypatch):
    from core.user import User

    def _raise(cls, *_):
        raise RuntimeError("No active LLM provider configured")

    monkeypatch.setattr(User, "from_markdown", classmethod(_raise))

    resp = client.post(
        "/api/config/profile/parse",
        files={"file": ("resume.md", io.BytesIO(b"# Test"), "text/plain")},
    )
    assert resp.status_code == 422
    assert "No active LLM provider" in resp.json()["detail"]


def test_parse_endpoint_surfaces_bad_json_error(client, monkeypatch):
    from core.user import User

    def _raise(cls, *_):
        raise ValueError("LLM returned invalid JSON: ...")

    monkeypatch.setattr(User, "from_markdown", classmethod(_raise))

    resp = client.post(
        "/api/config/profile/parse",
        files={"file": ("resume.md", io.BytesIO(b"# Test"), "text/plain")},
    )
    assert resp.status_code == 422
    assert "LLM returned invalid JSON" in resp.json()["detail"]


def test_get_profile_includes_llm_fields(client, db_session):
    from core.user import User as UserProfileModel
    import json
    data = {
        "email": "", "phone": "", "location": "", "skills": [],
        "work_history": [], "education": [], "target_salary_min": None,
        "target_salary_max": None, "target_roles": [], "resume_path": "",
        "llm_provider_type": "openrouter", "llm_model": "gpt-4o",
    }
    row = UserProfileModel(name="Test", data=json.dumps(data))
    db_session.add(row)
    db_session.commit()

    resp = client.get(f"/api/config/profiles/{row.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["llm_provider_type"] == "openrouter"
    assert body["llm_model"] == "gpt-4o"
    assert body["has_llm_key"] is False


def test_get_profile_has_llm_key_true(client, db_session, monkeypatch, tmp_path):
    import web.routers.config as config_mod
    import json
    from core.user import User as UserProfileModel

    env_file = tmp_path / ".env"
    monkeypatch.setattr(config_mod, "_ENV_PATH", env_file)

    data = {"email": "", "phone": "", "location": "", "skills": [],
            "work_history": [], "education": [], "target_salary_min": None,
            "target_salary_max": None, "target_roles": [], "resume_path": "",
            "llm_provider_type": "anthropic", "llm_model": "claude-3-5-sonnet"}
    row = UserProfileModel(name="Test", data=json.dumps(data))
    db_session.add(row)
    db_session.commit()

    env_file.write_text(f"LLM_KEY_PROFILE_{row.id}=sk-test-key\n")

    resp = client.get(f"/api/config/profiles/{row.id}")
    assert resp.status_code == 200
    assert resp.json()["has_llm_key"] is True


def test_put_profile_writes_llm_key_to_env(client, db_session, monkeypatch, tmp_path):
    import web.routers.config as config_mod
    import json
    from core.user import User as UserProfileModel

    env_file = tmp_path / ".env"
    env_file.write_text("")
    monkeypatch.setattr(config_mod, "_ENV_PATH", env_file)

    row = UserProfileModel(name="Test", data=json.dumps({
        "email": "", "phone": "", "location": "", "skills": [],
        "work_history": [], "education": [], "target_salary_min": None,
        "target_salary_max": None, "target_roles": [], "resume_path": "",
    }))
    db_session.add(row)
    db_session.commit()

    body = {
        "name": "Test",
        "data": {"email": "a@b.com", "llm_provider_type": "openai", "llm_model": "gpt-4o"},
        "llm_api_key": "sk-secret-123",
    }
    resp = client.put(f"/api/config/profiles/{row.id}", json=body)
    assert resp.status_code == 200

    env_content = env_file.read_text()
    assert f"LLM_KEY_PROFILE_{row.id}=sk-secret-123" in env_content


def test_put_profile_empty_llm_key_does_not_write_env(client, db_session, monkeypatch, tmp_path):
    import web.routers.config as config_mod
    import json
    from core.user import User as UserProfileModel

    env_file = tmp_path / ".env"
    env_file.write_text("")
    monkeypatch.setattr(config_mod, "_ENV_PATH", env_file)

    row = UserProfileModel(name="Test", data=json.dumps({
        "email": "", "phone": "", "location": "", "skills": [],
        "work_history": [], "education": [], "target_salary_min": None,
        "target_salary_max": None, "target_roles": [], "resume_path": "",
    }))
    db_session.add(row)
    db_session.commit()

    body = {"name": "Test", "data": {"llm_provider_type": "openai"}, "llm_api_key": ""}
    resp = client.put(f"/api/config/profiles/{row.id}", json=body)
    assert resp.status_code == 200
    assert env_file.read_text() == ""


def test_put_profile_rejects_injected_llm_key(client, db_session, monkeypatch, tmp_path):
    import web.routers.config as config_mod
    import json
    from core.user import User as UserProfileModel

    env_file = tmp_path / ".env"
    env_file.write_text("")
    monkeypatch.setattr(config_mod, "_ENV_PATH", env_file)

    row = UserProfileModel(name="Test", data=json.dumps({
        "email": "", "phone": "", "location": "", "skills": [],
        "work_history": [], "education": [], "target_salary_min": None,
        "target_salary_max": None, "target_roles": [], "resume_path": "",
    }))
    db_session.add(row)
    db_session.commit()

    for bad_key in ["sk-abc\nINJECTED=bad", "sk-abc\r\nINJECTED=bad"]:
        resp = client.put(f"/api/config/profiles/{row.id}", json={
            "name": "Test",
            "data": {},
            "llm_api_key": bad_key,
        })
        assert resp.status_code == 422

    assert env_file.read_text() == ""


def test_put_profile_accepts_base64_padded_key(client, db_session, monkeypatch, tmp_path):
    import web.routers.config as config_mod
    import json
    from core.user import User as UserProfileModel

    env_file = tmp_path / ".env"
    env_file.write_text("")
    monkeypatch.setattr(config_mod, "_ENV_PATH", env_file)

    row = UserProfileModel(name="Test", data=json.dumps({
        "email": "", "phone": "", "location": "", "skills": [],
        "work_history": [], "education": [], "target_salary_min": None,
        "target_salary_max": None, "target_roles": [], "resume_path": "",
    }))
    db_session.add(row)
    db_session.commit()

    resp = client.put(f"/api/config/profiles/{row.id}", json={
        "name": "Test",
        "data": {},
        "llm_api_key": "sk-validkey==",
    })
    assert resp.status_code == 200
    assert f"LLM_KEY_PROFILE_{row.id}=sk-validkey==" in env_file.read_text()
