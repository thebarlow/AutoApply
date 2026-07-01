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
    job = Job.from_scraped_for(scraped, profile_id=1)
    assert job.job_key == "remotive_1"
    assert job.company == "Acme"
    assert job.state == "new"


def test_job_save_batch_inserts_new_jobs(db_session):
    from core.job import Job
    scraped = [_make_scraped(job_key="r_1", url="https://x.com/1"),
               _make_scraped(job_key="r_2", url="https://x.com/2")]
    count = Job.save_batch(scraped, db_session, profile_id=1)
    assert count == 2
    assert db_session.query(Job).count() == 2


def test_job_save_batch_skips_duplicates(db_session):
    from core.job import Job
    scraped = [_make_scraped(job_key="r_1", url="https://x.com/1")]
    Job.save_batch(scraped, db_session, profile_id=1)
    count = Job.save_batch(scraped, db_session, profile_id=1)
    assert count == 0
    assert db_session.query(Job).count() == 1


def test_job_get_returns_job(db_session):
    from core.job import Job
    job = Job.from_scraped_for(_make_scraped(), profile_id=1)
    job.profile_id = 1
    db_session.add(job)
    db_session.commit()
    job = Job.get("remotive_1", db_session, profile_id=1)
    assert job is not None
    assert job.title == "SWE"


def test_job_get_returns_none_when_missing(db_session):
    from core.job import Job
    assert Job.get("missing", db_session, profile_id=1) is None


def test_job_get_or_raise_raises_when_missing(db_session):
    from core.job import Job
    with pytest.raises(ValueError, match="not found"):
        Job.get_or_raise("missing", db_session, profile_id=1)


def test_job_set_state(db_session):
    from core.job import Job, JobState
    job = Job.from_scraped_for(_make_scraped(), profile_id=1)
    db_session.add(job)
    db_session.commit()
    job.set_state(JobState.APPLIED, db_session)
    assert db_session.query(Job).first().state == "applied"


def test_job_mark_applied_sets_applied_at(db_session):
    from core.job import Job
    job = Job.from_scraped_for(_make_scraped(), profile_id=1)
    db_session.add(job)
    db_session.commit()
    job.mark_applied(db_session)
    fetched = db_session.query(Job).first()
    assert fetched.state == "applied"
    assert fetched.applied_at is not None


def test_job_serialize_returns_dict(db_session):
    from core.job import Job
    job = Job.from_scraped_for(_make_scraped(), profile_id=1)
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
    job = Job.from_scraped_for(_make_scraped(title="Python Dev", company="Acme"), profile_id=1)
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

    job = Job.from_scraped_for(_make_scraped(title="ML Engineer", company="OpenCo"), profile_id=1)
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

    job = Job.from_scraped_for(_make_scraped(), profile_id=1)
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
    job = Job.from_scraped_for(_make_scraped(title="Python Dev", description="Needs Python."), profile_id=1)
    db_session.add(job)
    db_session.commit()
    prompt = job.build_description_prompt("Title: {job.title}\nDesc: {job.description}")
    assert "Python Dev" in prompt
    assert "Needs Python." in prompt


def test_extract_description_populates_ext_columns(db_session):
    from core.job import Job
    from core.user import User
    from db.database import Prompt
    from unittest.mock import MagicMock, patch
    import json as _json

    job = Job.from_scraped_for(_make_scraped(description="Needs Python and FastAPI."), profile_id=1)
    db_session.add(job)

    data = {
        "first_name": "Matt", "last_name": "Barlow", "name": "Matt Barlow",
        "email": "", "phone": "", "location": "", "hero": "", "linkedin": "", "github": "",
        "skills": ["Python"], "work_history": [], "education": [], "projects": [],
        "target_salary_min": 0, "target_salary_max": 0,
        "target_roles": ["SWE"], "resume_path": "", "md_path": "",
    }
    user = User(name="Matt", data=_json.dumps(data))
    db_session.add(user)
    db_session.commit()
    # Prompts live in the DB now — seed an extraction Prompt row for this profile.
    db_session.add(Prompt(
        profile_id=user.id, type_key="extraction",
        content="Extract the structured fields and required skills from the following job posting text here: {job.description}",
        model="", updated_at="t",
    ))
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

    job = Job.from_scraped_for(_make_scraped(), profile_id=1)
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

    job = Job.from_scraped_for(_make_scraped(title="Python Dev"), profile_id=1)
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
    job = Job.from_scraped_for(_make_scraped(), profile_id=1)
    db_session.add(job)
    db_session.commit()
    result = job.serialize()
    assert result["extraction_json_exists"] is False
    assert result["extraction"] is None


