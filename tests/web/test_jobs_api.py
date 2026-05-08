import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db
from db.models import Base, Job
from core.types import JobState
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


def _make_job(
    db_session,
    job_key: str,
    state: JobState = JobState.DRAFT,
    final_score: float = 0.75,
    description: str | None = None,
    remote: bool | None = None,
    resume_path: str | None = None,
    cover_path: str | None = None,
) -> Job:
    job = Job(
        job_key=job_key,
        source="indeed",
        title="Software Engineer",
        company="Acme Corp",
        location="Remote",
        salary="$120,000",
        url=f"https://indeed.com/job/{job_key}",
        state=state.value,
        desirability_score=0.80,
        fit_score=0.70,
        final_score=final_score,
        score_justification=json.dumps({
            "desirability": "Good salary and remote.",
            "fit": "Strong Python match.",
        }),
        description=description,
        remote=remote,
        resume_path=resume_path,
        cover_path=cover_path,
    )
    db_session.add(job)
    db_session.commit()
    return job


# --- GET /api/jobs ---

def test_get_jobs_returns_all_states(client, db_session):
    _make_job(db_session, "job_a", JobState.DRAFT)
    _make_job(db_session, "job_b", JobState.APPLIED)
    _make_job(db_session, "job_c", JobState.REJECTED)

    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    keys = [j["job_key"] for j in resp.json()]
    assert "job_a" in keys
    assert "job_b" in keys
    assert "job_c" in keys


def test_get_jobs_includes_artifact_paths(client, db_session):
    _make_job(db_session, "job_paths", resume_path="/outputs/job_paths_resume.pdf")

    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    job = resp.json()[0]
    assert job["resume_path"] == "/outputs/job_paths_resume.pdf"
    assert job["cover_path"] is None


def test_get_jobs_sorted_by_score(client, db_session):
    _make_job(db_session, "low", JobState.DRAFT, final_score=0.4)
    _make_job(db_session, "high", JobState.DRAFT, final_score=0.9)
    _make_job(db_session, "mid", JobState.DRAFT, final_score=0.65)

    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    scores = [j["final_score"] for j in resp.json()]
    assert scores == sorted(scores, reverse=True)


def test_get_jobs_empty(client):
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_jobs_justification_parsed(client, db_session):
    _make_job(db_session, "job_x", JobState.DRAFT)

    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    justification = resp.json()[0]["score_justification"]
    assert isinstance(justification, dict)
    assert "desirability" in justification
    assert "fit" in justification


# --- PATCH /api/jobs/{job_key}/state ---

def test_patch_state_to_applied(client, db_session):
    _make_job(db_session, "job_apply")
    resp = client.patch("/api/jobs/job_apply/state", json={"state": "applied"})
    assert resp.status_code == 200
    assert resp.json()["state"] == "applied"


def test_patch_state_to_rejected(client, db_session):
    _make_job(db_session, "job_reject")
    resp = client.patch("/api/jobs/job_reject/state", json={"state": "rejected"})
    assert resp.status_code == 200
    assert resp.json()["state"] == "rejected"


def test_patch_state_to_in_contact(client, db_session):
    _make_job(db_session, "job_contact")
    resp = client.patch("/api/jobs/job_contact/state", json={"state": "in_contact"})
    assert resp.status_code == 200
    assert resp.json()["state"] == "in_contact"


def test_patch_state_to_draft(client, db_session):
    _make_job(db_session, "job_draft", state=JobState.APPLIED)
    resp = client.patch("/api/jobs/job_draft/state", json={"state": "draft"})
    assert resp.status_code == 200
    assert resp.json()["state"] == "draft"


def test_patch_invalid_state_rejected_by_api(client, db_session):
    _make_job(db_session, "job_bad")
    resp = client.patch("/api/jobs/job_bad/state", json={"state": "pending"})
    assert resp.status_code == 400


def test_patch_state_not_found(client):
    resp = client.patch("/api/jobs/nonexistent/state", json={"state": "applied"})
    assert resp.status_code == 404


def test_get_jobs_includes_url(client, db_session):
    _make_job(db_session, "job_url", JobState.DRAFT)
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    job = resp.json()[0]
    assert "url" in job
    assert job["url"] == "https://indeed.com/job/job_url"


def test_get_jobs_includes_description(client, db_session):
    _make_job(db_session, "job_desc", JobState.DRAFT, description="We are looking for a software engineer.")

    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    job_data = resp.json()[0]
    assert job_data["description"] == "We are looking for a software engineer."


def test_get_jobs_remote_true_when_set(client, db_session):
    _make_job(db_session, "job_remote", JobState.DRAFT, remote=True)

    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    job_data = resp.json()[0]
    assert job_data["remote"] is True


def test_get_jobs_remote_none_when_not_set(client, db_session):
    _make_job(db_session, "job_noremote", JobState.DRAFT)
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    job_data = resp.json()[0]
    assert "remote" in job_data
    assert job_data["remote"] is None


# --- DELETE /api/jobs/{job_key} ---

