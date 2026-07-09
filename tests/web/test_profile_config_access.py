import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.database import Base
import web.routers.config as cfg


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_set_get_roundtrip_is_per_tenant(db):
    cfg._set(db, "w1", "0.7", profile_id=1)
    cfg._set(db, "w1", "0.2", profile_id=2)
    assert cfg._get(db, "w1", profile_id=1) == "0.7"
    assert cfg._get(db, "w1", profile_id=2) == "0.2"


def test_get_falls_back_to_profile_defaults(db):
    # No row → the PROFILE_CONFIG_DEFAULTS value (0.3), not an empty string.
    assert cfg._get(db, "auto_reject_threshold", profile_id=1) == "0.3"


def test_explicit_default_wins_over_map(db):
    assert cfg._get(db, "unknown_key", profile_id=1, default="x") == "x"


def test_global_helpers_use_config_table(db):
    cfg._set_global(db, "dev_tenant_id", "5")
    assert cfg._get_global(db, "dev_tenant_id") == "5"
    # Global write is NOT visible to the per-tenant reader and vice-versa.
    assert cfg._get(db, "dev_tenant_id", profile_id=1, default="") == ""
