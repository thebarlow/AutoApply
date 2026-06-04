from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def db_session():
    from db.database import Base, Config
    import core.job   # noqa: F401 — register ORM models with Base.metadata
    import core.user  # noqa: F401
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(Config(key="resume_github", value="gh/jane"))
    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


def _user(db):
    from core.user import User
    import json
    u = User(name="Jane Doe", data=json.dumps({
        "first_name": "Jane", "last_name": "Doe", "email": "j@x.com",
        "phone": "555", "location": "NYC",
        "work_history": [
            {"company": "Acme", "title": "Eng", "start": "2020", "end": "2024", "summary": "s1"},
            {"company": "Beta", "title": "Dev", "start": "2018", "end": "2020", "summary": "s2"},
        ],
        "education": [
            {"institution": "MIT", "degree": "BS", "field": "EE", "graduated": "2018", "gpa": 3.9}
        ],
        "projects": [
            {"name": "P0", "description": "d0", "url": "u0", "technologies": []},
            {"name": "P1", "description": "d1", "url": "u1", "technologies": []},
            {"name": "P2", "description": "d2", "url": "u2", "technologies": []},
        ],
    }))
    db.add(u)
    db.commit()
    return User.load(db)


def test_header_snapshot_pulls_contact_and_config(db_session):
    from core.document_builder import build_resume_header
    h = build_resume_header(_user(db_session), db_session)
    assert h.name == "Jane Doe"
    assert h.email == "j@x.com"
    assert h.github == "gh/jane"      # from config
    assert h.linkedin == ""           # config key absent


def test_education_snapshot(db_session):
    from core.document_builder import build_resume_document
    from core.schemas import ResumeGeneration
    doc = build_resume_document(_user(db_session), ResumeGeneration(), db_session)
    assert len(doc.education) == 1
    assert doc.education[0].institution == "MIT"
    assert doc.education[0].gpa == 3.9


def test_all_experience_kept_in_profile_order(db_session):
    from core.document_builder import build_resume_document
    from core.schemas import ResumeGeneration, ExperienceRef
    gen = ResumeGeneration(experience=[ExperienceRef(ref=1, description="- only beta")])
    doc = build_resume_document(_user(db_session), gen, db_session)
    assert [e.company for e in doc.experience] == ["Acme", "Beta"]
    assert doc.experience[0].description == ""
    assert doc.experience[1].description == "- only beta"


def test_projects_honor_llm_selection_and_order(db_session):
    from core.document_builder import build_resume_document
    from core.schemas import ResumeGeneration, ProjectRef
    gen = ResumeGeneration(projects=[
        ProjectRef(ref=2, description="best"),
        ProjectRef(ref=0, description="ok"),
    ])
    doc = build_resume_document(_user(db_session), gen, db_session)
    assert [p.name for p in doc.projects] == ["P2", "P0"]
    assert doc.projects[0].url == "u2"
    assert doc.projects[0].description == "best"


def test_unknown_project_refs_ignored(db_session):
    from core.document_builder import build_resume_document
    from core.schemas import ResumeGeneration, ProjectRef
    gen = ResumeGeneration(projects=[
        ProjectRef(ref=99, description="bad"),
        ProjectRef(ref=1, description="good"),
        ProjectRef(ref=1, description="dup"),
    ])
    doc = build_resume_document(_user(db_session), gen, db_session)
    assert [p.name for p in doc.projects] == ["P1"]


def test_skills_and_summary_passthrough(db_session):
    from core.document_builder import build_resume_document
    from core.schemas import ResumeGeneration, ResumeSkillGroup
    gen = ResumeGeneration(
        profile_summary="hi",
        skills=[ResumeSkillGroup(category="Lang", items=["Python"])],
    )
    doc = build_resume_document(_user(db_session), gen, db_session)
    assert doc.profile_summary == "hi"
    assert doc.skills[0].items == ["Python"]
    assert doc.section_order == ["Profile", "Experience", "Education", "Skills"]


def test_build_cover_document(db_session):
    from core.document_builder import build_cover_document
    doc = build_cover_document(_user(db_session), "Dear team,", db_session)
    assert doc.header.name == "Jane Doe"
    assert doc.body == "Dear team,"
    assert doc.signoff.name == "Jane Doe"
