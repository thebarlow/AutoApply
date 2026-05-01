import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, UserProfileModel
from core.types import UserProfile, WorkHistoryEntry, EducationEntry


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


SAMPLE_PROFILE_DICT = {
    "name": "Matt Barlow",
    "email": "matt@example.com",
    "phone": "555-1234",
    "location": "Remote",
    "skills": ["Python", "SQL", "FastAPI"],
    "work_history": [
        {
            "company": "Acme Corp",
            "title": "Software Engineer",
            "start": "2022-01",
            "end": "2024-01",
            "summary": "Built internal tooling.",
        }
    ],
    "education": [
        {
            "institution": "Columbia University",
            "degree": "B.S.",
            "field": "Electrical Engineering",
            "graduated": "2018",
            "gpa": 3.5,
        }
    ],
    "target_salary_min": 120000,
    "target_salary_max": 160000,
    "target_roles": ["Software Engineer", "Backend Engineer"],
    "resume_path": "",
}


def test_seed_profile_inserts(db_session, tmp_path):
    from db.seed_profile import seed_profile

    profile_file = tmp_path / "profile.json"
    profile_file.write_text(json.dumps(SAMPLE_PROFILE_DICT))

    seed_profile(db_session, str(profile_file))

    row = db_session.query(UserProfileModel).first()
    assert row is not None
    data = json.loads(row.data)
    assert data["name"] == "Matt Barlow"
    assert data["skills"] == ["Python", "SQL", "FastAPI"]


def test_seed_profile_upserts(db_session, tmp_path):
    from db.seed_profile import seed_profile

    profile_file = tmp_path / "profile.json"
    profile_file.write_text(json.dumps(SAMPLE_PROFILE_DICT))

    seed_profile(db_session, str(profile_file))
    seed_profile(db_session, str(profile_file))  # second call must not duplicate

    count = db_session.query(UserProfileModel).count()
    assert count == 1


from core.scorer import compute_final_score, determine_state
from core.types import JobState


def test_compute_final_score_equal_weights():
    assert compute_final_score(0.5, 0.5, 0.8, 0.6) == pytest.approx(0.7)


def test_compute_final_score_unequal_weights():
    assert compute_final_score(0.8, 0.2, 1.0, 0.0) == pytest.approx(0.8)


def test_compute_final_score_clamps_above_one():
    assert compute_final_score(1.0, 1.0, 1.0, 1.0) == pytest.approx(1.0)


def test_determine_state_approved():
    assert determine_state(0.9, reject_threshold=0.3, approve_threshold=0.8) == JobState.APPROVED


def test_determine_state_rejected():
    assert determine_state(0.2, reject_threshold=0.3, approve_threshold=0.8) == JobState.REJECTED


def test_determine_state_pending_review():
    assert determine_state(0.5, reject_threshold=0.3, approve_threshold=0.8) == JobState.PENDING_REVIEW


def test_determine_state_boundary_reject():
    # exactly at threshold → not rejected (< not <=)
    assert determine_state(0.3, reject_threshold=0.3, approve_threshold=0.8) == JobState.PENDING_REVIEW


def test_determine_state_boundary_approve():
    # exactly at threshold → approved (>= semantics)
    assert determine_state(0.8, reject_threshold=0.3, approve_threshold=0.8) == JobState.APPROVED


import json as _json
from db.models import Config, Job, UserProfileModel
from core.scorer import load_user_profile, load_config


def test_load_user_profile(db_session):
    db_session.add(UserProfileModel(data=_json.dumps(SAMPLE_PROFILE_DICT)))
    db_session.commit()

    profile = load_user_profile(db_session)
    assert isinstance(profile, UserProfile)
    assert profile.name == "Matt Barlow"
    assert isinstance(profile.work_history[0], WorkHistoryEntry)
    assert isinstance(profile.education[0], EducationEntry)