def test_delete_job(client, db_session):
    _make_job(db_session, "job_del")

    resp = client.delete("/api/jobs/job_del")
    assert resp.status_code == 200
    assert resp.json() == {"deleted": "job_del"}

    get_resp = client.get("/api/jobs")
    keys = [j["job_key"] for j in get_resp.json()]
    assert "job_del" not in keys


def test_delete_job_not_found(client):
    resp = client.delete("/api/jobs/nonexistent")
    assert resp.status_code == 404


# --- POST /api/jobs/{job_key}/score ---

def test_score_job_endpoint(client, db_session, monkeypatch):
    import web.routers.jobs as jobs_router

    _make_job(db_session, "job_score")

    def mock_score_job(job, profile, config, llm_client, model, db):
        job.desirability_score = 0.9
        job.fit_score = 0.8
        job.final_score = 0.85
        job.score_justification = json.dumps({"desirability": "Great.", "fit": "Perfect."})
        db.commit()

    monkeypatch.setattr(jobs_router, "_score_job", mock_score_job)
    monkeypatch.setattr(jobs_router, "_load_user_profile", lambda db: None)
    monkeypatch.setattr(jobs_router, "_load_config", lambda db: {})
    monkeypatch.setattr(jobs_router, "get_openai_client", lambda db: (None, "test-model"))

    resp = client.post("/api/jobs/job_score/score")
    assert resp.status_code == 200
    data = resp.json()
    assert data["final_score"] == pytest.approx(0.85)
    assert data["state"] == "draft"


def test_score_job_endpoint_not_found(client):
    resp = client.post("/api/jobs/nonexistent/score")
    assert resp.status_code == 404


def test_serve_resume_not_found(client, db_session):
    _make_job(db_session, "job_noresume")
    resp = client.get("/api/jobs/job_noresume/resume")
    assert resp.status_code == 404


def test_serve_cover_not_found(client, db_session):
    _make_job(db_session, "job_nocover")
    resp = client.get("/api/jobs/job_nocover/cover")
    assert resp.status_code == 404


def test_serve_resume_job_not_found(client):
    resp = client.get("/api/jobs/nonexistent/resume")
    assert resp.status_code == 404


def test_serve_cover_job_not_found(client):
    resp = client.get("/api/jobs/nonexistent/cover")
    assert resp.status_code == 404


def test_serve_resume_file_missing_on_disk(client, db_session):
    _make_job(db_session, "job_badpath", resume_path="/nonexistent/path/resume.pdf")
    resp = client.get("/api/jobs/job_badpath/resume")
    assert resp.status_code == 404


def test_serve_cover_file_missing_on_disk(client, db_session):
    _make_job(db_session, "job_badcover", cover_path="/nonexistent/path/cover.pdf")
    resp = client.get("/api/jobs/job_badcover/cover")
    assert resp.status_code == 404


def test_generate_resume_endpoint(client, db_session, monkeypatch):
    import web.routers.jobs as jobs_router

    _make_job(db_session, "job_resume")
    monkeypatch.setattr(jobs_router, "get_openai_client", lambda db: (None, "test-model"))

    def mock_generate_resume(job_key, db, client, model):
        job = db.query(Job).filter_by(job_key=job_key).first()
        job.resume_path = f"/outputs/{job_key}_resume.pdf"
        job.state = "generated"
        db.commit()

    monkeypatch.setattr(jobs_router, "_generate_resume", mock_generate_resume)

    resp = client.post("/api/jobs/job_resume/generate/resume")
    assert resp.status_code == 200
    data = resp.json()
    assert data["resume_path"] == "/outputs/job_resume_resume.pdf"
    assert data["state"] == "generated"


def test_generate_resume_endpoint_not_found(client):
    resp = client.post("/api/jobs/nonexistent/generate/resume")
    assert resp.status_code == 404


def test_generate_cover_endpoint(client, db_session, monkeypatch):
    import web.routers.jobs as jobs_router

    _make_job(db_session, "job_cover", resume_path="/outputs/job_cover_resume.pdf")
    monkeypatch.setattr(jobs_router, "get_openai_client", lambda db: (None, "test-model"))

    def mock_generate_cover(job_key, db, client, model):
        job = db.query(Job).filter_by(job_key=job_key).first()
        job.cover_path = f"/outputs/{job_key}_cover.pdf"
        db.commit()

    monkeypatch.setattr(jobs_router, "_generate_cover", mock_generate_cover)

    resp = client.post("/api/jobs/job_cover/generate/cover")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cover_path"] == "/outputs/job_cover_cover.pdf"


def test_generate_cover_endpoint_blocked_without_resume(client, db_session, monkeypatch):
    import web.routers.jobs as jobs_router

    _make_job(db_session, "job_nocover_block")
    monkeypatch.setattr(jobs_router, "get_openai_client", lambda db: (None, "test-model"))

    resp = client.post("/api/jobs/job_nocover_block/generate/cover")
    assert resp.status_code == 400
    assert "Resume must be generated" in resp.json()["detail"]


def test_generate_cover_endpoint_not_found(client):
    resp = client.post("/api/jobs/nonexistent/generate/cover")
    assert resp.status_code == 404


