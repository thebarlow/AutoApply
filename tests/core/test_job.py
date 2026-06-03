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
    from core.user import User, _PROMPTS_DEFAULTS_DIR
    _DEFAULT_SCORE_PROMPT = (_PROMPTS_DEFAULTS_DIR / "scoring.md").read_text(encoding="utf-8")
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

    prompt = job.build_score_prompt(user, _DEFAULT_SCORE_PROMPT)
    assert "Python Dev" in prompt
    assert "Acme" in prompt
    assert "Matt" in prompt
    assert "desirability_score" in prompt


def test_build_score_prompt_uses_custom_template(db_session):
    from core.job import Job
    from core.user import User
    import json as _json

    job = Job.from_scraped(_make_scraped(title="ML Engineer", company="OpenCo"))
    db_session.add(job)
    data = {
        "first_name": "Ada", "last_name": "L", "name": "Ada L",
        "email": "", "phone": "", "location": "", "hero": "", "linkedin": "", "github": "",
        "skills": ["Python"], "work_history": [], "education": [], "projects": [],
        "target_salary_min": 100000, "target_salary_max": 150000,
        "target_roles": ["ML"], "resume_path": "", "md_path": "",
    }
    db_session.add(User(name="Ada", data=_json.dumps(data)))
    db_session.commit()
    user = User.load(db_session)

    template = "Candidate: {user.first_name}. Job: {job.title}. Company: {job.company}."
    prompt = job.build_score_prompt(user, template)
    assert prompt == "Candidate: Ada. Job: ML Engineer. Company: OpenCo."


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
    choice = mock_client.chat.completions.create.return_value.choices[0]
    choice.message.content = _json.dumps({
        "desirability_score": 0.8,
        "fit_score": 0.7,
        "desirability_justification": {"raised": ["Good salary."], "lowered": []},
        "fit_justification": {"raised": ["Python match."], "lowered": []},
    })
    choice.finish_reason = "stop"

    config = {"w1": 0.5, "w2": 0.5}
    job.score(user, config, mock_client, "gpt-4", db_session, "Score this job.")

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
    from core.user import User
    from unittest.mock import MagicMock, patch
    import json as _json

    job = Job.from_scraped(_make_scraped(description="Needs Python and FastAPI."))
    db_session.add(job)

    data = {
        "first_name": "Matt", "last_name": "Barlow", "name": "Matt Barlow",
        "email": "", "phone": "", "location": "", "hero": "", "linkedin": "", "github": "",
        "skills": ["Python"], "work_history": [], "education": [], "projects": [],
        "target_salary_min": 0, "target_salary_max": 0,
        "target_roles": ["SWE"], "resume_path": "", "md_path": "",
        "prompt_extraction": "Extract structured fields from this posting: {job.description}",
    }
    db_session.add(User(name="Matt", data=_json.dumps(data)))
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
    choice = mock_client.chat.completions.create.return_value.choices[0]
    choice.message.content = extraction_result
    choice.finish_reason = "stop"

    with patch("core.llm.get_client_for_profile", return_value=(mock_client, "m")):
        job.extract_description(db_session)

    fetched = db_session.query(Job).first()
    assert fetched.ext_seniority == "Mid"
    assert "Python" in fetched.ext_required_skills
    assert fetched.ext_work_arrangement == "Remote"


def test_extract_description_skips_if_already_populated(db_session):
    from core.job import Job
    from unittest.mock import patch

    job = Job.from_scraped(_make_scraped())
    job.ext_seniority = "Senior"
    db_session.add(job)
    db_session.commit()

    # An already-extracted job must short-circuit before resolving a client/prompt.
    with patch("core.llm.get_client_for_profile") as mock_factory:
        job.extract_description(db_session)
        mock_factory.assert_not_called()
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


def test_job_has_ext_salary_columns(db_session):
    """ext_salary_min and ext_salary_max exist on the model."""
    from core.job import Job, JobState
    job = Job(
        job_key="sal-test",
        source="test",
        url="https://example.com/sal",
        state=JobState.NEW.value,
        ext_salary_min=80000.0,
        ext_salary_max=100000.0,
    )
    db_session.add(job)
    db_session.commit()
    fetched = db_session.query(Job).filter_by(job_key="sal-test").first()
    assert fetched.ext_salary_min == 80000.0
    assert fetched.ext_salary_max == 100000.0


def test_serialize_includes_salary_and_applied_at(db_session):
    """serialize() includes ext_salary_min, ext_salary_max, and applied_at."""
    from core.job import Job, JobState
    job = Job(
        job_key="ser-sal-test",
        source="test",
        url="https://example.com/ser-sal",
        state=JobState.NEW.value,
        ext_salary_min=70000.0,
        ext_salary_max=90000.0,
        applied_at="2026-05-01T12:00:00+00:00",
    )
    db_session.add(job)
    db_session.commit()
    result = job.serialize()
    assert result["ext_salary_min"] == 70000.0
    assert result["ext_salary_max"] == 90000.0
    assert result["applied_at"] == "2026-05-01T12:00:00+00:00"