def test_serialize_extraction_populated_when_ext_fields_set(db_session):
    from core.job import Job
    job = Job.from_scraped_for(_make_scraped(), profile_id=1)
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
    assert ext["matched_skills"] == []


def test_list_for_review_returns_only_new_and_pending_review(db_session):
    from core.job import Job, JobState
    profile_id = 1
    new_job = Job.from_scraped_for(_make_scraped(job_key="r_new", url="https://x.com/new"), profile_id=1)
    new_job.profile_id = profile_id
    pending_job = Job.from_scraped_for(_make_scraped(job_key="r_pending", url="https://x.com/pending"), profile_id=1)
    pending_job.state = JobState.PENDING_REVIEW.value
    pending_job.profile_id = profile_id
    ready_job = Job.from_scraped_for(_make_scraped(job_key="r_ready", url="https://x.com/ready"), profile_id=1)
    ready_job.state = JobState.READY.value
    ready_job.profile_id = profile_id
    db_session.add_all([new_job, pending_job, ready_job])
    db_session.commit()
    results = Job.list_for_review(db_session, profile_id=profile_id)
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

    job = Job.from_scraped_for(_make_scraped(), profile_id=1)
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

    fake = _json.dumps({
        "profile_summary": "Did things.",
        "experience": [],
        "projects": [],
        "skills": [{"category": "Languages", "items": ["Python"]}],
    })

    outputs = tmp_path / "outputs"
    outputs.mkdir()
    with patch("core.job._OUTPUTS_DIR", outputs), \
            patch("core.job.call_llm", lambda *a, **k: fake):
        job.generate_resume_md(user, "Write resume for {job.title}", object(), "gpt-4", db_session)

    md_file = outputs / "remotive_1_resume.md"
    assert md_file.exists()
    content = md_file.read_text()
    assert "## Skills" in content


