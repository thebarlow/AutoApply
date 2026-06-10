"""User.load resolves the profile passed to it; no active_profile_id fallback."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import core.job  # noqa: F401
from core.user import User
from db.database import Base


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_load_returns_requested_profile():
    db = _session()
    db.add_all([User(id=1, name="A", data="{}"), User(id=2, name="B", data="{}")])
    db.commit()
    assert User.load(db, profile_id=2).name == "B"


def test_load_raises_when_profile_missing():
    db = _session()
    db.add(User(id=1, name="A", data="{}"))
    db.commit()
    with pytest.raises(RuntimeError):
        User.load(db, profile_id=99)
