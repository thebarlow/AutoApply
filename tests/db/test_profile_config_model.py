import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.database import Base, ProfileConfig
from db.events import register_tenant_guard


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    register_tenant_guard()
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_profile_config_is_per_tenant(db):
    db.add(ProfileConfig(profile_id=1, key="w1", value="0.6"))
    db.add(ProfileConfig(profile_id=2, key="w1", value="0.9"))
    db.commit()
    v1 = db.query(ProfileConfig).filter_by(profile_id=1, key="w1").first().value
    v2 = db.query(ProfileConfig).filter_by(profile_id=2, key="w1").first().value
    assert (v1, v2) == ("0.6", "0.9")


def test_tenant_guard_rejects_missing_profile_id(db):
    db.add(ProfileConfig(key="w1", value="0.5"))  # no profile_id
    with pytest.raises(ValueError, match="missing profile_id"):
        db.commit()


def test_defaults_cover_all_moved_keys():
    from db.seed import PROFILE_CONFIG_DEFAULTS, DEFAULT_CONFIG
    moved = {
        "w1", "w2", "auto_reject_threshold", "auto_approve_threshold",
        "resume_github", "resume_linkedin", "resume_website",
        "resume_template_path", "cover_template_path",
        "resume_prompt_template", "cover_prompt_template",
        "source_remotive", "source_remoteok",
        "keywords_whitelist", "keywords_blacklist",
        "max_jobs_per_source", "job_searches",
    }
    assert moved.issubset(set(PROFILE_CONFIG_DEFAULTS))
    # Moved keys must NOT remain in the global default seed.
    assert moved.isdisjoint(set(DEFAULT_CONFIG))
