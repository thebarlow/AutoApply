# tests/core/test_run_ats_check.py
import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import core.job as jobmod
from core.job import Job
from core.schemas import ResumeDocument, ResumeHeader


@pytest.fixture
def db_session():
    from db.database import Base
    import core.user  # noqa: F401
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()
    Base.metadata.drop_all(engine)


_PARSED_OK = json.dumps({"name": "Jane Doe", "email": "jane@x.com", "phone": "",
                         "sections": [], "skills": [], "experience_dates": []})


def test_run_ats_check_passes_on_clean_pdf(db_session, tmp_path, monkeypatch):
    from db.database import Document, PromptDefault
    monkeypatch.setattr(jobmod, "_OUTPUTS_DIR", tmp_path, raising=True)

    db_session.add(PromptDefault(type_key="ats_parse", content="PROMPT {extracted_text}"))
    db_session.commit()

    doc = ResumeDocument(
        header=ResumeHeader(name="Jane Doe", email="jane@x.com", phone="555-1212", location="NYC"),
        section_order=["experience"],
    )
    Document.upsert(db_session, "job1", "resume", doc.model_dump_json(), profile_id=1)
    (tmp_path / "1_job1_resume.pdf").write_bytes(b"%PDF-1.4 fake")

    clean_text = "Jane Doe\njane@x.com • 555-1212 • NYC\nEXPERIENCE\n"
    from core.schemas import PdfText
    fake_pt = PdfText(text=clean_text, lines=[ln.strip() for ln in clean_text.splitlines() if ln.strip()])

    job = Job.__new__(Job)
    job.job_key = "job1"
    job.profile_id = 1
    job.ext_required_skills = ""
    job.ext_preferred_skills = ""

    class _User:
        skills = ["Python"]

    with patch("core.ats_gate.extract_text", return_value=fake_pt) as mock_extract, \
         patch("core.ats_gate.call_llm", return_value=_PARSED_OK) as mock_llm:
        report = job.run_ats_check(db_session, _User(), client=object(), model="m")

    assert report.passed is True
    assert mock_extract.called
    assert mock_llm.called, "semantic round-trip LLM should have been invoked"


def test_run_ats_check_missing_document_raises(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(jobmod, "_OUTPUTS_DIR", tmp_path, raising=True)
    (tmp_path / "1_job2_resume.pdf").write_bytes(b"%PDF-1.4 fake")  # PDF exists, but no Document row

    job = Job.__new__(Job)
    job.job_key = "job2"
    job.profile_id = 1
    job.ext_required_skills = ""
    job.ext_preferred_skills = ""

    class _User:
        skills = []

    with pytest.raises(FileNotFoundError, match="No structured resume document"):
        job.run_ats_check(db_session, _User(), client=object(), model="m")


def test_run_ats_check_missing_pdf_raises(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(jobmod, "_OUTPUTS_DIR", tmp_path, raising=True)
    job = Job.__new__(Job)
    job.job_key = "nope"
    job.ext_required_skills = ""
    job.ext_preferred_skills = ""

    class _User:
        skills = []

    with pytest.raises(FileNotFoundError):
        job.run_ats_check(db_session, _User(), client=object(), model="m")
