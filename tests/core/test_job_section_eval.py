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


from core.job import Job, _OUTPUTS_DIR
from core.resume_document_io import serialize_document_tree
from core.document_tree import build_resume_document_tree
from db.database import Document
from core.user import User


def _seed(db_session):
    data = {"first_name": "Jane", "last_name": "Doe", "email": "j@x.co", "skills": ["py"]}
    db_session.add(User(name="Jane Doe", data=json.dumps(data)))
    db_session.commit()
    return User.load(db_session)


def test_evaluate_resume_sections_maps_by_name_and_filters(db_session, monkeypatch):
    user = _seed(db_session)
    root = user.profile_tree_root()
    tree = build_resume_document_tree(root, {})
    job = Job(job_key="ev1", title="t", company="c", source="test", url="http://x", profile_id=1)
    db_session.add(job); db_session.commit()
    Document.upsert(db_session, "ev1", "resume", serialize_document_tree(tree), profile_id=1)
    (_OUTPUTS_DIR).mkdir(parents=True, exist_ok=True)
    (_OUTPUTS_DIR / "1_ev1_resume.md").write_text("# Jane Doe\n\n## Summary\n\nx\n", encoding="utf-8")

    # LLM returns a score for a regenerable section + a bogus non-regenerable one.
    def fake_call(prompt, client, model, **kw):
        return ('{"sections": [{"section": "Summary", "score": 0.5, "issues": []},'
                '{"section": "Header", "score": 0.1, "issues": []}]}')
    monkeypatch.setattr("core.job.call_llm", fake_call)

    out = job.evaluate_resume_sections("{current_document}\n{sections_to_score}",
                                       user, object(), "m", db_session)
    assert "Summary" in out
    assert out["Summary"]["score"] == 0.5
    assert "Header" not in out   # non-regenerable name dropped
