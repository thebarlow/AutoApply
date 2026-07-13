"""Tests for serve_resume theme-staleness re-render (Task 7).

Behavioral assertions:
  1. Re-renders when profile theme differs from stamped theme AND markdown exists.
  2. Does NOT re-render when theme is the same.
  3. Does NOT re-render when stamp is NULL and profile theme is also classic (NULL).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import web.routers.jobs as jobs_router


def _job(stamped_theme: str | None, pdf_path: Path) -> MagicMock:
    j = MagicMock()
    j.resume_path = str(pdf_path)
    j.resume_rendered_theme = stamped_theme
    j.job_key = "k"
    return j


def _user(theme: str | None):
    return type("U", (), {"resume_theme": theme})()


def test_rerenders_when_theme_differs(monkeypatch, tmp_path):
    """Re-renders when profile theme != stamped theme and markdown is present."""
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"%PDF")
    md = tmp_path / "1_k_resume.md"
    md.write_text("# Resume")

    job = _job("classic", pdf)
    monkeypatch.setattr(jobs_router.Job, "get", staticmethod(lambda *a, **k: job))
    monkeypatch.setattr(
        jobs_router.User,
        "load",
        staticmethod(lambda db, profile_id=None: _user("modern")),
    )
    monkeypatch.setattr(jobs_router, "_OUTPUTS_DIR", tmp_path)

    jobs_router.serve_resume(job_key="k", db=None, profile_id=1)

    job.generate_resume_pdf.assert_called_once()


def test_no_rerender_when_theme_same(monkeypatch, tmp_path):
    """Does NOT re-render when the stamped theme matches the profile theme."""
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"%PDF")
    md = tmp_path / "1_k_resume.md"
    md.write_text("# Resume")

    job = _job("modern", pdf)
    monkeypatch.setattr(jobs_router.Job, "get", staticmethod(lambda *a, **k: job))
    monkeypatch.setattr(
        jobs_router.User,
        "load",
        staticmethod(lambda db, profile_id=None: _user("modern")),
    )
    monkeypatch.setattr(jobs_router, "_OUTPUTS_DIR", tmp_path)

    jobs_router.serve_resume(job_key="k", db=None, profile_id=1)

    job.generate_resume_pdf.assert_not_called()


def test_rerender_failure_falls_back_to_existing_pdf(monkeypatch, tmp_path):
    """When themes differ + markdown exists but generate_resume_pdf raises,
    serve_resume still returns a FileResponse — no exception propagates."""
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"%PDF")
    md = tmp_path / "1_k_resume.md"
    md.write_text("# Resume")

    job = _job("classic", pdf)
    job.generate_resume_pdf.side_effect = RuntimeError("page overflow")
    monkeypatch.setattr(jobs_router.Job, "get", staticmethod(lambda *a, **k: job))
    monkeypatch.setattr(
        jobs_router.User,
        "load",
        staticmethod(lambda db, profile_id=None: _user("modern")),
    )
    monkeypatch.setattr(jobs_router, "_OUTPUTS_DIR", tmp_path)

    from fastapi.responses import FileResponse

    result = jobs_router.serve_resume(job_key="k", db=None, profile_id=1)

    assert isinstance(result, FileResponse)
    job.generate_resume_pdf.assert_called_once()


def test_null_stamp_classic_profile_no_rerender(monkeypatch, tmp_path):
    """NULL stamp treated as 'classic'; classic profile → no re-render."""
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"%PDF")
    md = tmp_path / "1_k_resume.md"
    md.write_text("# Resume")

    job = _job(None, pdf)
    monkeypatch.setattr(jobs_router.Job, "get", staticmethod(lambda *a, **k: job))
    monkeypatch.setattr(
        jobs_router.User,
        "load",
        staticmethod(lambda db, profile_id=None: _user(None)),
    )
    monkeypatch.setattr(jobs_router, "_OUTPUTS_DIR", tmp_path)

    jobs_router.serve_resume(job_key="k", db=None, profile_id=1)

    job.generate_resume_pdf.assert_not_called()
