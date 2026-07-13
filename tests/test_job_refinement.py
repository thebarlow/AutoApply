"""Unit tests for Job evaluate/refine methods."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.job import Job, _strip_yaml_frontmatter
from db.database import Base


# ─── _strip_yaml_frontmatter ──────────────────────────────────────────────────

class TestStripYamlFrontmatter:
    def test_extracts_frontmatter_and_body(self):
        text = "---\nname: John\nemail: j@example.com\n---\n\n## Profile\nContent here."
        fm, body = _strip_yaml_frontmatter(text)
        assert "name: John" in fm
        assert fm.endswith("\n")
        assert body.strip().startswith("## Profile")

    def test_no_frontmatter_returns_empty_string_and_full_text(self):
        text = "## Profile\nContent."
        fm, body = _strip_yaml_frontmatter(text)
        assert fm == ""
        assert body == text

    def test_only_closing_dashes_present_falls_back(self):
        text = "Some text\n---\nmore"
        fm, body = _strip_yaml_frontmatter(text)
        assert fm == ""
        assert body == text


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_job(job_key: str = "test_job") -> Job:
    job = Job.__new__(Job)
    job.job_key = job_key
    job.profile_id = 1
    job.title = "Backend Engineer"
    job.company = "Acme"
    job.location = "Remote"
    job.description = "Build things."
    job.salary = None
    for field in [
        "ext_seniority", "ext_role_type", "ext_domain", "ext_work_arrangement",
        "ext_employment_type", "ext_required_skills", "ext_preferred_skills",
        "ext_tech_stack", "ext_key_responsibilities", "ext_company_signals",
    ]:
        setattr(job, field, "")
    return job


def _make_user(skills=None) -> MagicMock:
    user = MagicMock()
    user.hero = "Engineer"
    user.skills = skills or ["Python", "Docker"]
    user.work_history = []
    user.projects = []
    user.first_name = "Jane"
    user.last_name = "Doe"
    user.email = "jane@example.com"
    user.phone = ""
    user.location = "Remote"
    user.target_roles = []
    user.target_salary_min = None
    user.target_salary_max = None
    user.education = []
    return user


def _make_llm_client(response_text: str) -> MagicMock:
    choice = MagicMock()
    choice.message.content = response_text
    choice.finish_reason = "stop"
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = None
    client = MagicMock()
    client.chat.completions.create.return_value = resp
    return client


# ─── evaluate_resume_md ───────────────────────────────────────────────────────

class TestEvaluateResumeMd:
    def test_returns_score_and_issues(self, tmp_path):
        job = _make_job()
        user = _make_user()
        (tmp_path / "1_test_job_resume.md").write_text(
            "---\nname: Jane Doe\n---\n\n## Profile\nExperienced engineer.",
            encoding="utf-8",
        )
        client = _make_llm_client(json.dumps({
            "score": 0.75,
            "issues": [{"category": "keyword_coverage", "description": "Missing Docker"}],
        }))
        with patch("core.job._OUTPUTS_DIR", tmp_path):
            result = job.evaluate_resume_md("Evaluate: {current_document}", user, client, "gpt-4o")
        assert result["score"] == 0.75
        assert result["issues"][0]["category"] == "keyword_coverage"

    def test_clamps_score_above_1(self, tmp_path):
        job = _make_job()
        user = _make_user()
        (tmp_path / "1_test_job_resume.md").write_text(
            "---\nname: Jane\n---\n\n## Profile\nContent.", encoding="utf-8"
        )
        client = _make_llm_client(json.dumps({"score": 1.5, "issues": []}))
        with patch("core.job._OUTPUTS_DIR", tmp_path):
            result = job.evaluate_resume_md("Eval", user, client, "gpt-4o")
        assert result["score"] == 1.0

    def test_clamps_score_below_0(self, tmp_path):
        job = _make_job()
        user = _make_user()
        (tmp_path / "1_test_job_resume.md").write_text(
            "---\nname: Jane\n---\n\n## Profile\nContent.", encoding="utf-8"
        )
        client = _make_llm_client(json.dumps({"score": -0.5, "issues": []}))
        with patch("core.job._OUTPUTS_DIR", tmp_path):
            result = job.evaluate_resume_md("Eval", user, client, "gpt-4o")
        assert result["score"] == 0.0

    def test_strips_frontmatter_before_injecting(self, tmp_path):
        job = _make_job()
        user = _make_user()
        (tmp_path / "1_test_job_resume.md").write_text(
            "---\nname: Jane\n---\n\n## Profile\nActual body.",
            encoding="utf-8",
        )
        captured = {}
        def fake_create(**kwargs):
            captured["prompt"] = kwargs["messages"][0]["content"]
            choice = MagicMock()
            choice.message.content = json.dumps({"score": 0.9, "issues": []})
            choice.finish_reason = "stop"
            r = MagicMock()
            r.choices = [choice]
            r.usage = None
            return r
        client = MagicMock()
        client.chat.completions.create.side_effect = fake_create
        with patch("core.job._OUTPUTS_DIR", tmp_path):
            job.evaluate_resume_md("{current_document}", user, client, "gpt-4o")
        assert "Actual body." in captured["prompt"]
        assert "name: Jane" not in captured["prompt"]

    def test_raises_file_not_found(self, tmp_path):
        job = _make_job()
        user = _make_user()
        with patch("core.job._OUTPUTS_DIR", tmp_path):
            with pytest.raises(FileNotFoundError):
                job.evaluate_resume_md("Eval", user, MagicMock(), "gpt-4o")

    def test_raises_on_invalid_json(self, tmp_path):
        job = _make_job()
        user = _make_user()
        (tmp_path / "1_test_job_resume.md").write_text(
            "---\nname: Jane\n---\n\n## Profile\nContent.", encoding="utf-8"
        )
        client = _make_llm_client("not json at all")
        with patch("core.job._OUTPUTS_DIR", tmp_path):
            with pytest.raises(RuntimeError, match="not valid JSON|no JSON object"):
                job.evaluate_resume_md("Eval", user, client, "gpt-4o")

    def test_raises_on_missing_keys(self, tmp_path):
        job = _make_job()
        user = _make_user()
        (tmp_path / "1_test_job_resume.md").write_text(
            "---\nname: Jane\n---\n\n## Profile\nContent.", encoding="utf-8"
        )
        client = _make_llm_client(json.dumps({"only_score": 0.5}))
        with patch("core.job._OUTPUTS_DIR", tmp_path):
            with pytest.raises(RuntimeError, match="failed schema validation"):
                job.evaluate_resume_md("Eval", user, client, "gpt-4o")


# ─── _refine_doc_md ───────────────────────────────────────────────────────────
#
# _refine_doc_md is now cover-only (tree-v1 résumés refine per-section via
# intake_pipeline._run_resume_section_refinement). The cover rewrite behavior is
# covered by tests/core/test_job_refine_structured.py; here we assert the
# not-found guard fires and résumé is rejected.

class TestRefineDocMd:
    def test_raises_file_not_found_when_no_document(self):
        import core.user  # noqa: F401
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        try:
            job = Job(job_key="no_doc", source="x", title="t",
                      company="Acme", url="u", state="new", profile_id=1)
            db.add(job)
            db.commit()
            with pytest.raises(FileNotFoundError):
                job._refine_doc_md("cover", object(), "p", None, "m", [], db)
        finally:
            db.close()
            Base.metadata.drop_all(engine)

    def test_rejects_resume_doc_type(self):
        job = Job(job_key="r", source="x", title="t",
                  company="Acme", url="u", state="new", profile_id=1)
        with pytest.raises(ValueError, match="only handles covers"):
            job._refine_doc_md("resume", object(), "p", None, "m", [], None)
