"""before_flush guard rejects tenant-owned inserts missing profile_id."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import core.user  # noqa: F401
from core.job import Job
from db.database import Base
from db.events import register_tenant_guard


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    register_tenant_guard()
    return sessionmaker(bind=engine)()


def test_insert_without_profile_id_raises():
    db = _session()
    db.add(Job(job_key="k", source="s", url="http://x", state="new"))  # no profile_id
    with pytest.raises(ValueError, match="profile_id"):
        db.flush()


def test_insert_with_profile_id_ok():
    db = _session()
    db.add(Job(job_key="k", source="s", url="http://x", state="new", profile_id=1))
    db.flush()  # must not raise
