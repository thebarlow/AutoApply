import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from db.models import Base, Job, Config, UserProfileModel
from core.types import JobState


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


def test_create_job(db_session):
    job = Job(
        job_key="indeed_12345",
        source="indeed",
        title="Software Engineer",
        company="Acme Corp",
        url="https://indeed.com/viewjob?jk=12345",
        state=JobState.SCRAPED,
    )
    db_session.add(job)
    db_session.commit()

    result = db_session.query(Job).filter_by(job_key="indeed_12345").first()
    assert result.title == "Software Engineer"
    assert result.state == JobState.SCRAPED
    assert result.scraped_at is not None


def test_job_url_uniqueness(db_session):
    url = "https://example.com/job1"
    db_session.add(Job(job_key="k1", source="indeed", url=url, state=JobState.SCRAPED))
    db_session.commit()
    db_session.add(Job(job_key="k2", source="indeed", url=url, state=JobState.SCRAPED))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_job_key_uniqueness(db_session):
    db_session.add(Job(job_key="dup", source="indeed", url="https://a.com/1", state=JobState.SCRAPED))
    db_session.commit()
    db_session.add(Job(job_key="dup", source="indeed", url="https://a.com/2", state=JobState.SCRAPED))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_create_and_retrieve_config(db_session):
    db_session.add(Config(key="w1", value="0.5"))
    db_session.commit()

    result = db_session.query(Config).filter_by(key="w1").first()
    assert result.value == "0.5"


def test_create_user_profile(db_session):
    data = {"name": "Matt", "skills": ["Python", "SQL"]}
    db_session.add(UserProfileModel(data=json.dumps(data)))
    db_session.commit()

    result = db_session.query(UserProfileModel).first()
    assert json.loads(result.data)["name"] == "Matt"
