import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.database import Base, ProfileConfig
from web.routers.jobs import _load_score_config


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_load_score_config_reads_caller_tenant(db):
    db.add(ProfileConfig(profile_id=1, key="w1", value="0.7"))
    db.add(ProfileConfig(profile_id=2, key="w1", value="0.1"))
    db.commit()
    assert _load_score_config(db, profile_id=1)["w1"] == 0.7
    assert _load_score_config(db, profile_id=2)["w1"] == 0.1


def test_load_score_config_defaults_when_absent(db):
    # No rows → PROFILE_CONFIG_DEFAULTS (0.3 / 0.8), matching pre-split behavior.
    cfg = _load_score_config(db, profile_id=9)
    assert cfg["auto_reject_threshold"] == 0.3
    assert cfg["auto_approve_threshold"] == 0.8
