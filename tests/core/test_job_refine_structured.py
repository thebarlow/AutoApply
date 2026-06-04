from __future__ import annotations

import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import core.job as jobmod
from core.job import Job
from db.database import Base, Document
from core.schemas import (
    ResumeDocument, ResumeExperience, ResumeProject, CoverDocument, ResumeHeader,
)


@pytest.fixture
def db():
    import core.user  # noqa: F401
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close(); Base.metadata.drop_all(engine)


def _resume_doc():
    return ResumeDocument(
        header=ResumeHeader(name="Jane Doe"),
        profile_summary="old",
        experience=[ResumeExperience(company="Acme", title="Eng", start="2020", end="2024", description="old A")],
        projects=[ResumeProject(name="P0", url="u0", description="old P0")],
    )


def test_resume_refine_patches_structured_doc(db, tmp_path, monkeypatch):
    monkeypatch.setattr(jobmod, "_OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr(jobmod, "call_llm",
                        lambda *a, **k: json.dumps({
                            "profile_summary": "new",
                            "experience": [{"ref": 0, "description": "new A"}],
                            "projects": [{"ref": 0, "description": "new P0"}],
                            "skills": [],
                        }))
    job = Job(job_key="k1", source="x", title="t", company="Acme", url="u", state="new")
    db.add(job); db.commit()
    Document.upsert(db, "k1", "resume", _resume_doc().model_dump_json())

    job._refine_doc_md("resume", object(), "ref {critique}", None, "m",
                       [{"category": "c", "description": "d"}], db)

    stored = ResumeDocument.model_validate_json(Document.fetch(db, "k1", "resume").structured_json)
    assert stored.profile_summary == "new"
    assert stored.experience[0].description == "new A"
    assert stored.experience[0].company == "Acme"
    assert stored.projects[0].description == "new P0"
    md = (tmp_path / "k1_resume.md").read_text(encoding="utf-8")
    assert "new A" in md


def test_cover_refine_rewrites_body(db, tmp_path, monkeypatch):
    monkeypatch.setattr(jobmod, "_OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr(jobmod, "call_llm", lambda *a, **k: "Dear hiring team, new body.")
    job = Job(job_key="k2", source="x", title="t", company="Acme", url="u", state="new")
    db.add(job); db.commit()
    Document.upsert(db, "k2", "cover",
                    CoverDocument(header=ResumeHeader(name="Jane Doe"), body="old body").model_dump_json())

    job._refine_doc_md("cover", object(), "ref {critique}", None, "m", [], db)

    stored = CoverDocument.model_validate_json(Document.fetch(db, "k2", "cover").structured_json)
    assert "new body" in stored.body
    assert stored.header.name == "Jane Doe"
