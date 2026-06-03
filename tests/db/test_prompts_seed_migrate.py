from __future__ import annotations
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def db_session():
    from db.database import Base
    import core.user  # noqa: F401 — registers User
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


def test_prompt_models_exist_and_persist(db_session):
    from db.database import Prompt, PromptDefault
    db_session.add(PromptDefault(type_key="scoring", content="default scoring body"))
    db_session.add(Prompt(profile_id=1, type_key="scoring", content="body", model="m", updated_at="2026-06-03T00:00:00Z"))
    db_session.commit()
    assert db_session.query(PromptDefault).filter_by(type_key="scoring").first().content == "default scoring body"
    row = db_session.query(Prompt).filter_by(profile_id=1, type_key="scoring").first()
    assert row.content == "body" and row.model == "m"


def test_prompts_unique_profile_type(db_session):
    from db.database import Prompt
    from sqlalchemy.exc import IntegrityError
    db_session.add(Prompt(profile_id=1, type_key="scoring", content="a", model="", updated_at="t"))
    db_session.commit()
    db_session.add(Prompt(profile_id=1, type_key="scoring", content="b", model="", updated_at="t"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
