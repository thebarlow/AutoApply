from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, SkillAlias


@pytest.fixture
def db_session():
    import core.job  # noqa: F401
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


def test_skill_alias_row_roundtrips(db_session):
    db_session.add(SkillAlias(alias_key="fastapi", canonical="FastAPI"))
    db_session.commit()
    row = db_session.query(SkillAlias).filter_by(alias_key="fastapi").one()
    assert row.canonical == "FastAPI"


def test_seed_skill_aliases_is_idempotent(db_session):
    from db.seed import seed_skill_aliases
    seed_skill_aliases(db_session)
    first = db_session.query(SkillAlias).count()
    # Known curated alias maps to its canonical.
    assert db_session.query(SkillAlias).filter_by(alias_key="js").one().canonical == "JavaScript"
    # Canonical self-row exists.
    assert db_session.query(SkillAlias).filter_by(alias_key="javascript").one().canonical == "JavaScript"
    seed_skill_aliases(db_session)
    assert db_session.query(SkillAlias).count() == first
