from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from web.main import app
from core.schemas import AtsReport, AtsIssue


def _client():
    return TestClient(app)


def test_confirm_applied_blocked_on_critical():
    bad = AtsReport.build(
        score=0.5,
        issues=[AtsIssue(layer="mechanical", severity="critical", code="contact_order", message="x")],
        extracted_text="t",
    )
    with patch("web.routers.tray._gate_report_for", return_value=bad), \
         patch("web.routers.tray.Job.get") as get, \
         patch("web.routers.tray.Job.mark_applied") as mark:
        get.return_value = object()  # non-None job so we pass the 404 check
        resp = _client().post("/api/jobs/job1/confirm-applied")
    assert resp.status_code == 409
    assert resp.json()["detail"]["passed"] is False
    mark.assert_not_called()


def test_confirm_applied_proceeds_when_passed():
    from unittest.mock import MagicMock
    from db.database import get_db

    ok = AtsReport.build(score=1.0, issues=[], extracted_text="t")
    fake_db = MagicMock()

    def override_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_db
    try:
        with patch("web.routers.tray._gate_report_for", return_value=ok), \
             patch("web.routers.tray.Job.get") as get, \
             patch("web.routers.tray._emit"):
            job = get.return_value
            job.serialize.return_value = {"job_key": "job1"}
            resp = _client().post("/api/jobs/job1/confirm-applied")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert resp.status_code == 200
    job.mark_applied.assert_called_once()


def test_gate_report_for_resolves_model_without_attribute_error(monkeypatch):
    import web.routers.tray as tray

    class _FakeJob:
        def run_ats_check(self, db, user, client, model):
            from core.schemas import AtsReport
            return AtsReport.build(score=1.0, issues=[], extracted_text="")

    captured = {}

    def _fake_get_client(user, model_override=""):
        captured["called"] = True
        return (object(), "some-model")

    monkeypatch.setattr(tray, "get_client_for_profile", _fake_get_client)
    monkeypatch.setattr(tray.User, "load", classmethod(lambda cls, db: object()))

    report = tray._gate_report_for(_FakeJob(), db=object())
    assert report.passed is True
    assert captured.get("called") is True
