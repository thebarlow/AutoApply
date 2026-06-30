from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import core.job as jobmod
from core.job import Job
from db.database import Base, Document
from core.schemas import CoverDocument, ResumeHeader


@pytest.fixture
def db():
    import core.user  # noqa: F401
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close(); Base.metadata.drop_all(engine)


def test_cover_refine_rewrites_body(db, tmp_path, monkeypatch):
    monkeypatch.setattr(jobmod, "_OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr(jobmod, "call_llm", lambda *a, **k: "Dear hiring team, new body.")
    job = Job(job_key="k2", source="x", title="t", company="Acme", url="u", state="new", profile_id=1)
    db.add(job); db.commit()
    Document.upsert(db, "k2", "cover",
                    CoverDocument(header=ResumeHeader(name="Jane Doe"), body="old body").model_dump_json(),
                    profile_id=1)

    job._refine_doc_md("cover", object(), "ref {critique}", None, "m", [], db)

    stored = CoverDocument.model_validate_json(Document.fetch(db, "k2", "cover", profile_id=1).structured_json)
    assert "new body" in stored.body
    assert stored.header.name == "Jane Doe"
