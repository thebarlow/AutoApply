# tests/db/test_ats_parse_seed.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def db_session():
    """In-memory SQLite session for isolated database tests."""
    from db.database import Base
    import core.job   # noqa: F401
    import core.user  # noqa: F401
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


def test_seed_ats_parse_prompt_inserts_default(db_session, monkeypatch):
    import db.database as dbmod
    from db.database import PromptDefault
    monkeypatch.setattr(dbmod, "SessionLocal", lambda: db_session, raising=True)
    monkeypatch.setattr(db_session, "close", lambda: None, raising=False)

    dbmod._seed_ats_parse_prompt()
    row = db_session.query(PromptDefault).filter_by(type_key="ats_parse").first()
    assert row is not None and "{extracted_text}" in row.content

    # Idempotent: second run does not duplicate.
    dbmod._seed_ats_parse_prompt()
    rows = db_session.query(PromptDefault).filter_by(type_key="ats_parse").all()
    assert len(rows) == 1