# --- extraction_json_exists in _serialize ---

def test_get_jobs_includes_extraction_json_exists_false(client, db_session):
    _make_job(db_session, "job_noextract")
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    job = resp.json()[0]
    assert "extraction_json_exists" in job
    assert job["extraction_json_exists"] is False


def test_get_jobs_includes_extraction_json_exists_true(client, db_session):
    job = _make_job(db_session, "job_hasextract")
    job.extraction_json = '{"required_skills": ["Python"]}'
    db_session.commit()
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    data = resp.json()[0]
    assert data["extraction_json_exists"] is True


# --- GET /api/jobs/{job_key}/description ---

def test_get_description_html_returns_html(client, db_session):
    job = _make_job(db_session, "job_html")
    job.extraction_json = '{"required_skills": ["Python", "FastAPI"]}'
    db_session.commit()
    resp = client.get("/api/jobs/job_html/description")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "Python" in resp.text


def test_get_description_html_not_found(client):
    resp = client.get("/api/jobs/nonexistent/description")
    assert resp.status_code == 404


def test_get_description_html_no_extraction(client, db_session):
    _make_job(db_session, "job_nohtml")
    resp = client.get("/api/jobs/job_nohtml/description")
    assert resp.status_code == 404


def test_get_description_rendered_view_converts_json(client, db_session):
    job = _make_job(db_session, "job_rendered")
    job.extraction_json = '{"required_skills": ["Python", "FastAPI"]}'
    db_session.commit()
    resp = client.get("/api/jobs/job_rendered/description")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "Required Skills" in resp.text
    assert "Python" in resp.text


def test_get_description_json_view_returns_raw(client, db_session):
    job = _make_job(db_session, "job_jsonview")
    job.extraction_json = '{"required_skills": ["Python"]}'
    db_session.commit()
    resp = client.get("/api/jobs/job_jsonview/description?view=json")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "required_skills" in resp.text
    assert "<pre" in resp.text


def test_get_description_invalid_view_param(client, db_session):
    job = _make_job(db_session, "job_badview")
    job.extraction_json = '{"required_skills": []}'
    db_session.commit()
    resp = client.get("/api/jobs/job_badview/description?view=invalid")
    assert resp.status_code == 422


# --- GET /api/jobs/{job_key}/description/prompt ---

def test_get_description_prompt_returns_text(client, db_session):
    from db.models import Config
    job = _make_job(db_session, "job_dprompt", description="We need Python skills.")
    db_session.add(Config(key="description_prompt_template", value="Extract from: {description}"))
    db_session.commit()
    resp = client.get("/api/jobs/job_dprompt/description/prompt")
    assert resp.status_code == 200
    assert "We need Python skills." in resp.text


def test_get_description_prompt_no_template(client, db_session):
    _make_job(db_session, "job_dprompt_notpl")
    resp = client.get("/api/jobs/job_dprompt_notpl/description/prompt")
    assert resp.status_code == 400


def test_get_description_prompt_not_found(client):
    resp = client.get("/api/jobs/nonexistent/description/prompt")
    assert resp.status_code == 404


# --- POST /api/jobs/{job_key}/description/extract ---

def test_extract_description_stores_result(client, db_session, monkeypatch):
    import web.routers.jobs as jobs_router
    from db.models import Config

    job = _make_job(db_session, "job_extract", description="We need Python.")
    db_session.add(Config(key="description_prompt_template", value="Extract: {description}"))
    db_session.commit()

    monkeypatch.setattr(jobs_router, "get_openai_client", lambda db: (None, "test-model"))

    def mock_llm_call(client, model, prompt):
        return '{"required_skills": ["Python"]}'

    monkeypatch.setattr(jobs_router, "_call_llm_for_extraction", mock_llm_call)

    resp = client.post("/api/jobs/job_extract/description/extract")
    assert resp.status_code == 200
    assert resp.json()["extraction_json_exists"] is True


def test_extract_description_no_template(client, db_session, monkeypatch):
    import web.routers.jobs as jobs_router
    _make_job(db_session, "job_extract_notpl")
    monkeypatch.setattr(jobs_router, "get_openai_client", lambda db: (None, "test-model"))
    resp = client.post("/api/jobs/job_extract_notpl/description/extract")
    assert resp.status_code == 400


def test_extract_description_not_found(client):
    resp = client.post("/api/jobs/nonexistent/description/extract")
    assert resp.status_code == 404


def test_extract_description_llm_failure_returns_500(client, db_session, monkeypatch):
    import web.routers.jobs as jobs_router
    from db.models import Config

    _make_job(db_session, "job_extract_fail", description="We need Python.")
    db_session.add(Config(key="description_prompt_template", value="Extract: {description}"))
    db_session.commit()

    monkeypatch.setattr(jobs_router, "get_openai_client", lambda db: (None, "test-model"))

    def raise_error(c, m, p):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(jobs_router, "_call_llm_for_extraction", raise_error)

    resp = client.post("/api/jobs/job_extract_fail/description/extract")
    assert resp.status_code == 500
    assert "extraction failed" in resp.json()["detail"].lower()

