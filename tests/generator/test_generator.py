import json
import uuid as _uuid

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
    build_description_prompt,
    build_prompt,
    strip_header_block,
    call_claude,
    generate_job,
    generate_resume,
    generate_cover,
    generate_md,
    generate_pdf,
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
        state=JobState.DRAFT.value,
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
    choice = MagicMock()
    choice.message.content = "  Hello world  "
    mock_client.chat.completions.create.return_value = MagicMock(choices=[choice])
    result = call_claude("some prompt", mock_client, "test-model")
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
        state=JobState.DRAFT.value,
        title="SWE",
        company="Acme",
        description="Python required.",
    ))
    db_session.commit()


def test_generate_job_transitions_to_generated(db_session, monkeypatch, tmp_path):
    mock_client = MagicMock()
    _seed_db(db_session)
    monkeypatch.setattr("generator.generator._OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr("generator.generator.get_openai_client", lambda db: (mock_client, "test-model"))
    monkeypatch.setattr("generator.generator.call_claude", lambda prompt, client, model: "## Profile\nContent here")
    monkeypatch.setattr("generator.generator.render_resume_pdf", lambda *a, **kw: None)
    monkeypatch.setattr("generator.generator.render_pdf", lambda *a, **kw: None)

    generate_job("test_job", db=db_session)

    db_session.expire_all()
    job = db_session.query(Job).filter_by(job_key="test_job").first()
    assert job.state == JobState.DRAFT.value
    assert job.resume_path is not None
    assert job.cover_path is not None


def test_generate_job_transitions_to_failed_on_claude_error(db_session, monkeypatch, tmp_path):
    mock_client = MagicMock()
    _seed_db(db_session)
    monkeypatch.setattr("generator.generator._OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr("generator.generator.get_openai_client", lambda db: (mock_client, "test-model"))

    def _raise(*a, **kw):
        raise RuntimeError("API error")

    monkeypatch.setattr("generator.generator.call_claude", _raise)

    generate_job("test_job", db=db_session)

    db_session.expire_all()
    job = db_session.query(Job).filter_by(job_key="test_job").first()
    assert job.state == JobState.DRAFT.value


def test_generate_job_transitions_to_failed_on_render_error(db_session, monkeypatch, tmp_path):
    mock_client = MagicMock()
    _seed_db(db_session)
    monkeypatch.setattr("generator.generator._OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr("generator.generator.get_openai_client", lambda db: (mock_client, "test-model"))
    monkeypatch.setattr("generator.generator.call_claude", lambda prompt, client, model: "## Profile\nContent here")

    def _raise(*a, **kw):
        raise RuntimeError("Pandoc failed")

    monkeypatch.setattr("generator.generator.render_resume_pdf", _raise)

    generate_job("test_job", db=db_session)

    db_session.expire_all()
    job = db_session.query(Job).filter_by(job_key="test_job").first()
    assert job.state == JobState.DRAFT.value


def test_generate_job_fails_if_template_missing(db_session, monkeypatch, tmp_path):
    mock_client = MagicMock()
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
        state=JobState.DRAFT.value,
        title="SWE",
        company="Acme",
    ))
    db_session.commit()
    monkeypatch.setattr("generator.generator._OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr("generator.generator.get_openai_client", lambda db: (mock_client, "test-model"))

    generate_job("no_tpl", db=db_session)

    db_session.expire_all()
    job = db_session.query(Job).filter_by(job_key="no_tpl").first()
    assert job.state == JobState.DRAFT.value


def test_generate_resume_sets_path_and_state(db_session, monkeypatch, tmp_path):
    _seed_db(db_session)
    monkeypatch.setattr("generator.generator._OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr("generator.generator.get_openai_client", lambda db: (MagicMock(), "test-model"))
    monkeypatch.setattr("generator.generator.call_claude", lambda prompt, client, model: "## Profile\nContent")
    monkeypatch.setattr("generator.generator.render_resume_pdf", lambda *a, **kw: None)

    generate_resume("test_job", db=db_session)

    db_session.expire_all()
    job = db_session.query(Job).filter_by(job_key="test_job").first()
    assert job.state == JobState.DRAFT.value
    assert job.resume_path is not None
    assert job.cover_path is None


def test_generate_cover_sets_cover_path_only(db_session, monkeypatch, tmp_path):
    _seed_db(db_session)
    monkeypatch.setattr("generator.generator._OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr("generator.generator.get_openai_client", lambda db: (MagicMock(), "test-model"))
    monkeypatch.setattr("generator.generator.call_claude", lambda prompt, client, model: "## Cover\nContent")
    monkeypatch.setattr("generator.generator.render_pdf", lambda *a, **kw: None)

    generate_cover("test_job", db=db_session)

    db_session.expire_all()
    job = db_session.query(Job).filter_by(job_key="test_job").first()
    assert job.cover_path is not None
    assert job.resume_path is None
    assert job.state == JobState.DRAFT.value  # state unchanged


def test_generate_resume_sets_failed_on_error(db_session, monkeypatch, tmp_path):
    _seed_db(db_session)
    monkeypatch.setattr("generator.generator._OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr("generator.generator.get_openai_client", lambda db: (MagicMock(), "test-model"))
    monkeypatch.setattr("generator.generator.call_claude", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("fail")))
    monkeypatch.setattr("generator.generator.render_resume_pdf", lambda *a, **kw: None)

    generate_resume("test_job", db=db_session)

    db_session.expire_all()
    job = db_session.query(Job).filter_by(job_key="test_job").first()
    assert job.state == JobState.DRAFT.value


def test_generate_cover_sets_failed_on_error(db_session, monkeypatch, tmp_path):
    _seed_db(db_session)
    monkeypatch.setattr("generator.generator._OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr("generator.generator.get_openai_client", lambda db: (MagicMock(), "test-model"))
    monkeypatch.setattr("generator.generator.call_claude", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("fail")))
    monkeypatch.setattr("generator.generator.render_pdf", lambda *a, **kw: None)

    generate_cover("test_job", db=db_session)

    db_session.expire_all()
    job = db_session.query(Job).filter_by(job_key="test_job").first()
    assert job.cover_path is None
    assert job.state == JobState.DRAFT.value  # cover failure does not change job state


def test_build_description_prompt_substitutes_description():
    job = Job(
        job_key="jd_test",
        source="test",
        url="https://example.com",
        state="draft",
        title="Backend Engineer",
        company="Acme",
        description="We need a Python expert.",
    )
    result = build_description_prompt(job, "Extract insights from: {description}")
    assert "We need a Python expert." in result
    assert "Extract insights from:" in result


def test_build_description_prompt_substitutes_title_and_company():
    job = Job(
        job_key="jd_test2",
        source="test",
        url="https://example.com/2",
        state="draft",
        title="Backend Engineer",
        company="Acme",
        description="Python required.",
    )
    result = build_description_prompt(job, "{title} at {company}: {description}")
    assert "Backend Engineer" in result
    assert "Acme" in result


def test_extraction_json_to_markdown_required_skills():
    from generator.generator import extraction_json_to_markdown
    data = {"required_skills": ["Python", "FastAPI"]}
    result = extraction_json_to_markdown(data)
    assert "## Required Skills" in result
    assert "- Python" in result
    assert "- FastAPI" in result


def test_extraction_json_to_markdown_overview_meta():
    from generator.generator import extraction_json_to_markdown
    data = {
        "seniority": "senior",
        "domain": "fintech",
        "work_arrangement": "remote",
        "role_type": "IC",
        "employment_type": "full-time",
    }
    result = extraction_json_to_markdown(data)
    assert "## Overview" in result
    assert "**Seniority:** senior" in result
    assert "**Domain:** fintech" in result


def test_extraction_json_to_markdown_empty_fields_omitted():
    from generator.generator import extraction_json_to_markdown
    data = {"required_skills": ["Python"], "preferred_skills": []}
    result = extraction_json_to_markdown(data)
    assert "Preferred Skills" not in result


def test_extraction_json_to_markdown_all_sections():
    from generator.generator import extraction_json_to_markdown
    data = {
        "required_skills": ["Python"],
        "preferred_skills": ["Go"],
        "tech_stack": ["FastAPI", "PostgreSQL"],
        "key_responsibilities": ["Build APIs"],
        "company_signals": ["fast-paced"],
        "seniority": "mid",
        "role_type": "IC",
        "domain": "devtools",
        "work_arrangement": "remote",
        "employment_type": "full-time",
    }
    result = extraction_json_to_markdown(data)
    assert "## Required Skills" in result
    assert "## Preferred Skills" in result
    assert "## Tech Stack" in result
    assert "## Key Responsibilities" in result
    assert "## Company Signals" in result
    assert "## Overview" in result


def test_build_prompt_is_alias_for_build_resume_prompt():
    job = _make_job_obj()
    profile = _make_profile()
    template = "{profile}\n{job}"
    assert build_prompt(job, profile, template) == build_resume_prompt(job, profile, template)


def _seed_db_new(db_session) -> None:
    """Seed config in the new active-prompt format."""
    prompt_id = _uuid.uuid4().hex
    resume_prompts = [{"id": prompt_id, "name": "Test Resume", "content": "Resume: {profile}\n{job}",
                       "provider_name": "TestProvider", "model_id": "test-model", "template_name": ""}]
    cover_prompts = [{"id": prompt_id, "name": "Test Cover", "content": "Cover: {profile}\n{job}",
                      "provider_name": "TestProvider", "model_id": "test-model", "template_name": ""}]
    db_session.add(Config(key="resume_prompts", value=json.dumps(resume_prompts)))
    db_session.add(Config(key="active_resume_prompt_id", value=prompt_id))
    db_session.add(Config(key="cover_prompts", value=json.dumps(cover_prompts)))
    db_session.add(Config(key="active_cover_prompt_id", value=prompt_id))
    db_session.add(Config(key="resume_github", value=""))
    db_session.add(Config(key="resume_linkedin", value=""))
    db_session.add(Config(key="resume_website", value=""))
    profile_data = {
        "name": "Jane Doe", "email": "jane@example.com", "phone": "555-0100",
        "location": "Remote", "skills": ["Python"], "work_history": [], "education": [],
        "projects": [], "hero": "",
        "target_salary_min": 100000, "target_salary_max": 150000,
        "target_roles": ["SWE"], "resume_path": "", "md_path": "",
    }
    db_session.add(UserProfileModel(data=json.dumps(profile_data)))
    db_session.add(Job(
        job_key="test_job", source="indeed", url="https://example.com/job/1",
        state=JobState.DRAFT.value, title="SWE", company="Acme", description="Python required.",
    ))
    db_session.commit()


def test_generate_md_writes_resume_file(db_session, monkeypatch, tmp_path):
    _seed_db_new(db_session)
    monkeypatch.setattr("generator.generator._OUTPUTS_DIR", tmp_path)
    mock_client = MagicMock()
    monkeypatch.setattr("generator.generator.call_claude", lambda prompt, client, model: "## Skills\nPython")

    generate_md("test_job", "resume", "Resume: {profile}\n{job}", mock_client, "test-model", db_session)

    out = tmp_path / "test_job_resume.md"
    assert out.exists()
    assert "## Skills" in out.read_text()


def test_generate_md_writes_cover_file(db_session, monkeypatch, tmp_path):
    _seed_db_new(db_session)
    monkeypatch.setattr("generator.generator._OUTPUTS_DIR", tmp_path)
    mock_client = MagicMock()
    monkeypatch.setattr("generator.generator.call_claude", lambda prompt, client, model: "Dear Hiring Manager")

    generate_md("test_job", "cover", "Cover: {profile}\n{job}", mock_client, "test-model", db_session)

    out = tmp_path / "test_job_cover.md"
    assert out.exists()
    assert "Dear Hiring Manager" in out.read_text()


def test_generate_md_raises_when_job_not_found(db_session, tmp_path):
    db_session.add(UserProfileModel(data=json.dumps({
        "name": "X", "email": "", "phone": "", "location": "", "skills": [],
        "work_history": [], "education": [], "projects": [], "hero": "",
        "target_salary_min": None, "target_salary_max": None,
        "target_roles": [], "resume_path": "", "md_path": "",
    })))
    db_session.commit()
    mock_client = MagicMock()
    with pytest.raises(RuntimeError, match="not found"):
        generate_md("missing_job", "resume", "{job}", mock_client, "model", db_session)


def test_generate_pdf_resume_updates_job_resume_path(db_session, monkeypatch, tmp_path):
    _seed_db_new(db_session)
    md_file = tmp_path / "test_job_resume.md"
    md_file.write_text("## Skills\nPython")
    monkeypatch.setattr("generator.generator._OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr("generator.generator.render_resume_pdf", lambda *a, **kw: None)

    template = tmp_path / "resume.tex"
    template.write_text("\\documentclass{article}")
    generate_pdf("test_job", "resume", template, db_session)

    db_session.expire_all()
    job = db_session.query(Job).filter_by(job_key="test_job").first()
    assert job.resume_path is not None
    assert "test_job_resume.pdf" in job.resume_path


def test_generate_pdf_cover_updates_job_cover_path(db_session, monkeypatch, tmp_path):
    _seed_db_new(db_session)
    md_file = tmp_path / "test_job_cover.md"
    md_file.write_text("Dear Hiring Manager")
    monkeypatch.setattr("generator.generator._OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr("generator.generator.render_pdf", lambda *a, **kw: None)

    template = tmp_path / "cover.tex"
    template.write_text("\\documentclass{article}")
    generate_pdf("test_job", "cover", template, db_session)

    db_session.expire_all()
    job = db_session.query(Job).filter_by(job_key="test_job").first()
    assert job.cover_path is not None
    assert "test_job_cover.pdf" in job.cover_path


def test_generate_pdf_raises_when_md_missing(db_session, monkeypatch, tmp_path):
    _seed_db_new(db_session)
    monkeypatch.setattr("generator.generator._OUTPUTS_DIR", tmp_path)
    template = tmp_path / "resume.tex"
    template.write_text("\\documentclass{article}")
    with pytest.raises(FileNotFoundError):
        generate_pdf("test_job", "resume", template, db_session)