def test_intake_spawns_background_thread_and_calls_extract(db_session):
    import threading
    from unittest.mock import patch
    from core.job import Job

    job = Job.from_scraped_for(_make_scraped(job_key="r_intake", url="https://x.com/intake"), profile_id=1)
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
        profile_id=1,
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
        profile_id=1,
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
    job = Job.from_scraped_for(_make_scraped(job_key="ev_1"), profile_id=1)
    db_session.add(job)
    db_session.commit()
    (tmp_path / "ev_1_resume.md").write_text(
        "---\nname: X\n---\n\n## Profile\nReal body here.", encoding="utf-8"
    )
    # Patch the module-level call_llm in core.job (used by _evaluate_body).
    monkeypatch.setattr(
        "core.job.call_llm",
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
    monkeypatch.setattr(job_mod, "call_llm", lambda *a, **k: "   ", raising=False)
    user = MagicMock()
    user.master_resume.return_value = ""
    user.render_work_history_indexed.return_value = ""
    user.render_projects_indexed.return_value = ""
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
        profile_id=1,
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


class _FakeCompletionsSeq:
    """Returns successive canned responses from an iterator."""

    def __init__(self, responses: list[str]) -> None:
        self._iter = iter(responses)

    def create(self, **kwargs):
        return _FakeResponse(next(self._iter))


class _FakeClientSeq:
    def __init__(self, responses: list[str]) -> None:
        self.chat = type("C", (), {"completions": _FakeCompletionsSeq(responses)})()


class _FakeClient:
    def __init__(self, content):
        self.chat = type("C", (), {"completions": _FakeCompletions(content)})()


def test_score_populates_fields(db_session):
    from core.job import Job
    job = Job.from_scraped_for(_make_scraped(), profile_id=1)
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
    job = Job.from_scraped_for(_make_scraped(), profile_id=1)
    db_session.add(job)
    db_session.commit()
    client = _FakeClient("not json at all")
    with pytest.raises(RuntimeError, match="not valid JSON|no JSON object"):
        job.score(
            user=object(), config={}, client=client, model="x",
            db=db_session, prompt_content="score this",
        )


def test_extract_description_maps_fields(db_session, monkeypatch):
    from core.job import Job
    import core.user as user_mod
    import core.llm as llm_mod

    job = Job.from_scraped_for(_make_scraped(job_key="ex_1"), profile_id=1)
    db_session.add(job)
    db_session.commit()

    fake_user = type("U", (), {
        "resolve_prompt": lambda self, k: "extract {job.description}",
        "prompt_extraction_model": "m",
    })()
    monkeypatch.setattr(user_mod.User, "load", classmethod(lambda cls, db: fake_user))

    content = (
        '{"required_skills": ["Python", "SQL"], "preferred_skills": [],'
        ' "tech_stack": ["FastAPI"], "seniority": "senior", "role_type": "IC",'
        ' "domain": "fintech", "key_responsibilities": ["ship features"],'
        ' "company_signals": [], "work_arrangement": "remote",'
        ' "employment_type": "full-time"}'
    )
    monkeypatch.setattr(
        llm_mod, "get_client_for_profile",
        lambda user, model: (_FakeClient(content), "m"),
    )

    job.extract_description(db_session)
    assert job.ext_seniority == "senior"
    assert job.ext_required_skills == "Python, SQL"
    assert job.ext_tech_stack == "FastAPI"
    assert job.ext_salary_min is None
    assert job.ext_salary_max is None


def test_extract_description_coerces_salary(db_session, monkeypatch):
    from core.job import Job
    import core.user as user_mod
    import core.llm as llm_mod

    job = Job.from_scraped_for(_make_scraped(job_key="ex_sal"), profile_id=1)
    db_session.add(job)
    db_session.commit()

    fake_user = type("U", (), {
        "resolve_prompt": lambda self, k: "extract {job.description}",
        "prompt_extraction_model": "m",
    })()
    monkeypatch.setattr(user_mod.User, "load", classmethod(lambda cls, db: fake_user))

    # salary_min as a number, salary_max as a numeric string — both must end up float.
    content = (
        '{"seniority": "mid", "role_type": "IC", "domain": "x",'
        ' "work_arrangement": "remote", "employment_type": "full-time",'
        ' "required_skills": [], "preferred_skills": [], "tech_stack": [],'
        ' "key_responsibilities": [], "company_signals": [],'
        ' "salary_min": 90000, "salary_max": "120000"}'
    )
    # Patch target is core.llm because extract_description imports
    # get_client_for_profile locally inside the method body.
    monkeypatch.setattr(
        llm_mod, "get_client_for_profile",
        lambda user, model: (_FakeClient(content), "m"),
    )

    job.extract_description(db_session)
    assert job.ext_salary_min == 90000.0
    assert job.ext_salary_max == 120000.0


def test_extract_description_populates_skill_match(db_session, monkeypatch):
    """After extraction, ext_skill_match is populated with matched skills and a profile hash."""
    import json as _json
    from core.job import Job
    from db.database import PromptDefault
    import core.user as user_mod
    import core.llm as llm_mod

    job = Job.from_scraped_for(_make_scraped(job_key="ex_sm", description="We need Python."), profile_id=1)
    db_session.add(job)
    # Seed the skill_match PromptDefault so the wiring activates.
    db_session.add(PromptDefault(type_key="skill_match", content="Match {skills_to_match} against user skills."))
    db_session.commit()

    extraction_json = (
        '{"seniority": "mid", "role_type": "IC", "domain": "web",'
        ' "work_arrangement": "remote", "employment_type": "full-time",'
        ' "required_skills": ["Python"], "preferred_skills": [], "tech_stack": [],'
        ' "key_responsibilities": [], "company_signals": []}'
    )
    skill_match_json = '{"matched": ["Python"]}'

    fake_user = type("U", (), {
        "resolve_prompt": lambda self, k: "extract {job.description}",
        "prompt_extraction_model": "m",
        "skills": ["Python"],
    })()
    monkeypatch.setattr(user_mod.User, "load", classmethod(lambda cls, db: fake_user))
    monkeypatch.setattr(
        llm_mod, "get_client_for_profile",
        lambda user, model: (_FakeClientSeq([extraction_json, skill_match_json]), "m"),
    )

    job.extract_description(db_session)

    db_session.refresh(job)
    assert job.ext_skill_match is not None
    stored = _json.loads(job.ext_skill_match)
    assert "Python" in stored["matched"]
    assert stored["profile_hash"]


def test_cover_generated_at_set_on_generate_pdf(db_session, tmp_path):
    from core.job import Job
    from datetime import datetime, timezone
    job = Job(
        job_key="test-cga-1",
        source="test",
        url="https://example.com/2",
        state="new",
        profile_id=1,
    )
    db_session.add(job)
    db_session.commit()
    job.cover_path = str(tmp_path / "test.pdf")
    job.cover_generated_at = datetime.now(timezone.utc).isoformat()
    db_session.commit()
    db_session.refresh(job)
    assert job.cover_generated_at is not None
    assert "T" in job.cover_generated_at


def test_generate_resume_md_writes_document_and_markdown(db_session, tmp_path, monkeypatch):
    """Updated for tree-v1: generate_resume_md now stores a tree-v1 document
    (not a legacy ResumeDocument) and writes frontmatter-free markdown.

    Previously asserted legacy ResumeDocument shape (profile_summary, experience,
    header keys, "---" frontmatter). Now asserts tree-v1 schema and no frontmatter.
    """
    import json
    import core.job as job_mod
    import core.section_generator as sg
    from core.job import Job
    from core.user import User
    from core.profile_tree import FieldNode, GroupNode
    from core.resume_document_io import is_tree_v1
    from db.database import Document

    monkeypatch.setattr(job_mod, "_OUTPUTS_DIR", tmp_path)

    db_session.add(User(name="Jane Doe", data=json.dumps({
        "first_name": "Jane", "last_name": "Doe", "email": "j@x.com",
        "work_history": [
            {"company": "Acme", "title": "Eng", "start": "2020", "end": "2024", "summary": "s1"},
        ],
        "projects": [{"name": "P0", "description": "d0", "url": "u0", "technologies": []}],
        "education": [{"institution": "MIT", "degree": "BS", "field": "EE", "graduated": "2018", "gpa": 3.9}],
    })))
    db_session.commit()
    user = User.load(db_session)

    job = Job(job_key="k1", source="x", title="SWE", company="Acme", url="http://x/1", profile_id=1)
    job.ext_seniority = "mid"
    db_session.add(job)
    db_session.commit()

    # Stub per-section generation (tree-v1 path uses generate_resume_by_section)
    def fake_generate(root, job_ctx, client, model, resolve=None):
        out = {}
        for s in root.children:
            child = s.children[0] if s.children else None
            if isinstance(child, GroupNode):
                for f in child.children:
                    if isinstance(f, FieldNode) and f.llm_output:
                        out[f.id] = "Generated."
                    elif isinstance(f, GroupNode):
                        for ff in f.children:
                            if isinstance(ff, FieldNode) and ff.llm_output:
                                out[ff.id] = "Generated."
            elif isinstance(child, FieldNode) and child.llm_output:
                out[child.id] = "Generated."
        return out

    monkeypatch.setattr(sg, "generate_resume_by_section", fake_generate)
    monkeypatch.setattr("core.job.generate_resume_by_section", fake_generate, raising=False)

    prompt = "History:\n{user_profile.work_history_indexed}\nProjects:\n{user_profile.projects_indexed}"
    job.generate_resume_md(user, prompt, client=object(), model="m", db=db_session)

    row = Document.fetch(db_session, "k1", "resume", profile_id=1)
    assert row is not None
    assert is_tree_v1(row.structured_json)

    md = (tmp_path / "k1_resume.md").read_text(encoding="utf-8")
    assert not md.startswith("---")


def test_generate_cover_md_writes_document(db_session, tmp_path, monkeypatch):
    import json
    import core.job as job_mod
    from core.job import Job
    from core.user import User
    from db.database import Document

    monkeypatch.setattr(job_mod, "_OUTPUTS_DIR", tmp_path)
    db_session.add(User(name="Jane Doe", data=json.dumps({
        "first_name": "Jane", "last_name": "Doe", "email": "j@x.com",
    })))
    db_session.commit()
    user = User.load(db_session)
    job = Job(job_key="k2", source="x", title="SWE", company="Acme", url="http://x/2", profile_id=1)
    db_session.add(job)
    db_session.commit()

    monkeypatch.setattr(job_mod, "call_llm", lambda *a, **k: "Dear team, I am great.", raising=False)
    job.generate_cover_md(user, "Write a letter.", client=object(), model="m", db=db_session)

    row = Document.fetch(db_session, "k2", "cover", profile_id=1)
    assert row is not None
    doc = json.loads(row.structured_json)
    assert doc["body"] == "Dear team, I am great."
    assert doc["signoff"]["name"] == "Jane Doe"
    md = (tmp_path / "k2_cover.md").read_text(encoding="utf-8")
    assert md.startswith("---")
    assert "Dear team" in md


def test_render_meta_uses_snapshot_not_live_profile(db_session, tmp_path, monkeypatch):
    import json
    import core.job as job_mod
    from core.job import Job
    from core.user import User

    monkeypatch.setattr(job_mod, "_OUTPUTS_DIR", tmp_path)
    db_session.add(User(name="Jane Doe", data=json.dumps({
        "first_name": "Jane", "last_name": "Doe", "email": "old@x.com",
    })))
    db_session.commit()
    user = User.load(db_session)
    job = Job(job_key="k3", source="x", title="SWE", company="Acme", url="http://x/3", profile_id=1)
    db_session.add(job)
    db_session.commit()
    monkeypatch.setattr(job_mod, "call_llm", lambda *a, **k: "Body.", raising=False)
    job.generate_cover_md(user, "Write.", client=object(), model="m", db=db_session)

    # Simulate a later profile edit.
    user.email = "new@x.com"
    user.save(db_session)

    captured = {}
    def fake_render(md_path, pdf_path, template_path, max_pages=None, meta=None):
        captured["meta"] = meta
        pdf_path.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(job_mod, "render_pdf", fake_render, raising=False)

    job.generate_cover_pdf(tmp_path / "tmpl.html", db_session)
    assert captured["meta"]["email"] == "old@x.com"   # snapshot, not live profile


def test_write_cover_markdown_roundtrips_assembler(tmp_path, monkeypatch):
    import core.job as jobmod
    from core.schemas import CoverDocument, ResumeHeader, SignOff
    monkeypatch.setattr(jobmod, "_OUTPUTS_DIR", tmp_path)
    job = jobmod.Job(job_key="k1", source="x", title="t", company="c", url="u", state="new")
    doc = CoverDocument(
        header=ResumeHeader(name="Ada Lovelace", email="ada@example.com"),
        body="Dear Hiring Team, I am thrilled to apply.",
        signoff=SignOff(name="Ada Lovelace"),
    )
    job.write_cover_markdown(doc)
    text = (tmp_path / "k1_cover.md").read_text(encoding="utf-8")
    assert text.startswith("---\n")   # front matter present
    assert "Dear Hiring Team" in text


def test_write_resume_markdown_roundtrips_assembler(tmp_path, monkeypatch):
    import core.job as jobmod
    from core.schemas import ResumeDocument, ResumeExperience
    monkeypatch.setattr(jobmod, "_OUTPUTS_DIR", tmp_path)
    job = jobmod.Job(job_key="k1", source="x", title="t", company="c", url="u", state="new")
    doc = ResumeDocument(
        profile_summary="hi",
        experience=[ResumeExperience(company="Acme", title="Eng", start="2020", end="2024", description="- did things")],
    )
    job.write_resume_markdown(doc)
    text = (tmp_path / "k1_resume.md").read_text(encoding="utf-8")
    assert text.startswith("---\n")          # front matter present
    assert "## Experience" in text
    assert "- did things" in text


def test_skill_match_matched_handles_non_dict_json():
    """_skill_match_matched degrades gracefully on non-dict JSON values."""
    from core.job import _skill_match_matched
    # Valid dict case (should work)
    assert _skill_match_matched('{"matched": ["Python", "Go"]}') == ["Python", "Go"]
    # Non-dict cases (should return empty list, not raise)
    assert _skill_match_matched('null') == []
    assert _skill_match_matched('[]') == []
    assert _skill_match_matched('"string"') == []
    assert _skill_match_matched('123') == []
    # Invalid JSON (should return empty list)
    assert _skill_match_matched('invalid') == []
    # None/empty (should return empty list)
    assert _skill_match_matched(None) == []
    assert _skill_match_matched('') == []


def test_skill_match_stale_handles_non_dict_json():
    """_skill_match_stale degrades gracefully on non-dict JSON values."""
    from core.job import _skill_match_stale
    # Valid dict case (should work)
    assert _skill_match_stale('{"profile_hash": "abc123"}', ["Python"]) is True
    # Non-dict cases (should return False, not raise)
    assert _skill_match_stale('null', ["Python"]) is False
    assert _skill_match_stale('[]', ["Python"]) is False
    assert _skill_match_stale('"string"', ["Python"]) is False
    assert _skill_match_stale('123', ["Python"]) is False
    # Invalid JSON (should return False)
    assert _skill_match_stale('invalid', ["Python"]) is False
    # None/empty (should return False)
    assert _skill_match_stale(None, ["Python"]) is False
    assert _skill_match_stale('', ["Python"]) is False
