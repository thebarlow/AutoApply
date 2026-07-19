"""Job core methods must scope by profile_id."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import core.user  # noqa: F401
from core.job import Job
from db.database import Base


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _add(db, key, url, profile_id):
    db.add(Job(job_key=key, source="s", url=url, state="new", profile_id=profile_id))
    db.commit()


def test_get_scopes_to_tenant():
    db = _session()
    _add(db, "k", "http://x", 1)
    assert Job.get("k", db, profile_id=1) is not None
    assert Job.get("k", db, profile_id=2) is None


def test_two_tenants_can_share_a_job_key():
    db = _session()
    _add(db, "k", "http://x1", 1)
    _add(db, "k", "http://x2", 2)  # same job_key, different tenant — must not collide
    assert Job.get("k", db, profile_id=1).url == "http://x1"
    assert Job.get("k", db, profile_id=2).url == "http://x2"


def test_from_scraped_stamps_profile_id():
    job = Job.from_scraped_for(_FakeScraped(), profile_id=3)
    assert job.profile_id == 3


class _FakeScraped:
    job_key = "fk"; source = "s"; title = "t"; company = "c"; url = "http://fk"
    description = ""; location = ""; salary = ""; remote = False; posted_at = ""
