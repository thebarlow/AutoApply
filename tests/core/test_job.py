from __future__ import annotations
import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def db_session():
    from db.database import Base
    import core.job   # noqa: F401
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


def _make_scraped(**kwargs):
    from scraper.base import ScrapedJob
    defaults = dict(
        source="remotive", job_key="remotive_1", title="SWE", company="Acme",
        url="https://remotive.com/1", description="Python required.",
        location="Remote", salary="$120k", remote=True, posted_at="2026-01-01",
    )
    return ScrapedJob(**{**defaults, **kwargs})


def test_job_from_scraped_sets_fields():
    from core.job import Job
    scraped = _make_scraped()
    job = Job.from_scraped(scraped)
    assert job.job_key == "remotive_1"
    assert job.company == "Acme"
    assert job.state == "new"


def test_job_save_batch_inserts_new_jobs(db_session):
    from core.job import Job
    scraped = [_make_scraped(job_key="r_1", url="https://x.com/1"),
               _make_scraped(job_key="r_2", url="https://x.com/2")]
    count = Job.save_batch(scraped, db_session)
    assert count == 2
    assert db_session.query(Job).count() == 2


def test_job_save_batch_skips_duplicates(db_session):
    from core.job import Job
    scraped = [_make_scraped(job_key="r_1", url="https://x.com/1")]
    Job.save_batch(scraped, db_session)
    count = Job.save_batch(scraped, db_session)
    assert count == 0
    assert db_session.query(Job).count() == 1


def test_job_get_returns_job(db_session):
    from core.job import Job
    db_session.add(Job.from_scraped(_make_scraped()))
    db_session.commit()
    job = Job.get("remotive_1", db_session)
    assert job is not None
    assert job.title == "SWE"


def test_job_get_returns_none_when_missing(db_session):
    from core.job import Job
    assert Job.get("missing", db_session) is None


def test_job_get_or_raise_raises_when_missing(db_session):
    from core.job import Job
    with pytest.raises(ValueError, match="not found"):
        Job.get_or_raise("missing", db_session)


def test_job_set_state(db_session):
    from core.job import Job, JobState
    job = Job.from_scraped(_make_scraped())
    db_session.add(job)
    db_session.commit()
    job.set_state(JobState.APPLIED, db_session)
    assert db_session.query(Job).first().state == "applied"


def test_job_mark_applied_sets_applied_at(db_session):
    from core.job import Job
    job = Job.from_scraped(_make_scraped())
    db_session.add(job)
    db_session.commit()
    job.mark_applied(db_session)
    fetched = db_session.query(Job).first()
    assert fetched.state == "applied"
    assert fetched.applied_at is not None


def test_job_serialize_returns_dict(db_session):
    from core.job import Job
    job = Job.from_scraped(_make_scraped())
    job.desirability_score = 0.8
    job.fit_score = 0.7
    job.final_score = 0.75
    job.score_justification = json.dumps({"desirability": "Good.", "fit": "OK."})
    db_session.add(job)
    db_session.commit()
    result = job.serialize()
    assert result["job_key"] == "remotive_1"
    assert result["final_score"] == 0.75
    assert isinstance(result["score_justification"], dict)
    assert "extraction_json_exists" in result


def test_build_score_prompt_contains_job_and_user(db_session):
    from core.job import Job
    from core.user import User
    job = Job.from_scraped(_make_scraped(title="Python Dev", company="Acme"))
    db_session.add(job)
    db_session.commit()

    data = {
        "first_name": "Matt", "last_name": "Barlow", "name": "Matt Barlow",
        "email": "m@x.com", "phone": "", "location": "Remote", "hero": "",
        "linkedin": "", "github": "",
        "skills": ["Python", "SQL"], "work_history": [], "education": [],
        "projects": [], "target_salary_min": 120000, "target_salary_max": 160000,
        "target_roles": ["SWE"], "resume_path": "", "md_path": "",
    }
    import json as _json
    db_session.add(User(name="Matt", data=_json.dumps(data)))
    db_session.commit()
    user = User.load(db_session)

    prompt = job.build_score_prompt(user)
    assert "Python Dev" in prompt
    assert "Acme" in prompt
    assert "Matt Barlow" in prompt
    assert "desirability_score" in prompt


