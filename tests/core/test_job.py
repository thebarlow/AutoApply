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
    assert job.state == "draft"


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
