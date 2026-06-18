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


def test_render_work_history_indexed():
    import json
    from core.user import User
    u = User(name="X", data=json.dumps({
        "work_history": [
            {"company": "Acme", "title": "Eng", "start": "2020", "end": "2024", "summary": "s1"},
            {"company": "Beta", "title": "Dev", "start": "2018", "end": "2020", "summary": "s2"},
        ],
    }))
    u._hydrate()
    out = u.render_work_history_indexed()
    assert "[0]" in out and "Acme" in out
    assert "[1]" in out and "Beta" in out
    assert out.index("[0]") < out.index("[1]")


def test_render_projects_indexed():
    import json
    from core.user import User
    u = User(name="X", data=json.dumps({
        "projects": [
            {"name": "P0", "description": "d0", "url": "u0", "technologies": ["Py"]},
            {"name": "P1", "description": "d1", "url": "", "technologies": []},
        ],
    }))
    u._hydrate()
    out = u.render_projects_indexed()
    assert "[0]" in out and "P0" in out
    assert "[1]" in out and "P1" in out


def test_render_indexed_empty():
    import json
    from core.user import User
    u = User(name="X", data=json.dumps({}))
    u._hydrate()
    assert u.render_work_history_indexed() == ""
    assert u.render_projects_indexed() == ""


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
    from db.database import Prompt, PromptDefault
    from db.seed import PROMPT_TYPE_KEYS
    import unittest.mock as mock

    u = User(name="Matt", data=json.dumps({
        **SAMPLE_DATA,
    }))
    db_session.add(u)
    db_session.commit()
    for tk in PROMPT_TYPE_KEYS:
        db_session.add(PromptDefault(type_key=tk, content="default " * 20))
    db_session.add(Prompt(
        profile_id=u.id, type_key="resume_parse",
        content="Parse this resume carefully and extract all structured information.", model="", updated_at="t",
    ))
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
    data = {
        **SAMPLE_DATA,
        "website": "https://example.com",
    }
    db_session.add(User(name="Matt", data=json.dumps(data)))
    db_session.commit()
    user = User.load(db_session)
    assert user.website == "https://example.com"
    # Prompts now live in the DB; _hydrate initialises model attrs to empty string.
    assert user.prompt_scoring_model == ""
    assert user.prompt_resume_model == ""
    assert user.prompt_cover_model == ""
    assert user.prompt_extraction_model == ""


def test_user_hydrates_new_fields_default_to_empty(db_session):
    from core.user import User
    db_session.add(User(name="Matt", data=json.dumps(SAMPLE_DATA)))
    db_session.commit()
    user = User.load(db_session)
    assert user.website == ""
    # Prompts live in DB now; _model attrs default to empty string.
    assert user.prompt_scoring_model == ""
    assert user.prompt_resume_model == ""
    assert user.prompt_cover_model == ""
    assert user.prompt_extraction_model == ""


def test_user_to_dict_includes_new_fields(db_session):
    from core.user import User
    data = {**SAMPLE_DATA, "website": "https://portfolio.dev"}
    db_session.add(User(name="Matt", data=json.dumps(data)))
    db_session.commit()
    user = User.load(db_session)
    serialized = user._to_dict()
    assert serialized["website"] == "https://portfolio.dev"
    # Prompts now live in the DB; they are no longer serialised into the profile JSON.
    assert "prompt_resume" not in serialized
    assert "prompt_scoring" not in serialized


def test_user_prompt_resume_parse_round_trips(db_session):
    from core.user import User
    from db.database import Prompt, PromptDefault
    from db.seed import PROMPT_TYPE_KEYS
    import json as _json
    # Prompts live in DB now — seed a Prompt row directly.
    u = User(name="Matt", data=_json.dumps(SAMPLE_DATA))
    db_session.add(u)
    db_session.commit()
    for tk in PROMPT_TYPE_KEYS:
        db_session.add(PromptDefault(type_key=tk, content="default " * 20))
    db_session.add(Prompt(
        profile_id=u.id, type_key="resume_parse",
        content="Custom parse prompt: {user.first_name} " * 5,
        model="", updated_at="t",
    ))
    db_session.commit()
    user = User.load(db_session)
    assert user.resolve_prompt("resume_parse").startswith("Custom parse prompt:")


def test_from_markdown_uses_custom_system_prompt(db_session):
    from core.user import User
    from db.database import Prompt, PromptDefault
    from db.seed import PROMPT_TYPE_KEYS
    import json as _json
    import unittest.mock as mock

    data = {**SAMPLE_DATA}
    u = User(name="Matt", data=_json.dumps(data))
    db_session.add(u)
    db_session.commit()
    for tk in PROMPT_TYPE_KEYS:
        db_session.add(PromptDefault(type_key=tk, content="default " * 20))
    db_session.add(Prompt(
        profile_id=u.id, type_key="resume_parse",
        content="You parse resumes for {user.first_name} and extract every detail with great care and precision.",
        model="", updated_at="t",
    ))
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
    assert "You parse resumes for Matt and extract every detail with great care and precision." == system_msg["content"]


# ── resolve_prompt validation / auto-reset (DB-based) ───────────────────────

