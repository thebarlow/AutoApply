import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.database import Base, Config, ProfileConfig
import web.routers.config as cfg


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_get_is_per_tenant(db):
    db.add_all([
        ProfileConfig(profile_id=1, key="w1", value="0.7"),
        ProfileConfig(profile_id=2, key="w1", value="0.2"),
    ])
    db.commit()
    assert cfg._get(db, "w1", profile_id=1) == "0.7"
    assert cfg._get(db, "w1", profile_id=2) == "0.2"


def test_get_falls_back_to_profile_defaults(db):
    # No row → the PROFILE_CONFIG_DEFAULTS value (0.3), not an empty string.
    assert cfg._get(db, "auto_reject_threshold", profile_id=1) == "0.3"


def test_explicit_default_wins_over_map(db):
    assert cfg._get(db, "unknown_key", profile_id=1, default="x") == "x"


def test_global_reader_uses_config_table(db):
    db.add(Config(key="dev_tenant_id", value="5"))
    db.commit()
    assert cfg._get_global(db, "dev_tenant_id") == "5"
    # A global row is NOT visible to the per-tenant reader.
    assert cfg._get(db, "dev_tenant_id", profile_id=1, default="") == ""
