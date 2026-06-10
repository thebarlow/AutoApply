"""Tenant seam: dev-tenant resolution and scoped() query filtering."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import core.job  # noqa: F401
import core.user  # noqa: F401
from core.job import Job
from db.database import Base, Config
from web.tenancy import get_dev_tenant_id, scoped


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_dev_tenant_defaults_to_one_when_unset():
    db = _session()
    assert get_dev_tenant_id(db) == 1


def test_dev_tenant_reads_config_override():
    db = _session()
    db.add(Config(key="dev_tenant_id", value="7"))
    db.commit()
    assert get_dev_tenant_id(db) == 7


def test_dev_tenant_ignores_blank_config():
    db = _session()
    db.add(Config(key="dev_tenant_id", value=""))
    db.commit()
    assert get_dev_tenant_id(db) == 1


def test_scoped_filters_by_profile_id():
    db = _session()
    db.add_all([
        Job(job_key="a", source="s", url="http://a", profile_id=1),
        Job(job_key="b", source="s", url="http://b", profile_id=2),
    ])
    db.commit()
    keys = {j.job_key for j in scoped(db, Job, 1).all()}
    assert keys == {"a"}
