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
