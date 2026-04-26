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
