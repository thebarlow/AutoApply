"""Test tree-v1 résumé refinement in _refine_doc_md."""
from __future__ import annotations

import json
import pytest
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


def test_refine_tree_v1_repersists_tree(db_session, tmp_path, monkeypatch):
    import core.job as job_mod
    from core.job import Job
    from core.user import User
    from core.resume_document_io import is_tree_v1, serialize_document_tree
    from core.document_tree import build_resume_document_tree
    from db.database import Document

    monkeypatch.setattr(job_mod, "_OUTPUTS_DIR", tmp_path)

    db_session.add(User(name="Jane Doe", data=json.dumps({
        "first_name": "Jane", "last_name": "Doe", "email": "j@x.com",
        "work_history": [
            {"company": "Acme", "title": "Eng", "start": "2020", "end": "2024", "summary": "s1"},
        ],
        "projects": [{"name": "P0", "description": "d0", "url": "u0", "technologies": []}],
        "education": [{"institution": "MIT", "degree": "BS", "field": "EE", "graduated": "2018", "gpa": 3.9}],
    })))
    db_session.commit()
    user = User.load(db_session)

    root = user.profile_tree_root()
    tree = build_resume_document_tree(root, {})
    job = Job(job_key="rfjk", source="x", title="t", company="c", url="http://x/1", profile_id=1)
    db_session.add(job)
    db_session.commit()
    Document.upsert(db_session, "rfjk", "resume", serialize_document_tree(tree),
                    profile_id=1)

    captured = {"called": False}

    def fake_generate(root, job_ctx, client, model, resolve=None):
        captured["called"] = True
        return {}

    monkeypatch.setattr("core.job.generate_resume_by_section", fake_generate)

    job._refine_doc_md("resume", user, "{critique}", client=object(),
                       model="m", issues=[{"issue": "x"}], db=db_session)

    assert captured["called"] is True
    row = Document.fetch(db_session, "rfjk", "resume", profile_id=1)
    assert is_tree_v1(row.structured_json)
