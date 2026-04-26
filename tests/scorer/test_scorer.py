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
    from scripts.seed_profile import seed_profile

    profile_file = tmp_path / "profile.json"
    profile_file.write_text(json.dumps(SAMPLE_PROFILE_DICT))

    seed_profile(db_session, str(profile_file))

    row = db_session.query(UserProfileModel).first()
    assert row is not None
    data = json.loads(row.data)
    assert data["name"] == "Matt Barlow"
    assert data["skills"] == ["Python", "SQL", "FastAPI"]


def test_seed_profile_upserts(db_session, tmp_path):
    from scripts.seed_profile import seed_profile

    profile_file = tmp_path / "profile.json"
    profile_file.write_text(json.dumps(SAMPLE_PROFILE_DICT))

    seed_profile(db_session, str(profile_file))
    seed_profile(db_session, str(profile_file))  # second call must not duplicate

    count = db_session.query(UserProfileModel).count()
    assert count == 1


from scorer.scorer import compute_final_score, determine_state
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
    # exactly at threshold → not approved (> not >=)
    assert determine_state(0.8, reject_threshold=0.3, approve_threshold=0.8) == JobState.PENDING_REVIEW
