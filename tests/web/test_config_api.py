import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db
from db.database import Base, Config
from db.seed import PROFILE_CONFIG_DEFAULTS
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


def test_get_sources_defaults_to_false(client):
    resp = client.get("/api/config/sources")
    assert resp.status_code == 200
    assert resp.json() == {"remotive": False, "remoteok": False}


def test_put_sources_persists(client):
    resp = client.put("/api/config/sources", json={"remotive": True, "remoteok": False})
    assert resp.status_code == 200
    assert resp.json() == {"remotive": True, "remoteok": False}
    resp2 = client.get("/api/config/sources")
    assert resp2.json() == {"remotive": True, "remoteok": False}


def test_get_search_defaults(client):
    resp = client.get("/api/config/search")
    assert resp.status_code == 200
    data = resp.json()
    assert data["keywords_whitelist"] == []
    assert data["keywords_blacklist"] == []
    assert data["max_jobs_per_source"] == 50


def test_put_search_persists(client):
    body = {
        "keywords_whitelist": ["Python", "FastAPI"],
        "keywords_blacklist": ["Senior"],
        "max_jobs_per_source": 100,
    }
    resp = client.put("/api/config/search", json=body)
    assert resp.status_code == 200
    resp2 = client.get("/api/config/search")
    data = resp2.json()
    assert data["keywords_whitelist"] == ["Python", "FastAPI"]
    assert data["keywords_blacklist"] == ["Senior"]
    assert data["max_jobs_per_source"] == 100


def test_get_templates_defaults(client):
    resp = client.get("/api/config/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert data["resume_template_path"] == "generator/resume_template.html"
    assert data["cover_template_path"] == "generator/cover_template.html"
    # resume/cover_prompt_template default to the seeded PROFILE_CONFIG_DEFAULTS
    # prompt text (not empty) since Task 4 dropped the endpoint's inline "" default.
    assert data["resume_prompt_template"] == PROFILE_CONFIG_DEFAULTS["resume_prompt_template"]
    assert data["cover_prompt_template"] == PROFILE_CONFIG_DEFAULTS["cover_prompt_template"]
    assert data["github"] == ""
    assert data["linkedin"] == ""
    assert data["website"] == ""


def test_put_templates_persists(client):
    body = {
        "resume_template_path": "/custom/resume.html",
        "cover_template_path": "/custom/cover.html",
        "resume_prompt_template": "Write a resume for {profile} applying to {job}",
        "cover_prompt_template": "Write a cover letter for {profile} applying to {job}",
        "github": "github.com/matt",
        "linkedin": "linkedin.com/in/matt",
        "website": "matt.dev",
    }
    resp = client.put("/api/config/templates", json=body)
    assert resp.status_code == 200
    resp2 = client.get("/api/config/templates")
    data = resp2.json()
    assert data["resume_template_path"] == "/custom/resume.html"
    assert data["github"] == "github.com/matt"
    assert data["resume_prompt_template"] == "Write a resume for {profile} applying to {job}"


def test_get_scoring_defaults(client):
    resp = client.get("/api/config/scoring")
    assert resp.status_code == 200
    data = resp.json()
    assert data["w1"] == pytest.approx(0.5)
    assert data["w2"] == pytest.approx(0.5)
    # PROFILE_CONFIG_DEFAULTS (Task 4 dropped the endpoint's inline "0.5" default).
    assert data["auto_reject_threshold"] == pytest.approx(0.3)
    assert data["auto_approve_threshold"] == pytest.approx(0.8)


def test_put_scoring_persists(client):
    body = {"w1": 0.6, "w2": 0.4, "auto_reject_threshold": 0.2, "auto_approve_threshold": 0.8}
    resp = client.put("/api/config/scoring", json=body)
    assert resp.status_code == 200
    resp2 = client.get("/api/config/scoring")
    data = resp2.json()
    assert data["w1"] == pytest.approx(0.6)
    assert data["w2"] == pytest.approx(0.4)


def test_put_scoring_rejects_weights_not_summing_to_one(client):
    body = {"w1": 0.7, "w2": 0.7, "auto_reject_threshold": 0.2, "auto_approve_threshold": 0.8}
    resp = client.put("/api/config/scoring", json=body)
    assert resp.status_code == 422


def test_put_scoring_rejects_inverted_thresholds(client):
    body = {"w1": 0.5, "w2": 0.5, "auto_reject_threshold": 0.8, "auto_approve_threshold": 0.2}
    resp = client.put("/api/config/scoring", json=body)
    assert resp.status_code == 422


def test_get_job_fields(client):
    resp = client.get("/api/job-fields")
    assert resp.status_code == 200
    data = resp.json()
    assert "fields" in data
    assert isinstance(data["fields"], list)
    # Spot-check a few columns that should always be present
    names = [f["name"] for f in data["fields"]]
    assert "job.title" in names
    assert "job.company" in names
    assert "job.description" in names
