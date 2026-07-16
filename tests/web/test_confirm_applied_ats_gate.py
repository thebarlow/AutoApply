from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from db.database import get_db
from web.main import app
from core.schemas import AtsReport, AtsIssue


def _client():
    return TestClient(app)


def _job_with_report(report: AtsReport | None, *, stale: bool = False) -> MagicMock:
    job = MagicMock()
    job.ats_report_json = report.model_dump_json() if report is not None else None
    job.ats_is_stale.return_value = stale
    job.serialize.return_value = {"job_key": "job1"}
    return job


def _with_db():
    fake_db = MagicMock()

    def override_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_db
    return fake_db


def test_confirm_applied_blocked_on_critical():
    bad = AtsReport.build(
        score=0.5,
        issues=[AtsIssue(layer="mechanical", severity="critical", code="contact_order", message="x")],
        extracted_text="t",
    )
    job = _job_with_report(bad)
    _with_db()
    try:
        with patch("web.routers.tray.Job.get", return_value=job), \
             patch("web.routers.tray._emit"):
            resp = _client().post("/api/jobs/job1/confirm-applied")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert resp.status_code == 409
    assert resp.json()["detail"]["passed"] is False
    job.mark_applied.assert_not_called()


def test_confirm_applied_proceeds_when_passed():
    ok = AtsReport.build(score=1.0, issues=[], extracted_text="t")
    job = _job_with_report(ok)
    _with_db()
    try:
        with patch("web.routers.tray.Job.get", return_value=job), \
             patch("web.routers.tray._emit"):
            resp = _client().post("/api/jobs/job1/confirm-applied")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert resp.status_code == 200
    job.mark_applied.assert_called_once()


def test_confirm_applied_no_report_returns_422():
    job = _job_with_report(None)
    _with_db()
    try:
        with patch("web.routers.tray.Job.get", return_value=job), \
             patch("web.routers.tray._emit"):
            resp = _client().post("/api/jobs/job1/confirm-applied")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert resp.status_code == 422
    job.mark_applied.assert_not_called()


def test_confirm_applied_stale_report_returns_422():
    ok = AtsReport.build(score=1.0, issues=[], extracted_text="t")
    job = _job_with_report(ok, stale=True)
    _with_db()
    try:
        with patch("web.routers.tray.Job.get", return_value=job), \
             patch("web.routers.tray._emit"):
            resp = _client().post("/api/jobs/job1/confirm-applied")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert resp.status_code == 422
    job.mark_applied.assert_not_called()
