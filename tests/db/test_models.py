import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from db.models import Base, Job, Config, UserProfileModel
from core.types import JobState
from db.database import init_db, get_db, SessionLocal
from db.seed import seed_default_config, DEFAULT_CONFIG


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
        state=JobState.DRAFT,
    )
    db_session.add(job)
    db_session.commit()

    result = db_session.query(Job).filter_by(job_key="indeed_12345").first()
    assert result.title == "Software Engineer"
    assert result.state == JobState.DRAFT
    assert result.scraped_at is not None


def test_job_url_uniqueness(db_session):
    url = "https://example.com/job1"
    db_session.add(Job(job_key="k1", source="indeed", url=url, state=JobState.DRAFT))
    db_session.commit()
    db_session.add(Job(job_key="k2", source="indeed", url=url, state=JobState.DRAFT))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_job_key_uniqueness(db_session):
    db_session.add(Job(job_key="dup", source="indeed", url="https://a.com/1", state=JobState.DRAFT))
    db_session.commit()
    db_session.add(Job(job_key="dup", source="indeed", url="https://a.com/2", state=JobState.DRAFT))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_create_and_retrieve_config(db_session):
    db_session.add(Config(key="w1", value="0.5"))
    db_session.commit()

    result = db_session.query(Config).filter_by(key="w1").first()
    assert result.value == "0.5"


def test_create_user_profile(db_session):
    data = {"name": "Matt", "skills": ["Python", "SQL"]}
    db_session.add(UserProfileModel(name="Matt", data=json.dumps(data)))
    db_session.commit()

    result = db_session.query(UserProfileModel).first()
    assert result.name == "Matt"
    assert json.loads(result.data)["name"] == "Matt"


def test_init_db_creates_tables(monkeypatch, tmp_path):
    import importlib
    from sqlalchemy import inspect as sa_inspect

    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    import db.database as db_module
    importlib.reload(db_module)

    db_module.init_db()

    inspector = sa_inspect(db_module.engine)
    assert "jobs" in inspector.get_table_names()
    assert "config" in inspector.get_table_names()
    assert "user_profile" in inspector.get_table_names()

    db_module.engine.dispose()
    importlib.reload(db_module)  # restore module state for other tests


def test_seed_default_config(db_session):
    seed_default_config(db_session)

    w1 = db_session.query(Config).filter_by(key="w1").first()
    assert w1 is not None
    assert float(w1.value) == 0.5

    reject = db_session.query(Config).filter_by(key="auto_reject_threshold").first()
    assert float(reject.value) == 0.3


def test_seed_is_idempotent(db_session):
    seed_default_config(db_session)
    seed_default_config(db_session)  # second call must not raise or duplicate

    results = db_session.query(Config).filter_by(key="w1").all()
    assert len(results) == 1


def test_resume_prompt_template_seeded(db_session):
    seed_default_config(db_session)
    row = db_session.query(Config).filter_by(key="resume_prompt_template").first()
    assert row is not None
    assert "{profile}" in row.value
    assert "{job}" in row.value
    assert row.value.format(profile="p", job="j")


def test_cover_prompt_template_seeded(db_session):
    seed_default_config(db_session)
    row = db_session.query(Config).filter_by(key="cover_prompt_template").first()
    assert row is not None
    assert "{profile}" in row.value
    assert "{job}" in row.value
    assert row.value.format(profile="p", job="j")


def test_contact_link_keys_seeded(db_session):
    seed_default_config(db_session)
    for key in ("resume_github", "resume_linkedin", "resume_website"):
        row = db_session.query(Config).filter_by(key=key).first()
        assert row is not None
        assert row.value == ""


def test_scraper_config_keys_seeded(db_session):
    seed_default_config(db_session)
    row = db_session.query(Config).filter_by(key="max_jobs_per_source").first()
    assert row is not None
    assert row.value == "50"

    row2 = db_session.query(Config).filter_by(key="scraper_sources").first()
    assert row2 is not None
    assert row2.value == "remotive,remoteok"


def test_job_has_extraction_md_column(db_session):
    job = Job(
        job_key="test_extraction",
        source="test",
        url="https://example.com/1",
        state="draft",
        extraction_md="# Extracted\n- Python required",
    )
    db_session.add(job)
    db_session.commit()
    fetched = db_session.query(Job).filter_by(job_key="test_extraction").first()
    assert fetched.extraction_md == "# Extracted\n- Python required"
