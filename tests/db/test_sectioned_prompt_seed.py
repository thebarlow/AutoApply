from __future__ import annotations

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


def test_key_registered():
    from db.seed import PROMPT_TYPE_KEYS
    assert "resume_eval_sectioned" in PROMPT_TYPE_KEYS


def test_default_file_seeds_and_resolves(db_session):
    """seed_prompt_defaults loads the .md; resolve_prompt returns it for a fresh profile."""
    from db.seed import seed_prompt_defaults
    from core.user import User

    seed_prompt_defaults(db_session)
    db_session.add(User(name="T", data="{}"))
    db_session.commit()
    u = User.load(db_session)
    content = u.resolve_prompt("resume_eval_sectioned")
    assert "{current_document}" in content
    assert "{sections_to_score}" in content
    assert '"sections"' in content
