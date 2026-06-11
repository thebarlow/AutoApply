from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def db_session():
    from db.database import Base
    # These imports register Job and User ORM models with Base.metadata before create_all.
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


def test_upsert_then_fetch(db_session):
    from db.database import Document
    Document.upsert(db_session, "job1", "resume", '{"a": 1}', profile_id=1)
    row = Document.fetch(db_session, "job1", "resume", profile_id=1)
    assert row is not None
    assert row.structured_json == '{"a": 1}'
    assert row.created_at  # ISO timestamp populated


def test_upsert_is_idempotent_per_key(db_session):
    from db.database import Document
    Document.upsert(db_session, "job1", "resume", '{"v": 1}', profile_id=1)
    Document.upsert(db_session, "job1", "resume", '{"v": 2}', profile_id=1)
    rows = db_session.query(Document).filter_by(job_key="job1", doc_type="resume").all()
    assert len(rows) == 1
    assert rows[0].structured_json == '{"v": 2}'


def test_fetch_missing_returns_none(db_session):
    from db.database import Document
    assert Document.fetch(db_session, "nope", "resume", profile_id=1) is None


def test_doc_types_are_independent(db_session):
    from db.database import Document
    Document.upsert(db_session, "job1", "resume", '{"r": 1}', profile_id=1)
    Document.upsert(db_session, "job1", "cover", '{"c": 1}', profile_id=1)
    assert Document.fetch(db_session, "job1", "resume", profile_id=1).structured_json == '{"r": 1}'
    assert Document.fetch(db_session, "job1", "cover", profile_id=1).structured_json == '{"c": 1}'
