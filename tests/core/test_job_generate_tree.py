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


def test_generate_resume_md_writes_tree_v1(db_session, tmp_path, monkeypatch):
    """generate_resume_md stores a tree-v1 row and a frontmatter-free .md."""
    import core.job as job_mod
    import core.section_generator as sg
    from core.job import Job
    from core.user import User
    from core.profile_tree import FieldNode, GroupNode
    from core.resume_document_io import is_tree_v1
    from db.database import Document

    monkeypatch.setattr(job_mod, "_OUTPUTS_DIR", tmp_path)

    # Seed user with legacy data so profile_tree is built via legacy_to_tree.
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

    # Stub per-section generation: fill every llm_output field deterministically.
    def fake_generate(root, job_ctx, client, model, resolve=None):
        out = {}
        for s in root.children:
            child = s.children[0] if s.children else None
            if isinstance(child, GroupNode):
                for f in child.children:
                    if isinstance(f, FieldNode) and f.llm_output:
                        out[f.id] = "Generated."
                    elif isinstance(f, GroupNode):
                        for ff in f.children:
                            if isinstance(ff, FieldNode) and ff.llm_output:
                                out[ff.id] = "Generated."
            elif isinstance(child, FieldNode) and child.llm_output:
                out[child.id] = "Generated."
        return out

    monkeypatch.setattr(sg, "generate_resume_by_section", fake_generate)
    monkeypatch.setattr("core.job.generate_resume_by_section", fake_generate, raising=False)

    job = Job(job_key="genjk", source="x", title="t", company="c", url="http://x/1", profile_id=user.id)
    job.extracted_description = "Build things."
    job.ext_seniority = "mid"
    db_session.add(job)
    db_session.commit()

    job.generate_resume_md(user, "{job.extracted_description}", client=object(),
                           model="m", db=db_session)

    row = Document.fetch(db_session, "genjk", "resume", profile_id=user.id)
    assert row is not None
    assert is_tree_v1(row.structured_json)
    md = (tmp_path / "1_genjk_resume.md").read_text(encoding="utf-8")
    assert not md.startswith("---")