def test_score_populates_scores(db_session):
    from core.job import Job
    from core.user import User
    from unittest.mock import MagicMock
    import json as _json

    job = Job.from_scraped(_make_scraped())
    db_session.add(job)
    data = {
        "first_name": "Matt", "last_name": "Barlow", "name": "Matt Barlow",
        "email": "", "phone": "", "location": "", "hero": "", "linkedin": "", "github": "",
        "skills": ["Python"], "work_history": [], "education": [], "projects": [],
        "target_salary_min": 100000, "target_salary_max": 150000,
        "target_roles": ["SWE"], "resume_path": "", "md_path": "",
    }
    db_session.add(User(name="Matt", data=_json.dumps(data)))
    db_session.commit()
    user = User.load(db_session)

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = _json.dumps({
        "desirability_score": 0.8,
        "fit_score": 0.7,
        "desirability_justification": "Good salary.",
        "fit_justification": "Python match.",
    })

    config = {"w1": 0.5, "w2": 0.5}
    job.score(user, config, mock_client, "gpt-4", db_session)

    fetched = db_session.query(Job).first()
    assert fetched.desirability_score == 0.8
    assert fetched.fit_score == 0.7
    assert fetched.final_score == pytest.approx(0.75)
    assert fetched.score_justification is not None


def test_build_description_prompt_substitutes_fields(db_session):
    from core.job import Job
    job = Job.from_scraped(_make_scraped(title="Python Dev", description="Needs Python."))
    db_session.add(job)
    db_session.commit()
    prompt = job.build_description_prompt("Title: {job.title}\nDesc: {job.description}")
    assert "Python Dev" in prompt
    assert "Needs Python." in prompt


def test_extract_description_populates_ext_columns(db_session):
    from core.job import Job
    from unittest.mock import MagicMock, patch
    import json as _json

    job = Job.from_scraped(_make_scraped(description="Needs Python and FastAPI."))
    db_session.add(job)
    db_session.commit()

    extraction_result = _json.dumps({
        "seniority": "Mid",
        "role_type": "Backend",
        "domain": "Web",
        "work_arrangement": "Remote",
        "employment_type": "Full-time",
        "required_skills": ["Python", "FastAPI"],
        "preferred_skills": ["Docker"],
        "tech_stack": ["Python", "PostgreSQL"],
        "key_responsibilities": ["Build APIs"],
        "company_signals": ["Startup"],
    })

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = extraction_result
    mock_client.chat.completions.create.return_value.choices[0].finish_reason = "stop"

    from db.database import Config
    db_session.add(Config(key="active_description_prompt_id", value="p1"))
    db_session.add(Config(key="description_prompts", value=_json.dumps([{
        "id": "p1", "content": "Extract: {job.description}",
        "provider_name": "test", "model_id": "m",
    }])))
    db_session.commit()

    with patch("core.llm.get_client_for_named_provider", return_value=(mock_client, "m")):
        job.extract_description(db_session)

    fetched = db_session.query(Job).first()
    assert fetched.ext_seniority == "Mid"
    assert "Python" in fetched.ext_required_skills
    assert fetched.ext_work_arrangement == "Remote"


def test_extract_description_skips_if_already_populated(db_session):
    from core.job import Job
    from unittest.mock import MagicMock

    job = Job.from_scraped(_make_scraped())
    job.ext_seniority = "Senior"
    db_session.add(job)
    db_session.commit()

    mock_client = MagicMock()
    # extract_description should not call the LLM at all
    job.extract_description(db_session)
    mock_client.chat.completions.create.assert_not_called()
    assert db_session.query(Job).first().ext_seniority == "Senior"


def test_build_resume_prompt_substitutes_job_and_user(db_session):
    from core.job import Job
    from core.user import User
    import json as _json

    job = Job.from_scraped(_make_scraped(title="Python Dev"))
    db_session.add(job)
    data = {
        "first_name": "Matt", "last_name": "Barlow", "name": "Matt Barlow",
        "email": "", "phone": "", "location": "", "hero": "", "linkedin": "", "github": "",
        "skills": ["Python"], "work_history": [], "education": [], "projects": [],
        "target_salary_min": 100000, "target_salary_max": 150000,
        "target_roles": ["SWE"], "resume_path": "", "md_path": "",
    }
    db_session.add(User(name="Matt", data=_json.dumps(data)))
    db_session.commit()
    user = User.load(db_session)

    prompt = job.build_resume_prompt(user, "Job: {job.title}\nProfile: {user_profile.skills}", db_session)
    assert "Python Dev" in prompt
    assert "Python" in prompt


