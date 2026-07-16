"""Price card + fresh-vs-regen resolver."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core import pricing


@pytest.fixture
def db_session():
    from db.database import Base
    import core.job   # noqa: F401
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


def test_default_prices():
    assert pricing.price_for("intake") == 2
    assert pricing.price_for("generate_fresh") == 4
    assert pricing.price_for("regenerate") == 2
    for small in ("score", "extract", "resume_parse", "ats", "rematch", "draft"):
        assert pricing.price_for(small) == 1


def test_price_env_override(monkeypatch):
    monkeypatch.setenv("PRICE_GENERATE_FRESH", "7")
    assert pricing.price_for("generate_fresh") == 7


def test_unknown_action_raises():
    with pytest.raises(KeyError):
        pricing.price_for("nonsense")


def test_unit_usd_default_and_override(monkeypatch):
    assert pricing.unit_usd() == 0.02
    monkeypatch.setenv("CREDIT_UNIT_USD", "0.05")
    assert pricing.unit_usd() == 0.05


def _make_job(db, **kw):
    from core.job import Job
    job = Job(job_key="j1", profile_id=1, source="test", title="T",
              company="C", url="u", description="d", **kw)
    db.add(job)
    db.commit()
    return job


def test_resolver_fresh_when_no_document_or_path(db_session):
    job = _make_job(db_session)
    assert pricing.resolve_generate_action(db_session, job, "resume") == "generate_fresh"
    assert pricing.resolve_generate_action(db_session, job, "cover") == "generate_fresh"


def test_resolver_regen_when_document_row_exists(db_session):
    from db.database import Document
    job = _make_job(db_session)
    Document.upsert(db_session, "j1", "resume", "{}", profile_id=1)
    assert pricing.resolve_generate_action(db_session, job, "resume") == "regenerate"
    # cover has no row -> still fresh
    assert pricing.resolve_generate_action(db_session, job, "cover") == "generate_fresh"


def test_resolver_regen_when_output_path_set(db_session):
    job = _make_job(db_session, cover_path="C:/somewhere/out.pdf")
    assert pricing.resolve_generate_action(db_session, job, "cover") == "regenerate"
