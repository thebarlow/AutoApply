"""Skill aliases are per-tenant."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import core.job  # noqa: F401
import core.user  # noqa: F401
from db.database import Base, SkillAlias


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


@pytest.mark.xfail(reason="composite PK on (profile_id, alias_key) lands in Task 9", strict=True)
def test_alias_lookup_is_tenant_scoped():
    db = _session()
    db.add_all([
        SkillAlias(profile_id=1, alias_key="js", canonical="JavaScript"),
        SkillAlias(profile_id=2, alias_key="js", canonical="Java"),
    ])
    db.commit()
    t1 = {r.canonical for r in db.query(SkillAlias).filter_by(profile_id=1).all()}
    t2 = {r.canonical for r in db.query(SkillAlias).filter_by(profile_id=2).all()}
    assert t1 == {"JavaScript"} and t2 == {"Java"}
