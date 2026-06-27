"""Tests for the idempotent resume_parse prompt v2 reseed migration."""
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
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


def _make_profile(db, prompt_content):
    from db.database import Prompt
    from core.user import User

    u = User(name="P", data="{}")
    db.add(u)
    db.flush()
    db.add(
        Prompt(
            profile_id=u.id,
            type_key="resume_parse",
            content=prompt_content,
            model="",
            updated_at="t",
        )
    )
    db.commit()
    return u.id


def test_stock_prompt_is_upgraded(db_session):
    from db.database import Prompt
    from db.migrations_data import upgrade_resume_parse_prompt, _V1_BASELINE

    pid = _make_profile(db_session, _V1_BASELINE)
    n = upgrade_resume_parse_prompt(db_session)
    row = db_session.query(Prompt).filter_by(profile_id=pid, type_key="resume_parse").first()
    assert "extra_sections" in row.content
    assert n >= 1


def test_customized_prompt_is_left_alone(db_session):
    from db.database import Prompt
    from db.migrations_data import upgrade_resume_parse_prompt, _V1_BASELINE

    pid = _make_profile(db_session, _V1_BASELINE + "\n# MY CUSTOM RULE\n")
    upgrade_resume_parse_prompt(db_session)
    row = db_session.query(Prompt).filter_by(profile_id=pid, type_key="resume_parse").first()
    assert "MY CUSTOM RULE" in row.content
    assert "extra_sections" not in row.content


def test_idempotent(db_session):
    from db.migrations_data import upgrade_resume_parse_prompt, _V1_BASELINE

    _make_profile(db_session, _V1_BASELINE)
    upgrade_resume_parse_prompt(db_session)
    second = upgrade_resume_parse_prompt(db_session)
    assert second == 0