def test_load_user_profile_missing(db_session):
    with pytest.raises(SystemExit):
        load_user_profile(db_session)


def test_load_config(db_session):
    for key, value in [("w1", "0.6"), ("w2", "0.4"), ("auto_reject_threshold", "0.25"), ("auto_approve_threshold", "0.75")]:
        db_session.add(Config(key=key, value=value))
    db_session.commit()

    config = load_config(db_session)
    assert config["w1"] == pytest.approx(0.6)
    assert config["w2"] == pytest.approx(0.4)
    assert config["auto_reject_threshold"] == pytest.approx(0.25)
    assert config["auto_approve_threshold"] == pytest.approx(0.75)


from core.scorer import build_prompt, parse_claude_response


def test_build_prompt_contains_job_fields():
    profile = UserProfile(
        name="Matt",
        skills=["Python", "SQL"],
        work_history=[
            WorkHistoryEntry(company="Acme", title="Engineer", start="2022-01", end="2024-01", summary="Built things.")
        ],
        education=[
            EducationEntry(institution="Columbia", degree="B.S.", field="EE", graduated="2018", gpa=3.5)
        ],
        target_salary_min=120000,
        target_salary_max=160000,
        target_roles=["Software Engineer"],
    )
    job = Job(
        job_key="test_001",
        source="indeed",
        title="Backend Engineer",
        company="TechCorp",
        location="Remote",
        salary="$130k-$150k",
        description="We need a Python expert.",
        url="https://example.com/job/1",
        state=JobState.SCRAPED,
    )

    prompt = build_prompt(job, profile)
    assert "Backend Engineer" in prompt
    assert "TechCorp" in prompt
    assert "Python" in prompt
    assert "Matt" in prompt
    assert "120000" in prompt


def test_parse_claude_response_valid():
    raw = json.dumps({
        "desirability_score": 0.85,
        "fit_score": 0.70,
        "desirability_justification": "Good salary, remote.",
        "fit_justification": "Python matches well.",
    })

    result = parse_claude_response(raw)
    assert result["desirability_score"] == pytest.approx(0.85)
    assert result["fit_score"] == pytest.approx(0.70)
    assert result["desirability_justification"] == "Good salary, remote."
    assert result["fit_justification"] == "Python matches well."


def test_parse_claude_response_invalid_returns_none():
    result = parse_claude_response("not valid json at all")
    assert result is None


def test_parse_claude_response_missing_keys_returns_none():
    result = parse_claude_response(json.dumps({"desirability_score": 0.8}))
    assert result is None


from unittest.mock import MagicMock
from core.scorer import score_job


MOCK_CLAUDE_RESPONSE = _json.dumps({
    "desirability_score": 0.85,
    "fit_score": 0.75,
    "desirability_justification": "Good salary, fully remote.",
    "fit_justification": "Python and SQL match perfectly.",
})

MOCK_CLAUDE_RESPONSE_LOW = _json.dumps({
    "desirability_score": 0.1,
    "fit_score": 0.15,
    "desirability_justification": "Poor salary, on-site only.",
    "fit_justification": "Requires Java, candidate has none.",
})

MOCK_CLAUDE_RESPONSE_MID = _json.dumps({
    "desirability_score": 0.5,
    "fit_score": 0.55,
    "desirability_justification": "Decent role.",
    "fit_justification": "Partial skill match.",
})


@pytest.fixture
def seeded_db(db_session):
    """DB with profile and config seeded."""
    db_session.add(UserProfileModel(data=_json.dumps(SAMPLE_PROFILE_DICT)))
    for key, value in [("w1", "0.5"), ("w2", "0.5"), ("auto_reject_threshold", "0.3"), ("auto_approve_threshold", "0.8")]:
        db_session.add(Config(key=key, value=value))
    db_session.commit()
    return db_session


