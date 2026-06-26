"""Tests: theme resolution and stamping in generate_resume_pdf."""
from pathlib import Path

import core.job as job_mod
import core.user as user_mod
from core.job import Job
from generator.themes import CLASSIC, MODERN


def test_resolve_default_is_classic(monkeypatch):
    j = Job.__new__(Job)
    j.profile_id = 1
    monkeypatch.setattr(
        user_mod.User,
        "load",
        staticmethod(lambda db, profile_id=None: type("U", (), {"resume_theme": None})()),
    )
    assert j._resolve_resume_theme(db=None) is CLASSIC


def test_resolve_explicit(monkeypatch):
    j = Job.__new__(Job)
    j.profile_id = 1
    monkeypatch.setattr(
        user_mod.User,
        "load",
        staticmethod(lambda db, profile_id=None: type("U", (), {"resume_theme": "modern"})()),
    )
    assert j._resolve_resume_theme(db=None) is MODERN


def test_generate_passes_theme_css_and_stamps(monkeypatch, tmp_path):
    j = Job.__new__(Job)
    j.profile_id = 1
    j.job_key = "k1"
    captured = {}

    monkeypatch.setattr(job_mod, "_OUTPUTS_DIR", tmp_path)
    (tmp_path / "k1_resume.md").write_text("# X\n\nbody", encoding="utf-8")
    monkeypatch.setattr(Job, "_resolve_resume_max_pages", lambda self, db: None)
    monkeypatch.setattr(Job, "_render_meta", lambda self, kind, db: {})
    monkeypatch.setattr(Job, "_resolve_resume_theme", lambda self, db: MODERN)

    def _fake_render(md, pdf, tpl, max_pages=None, meta=None, css_path=None):
        captured["css_path"] = css_path
        Path(pdf).write_bytes(b"%PDF fake")

    monkeypatch.setattr(job_mod, "render_pdf", _fake_render)

    class _DB:
        def commit(self):
            pass

    j.generate_resume_pdf(Path("generator/resume_template.html"), _DB())

    assert captured["css_path"].name == "resume_modern.css"
    assert j.resume_rendered_theme == "modern"
