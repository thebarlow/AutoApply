"""Backfill populates ext_skill_match for extracted jobs; leaves blank jobs alone."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def db_session():
    from db.database import Base
    import core.job   # noqa: F401 — registers Job mapper
    import core.user  # noqa: F401 — registers User mapper

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


@pytest.fixture
def fake_user(db_session):
    """Minimal User row for profile_id=1."""
    from core.user import User

    u = User(id=1, name="Test", data="{}")
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def make_job(db_session):
    """Factory: create and persist a Job for profile_id=1."""
    from core.job import Job

    def _make(job_key: str, ext_seniority: str = "", ext_required_skills: str = "") -> Job:
        j = Job()
        j.profile_id = 1
        j.job_key = job_key
        j.title = "Dev"
        j.company = "Co"
        j.url = f"https://example.com/{job_key}"
        j.description = "desc"
        j.source = "test"
        j.state = "new"
        j.ext_seniority = ext_seniority or None
        j.ext_required_skills = ext_required_skills or None
        db_session.add(j)
        db_session.commit()
        return j

    return _make


@pytest.fixture
def seed_skill_match_prompt(db_session):
    """Insert a minimal skill_match PromptDefault row."""
    from db.database import PromptDefault

    row = PromptDefault(type_key="skill_match", content="Match these skills: {skills_to_match}")
    db_session.add(row)
    db_session.commit()
    return row


def _fake_client_factory(user):
    """Returns a client whose completions echo back {"matched":["Python"]}."""
    from types import SimpleNamespace

    class _Completions:
        def create(self, **k):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='{"matched":["Python"]}'),
                        finish_reason="stop",
                    )
                ],
                usage=SimpleNamespace(cost=0.0),
            )

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    return _Client(), "test-model"


def test_backfill_populates_only_extracted_jobs(
    db_session, make_job, seed_skill_match_prompt, fake_user
):
    # extracted job: has seniority + required skills → should be matched
    extracted = make_job(job_key="a", ext_seniority="mid", ext_required_skills="Python")
    # blank job: seniority is empty → filter excludes it
    blank = make_job(job_key="b", ext_seniority="", ext_required_skills="")

    from scripts.backfill_skill_match import backfill_skill_match

    n = backfill_skill_match(db_session, profile_id=1, client_factory=_fake_client_factory)

    db_session.refresh(extracted)
    db_session.refresh(blank)

    assert n == 1
    assert "Python" in json.loads(extracted.ext_skill_match)["matched"]
    assert blank.ext_skill_match is None