def make_job(job_key: str, state: JobState = JobState.SCRAPED) -> Job:
    return Job(
        job_key=job_key,
        source="indeed",
        title="Software Engineer",
        company="TechCorp",
        location="Remote",
        salary="$130k",
        description="Python and SQL required.",
        url=f"https://example.com/{job_key}",
        state=state,
    )


def mock_client(response_text: str):
    client = MagicMock()
    message = MagicMock()
    message.content = [MagicMock(text=response_text)]
    client.messages.create.return_value = message
    return client


def test_score_job_approved(seeded_db):
    job = make_job("job_001")
    seeded_db.add(job)
    seeded_db.commit()

    profile = load_user_profile(seeded_db)
    config = load_config(seeded_db)
    client = mock_client(MOCK_CLAUDE_RESPONSE)

    score_job(job, profile, config, client, seeded_db)
    seeded_db.refresh(job)

    assert job.state == JobState.APPROVED
    assert job.desirability_score == pytest.approx(0.85)
    assert job.fit_score == pytest.approx(0.75)
    assert job.final_score == pytest.approx(0.8)
    justification = _json.loads(job.score_justification)
    assert "desirability" in justification
    assert "fit" in justification


def test_score_job_rejected(seeded_db):
    job = make_job("job_002")
    seeded_db.add(job)
    seeded_db.commit()

    profile = load_user_profile(seeded_db)
    config = load_config(seeded_db)
    client = mock_client(MOCK_CLAUDE_RESPONSE_LOW)

    score_job(job, profile, config, client, seeded_db)
    seeded_db.refresh(job)

    assert job.state == JobState.REJECTED
    assert job.final_score == pytest.approx(0.125)


def test_score_job_pending_review(seeded_db):
    job = make_job("job_003")
    seeded_db.add(job)
    seeded_db.commit()

    profile = load_user_profile(seeded_db)
    config = load_config(seeded_db)
    client = mock_client(MOCK_CLAUDE_RESPONSE_MID)

    score_job(job, profile, config, client, seeded_db)
    seeded_db.refresh(job)

    assert job.state == JobState.PENDING_REVIEW


def test_malformed_claude_response(seeded_db):
    job = make_job("job_004")
    seeded_db.add(job)
    seeded_db.commit()

    profile = load_user_profile(seeded_db)
    config = load_config(seeded_db)
    client = mock_client("not valid json")

    score_job(job, profile, config, client, seeded_db)
    seeded_db.refresh(job)

    assert job.state == JobState.SCRAPED
    assert job.final_score is None


from core.scorer import run_scorer


def test_score_batch_skips_non_scraped(seeded_db):
    scraped1 = make_job("batch_001", JobState.SCRAPED)
    scraped2 = make_job("batch_002", JobState.SCRAPED)
    already_approved = make_job("batch_003", JobState.APPROVED)
    seeded_db.add_all([scraped1, scraped2, already_approved])
    seeded_db.commit()

    client = mock_client(MOCK_CLAUDE_RESPONSE)
    run_scorer(seeded_db, client, job_key=None)

    seeded_db.refresh(scraped1)
    seeded_db.refresh(scraped2)
    seeded_db.refresh(already_approved)

    assert scraped1.state == JobState.APPROVED
    assert scraped2.state == JobState.APPROVED
    assert already_approved.state == JobState.APPROVED  # unchanged
    assert client.messages.create.call_count == 2  # only SCRAPED jobs called Claude


def test_single_job_key_flag(seeded_db):
    target = make_job("single_001", JobState.SCRAPED)
    other = make_job("single_002", JobState.SCRAPED)
    seeded_db.add_all([target, other])
    seeded_db.commit()

    client = mock_client(MOCK_CLAUDE_RESPONSE)
    run_scorer(seeded_db, client, job_key="single_001")

    seeded_db.refresh(target)
    seeded_db.refresh(other)

    assert target.state == JobState.APPROVED
    assert other.state == JobState.SCRAPED  # untouched
    assert client.messages.create.call_count == 1
