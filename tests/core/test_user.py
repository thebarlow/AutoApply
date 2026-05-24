from __future__ import annotations
import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import MagicMock


@pytest.fixture
def db_session():
    from db.database import Base
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


SAMPLE_DATA = {
    "first_name": "Matt",
    "last_name": "Barlow",
    "email": "matt@example.com",
    "phone": "555-1234",
    "location": "Remote",
    "skills": ["Python", "SQL"],
    "work_history": [
        {"company": "Acme", "title": "SWE", "start": "2022-01", "end": "Present", "summary": "Built things."}
    ],
    "education": [
        {"institution": "Columbia", "degree": "B.S.", "field": "EE", "graduated": "2018", "gpa": 3.5}
    ],
    "projects": [
        {"name": "auto_apply", "description": "Job pipeline", "url": "https://github.com/x", "technologies": ["Python"]}
    ],
    "target_salary_min": 120000,
    "target_salary_max": 160000,
    "target_roles": ["Backend Engineer"],
    "resume_path": "",
    "md_path": "",
    "hero": "",
    "linkedin": "",
    "github": "",
}


def test_user_load_hydrates_fields(db_session):
    from core.user import User
    db_session.add(User(name="Matt", data=json.dumps(SAMPLE_DATA)))
    db_session.commit()

    user = User.load(db_session)
    assert user.email == "matt@example.com"
    assert user.skills == ["Python", "SQL"]
    assert user.work_history[0].company == "Acme"
    assert user.education[0].institution == "Columbia"
    assert user.projects[0].name == "auto_apply"
    assert user.target_salary_min == 120000


def test_user_load_raises_when_no_profile(db_session):
    from core.user import User
    with pytest.raises(RuntimeError, match="No user profile found"):
        User.load(db_session)


def test_user_load_uses_active_profile_id(db_session):
    from core.user import User
    # Insert two profiles
    db_session.add(User(name="First", data=json.dumps({**SAMPLE_DATA, "email": "first@x.com"})))
    db_session.add(User(name="Second", data=json.dumps({**SAMPLE_DATA, "email": "second@x.com"})))
    db_session.commit()

    from db.database import Config
    db_session.add(Config(key="active_profile_id", value="2"))
    db_session.commit()

    user = User.load(db_session)
    assert user.email == "second@x.com"


def test_user_save_persists_changes(db_session):
    from core.user import User
    db_session.add(User(name="Matt", data=json.dumps(SAMPLE_DATA)))
    db_session.commit()

    user = User.load(db_session)
    user.email = "updated@example.com"
    user.save(db_session)

    fresh = User.load(db_session)
    assert fresh.email == "updated@example.com"


def test_user_full_name_uses_name_column(db_session):
    from core.user import User
    db_session.add(User(name="Matt Barlow", data=json.dumps(SAMPLE_DATA)))
    db_session.commit()
    user = User.load(db_session)
    assert user.full_name() == "Matt Barlow"


def test_user_full_name_falls_back_to_first_last(db_session):
    from core.user import User
    data = {**SAMPLE_DATA, "first_name": "Matt", "last_name": "Barlow"}
    db_session.add(User(name="", data=json.dumps(data)))
    db_session.commit()
    user = User.load(db_session)
    assert user.full_name() == "Matt Barlow"


def test_user_from_markdown_returns_profile_dict(db_session):
    from core.user import User
    import unittest.mock as mock

    db_session.add(User(name="Matt", data=json.dumps({
        **SAMPLE_DATA,
        "llm_provider_type": "openai",
        "llm_model": "gpt-4o",
        "prompt_resume_parse": "Parse this resume.",
    })))
    db_session.commit()

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = json.dumps({
        "name": "Matt Barlow", "email": "matt@x.com", "phone": "", "location": "",
        "skills": ["Python"], "work_history": [], "education": [], "projects": [],
        "target_roles": [],
    })

    with mock.patch("core.llm.get_client_for_profile", return_value=(mock_client, "gpt-4o")):
        result = User.from_markdown("resume text here", db_session)

    assert result["email"] == "matt@x.com"
    assert result["skills"] == ["Python"]