def test_evaluate_empty_doc_short_circuits_to_zero(db_session, tmp_path, monkeypatch):
    """An empty document body must score 0 without calling the LLM."""
    from unittest.mock import MagicMock
    import core.job as job_mod
    from core.job import Job

    monkeypatch.setattr(job_mod, "_OUTPUTS_DIR", tmp_path)
    job = Job(job_key="empty-eval", source="test", url="https://example.com/e", state="new")
    (tmp_path / "empty-eval_cover.md").write_text("---\ncompany: X\n---\n\n   \n", encoding="utf-8")

    called = {"llm": False}

    def _fail_llm(*a, **k):
        called["llm"] = True
        raise AssertionError("LLM must not be called for empty doc")

    monkeypatch.setattr("core.llm.call_llm", _fail_llm)
    result = job._evaluate_doc_md("cover", "EVAL {current_document}", MagicMock(), MagicMock(), "m")
    assert result["score"] == 0.0
    assert result["issues"]
    assert called["llm"] is False


def test_evaluate_resume_md_returns_score_and_issues(db_session, tmp_path, monkeypatch):
    import core.job as job_mod
    from core.job import Job
    monkeypatch.setattr(job_mod, "_OUTPUTS_DIR", tmp_path)
    job = Job.from_scraped(_make_scraped(job_key="ev_1"))
    db_session.add(job)
    db_session.commit()
    (tmp_path / "ev_1_resume.md").write_text(
        "---\nname: X\n---\n\n## Profile\nReal body here.", encoding="utf-8"
    )
    # Patch target is core.llm (not core.job) because _evaluate_doc_md imports
    # call_llm locally inside the method body.
    monkeypatch.setattr(
        "core.llm.call_llm",
        lambda *a, **k: '{"score": 0.9, "issues": [{"category": "structure", "description": "fix"}]}',
    )
    out = job.evaluate_resume_md("eval prompt {current_document}", object(), object(), "m")
    assert out["score"] == 0.9
    assert out["issues"][0]["category"] == "structure"


def test_generate_cover_md_rejects_empty_content(db_session, tmp_path, monkeypatch):
    """A length-truncated (empty) LLM response must raise, not write a blank letter."""
    from unittest.mock import MagicMock
    import core.job as job_mod
    from core.job import Job

    monkeypatch.setattr(job_mod, "_OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr("core.llm.call_llm", lambda *a, **k: "   ")
    user = MagicMock()
    user.master_resume.return_value = ""
    user.first_name = "A"
    user.last_name = "B"
    user.email = "a@b.com"
    user.phone = ""
    user.location = ""
    user.education = None
    user.full_name.return_value = "A B"
    job = Job(job_key="empty-gen", source="test", url="https://example.com/g", state="new")
    with pytest.raises(RuntimeError, match="empty content"):
        job.generate_cover_md(user, "PROMPT", MagicMock(), "m", db_session)
    assert not (tmp_path / "empty-gen_cover.md").exists()


def test_resume_generated_at_set_on_generate_pdf(db_session, tmp_path):
    from core.job import Job
    from datetime import datetime, timezone
    job = Job(
        job_key="test-rga-1",
        source="test",
        url="https://example.com/1",
        state="new",
    )
    db_session.add(job)
    db_session.commit()
    job.resume_path = str(tmp_path / "test.pdf")
    job.resume_generated_at = datetime.now(timezone.utc).isoformat()
    db_session.commit()
    db_session.refresh(job)
    assert job.resume_generated_at is not None
    assert "T" in job.resume_generated_at


class _FakeUsage:
    cost = 0.0


class _FakeChoice:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})()
        self.finish_reason = "stop"


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]
        self.usage = _FakeUsage()


class _FakeCompletions:
    def __init__(self, content):
        self._content = content

    def create(self, **kwargs):
        return _FakeResponse(self._content)


class _FakeClient:
    def __init__(self, content):
        self.chat = type("C", (), {"completions": _FakeCompletions(content)})()


def test_score_populates_fields(db_session):
    from core.job import Job
    job = Job.from_scraped(_make_scraped())
    db_session.add(job)
    db_session.commit()
    content = (
        '{"fit_score": 0.8, "desirability_score": 0.6,'
        ' "fit_justification": {"raised": ["Python match"], "lowered": []},'
        ' "desirability_justification": {"raised": [], "lowered": ["low salary"]}}'
    )
    client = _FakeClient(content)
    job.score(
        user=object(), config={"w1": 0.5, "w2": 0.5},
        client=client, model="x", db=db_session,
        prompt_content="score this",
    )
    assert job.fit_score == 0.8
    assert job.desirability_score == 0.6
    assert job.final_score == pytest.approx(0.7)
    import json as _json
    just = _json.loads(job.score_justification)
    assert just["fit"]["raised"] == ["Python match"]


def test_score_raises_on_bad_json(db_session):
    from core.job import Job
    job = Job.from_scraped(_make_scraped())
    db_session.add(job)
    db_session.commit()
    client = _FakeClient("not json at all")
    with pytest.raises(RuntimeError, match="not valid JSON|no JSON object"):
        job.score(
            user=object(), config={}, client=client, model="x",
            db=db_session, prompt_content="score this",
        )


def test_cover_generated_at_set_on_generate_pdf(db_session, tmp_path):
    from core.job import Job
    from datetime import datetime, timezone
    job = Job(
        job_key="test-cga-1",
        source="test",
        url="https://example.com/2",
        state="new",
    )
    db_session.add(job)
    db_session.commit()
    job.cover_path = str(tmp_path / "test.pdf")
    job.cover_generated_at = datetime.now(timezone.utc).isoformat()
    db_session.commit()
    db_session.refresh(job)
    assert job.cover_generated_at is not None
    assert "T" in job.cover_generated_at
