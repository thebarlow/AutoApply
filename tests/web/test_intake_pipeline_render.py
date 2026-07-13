"""Unit tests for _render_doc_from_json (tree-v1 vs legacy resume dispatch)."""
from __future__ import annotations

import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


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


def _make_job(db_session):
    """Create a minimal Job row and return it."""
    from core.job import Job
    from scraper.base import ScrapedJob
    scraped = ScrapedJob(
        source="remotive", job_key="test_render_1", title="SWE", company="Acme",
        url="https://example.com/1", description="Python required.",
        location="Remote", salary="$120k", remote=True, posted_at="2026-01-01",
    )
    job = Job.from_scraped_for(scraped, profile_id=1)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def _make_user(db_session):
    """Create a minimal User row and return it."""
    import json as _json
    from core.user import User
    data = {
        "first_name": "Test", "last_name": "User", "name": "Test User",
        "email": "t@x.com", "phone": "", "location": "Remote", "hero": "",
        "linkedin": "", "github": "",
        "skills": ["Python"], "work_history": [], "education": [],
        "projects": [], "target_salary_min": 100000, "target_salary_max": 150000,
        "target_roles": ["SWE"], "resume_path": "", "md_path": "",
    }
    db_session.add(User(name="Test", data=_json.dumps(data)))
    db_session.commit()
    return User.load(db_session)


def test_render_tree_v1_resume_no_frontmatter(db_session, monkeypatch, tmp_path):
    """tree-v1 resume JSON produces markdown WITHOUT '---' frontmatter prefix."""
    from web.intake_pipeline import _render_doc_from_json
    from core.document_tree import build_resume_document_tree
    from core.resume_document_io import serialize_document_tree
    from core.paths import OUTPUTS_DIR

    # No-op PDF generation (avoids Chromium)
    monkeypatch.setattr("core.job.Job.generate_resume_pdf", lambda self, *a, **k: None)

    user = _make_user(db_session)
    job = _make_job(db_session)

    tree = build_resume_document_tree(user.profile_tree_root(), {})
    tree_json = serialize_document_tree(tree)

    template_path = Path("generator/resume_template.html")
    _render_doc_from_json(job, "resume", tree_json, template_path, db_session)

    md_path = OUTPUTS_DIR / f"{job.profile_id}_{job.job_key}_resume.md"
    md_content = md_path.read_text(encoding="utf-8")
    assert not md_content.startswith("---"), "tree-v1 resume should NOT have frontmatter"


def test_render_legacy_resume_has_frontmatter(db_session, monkeypatch, tmp_path):
    """Legacy ResumeDocument JSON produces markdown WITH '---' frontmatter prefix."""
    from web.intake_pipeline import _render_doc_from_json
    from core.schemas import ResumeDocument
    from core.paths import OUTPUTS_DIR

    monkeypatch.setattr("core.job.Job.generate_resume_pdf", lambda self, *a, **k: None)

    job = _make_job(db_session)

    legacy_json = ResumeDocument().model_dump_json()

    template_path = Path("generator/resume_template.html")
    _render_doc_from_json(job, "resume", legacy_json, template_path, db_session)

    md_path = OUTPUTS_DIR / f"{job.profile_id}_{job.job_key}_resume.md"
    md_content = md_path.read_text(encoding="utf-8")
    assert md_content.startswith("---"), "Legacy resume SHOULD have frontmatter"