def test_serialize_extraction_none_when_no_ext_fields(db_session):
    from core.job import Job
    job = Job.from_scraped(_make_scraped())
    db_session.add(job)
    db_session.commit()
    result = job.serialize()
    assert result["extraction_json_exists"] is False
    assert result["extraction"] is None


def test_serialize_extraction_populated_when_ext_fields_set(db_session):
    from core.job import Job
    job = Job.from_scraped(_make_scraped())
    job.ext_seniority = "Mid"
    job.ext_required_skills = "Python, FastAPI, Docker"
    job.ext_tech_stack = "Python, PostgreSQL"
    job.ext_preferred_skills = "  Kubernetes , Go "
    db_session.add(job)
    db_session.commit()
    result = job.serialize()
    assert result["extraction_json_exists"] is True
    ext = result["extraction"]
    assert ext is not None
    assert ext["seniority"] == "Mid"
    assert ext["required_skills"] == ["Python", "FastAPI", "Docker"]
    assert ext["tech_stack"] == ["Python", "PostgreSQL"]
    # verify strip logic removes surrounding whitespace
    assert ext["preferred_skills"] == ["Kubernetes", "Go"]


def test_all_inbox_returns_only_new_and_pending_review(db_session):
    from core.job import Job, JobState
    new_job = Job.from_scraped(_make_scraped(job_key="r_new", url="https://x.com/new"))
    pending_job = Job.from_scraped(_make_scraped(job_key="r_pending", url="https://x.com/pending"))
    pending_job.state = JobState.PENDING_REVIEW.value
    ready_job = Job.from_scraped(_make_scraped(job_key="r_ready", url="https://x.com/ready"))
    ready_job.state = JobState.READY.value
    db_session.add_all([new_job, pending_job, ready_job])
    db_session.commit()
    results = Job.all_inbox(db_session)
    keys = {j.job_key for j in results}
    assert "r_new" in keys
    assert "r_pending" in keys
    assert "r_ready" not in keys
    assert len(results) == 2


def test_generate_resume_md_writes_file(db_session, tmp_path):
    from core.job import Job
    from core.user import User
    from unittest.mock import MagicMock, patch
    import json as _json

    job = Job.from_scraped(_make_scraped())
    db_session.add(job)
    data = {
        "first_name": "Matt", "last_name": "Barlow", "name": "Matt Barlow",
        "email": "m@x.com", "phone": "555", "location": "Remote",
        "hero": "", "linkedin": "li", "github": "gh",
        "skills": ["Python"], "work_history": [], "education": [], "projects": [],
        "target_salary_min": 100000, "target_salary_max": 150000,
        "target_roles": ["SWE"], "resume_path": "", "md_path": "",
    }
    db_session.add(User(name="Matt", data=_json.dumps(data)))
    from db.database import Config as _Config
    db_session.add(_Config(key="resume_github", value=""))
    db_session.add(_Config(key="resume_linkedin", value=""))
    db_session.add(_Config(key="resume_website", value=""))
    db_session.commit()
    user = User.load(db_session)

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = "## Experience\n- Did things"
    mock_client.chat.completions.create.return_value.choices[0].finish_reason = "stop"

    outputs = tmp_path / "outputs"
    outputs.mkdir()
    with patch("core.job._OUTPUTS_DIR", outputs):
        job.generate_resume_md(user, "Write resume for {job.title}", mock_client, "gpt-4", db_session)

    md_file = outputs / "remotive_1_resume.md"
    assert md_file.exists()
    content = md_file.read_text()
    assert "## Experience" in content


def test_intake_spawns_background_thread_and_calls_extract(db_session):
    import threading
    from unittest.mock import patch
    from core.job import Job

    job = Job.from_scraped(_make_scraped(job_key="r_intake", url="https://x.com/intake"))
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    spawned_threads = []
    called = []

    original_thread_init = threading.Thread.__init__

    def capturing_init(self, *args, **kwargs):
        original_thread_init(self, *args, **kwargs)
        spawned_threads.append(self)

    def fake_extract(self, db):
        called.append(self.job_key)

    # Keep all patches active while the thread executes
    with patch.object(threading.Thread, "__init__", capturing_init), \
         patch.object(Job, "extract_description", fake_extract), \
         patch("db.database.SessionLocal", return_value=db_session):
        job.intake()
        # Ensure thread completes while patches are still active
        assert len(spawned_threads) == 1
        spawned_threads[0].join(timeout=5)

    assert called == ["r_intake"]
