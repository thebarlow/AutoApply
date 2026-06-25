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


@pytest.fixture
def seeded_job_with_profile_data(db_session):
    """Return a factory: given a data dict, seed a User+Job and return the Job."""
    from core.job import Job
    from core.user import User as UserModel

    def _factory(profile_data: dict) -> Job:
        user_row = UserModel(name="Test", data=json.dumps(profile_data))
        db_session.add(user_row)
        db_session.commit()
        db_session.refresh(user_row)
        job = Job(
            job_key="test_1",
            source="test",
            title="SWE",
            company="Acme",
            url="https://example.com",
            description="Test job",
            profile_id=user_row.id,
        )
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)
        return job

    return _factory


from core.user import _normalize_max_pages


@pytest.mark.parametrize("value,expected", [
    (1, 1), (3, 3), (0, None), (-2, None), (None, None),
    ("2", 2), ("0", None), ("x", None), (True, None), (2.5, None),
])
def test_normalize_max_pages(value, expected):
    assert _normalize_max_pages(value) == expected


def test_resolve_resume_max_pages_integer(db_session, seeded_job_with_profile_data):
    job = seeded_job_with_profile_data({"resume_max_pages": 2})
    assert job._resolve_resume_max_pages(db_session) == 2


def test_resolve_resume_max_pages_absent_is_unlimited(db_session, seeded_job_with_profile_data):
    job = seeded_job_with_profile_data({})
    assert job._resolve_resume_max_pages(db_session) is None


def test_resolve_resume_max_pages_null_is_unlimited(db_session, seeded_job_with_profile_data):
    job = seeded_job_with_profile_data({"resume_max_pages": None})
    assert job._resolve_resume_max_pages(db_session) is None


def test_new_profile_data_seeds_one_page_limit():
    from web.routers.config import _EMPTY_PROFILE_DATA
    assert _EMPTY_PROFILE_DATA.get("resume_max_pages") == 1
