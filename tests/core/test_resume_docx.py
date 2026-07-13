# tests/core/test_resume_docx.py
from pathlib import Path

import pytest

import core.job as jobmod
from core.job import Job, _OUTPUTS_DIR


def test_generate_resume_docx_produces_openable_file(tmp_path, monkeypatch):
    docx = pytest.importorskip("docx")  # python-docx
    monkeypatch.setattr(jobmod, "_OUTPUTS_DIR", tmp_path, raising=True)
    md = tmp_path / "1_job1_resume.md"
    md.write_text("## Experience\n\nJane Doe — Python engineer at Acme Corp\n", encoding="utf-8")

    job = Job.__new__(Job)
    job.job_key = "job1"
    job.profile_id = 1

    class _DB:
        def commit(self): pass

    job.generate_resume_docx(_DB())

    out = tmp_path / "1_job1_resume.docx"
    assert out.exists() and out.stat().st_size > 0
    document = docx.Document(str(out))
    full = "\n".join(p.text for p in document.paragraphs)
    assert "Acme Corp" in full
    assert job.resume_docx_path == str(out)