def test_user_render_for_prompt_contains_skills(db_session):
    from core.user import User
    db_session.add(User(name="Matt", data=json.dumps(SAMPLE_DATA)))
    db_session.commit()
    user = User.load(db_session)
    prompt = user.render_for_prompt()
    assert "Python" in prompt
    assert "SQL" in prompt
    assert "Work History" in prompt


def test_user_master_resume_falls_back_to_render(db_session):
    from core.user import User
    db_session.add(User(name="Matt", data=json.dumps({**SAMPLE_DATA, "md_path": ""})))
    db_session.commit()
    user = User.load(db_session)
    result = user.master_resume()
    assert "Python" in result


def test_user_hydrates_new_fields_from_data(db_session):
    from core.user import User
    from pathlib import Path
    data = {
        **SAMPLE_DATA,
        "website": "https://example.com",
        "prompt_scoring": "custom scoring prompt",
        "prompt_resume": "custom resume prompt",
        "prompt_cover": "custom cover prompt",
        "prompt_extraction": "custom extraction prompt",
    }
    db_session.add(User(name="Matt", data=json.dumps(data)))
    db_session.commit()
    user = User.load(db_session)
    assert user.website == "https://example.com"
    assert user.prompt_scoring.endswith(".md")
    assert Path(user.prompt_scoring).read_text(encoding="utf-8") == "custom scoring prompt"
    assert user.prompt_resume.endswith(".md")
    assert user.prompt_cover.endswith(".md")
    assert user.prompt_extraction.endswith(".md")


def test_user_hydrates_new_fields_default_to_empty(db_session):
    from core.user import User
    db_session.add(User(name="Matt", data=json.dumps(SAMPLE_DATA)))
    db_session.commit()
    user = User.load(db_session)
    assert user.website == ""
    assert user.prompt_scoring == ""
    assert user.prompt_resume == ""
    assert user.prompt_cover == ""
    assert user.prompt_extraction == ""


def test_user_to_dict_includes_new_fields(db_session):
    from core.user import User
    data = {**SAMPLE_DATA, "website": "https://portfolio.dev", "prompt_resume": "my prompt"}
    db_session.add(User(name="Matt", data=json.dumps(data)))
    db_session.commit()
    user = User.load(db_session)
    serialized = user._to_dict()
    assert serialized["website"] == "https://portfolio.dev"
    assert serialized["prompt_resume"].endswith(".md")
    assert "prompt_scoring" in serialized
    assert "prompt_cover" in serialized
    assert "prompt_extraction" in serialized


def test_user_prompt_resume_parse_round_trips(db_session):
    from core.user import User
    from pathlib import Path
    import json as _json
    data = {**SAMPLE_DATA, "prompt_resume_parse": "Custom parse prompt: {user.first_name}"}
    db_session.add(User(name="Matt", data=_json.dumps(data)))
    db_session.commit()
    user = User.load(db_session)
    assert user.prompt_resume_parse.endswith(".md")
    assert Path(user.prompt_resume_parse).read_text(encoding="utf-8") == "Custom parse prompt: {user.first_name}"


def test_from_markdown_uses_custom_system_prompt(db_session):
    from core.user import User
    import json as _json
    import unittest.mock as mock

    data = {
        **SAMPLE_DATA,
        "prompt_resume_parse": "You parse resumes for {user.first_name}.",
        "llm_provider_type": "openai",
        "llm_model": "gpt-4o",
    }
    db_session.add(User(name="Matt", data=_json.dumps(data)))
    db_session.commit()

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = _json.dumps({
        "name": "Ada L", "email": "ada@x.com", "phone": "", "location": "",
        "skills": ["Python"], "work_history": [], "education": [], "projects": [],
        "target_roles": [],
    })

    captured = {}
    configured_return = mock_client.chat.completions.create.return_value

    def capture_create(**kwargs):
        captured["messages"] = kwargs.get("messages", [])
        return configured_return

    mock_client.chat.completions.create.side_effect = capture_create

    with mock.patch("core.llm.get_client_for_profile", return_value=(mock_client, "gpt-4o")):
        User.from_markdown("resume text here", db_session)

    system_msg = next(m for m in captured["messages"] if m["role"] == "system")
    assert "You parse resumes for Matt." == system_msg["content"]
