"""Document.fetch/upsert must scope by profile_id."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import core.job  # noqa: F401
import core.user  # noqa: F401
from db.database import Base, Document


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_upsert_stamps_and_fetch_scopes():
    db = _session()
    Document.upsert(db, "job1", "resume", "{}", profile_id=1)
    assert Document.fetch(db, "job1", "resume", profile_id=1) is not None
    assert Document.fetch(db, "job1", "resume", profile_id=2) is None


@pytest.mark.xfail(reason="composite unique lands in Task 9", strict=True)
def test_two_tenants_independent_docs_same_job_key():
    db = _session()
    Document.upsert(db, "job1", "resume", '{"t":1}', profile_id=1)
    Document.upsert(db, "job1", "resume", '{"t":2}', profile_id=2)
    assert Document.fetch(db, "job1", "resume", profile_id=1).structured_json == '{"t":1}'
    assert Document.fetch(db, "job1", "resume", profile_id=2).structured_json == '{"t":2}'