def _make_user_with_scoring(db_session, scoring_content, monkeypatch):
    from core.user import User
    from db.database import Config, Prompt, PromptDefault
    from db.seed import PROMPT_TYPE_KEYS
    sent = []
    monkeypatch.setattr("web.sse.send", lambda t, d: sent.append((t, d)))
    u = User(name="Matt", data=json.dumps(SAMPLE_DATA))
    db_session.add(u)
    db_session.commit()
    db_session.add(Config(key="active_profile_id", value=str(u.id)))
    for tk in PROMPT_TYPE_KEYS:
        db_session.add(PromptDefault(type_key=tk, content="default scoring prompt word " * 5))
    db_session.add(Prompt(profile_id=u.id, type_key="scoring", content=scoring_content, model="", updated_at="t"))
    db_session.commit()
    return User.load(db_session), sent


def test_resolve_prompt_keeps_valid_custom(db_session, monkeypatch):
    content = "Score this job against the candidate carefully using at least eleven distinct words here."
    user, sent = _make_user_with_scoring(db_session, content, monkeypatch)
    assert user.resolve_prompt("scoring").startswith("Score this job")
    assert sent == []  # no reset, no alert


def test_resolve_prompt_resets_when_too_short(db_session, monkeypatch):
    user, sent = _make_user_with_scoring(db_session, "too short prompt", monkeypatch)
    result = user.resolve_prompt("scoring")
    assert result.startswith("default scoring")
    assert len(sent) == 1 and sent[0][0] == "prompt_reset"
    assert "too short" in sent[0][1]["reason"]


def test_resolve_prompt_resets_when_missing(db_session, monkeypatch):
    # No Prompt row at all for scoring — simulates missing.
    from core.user import User
    from db.database import Config, PromptDefault
    from db.seed import PROMPT_TYPE_KEYS
    sent = []
    monkeypatch.setattr("web.sse.send", lambda t, d: sent.append((t, d)))
    u = User(name="Matt", data=json.dumps(SAMPLE_DATA))
    db_session.add(u)
    db_session.commit()
    db_session.add(Config(key="active_profile_id", value=str(u.id)))
    for tk in PROMPT_TYPE_KEYS:
        db_session.add(PromptDefault(type_key=tk, content="default scoring prompt word " * 5))
    db_session.commit()
    user = User.load(db_session)
    result = user.resolve_prompt("scoring")
    assert result.startswith("default scoring")
    assert len(sent) == 1 and sent[0][0] == "prompt_reset"
    assert "unset" in sent[0][1]["reason"]


# ── DB-based resolve_prompt (Task 4) ────────────────────────────────────────

def _make_profile_with_prompts(db, *, content="word " * 20, model=""):
    from core.user import User
    from db.database import Config, Prompt, PromptDefault
    from db.seed import PROMPT_TYPE_KEYS
    u = User(name="P", data=json.dumps(SAMPLE_DATA))
    db.add(u)
    db.commit()
    db.add(Config(key="active_profile_id", value=str(u.id)))
    for tk in PROMPT_TYPE_KEYS:
        db.add(PromptDefault(type_key=tk, content="default " * 20))
        db.add(Prompt(profile_id=u.id, type_key=tk, content=content, model=model, updated_at="t"))
    db.commit()
    return u


def test_resolve_prompt_returns_db_content(db_session):
    from core.user import User
    _make_profile_with_prompts(db_session, content="custom scoring " * 10)
    user = User.load(db_session)
    assert user.resolve_prompt("scoring").startswith("custom scoring")


def test_resolve_prompt_autoresets_when_too_short(db_session):
    from core.user import User
    from db.database import Prompt
    u = _make_profile_with_prompts(db_session)
    row = db_session.query(Prompt).filter_by(profile_id=u.id, type_key="scoring").first()
    row.content = "too short"
    db_session.commit()
    user = User.load(db_session)
    result = user.resolve_prompt("scoring")
    assert result.startswith("default")
    repaired = db_session.query(Prompt).filter_by(profile_id=u.id, type_key="scoring").first()
    assert repaired.content.startswith("default")


def test_resolve_prompt_raises_without_default(db_session):
    from core.user import User, PromptNotConfiguredError
    from db.database import Prompt, PromptDefault
    u = _make_profile_with_prompts(db_session)
    db_session.query(Prompt).filter_by(profile_id=u.id, type_key="scoring").delete()
    db_session.query(PromptDefault).filter_by(type_key="scoring").delete()
    db_session.commit()
    user = User.load(db_session)
    with pytest.raises(PromptNotConfiguredError):
        user.resolve_prompt("scoring")


def test_hydrate_populates_model_from_rows(db_session):
    from core.user import User
    _make_profile_with_prompts(db_session, model="gpt-x")
    user = User.load(db_session)
    assert user.prompt_scoring_model == "gpt-x"


def test_load_migrates_legacy_profile_to_tree(db_session):
    from core.user import User
    db_session.add(User(name="Matt", data=json.dumps(SAMPLE_DATA)))
    db_session.commit()

    user = User.load(db_session)
    assert getattr(user, "profile_tree", None) is not None
    assert [s.role for s in user.profile_tree.children][0] == "header"
    # Derived legacy attrs survive the round-trip.
    assert user.email == "matt@example.com"
    assert user.skills == ["Python", "SQL"]
    assert user.work_history[0].company == "Acme"
    # Migration persisted the tree.
    stored = json.loads(db_session.query(User).first().data)
    assert "profile_tree" in stored


def test_migration_is_idempotent(db_session):
    from core.user import User
    db_session.add(User(name="Matt", data=json.dumps(SAMPLE_DATA)))
    db_session.commit()

    User.load(db_session)
    data_after_first = db_session.query(User).first().data
    User.load(db_session)
    data_after_second = db_session.query(User).first().data
    assert data_after_first == data_after_second
