"""Tests for resume_parse prompt v3 reseed: v1 and v2 stock baselines both upgrade."""
import pathlib
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


def _make_profile(db, prompt_content: str) -> int:
    """Seed a User + resume_parse Prompt row and return the profile id."""
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


def test_v3_file_mentions_headings():
    """The updated prompt file must contain the new *_heading keys."""
    txt = pathlib.Path("prompts/defaults/resume_parse.md").read_text(encoding="utf-8")
    assert "work_history_heading" in txt
    assert "summary_heading" in txt
    assert "education_heading" in txt
    assert "projects_heading" in txt
    assert "skills_heading" in txt


def test_upgrade_from_v1_baseline(db_session):
    """Stock v1 profile is upgraded to v3."""
    from db.database import Prompt
    from db.migrations_data import upgrade_resume_parse_prompt, _V1_BASELINE

    pid = _make_profile(db_session, _V1_BASELINE)
    n = upgrade_resume_parse_prompt(db_session)
    assert n >= 1
    row = db_session.query(Prompt).filter_by(profile_id=pid, type_key="resume_parse").first()
    assert "work_history_heading" in row.content


def test_upgrade_from_v2_baseline(db_session):
    """Stock v2 profile is upgraded to v3."""
    from db.database import Prompt
    from db.migrations_data import upgrade_resume_parse_prompt, _V2_BASELINE

    pid = _make_profile(db_session, _V2_BASELINE)
    n = upgrade_resume_parse_prompt(db_session)
    assert n >= 1
    row = db_session.query(Prompt).filter_by(profile_id=pid, type_key="resume_parse").first()
    assert "work_history_heading" in row.content


def test_customized_prompt_is_left_alone(db_session):
    """A user-customized prompt must not be overwritten."""
    from db.database import Prompt
    from db.migrations_data import upgrade_resume_parse_prompt, _V2_BASELINE

    pid = _make_profile(db_session, _V2_BASELINE + "\n# MY CUSTOM RULE\n")
    upgrade_resume_parse_prompt(db_session)
    row = db_session.query(Prompt).filter_by(profile_id=pid, type_key="resume_parse").first()
    assert "MY CUSTOM RULE" in row.content
    assert "work_history_heading" not in row.content


def test_idempotent(db_session):
    """Running upgrade twice returns 0 on the second call."""
    from db.migrations_data import upgrade_resume_parse_prompt, _V2_BASELINE

    _make_profile(db_session, _V2_BASELINE)
    upgrade_resume_parse_prompt(db_session)
    second = upgrade_resume_parse_prompt(db_session)
    assert second == 0
