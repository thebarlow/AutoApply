from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.schemas import AtsReport, AtsIssue


@pytest.fixture
def db_session():
    from db.database import Base
    import core.job   # noqa: F401
    import core.user  # noqa: F401
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


def _job():
    from core.job import Job
    return Job(job_key="job1")


def test_store_ats_report_sets_columns(db_session):
    job = _job()
    report = AtsReport.build(score=0.9, issues=[], extracted_text="t")
    job.store_ats_report(report)
    assert job.ats_passed is True
    assert job.ats_score == 0.9
    assert job.ats_report_json is not None
    assert job.ats_checked_at  # ISO timestamp set


def test_store_ats_report_records_failure(db_session):
    job = _job()
    report = AtsReport.build(
        score=0.3,
        issues=[AtsIssue(layer="mechanical", severity="critical", code="no_text_layer", message="x")],
        extracted_text="t",
    )
    job.store_ats_report(report)
    assert job.ats_passed is False
    round_tripped = AtsReport.model_validate_json(job.ats_report_json)
    assert round_tripped.passed is False


def test_ats_is_stale_when_never_checked(db_session):
    job = _job()
    assert job.ats_is_stale() is True


def test_ats_is_stale_false_after_check(db_session):
    job = _job()
    job.resume_generated_at = "2026-06-05T10:00:00+00:00"
    job.store_ats_report(AtsReport.build(score=1.0, issues=[], extracted_text="t"))
    assert job.ats_is_stale() is False


def test_ats_is_stale_when_resume_rerendered_after_check(db_session):
    job = _job()
    job.store_ats_report(AtsReport.build(score=1.0, issues=[], extracted_text="t"))
    # Résumé re-rendered after the check (later timestamp).
    job.resume_generated_at = "2999-01-01T00:00:00+00:00"
    assert job.ats_is_stale() is True
