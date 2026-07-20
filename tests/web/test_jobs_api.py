import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db
from db.database import Base
from core.job import Job, JobState
import core.user  # noqa: F401 — register User with Base.metadata
from web.main import app
from web.tenancy import current_profile_id


@pytest.fixture
def db_session():
    import core.job  # noqa: F401 — ensure Job registered with Base.metadata
    import core.user  # noqa: F401 — ensure User registered with Base.metadata
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
    app.dependency_overrides[current_profile_id] = lambda: 1
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_job(
    db_session,
    job_key: str,
    state: JobState = JobState.NEW,
    final_score: float = 0.75,
    description: str | None = None,
    remote: bool | None = None,
    resume_path: str | None = None,
    cover_path: str | None = None,
) -> Job:
    job = Job(
        job_key=job_key,
        profile_id=1,
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
    _make_job(db_session, "job_a", JobState.NEW)
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
    _make_job(db_session, "low", JobState.NEW, final_score=0.4)
    _make_job(db_session, "high", JobState.NEW, final_score=0.9)
    _make_job(db_session, "mid", JobState.NEW, final_score=0.65)

    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    scores = [j["final_score"] for j in resp.json()]
    assert scores == sorted(scores, reverse=True)


def test_get_jobs_empty(client):
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_jobs_justification_parsed(client, db_session):
    _make_job(db_session, "job_x", JobState.NEW)

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


def test_patch_state_to_applied_stamps_applied_at(client, db_session):
    """The stats counter counts applied_at, so the state PATCH must set it."""
    _make_job(db_session, "job_ts")
    resp = client.patch("/api/jobs/job_ts/state", json={"state": "applied"})
    assert resp.status_code == 200
    assert resp.json()["applied_at"]


def test_patch_state_to_rejected(client, db_session):
    _make_job(db_session, "job_reject")
    resp = client.patch("/api/jobs/job_reject/state", json={"state": "rejected"})
    assert resp.status_code == 200
    assert resp.json()["state"] == "rejected"


def test_patch_state_to_contact(client, db_session):
    _make_job(db_session, "job_contact")
    resp = client.patch("/api/jobs/job_contact/state", json={"state": "contact"})
    assert resp.status_code == 200
    assert resp.json()["state"] == "contact"


def test_patch_state_to_new(client, db_session):
    _make_job(db_session, "job_new", state=JobState.APPLIED)
    resp = client.patch("/api/jobs/job_new/state", json={"state": "new"})
    assert resp.status_code == 200
    assert resp.json()["state"] == "new"


def test_patch_invalid_state_rejected_by_api(client, db_session):
    _make_job(db_session, "job_bad")
    resp = client.patch("/api/jobs/job_bad/state", json={"state": "pending"})
    assert resp.status_code == 400


def test_patch_state_not_found(client):
    resp = client.patch("/api/jobs/nonexistent/state", json={"state": "applied"})
    assert resp.status_code == 404


def test_get_jobs_includes_url(client, db_session):
    _make_job(db_session, "job_url", JobState.NEW)
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    job = resp.json()[0]
    assert "url" in job
    assert job["url"] == "https://indeed.com/job/job_url"


def test_get_jobs_includes_description(client, db_session):
    _make_job(db_session, "job_desc", JobState.NEW, description="We are looking for a software engineer.")

    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    job_data = resp.json()[0]
    assert job_data["description"] == "We are looking for a software engineer."


def test_get_jobs_remote_true_when_set(client, db_session):
    _make_job(db_session, "job_remote", JobState.NEW, remote=True)

    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    job_data = resp.json()[0]
    assert job_data["remote"] is True


def test_get_jobs_remote_none_when_not_set(client, db_session):
    _make_job(db_session, "job_noremote", JobState.NEW)
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    job_data = resp.json()[0]
    assert "remote" in job_data
    assert job_data["remote"] is None


# --- DELETE /api/jobs/{job_key} ---

def test_delete_job_soft_deletes(client, db_session):
    """DELETE sets state to 'deleted'; row is still present in the DB."""
    _make_job(db_session, "job_del")

    resp = client.delete("/api/jobs/job_del")
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_key"] == "job_del"
    assert data["state"] == "deleted"

    # Row still present in the jobs list
    get_resp = client.get("/api/jobs")
    keys = [j["job_key"] for j in get_resp.json()]
    assert "job_del" in keys

    # State is persisted in the DB
    db_job = db_session.query(Job).filter_by(job_key="job_del").first()
    assert db_job is not None
    assert db_job.state == "deleted"


def test_delete_job_not_found(client):
    resp = client.delete("/api/jobs/nonexistent")
    assert resp.status_code == 404


# --- POST /api/jobs/{job_key}/score ---

def test_score_job_endpoint(client, db_session, monkeypatch):
    import unittest.mock as mock
    import web.routers.jobs as jobs_router
    from core.job import Job

    _make_job(db_session, "job_score")

    def mock_score(self, user, config, client, model, db, prompt_content):
        self.desirability_score = 0.9
        self.fit_score = 0.8
        self.final_score = 0.85
        self.score_justification = json.dumps({"desirability": "Great.", "fit": "Perfect."})
        db.commit()

    monkeypatch.setattr(Job, "score", mock_score)

    fake_user = mock.MagicMock()
    fake_user.prompt_scoring_model = ""
    fake_user.resolve_prompt.return_value = "Score this job."

    monkeypatch.setattr("web.routers.jobs.User.load", classmethod(lambda cls, db, profile_id=None: fake_user))
    monkeypatch.setattr("web.routers.jobs.get_client_for_profile", lambda user, model: (None, "test-model"))

    resp = client.post("/api/jobs/job_score/score")
    assert resp.status_code == 200
    data = resp.json()
    assert data["final_score"] == pytest.approx(0.85)
    assert data["state"] == "new"


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
    import web.intake_pipeline as pipeline

    _make_job(db_session, "job_resume")

    def mock_do_generate_resume(job, db, profile_id):
        job.resume_path = f"/outputs/{job.job_key}_resume.pdf"
        job.state = "generated"
        db.commit()

    # run_resume_generation calls the name bound in its own module namespace.
    monkeypatch.setattr(pipeline, "_do_generate_resume", mock_do_generate_resume)

    # The endpoint returns 202 and spawns the work (spawn is neutralized in tests);
    # drive the background fn directly against the test session.
    resp = client.post("/api/jobs/job_resume/generate/resume")
    assert resp.status_code == 202
    pipeline.run_resume_generation("job_resume", 1, db=db_session)
    job = Job.get("job_resume", db_session, profile_id=1)
    assert job.resume_path == "/outputs/job_resume_resume.pdf"
    assert job.state == "generated"


def test_generate_resume_endpoint_not_found(client):
    resp = client.post("/api/jobs/nonexistent/generate/resume")
    assert resp.status_code == 404


def test_generate_cover_endpoint(client, db_session, monkeypatch):
    import web.intake_pipeline as pipeline

    _make_job(db_session, "job_cover", resume_path="/outputs/job_cover_resume.pdf")

    def mock_do_generate_cover(job, db, profile_id):
        job.cover_path = f"/outputs/{job.job_key}_cover.pdf"
        db.commit()

    monkeypatch.setattr(pipeline, "_do_generate_cover", mock_do_generate_cover)

    resp = client.post("/api/jobs/job_cover/generate/cover")
    assert resp.status_code == 202
    pipeline.run_cover_generation("job_cover", 1, db=db_session)
    job = Job.get("job_cover", db_session, profile_id=1)
    assert job.cover_path == "/outputs/job_cover_cover.pdf"


def test_generate_cover_endpoint_blocked_without_resume(client, db_session):
    _make_job(db_session, "job_nocover_block")
    # The endpoint no longer blocks at the router level (the generator handles a
    # missing resume); it just spawns generation and returns 202. We verify the
    # job exists and doesn't 404.
    resp = client.post("/api/jobs/job_nocover_block/generate/cover")
    assert resp.status_code == 202


def test_generate_cover_endpoint_not_found(client):
    resp = client.post("/api/jobs/nonexistent/generate/cover")
    assert resp.status_code == 404


# --- extraction_json_exists in serialize ---

def test_get_jobs_includes_extraction_json_exists_false(client, db_session):
    _make_job(db_session, "job_noextract")
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    job = resp.json()[0]
    assert "extraction_json_exists" in job
    assert job["extraction_json_exists"] is False


def test_get_jobs_includes_extraction_json_exists_true(client, db_session):
    job = _make_job(db_session, "job_hasextract")
    job.ext_required_skills = "Python"
    db_session.commit()
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    data = resp.json()[0]
    assert data["extraction_json_exists"] is True


# --- POST /api/jobs/{job_key}/description/extract ---

def _seed_description_prompt(db_session, content: str = "Extract: {description}") -> None:
    from db.database import Config
    import json as _json
    db_session.add(Config(key="active_description_prompt_id", value="p1"))
    db_session.add(Config(key="description_prompts", value=_json.dumps([
        {"id": "p1", "name": "Default", "content": content, "provider_name": "test-provider", "model_id": "test-model", "template_name": ""}
    ])))
    db_session.commit()


def test_extract_description_stores_result(client, db_session, monkeypatch):
    import unittest.mock as mock
    import web.routers.jobs as jobs_router

    _make_job(db_session, "job_extract", description="We need Python.")

    fake_user = mock.MagicMock()
    fake_user.prompt_extraction_model = ""
    fake_user.resolve_prompt.return_value = "Extract: {description}"

    monkeypatch.setattr("web.routers.jobs.User.load", classmethod(lambda cls, db, profile_id=None: fake_user))
    monkeypatch.setattr("web.routers.jobs.get_client_for_profile", lambda user, model: (None, "test-model"))

    def mock_llm_call(client, model, prompt, label="extract"):
        return '{"required_skills": ["Python"]}'

    monkeypatch.setattr(jobs_router, "_call_llm_for_extraction", mock_llm_call)

    resp = client.post("/api/jobs/job_extract/description/extract")
    assert resp.status_code == 200
    assert resp.json()["extraction_json_exists"] is True


def test_extract_description_no_template(client, db_session):
    from core.user import User
    import json as _json
    _make_job(db_session, "job_extract_notpl")
    # Seed user with no extraction prompt — resolve_prompt raises PromptNotConfiguredError → 400
    minimal_data = {
        "first_name": "Matt", "last_name": "Barlow", "email": "matt@example.com",
        "phone": "", "location": "", "skills": [], "work_history": [], "education": [],
        "projects": [], "target_salary_min": 0, "target_salary_max": 0,
        "target_roles": [], "resume_path": "", "md_path": "", "hero": "",
        "linkedin": "", "github": "",
    }
    db_session.add(User(name="Matt", data=_json.dumps(minimal_data)))
    db_session.commit()
    resp = client.post("/api/jobs/job_extract_notpl/description/extract")
    assert resp.status_code == 400


def test_extract_description_not_found(client):
    resp = client.post("/api/jobs/nonexistent/description/extract")
    assert resp.status_code == 404


def test_extract_description_endpoint_delegates_to_helper(client, db_session, monkeypatch):
    """_do_extract_description is called by the route handler."""
    job = _make_job(db_session, "exttest", JobState.NEW)

    called = {}

    def fake_helper(j, db, profile_id):
        called["job_key"] = j.job_key

    monkeypatch.setattr("web.routers.jobs._do_extract_description", fake_helper)
    monkeypatch.setattr("web.llm_status.start", lambda *a: None)
    monkeypatch.setattr("web.llm_status.finish", lambda *a: None)

    resp = client.post(f"/api/jobs/{job.job_key}/description/extract")
    assert resp.status_code == 200
    assert called.get("job_key") == job.job_key


def test_extract_description_llm_failure_returns_500(client, db_session, monkeypatch):
    import unittest.mock as mock
    import web.routers.jobs as jobs_router

    _make_job(db_session, "job_extract_fail", description="We need Python.")

    fake_user = mock.MagicMock()
    fake_user.prompt_extraction_model = ""
    fake_user.resolve_prompt.return_value = "Extract: {description}"

    monkeypatch.setattr("web.routers.jobs.User.load", classmethod(lambda cls, db, profile_id=None: fake_user))
    monkeypatch.setattr("web.routers.jobs.get_client_for_profile", lambda user, model: (None, "test-model"))

    def raise_error(c, m, p, label="extract"):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(jobs_router, "_call_llm_for_extraction", raise_error)

    resp = client.post("/api/jobs/job_extract_fail/description/extract")
    assert resp.status_code == 500
    assert "extraction failed" in resp.json()["detail"].lower()


def test_do_extract_description_parses_salary(db_session, monkeypatch):
    """_do_extract_description sets ext_salary_min and ext_salary_max from JSON."""
    from web.routers.jobs import _do_extract_description
    from unittest.mock import MagicMock

    job = _make_job(db_session, "salparse", JobState.NEW)

    mock_user = MagicMock()
    mock_user.resolve_prompt.return_value = "extract this"
    mock_user.prompt_extraction_model = "gpt-4"
    monkeypatch.setattr("web.routers.jobs.User.load", lambda db, profile_id=None: mock_user)
    monkeypatch.setattr(
        "web.routers.jobs.get_client_for_profile",
        lambda user, model: (MagicMock(), "gpt-4"),
    )
    monkeypatch.setattr(
        "web.routers.jobs._call_llm_for_extraction",
        lambda client, model, prompt, label="extract": '{"seniority":"mid","role_type":"engineer","domain":"software","work_arrangement":"remote","employment_type":"full-time","required_skills":[],"preferred_skills":[],"tech_stack":[],"key_responsibilities":[],"company_signals":[],"salary_min":80000,"salary_max":120000}',
    )

    _do_extract_description(job, db_session, 1)

    db_session.refresh(job)
    assert job.ext_salary_min == 80000.0
    assert job.ext_salary_max == 120000.0


def test_do_extract_description_handles_null_salary(db_session, monkeypatch):
    """_do_extract_description sets salary to None when absent from JSON."""
    from web.routers.jobs import _do_extract_description
    from unittest.mock import MagicMock

    job = _make_job(db_session, "salnull", JobState.NEW)

    mock_user = MagicMock()
    mock_user.resolve_prompt.return_value = "extract this"
    mock_user.prompt_extraction_model = "gpt-4"
    monkeypatch.setattr("web.routers.jobs.User.load", lambda db, profile_id=None: mock_user)
    monkeypatch.setattr(
        "web.routers.jobs.get_client_for_profile",
        lambda user, model: (MagicMock(), "gpt-4"),
    )
    monkeypatch.setattr(
        "web.routers.jobs._call_llm_for_extraction",
        lambda client, model, prompt, label="extract": '{"seniority":"mid","role_type":"engineer","domain":"software","work_arrangement":"remote","employment_type":"full-time","required_skills":[],"preferred_skills":[],"tech_stack":[],"key_responsibilities":[],"company_signals":[]}',
    )

    _do_extract_description(job, db_session, 1)

    db_session.refresh(job)
    assert job.ext_salary_min is None
    assert job.ext_salary_max is None


def test_do_extract_description_populates_skill_match(db_session, monkeypatch):
    """After extraction via _do_extract_description, ext_skill_match is set."""
    import json as _json
    from web.routers.jobs import _do_extract_description
    from unittest.mock import MagicMock
    from db.database import PromptDefault

    job = _make_job(db_session, "sm_web", JobState.NEW)
    job.description = "We need Python."
    db_session.commit()

    # Seed the skill_match PromptDefault so the wiring activates.
    db_session.add(PromptDefault(type_key="skill_match", content="Match {skills_to_match} against user skills."))
    db_session.commit()

    mock_user = MagicMock()
    mock_user.resolve_prompt.return_value = "extract this"
    mock_user.prompt_extraction_model = "gpt-4"
    mock_user.skills = ["Python"]
    monkeypatch.setattr("web.routers.jobs.User.load", lambda db, profile_id=None: mock_user)

    # Mock client returns skill_match JSON when called by match_profile_skills.
    mock_client = MagicMock()
    sm_choice = MagicMock()
    sm_choice.message.content = '{"matched": ["Python"]}'
    sm_choice.finish_reason = "stop"
    sm_response = MagicMock()
    sm_response.choices = [sm_choice]
    sm_response.usage = None
    mock_client.chat.completions.create.return_value = sm_response
    monkeypatch.setattr(
        "web.routers.jobs.get_client_for_profile",
        lambda user, model: (mock_client, "gpt-4"),
    )

    # Extraction payload — _call_llm_for_extraction is still patched out.
    monkeypatch.setattr(
        "web.routers.jobs._call_llm_for_extraction",
        lambda client, model, prompt, label="extract": (
            '{"seniority":"mid","role_type":"IC","domain":"web",'
            '"work_arrangement":"remote","employment_type":"full-time",'
            '"required_skills":["Python"],"preferred_skills":[],"tech_stack":[],'
            '"key_responsibilities":[],"company_signals":[]}'
        ),
    )

    _do_extract_description(job, db_session, 1)

    db_session.refresh(job)
    assert job.ext_skill_match is not None
    stored = _json.loads(job.ext_skill_match)
    assert "Python" in stored["matched"]
    assert stored["profile_hash"]


# --- POST /api/jobs/{job_key}/rematch-skills ---


def test_rematch_skills_updates_ext_skill_match(client, db_session, monkeypatch):
    """POST /rematch-skills re-runs the semantic matcher and persists results."""
    import json as _json
    from unittest.mock import MagicMock
    from db.database import PromptDefault

    job = _make_job(db_session, "rematch_job", JobState.NEW)
    job.description = "We need Python."
    job.ext_required_skills = "Python"
    job.ext_skill_match = None
    db_session.commit()

    db_session.add(
        PromptDefault(type_key="skill_match", content="Match {skills_to_match} against user skills.")
    )
    db_session.commit()

    mock_user = MagicMock()
    mock_user.prompt_extraction_model = "gpt-4"
    mock_user.skills = ["Python"]
    monkeypatch.setattr("web.routers.jobs.User.load", lambda db, profile_id=None: mock_user)

    mock_client = MagicMock()
    sm_choice = MagicMock()
    sm_choice.message.content = '{"matched": ["Python"]}'
    sm_choice.finish_reason = "stop"
    sm_response = MagicMock()
    sm_response.choices = [sm_choice]
    sm_response.usage = None
    mock_client.chat.completions.create.return_value = sm_response
    monkeypatch.setattr(
        "web.routers.jobs.get_client_for_profile",
        lambda user, model: (mock_client, "gpt-4"),
    )

    res = client.post("/api/jobs/rematch_job/rematch-skills")
    assert res.status_code == 200

    db_session.refresh(job)
    assert job.ext_skill_match is not None
    stored = _json.loads(job.ext_skill_match)
    assert "Python" in stored["matched"]


def test_rematch_skills_404_for_unknown_job(client):
    """POST /rematch-skills returns 404 when the job_key does not exist."""
    res = client.post("/api/jobs/no_such_job/rematch-skills")
    assert res.status_code == 404


# --- PATCH /api/jobs/{job_key}/fields ---

def test_patch_job_fields_updates_provided_fields(client, db_session):
    _make_job(db_session, "job_x")
    res = client.patch(
        "/api/jobs/job_x/fields",
        json={
            "title": "Senior Engineer",
            "company": "NewCo",
            "salary": "$150k",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["title"] == "Senior Engineer"
    assert body["company"] == "NewCo"
    assert body["salary"] == "$150k"
    # Unprovided fields preserved
    assert body["location"] == "Remote"


def test_patch_job_fields_404_when_missing(client):
    res = client.patch("/api/jobs/nope/fields", json={"title": "x"})
    assert res.status_code == 404


def test_patch_job_fields_ignores_unknown_keys(client, db_session):
    _make_job(db_session, "job_y")
    res = client.patch(
        "/api/jobs/job_y/fields",
        json={"title": "T", "bogus": "x"},
    )
    assert res.status_code == 200
    assert res.json()["title"] == "T"


# --- PATCH /api/jobs/{job_key}/flag ---

def test_flag_job(client, db_session):
    _make_job(db_session, "job_flag")
    resp = client.patch("/api/jobs/job_flag/flag", json={"flagged": True})
    assert resp.status_code == 200
    assert resp.json()["flagged"] is True


def test_unflag_job(client, db_session):
    job = _make_job(db_session, "job_unflag")
    job.flagged = True
    db_session.commit()
    resp = client.patch("/api/jobs/job_unflag/flag", json={"flagged": False})
    assert resp.status_code == 200
    assert resp.json()["flagged"] is False


def test_flag_job_not_found(client):
    resp = client.patch("/api/jobs/nonexistent/flag", json={"flagged": True})
    assert resp.status_code == 404


def test_get_jobs_includes_flagged_field(client, db_session):
    _make_job(db_session, "job_f")
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    assert "flagged" in resp.json()[0]
    assert resp.json()[0]["flagged"] is False
