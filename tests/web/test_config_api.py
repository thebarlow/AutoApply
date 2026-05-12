import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db
from db.models import Base, Config
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
    assert data["resume_template_path"] == "generator/resume_template.tex"
    assert data["cover_template_path"] == "generator/cover_template.tex"
    assert data["resume_prompt_template"] == ""
    assert data["cover_prompt_template"] == ""
    assert data["github"] == ""
    assert data["linkedin"] == ""
    assert data["website"] == ""


def test_put_templates_persists(client):
    body = {
        "resume_template_path": "/custom/resume.tex",
        "cover_template_path": "/custom/cover.tex",
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
    assert data["resume_template_path"] == "/custom/resume.tex"
    assert data["github"] == "github.com/matt"
    assert data["resume_prompt_template"] == "Write a resume for {profile} applying to {job}"


def test_get_scoring_defaults(client):
    resp = client.get("/api/config/scoring")
    assert resp.status_code == 200
    data = resp.json()
    assert data["w1"] == pytest.approx(0.5)
    assert data["w2"] == pytest.approx(0.5)
    assert data["auto_reject_threshold"] == pytest.approx(0.5)
    assert data["auto_approve_threshold"] == pytest.approx(0.5)


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


def test_get_llm_empty(client):
    resp = client.get("/api/config/llm")
    assert resp.status_code == 200
    data = resp.json()
    assert data["providers"] == []
    assert data["active"] == ""


def test_put_llm_persists_provider_and_writes_key(client, tmp_path, monkeypatch):
    import web.routers.config as config_mod
    monkeypatch.setattr(config_mod, "_ENV_PATH", tmp_path / ".env")

    body = {
        "providers": [{"name": "openrouter", "model": "anthropic/claude-sonnet-4-6", "api_key": "sk-test"}],
        "active": "openrouter",
    }
    resp = client.put("/api/config/llm", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["providers"]) == 1
    assert data["providers"][0]["name"] == "openrouter"
    assert data["providers"][0]["has_key"] is True
    assert data["active"] == "openrouter"
    assert "LLM_KEY_OPENROUTER=sk-test" in (tmp_path / ".env").read_text()


def test_put_llm_blank_key_preserves_existing(client, tmp_path, monkeypatch):
    import web.routers.config as config_mod
    env_path = tmp_path / ".env"
    env_path.write_text("LLM_KEY_OPENROUTER=existing-key\n")
    monkeypatch.setattr(config_mod, "_ENV_PATH", env_path)

    body = {
        "providers": [{"name": "openrouter", "model": "gpt-4o", "api_key": ""}],
        "active": "openrouter",
    }
    resp = client.put("/api/config/llm", json=body)
    assert resp.status_code == 200
    assert "existing-key" in env_path.read_text()


def test_put_llm_unknown_provider_returns_422(client, tmp_path, monkeypatch):
    import web.routers.config as config_mod
    monkeypatch.setattr(config_mod, "_ENV_PATH", tmp_path / ".env")

    body = {
        "providers": [{"name": "unknown_llm", "model": "x", "api_key": "key"}],
        "active": "unknown_llm",
    }
    resp = client.put("/api/config/llm", json=body)
    assert resp.status_code == 422


# ---- Named Providers ----

def test_get_providers_empty(client):
    resp = client.get("/api/config/providers")
    assert resp.status_code == 200
    assert resp.json() == {"providers": []}


def test_create_and_list_provider(client, tmp_path, monkeypatch):
    import web.routers.config as config_mod
    monkeypatch.setattr(config_mod, "_ENV_PATH", tmp_path / ".env")

    resp = client.post("/api/config/providers", json={
        "name": "My OpenRouter", "provider_type": "openrouter", "api_key": "sk-test-123"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "My OpenRouter"
    assert data["provider_type"] == "openrouter"
    assert "id" in data

    resp2 = client.get("/api/config/providers")
    providers = resp2.json()["providers"]
    assert len(providers) == 1
    assert providers[0]["name"] == "My OpenRouter"
    assert providers[0]["has_key"] is True
    assert "masked_key" in providers[0]


def test_update_provider(client, tmp_path, monkeypatch):
    import web.routers.config as config_mod
    monkeypatch.setattr(config_mod, "_ENV_PATH", tmp_path / ".env")

    pid = client.post("/api/config/providers", json={
        "name": "Old Name", "provider_type": "anthropic", "api_key": "sk-ant-abc"
    }).json()["id"]

    resp = client.put(f"/api/config/providers/{pid}", json={
        "name": "New Name", "provider_type": "anthropic", "api_key": ""
    })
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"

    resp2 = client.get("/api/config/providers")
    assert resp2.json()["providers"][0]["name"] == "New Name"


def test_delete_provider(client, tmp_path, monkeypatch):
    import web.routers.config as config_mod
    monkeypatch.setattr(config_mod, "_ENV_PATH", tmp_path / ".env")

    pid = client.post("/api/config/providers", json={
        "name": "ToDelete", "provider_type": "openai", "api_key": "sk-xyz"
    }).json()["id"]

    resp = client.delete(f"/api/config/providers/{pid}")
    assert resp.status_code == 204

    resp2 = client.get("/api/config/providers")
    assert resp2.json()["providers"] == []


# ---- LaTeX Templates ----

def test_get_latex_templates_empty(client):
    resp = client.get("/api/config/latex-templates")
    assert resp.status_code == 200
    assert resp.json() == {"templates": []}


def test_create_latex_template(client, tmp_path, monkeypatch):
    import web.routers.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "_TEMPLATES_DIR", tmp_path)

    tex_bytes = b"\\documentclass{article}\\begin{document}Hello\\end{document}"
    resp = client.post(
        "/api/config/latex-templates",
        data={"name": "resume.tex"},
        files={"file": ("resume_template.tex", tex_bytes, "text/plain")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "resume.tex"
    assert "id" in data
    assert "path" in data

    resp2 = client.get("/api/config/latex-templates")
    templates = resp2.json()["templates"]
    assert len(templates) == 1
    assert templates[0]["name"] == "resume.tex"


def test_update_latex_template_name(client, tmp_path, monkeypatch):
    import web.routers.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "_TEMPLATES_DIR", tmp_path)

    tex_bytes = b"\\documentclass{article}"
    tid = client.post(
        "/api/config/latex-templates",
        data={"name": "old.tex"},
        files={"file": ("old.tex", tex_bytes, "text/plain")},
    ).json()["id"]

    resp = client.put(f"/api/config/latex-templates/{tid}", json={"name": "new.tex"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "new.tex"


def test_delete_latex_template(client, tmp_path, monkeypatch):
    import web.routers.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "_TEMPLATES_DIR", tmp_path)

    tex_bytes = b"\\documentclass{article}"
    tid = client.post(
        "/api/config/latex-templates",
        data={"name": "to_delete.tex"},
        files={"file": ("to_delete.tex", tex_bytes, "text/plain")},
    ).json()["id"]

    resp = client.delete(f"/api/config/latex-templates/{tid}")
    assert resp.status_code == 204

    resp2 = client.get("/api/config/latex-templates")
    assert resp2.json()["templates"] == []


def test_delete_provider_not_found(client):
    resp = client.delete("/api/config/providers/nonexistent-id")
    assert resp.status_code == 404


# ---- Unified Prompt List ----

def test_unified_prompt_list_empty(client):
    resp = client.get("/api/config/prompts")
    assert resp.status_code == 200
    assert resp.json() == {"prompts": []}


def test_unified_prompt_list_includes_all_types(client):
    client.post("/api/config/prompts/resume", json={"name": "R1", "content": "resume content"})
    client.post("/api/config/prompts/cover", json={"name": "C1", "content": "cover content"})
    client.post("/api/config/prompts/description", json={"name": "D1", "content": "desc content"})

    resp = client.get("/api/config/prompts")
    prompts = resp.json()["prompts"]
    assert len(prompts) == 3
    types = {p["type"] for p in prompts}
    assert types == {"resume", "cover", "description"}


# ---- Extended Prompt Fields ----

def test_create_prompt_with_extended_fields(client):
    resp = client.post("/api/config/prompts/resume", json={
        "name": "Resume v1",
        "content": "write a resume",
        "provider_name": "My OpenRouter",
        "model_id": "anthropic/claude-sonnet-4-6",
        "template_name": "resume.tex",
    })
    assert resp.status_code == 200
    pid = resp.json()["id"]

    detail = client.get(f"/api/config/prompts/resume/{pid}").json()
    assert detail["provider_name"] == "My OpenRouter"
    assert detail["model_id"] == "anthropic/claude-sonnet-4-6"
    assert detail["template_name"] == "resume.tex"


def test_update_prompt_extended_fields(client):
    pid = client.post("/api/config/prompts/cover", json={
        "name": "C1", "content": "cover", "provider_name": "", "model_id": "", "template_name": "",
    }).json()["id"]

    client.put(f"/api/config/prompts/cover/{pid}", json={
        "name": "C1", "content": "cover updated",
        "provider_name": "Anthropic Direct",
        "model_id": "claude-opus-4-7",
        "template_name": "cover.tex",
    })
    detail = client.get(f"/api/config/prompts/cover/{pid}").json()
    assert detail["provider_name"] == "Anthropic Direct"
    assert detail["model_id"] == "claude-opus-4-7"


def test_active_status_all_false_by_default(client):
    resp = client.get("/api/config/prompts/active-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["resume_has_template"] is False
    assert data["cover_has_template"] is False
    assert data["description_has_prompt"] is False


def test_active_status_description_has_prompt_true_when_active_prompt_set(client, db_session):
    import uuid
    pid = uuid.uuid4().hex
    prompts = [{"id": pid, "name": "Desc", "content": "...",
                "provider_name": "P", "model_id": "m", "template_name": ""}]
    db_session.add(Config(key="description_prompts", value=json.dumps(prompts)))
    db_session.add(Config(key="active_description_prompt_id", value=pid))
    db_session.commit()

    resp = client.get("/api/config/prompts/active-status")
    assert resp.status_code == 200
    assert resp.json()["description_has_prompt"] is True


def test_active_status_resume_has_template_true_when_template_file_exists(client, db_session, tmp_path):
    import uuid
    tpl = tmp_path / "resume.tex"
    tpl.write_text("\\documentclass{article}")
    pid = uuid.uuid4().hex
    prompts = [{"id": pid, "name": "R", "content": "...",
                "provider_name": "P", "model_id": "m", "template_name": "MyTpl"}]
    templates = [{"id": "tid", "name": "MyTpl", "path": str(tpl)}]
    db_session.add(Config(key="resume_prompts", value=json.dumps(prompts)))
    db_session.add(Config(key="active_resume_prompt_id", value=pid))
    db_session.add(Config(key="latex_templates", value=json.dumps(templates)))
    db_session.commit()

    resp = client.get("/api/config/prompts/active-status")
    assert resp.status_code == 200
    assert resp.json()["resume_has_template"] is True


def test_active_status_resume_has_template_false_when_template_file_missing(client, db_session, tmp_path):
    import uuid
    pid = uuid.uuid4().hex
    prompts = [{"id": pid, "name": "R", "content": "...",
                "provider_name": "P", "model_id": "m", "template_name": "MyTpl"}]
    # Template record exists but path does not exist on disk
    templates = [{"id": "tid", "name": "MyTpl", "path": str(tmp_path / "nonexistent.tex")}]
    db_session.add(Config(key="resume_prompts", value=json.dumps(prompts)))
    db_session.add(Config(key="active_resume_prompt_id", value=pid))
    db_session.add(Config(key="latex_templates", value=json.dumps(templates)))
    db_session.commit()

    resp = client.get("/api/config/prompts/active-status")
    assert resp.status_code == 200
    assert resp.json()["resume_has_template"] is False


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
