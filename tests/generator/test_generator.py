import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import MagicMock

from core.types import JobState, UserProfile, WorkHistoryEntry, EducationEntry
from db.models import Base, Job, Config, UserProfileModel
from generator.generator import (
    build_resume_prompt,
    build_cover_prompt,
    strip_header_block,
    call_claude,
    generate_job,
)


@pytest.fixture
def db_session():
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


def _make_profile() -> UserProfile:
    return UserProfile(
        name="Jane Doe",
        email="jane@example.com",
        phone="555-0100",
        location="Remote",
        skills=["Python", "SQL"],
        work_history=[
            WorkHistoryEntry(
                company="Corp", title="Dev", start="2020", end="2023",
                summary="Built data pipelines."
            )
        ],
        education=[
            EducationEntry(
                institution="MIT", degree="BS", field="CS",
                graduated="2020", gpa=3.8
            )
        ],
        target_salary_min=100000,
        target_salary_max=150000,
        target_roles=["SWE"],
        resume_path="",
    )


def _make_job_obj() -> Job:
    return Job(
        job_key="test_job",
        source="indeed",
        url="https://example.com/1",
        state=JobState.APPROVED.value,
        title="Senior Software Engineer",
        company="Acme Corp",
        location="Remote",
        salary="$140,000",
        description="We need Python and SQL expertise.",
    )


def test_build_resume_prompt_contains_job_fields():
    job = _make_job_obj()
    profile = _make_profile()
    template = "Profile:\n{profile}\nJob:\n{job}"
    result = build_resume_prompt(job, profile, template)
    assert "Senior Software Engineer" in result
    assert "Acme Corp" in result
    assert "Python and SQL expertise" in result


def test_build_resume_prompt_contains_profile_fields():
    job = _make_job_obj()
    profile = _make_profile()
    template = "{profile}\n{job}"
    result = build_resume_prompt(job, profile, template)
    assert "Jane Doe" in result
    assert "Python" in result
    assert "Corp" in result
    assert "MIT" in result
    assert "Built data pipelines" in result


def test_build_cover_prompt_contains_job_and_profile():
    job = _make_job_obj()
    profile = _make_profile()
    template = "{profile}\n{job}"
    result = build_cover_prompt(job, profile, template)
    assert "Jane Doe" in result
    assert "Acme Corp" in result
    assert "Python and SQL expertise" in result


def test_strip_header_block_removes_yaml_frontmatter():
    md = "---\nname: John\n---\n## Profile\nSome content"
    result = strip_header_block(md)
    assert result.startswith("## Profile")
    assert "name: John" not in result


def test_strip_header_block_passthrough_when_no_header():
    md = "## Profile\nSome content"
    result = strip_header_block(md)
    assert result == md


def test_call_claude_returns_stripped_text():
    mock_client = MagicMock()
    mock_client.messages.create.return_value.content = [MagicMock(text="  Hello world  ")]
    result = call_claude("some prompt", mock_client)
    assert result == "Hello world"


def _seed_db(db_session) -> None:
    """Seed minimal config, profile, and an approved job for generator tests."""
    db_session.add(Config(key="resume_prompt_template", value="Resume: {profile}\n{job}"))
    db_session.add(Config(key="cover_prompt_template", value="Cover: {profile}\n{job}"))
    db_session.add(Config(key="resume_github", value=""))
    db_session.add(Config(key="resume_linkedin", value=""))
    db_session.add(Config(key="resume_website", value=""))
    profile_data = {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "phone": "555-0100",
        "location": "Remote",
        "skills": ["Python"],
        "work_history": [],
        "education": [],
        "target_salary_min": 100000,
        "target_salary_max": 150000,
        "target_roles": ["SWE"],
        "resume_path": "",
    }
    db_session.add(UserProfileModel(data=json.dumps(profile_data)))
    db_session.add(Job(
        job_key="test_job",
        source="indeed",
        url="https://example.com/job/1",
        state=JobState.APPROVED.value,
        title="SWE",
        company="Acme",
        description="Python required.",
    ))
    db_session.commit()


def test_generate_job_transitions_to_generated(db_session, monkeypatch, tmp_path):
    _seed_db(db_session)
    monkeypatch.setattr("generator.generator._OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr("generator.generator.call_claude", lambda prompt, client: "## Profile\nContent here")
    monkeypatch.setattr("generator.generator.render_resume_pdf", lambda *a, **kw: None)
    monkeypatch.setattr("generator.generator.render_pdf", lambda *a, **kw: None)

    generate_job("test_job", db=db_session)

    db_session.expire_all()
    job = db_session.query(Job).filter_by(job_key="test_job").first()
    assert job.state == JobState.GENERATED.value
    assert job.resume_path is not None
    assert job.cover_path is not None


def test_generate_job_transitions_to_failed_on_claude_error(db_session, monkeypatch, tmp_path):
    _seed_db(db_session)
    monkeypatch.setattr("generator.generator._OUTPUTS_DIR", tmp_path)

    def _raise(*a, **kw):
        raise RuntimeError("API error")

    monkeypatch.setattr("generator.generator.call_claude", _raise)

    generate_job("test_job", db=db_session)

    db_session.expire_all()
    job = db_session.query(Job).filter_by(job_key="test_job").first()
    assert job.state == JobState.FAILED.value


def test_generate_job_transitions_to_failed_on_render_error(db_session, monkeypatch, tmp_path):
    _seed_db(db_session)
    monkeypatch.setattr("generator.generator._OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr("generator.generator.call_claude", lambda prompt, client: "## Profile\nContent here")

    def _raise(*a, **kw):
        raise RuntimeError("Pandoc failed")

    monkeypatch.setattr("generator.generator.render_resume_pdf", _raise)

    generate_job("test_job", db=db_session)

    db_session.expire_all()
    job = db_session.query(Job).filter_by(job_key="test_job").first()
    assert job.state == JobState.FAILED.value


def test_generate_job_fails_if_template_missing(db_session, monkeypatch, tmp_path):
    profile_data = {
        "name": "Jane Doe", "email": "jane@example.com", "phone": "555-0100",
        "location": "Remote", "skills": [], "work_history": [], "education": [],
        "target_salary_min": None, "target_salary_max": None,
        "target_roles": [], "resume_path": "",
    }
    db_session.add(UserProfileModel(data=json.dumps(profile_data)))
    db_session.add(Job(
        job_key="no_tpl",
        source="indeed",
        url="https://example.com/job/2",
        state=JobState.APPROVED.value,
        title="SWE",
        company="Acme",
    ))
    db_session.commit()
    monkeypatch.setattr("generator.generator._OUTPUTS_DIR", tmp_path)

    generate_job("no_tpl", db=db_session)

    db_session.expire_all()
    job = db_session.query(Job).filter_by(job_key="no_tpl").first()
    assert job.state == JobState.FAILED.value
