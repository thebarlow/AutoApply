"""Tests for POST /api/config/profiles/{id}/parse/apply (Task 6)."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db, Base
from core.user import User as UserProfileModel
from core.profile_tree import RootNode
from web.main import app


# ---------------------------------------------------------------------------
# Fixtures (mirrors test_profile_api.py)
# ---------------------------------------------------------------------------

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


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Profile fixtures
# ---------------------------------------------------------------------------

def _make_profile(db_session, data: dict | None = None) -> int:
    """Create a UserProfileModel row and return its id."""
    row = UserProfileModel(name="Test User", data=json.dumps(data or {}))
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row.id


@pytest.fixture
def a_profile_with_resume(db_session) -> int:
    """A profile with an empty profile tree — no builtin data yet."""
    return _make_profile(db_session)


@pytest.fixture
def a_profile_with_skills(db_session) -> int:
    """A profile whose Skills tree section already holds ['Go']."""
    pid = _make_profile(db_session)

    # Build a tree with Skills populated with ["Go"]
    stored_user = UserProfileModel.load(db_session, profile_id=pid)
    root: RootNode = stored_user.profile_tree

    from core.parsed_sections import find_section, replace_section
    from core.schemas import ParseResponse

    parsed = ParseResponse(skills=["Go"])
    from core.parsed_sections import builtin_sections_from_parse
    src_root_children = builtin_sections_from_parse(parsed)
    skills_src = next((s for s in src_root_children if s.role == "skills"), None)
    assert skills_src is not None, "skills section not found from parse"

    existing = find_section(root, role="skills")
    if existing:
        replace_section(existing, skills_src)
    else:
        from core.parsed_sections import add_section
        add_section(root, skills_src)

    from core.profile_tree import tree_to_legacy
    row = db_session.query(UserProfileModel).filter_by(id=pid).first()
    existing_data = json.loads(row.data) if row.data else {}
    derived = tree_to_legacy(root)
    merged = {**existing_data, **derived, "profile_tree": root.model_dump(mode="json")}
    row.data = json.dumps(merged)
    db_session.commit()
    return pid


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _profile_tree_section_names(db, pid: int) -> list[str]:
    """Return the list of section names from the stored profile tree."""
    row = db.query(UserProfileModel).filter_by(id=pid).first()
    data = json.loads(row.data) if row.data else {}
    tree_dict = data.get("profile_tree")
    if not tree_dict:
        return []
    root = RootNode.model_validate(tree_dict)
    return [s.name for s in root.children]


def _skills_values(db, pid: int) -> list[str]:
    """Return the taglist values from the Skills section of the stored tree."""
    row = db.query(UserProfileModel).filter_by(id=pid).first()
    data = json.loads(row.data) if row.data else {}
    tree_dict = data.get("profile_tree")
    if not tree_dict:
        return []
    root = RootNode.model_validate(tree_dict)
    for s in root.children:
        if s.role == "skills" or s.name.casefold() == "skills":
            for child in s.children:
                if getattr(child, "kind", None) == "taglist":
                    return list(child.value or [])
    return []


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_apply_adds_novel_and_populates_builtin(client, db_session, a_profile_with_resume):
    """Builtin 'replace' populates Skills; novel 'add' inserts Certifications."""
    proposal = {
        "builtin": {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "skills": ["Python"],
            "work_history": [],
            "education": [],
            "projects": [],
        },
        "extra_sections": [
            {
                "name": "Certifications",
                "kind": "list",
                "entries": [{"fields": [{"label": "Name", "value": "AWS"}]}],
            },
        ],
        "is_onboarding": True,
        "sections": [
            {
                "name": "Skills",
                "kind": "taglist",
                "origin": "builtin",
                "builtin_role": "skills",
                "extra_index": -1,
                "matches_existing": True,
                "existing_has_data": False,
                "default_action": "replace",
                "allowed_actions": ["replace", "skip"],
                "preview": {},
                "action": "replace",
            },
            {
                "name": "Certifications",
                "kind": "list",
                "origin": "novel",
                "builtin_role": "",
                "extra_index": 0,
                "matches_existing": False,
                "existing_has_data": False,
                "default_action": "add",
                "allowed_actions": ["add", "skip", "merge"],
                "preview": {},
                "action": "add",
            },
        ],
    }
    r = client.post(
        f"/api/config/profiles/{a_profile_with_resume}/parse/apply", json=proposal
    )
    assert r.status_code == 200
    body = r.json()
    assert body["applied"] == 2

    names = _profile_tree_section_names(db_session, a_profile_with_resume)
    assert "Certifications" in names
    assert "Python" in _skills_values(db_session, a_profile_with_resume)


def test_apply_skip_is_noop_and_merge_unions(client, db_session, a_profile_with_skills):
    """skip rows leave tree unchanged; merge on taglist unions case-insensitively."""
    # Skills already has ["Go"]. Merge with ["go", "Rust"] → {"Go", "Rust"} (no dup).
    proposal = {
        "builtin": {
            "first_name": "",
            "skills": ["go", "Rust"],
            "work_history": [],
            "education": [],
            "projects": [],
        },
        "extra_sections": [],
        "is_onboarding": False,
        "sections": [
            {
                "name": "Skills",
                "kind": "taglist",
                "origin": "builtin",
                "builtin_role": "skills",
                "extra_index": -1,
                "matches_existing": True,
                "existing_has_data": True,
                "default_action": "merge",
                "allowed_actions": ["merge", "replace", "skip"],
                "preview": {},
                "action": "merge",
            },
            {
                # This row should be a no-op regardless of content.
                "name": "Work History",
                "kind": "list",
                "origin": "builtin",
                "builtin_role": "work_history",
                "extra_index": -1,
                "matches_existing": True,
                "existing_has_data": False,
                "default_action": "skip",
                "allowed_actions": ["replace", "skip"],
                "preview": {},
                "action": "skip",
            },
        ],
    }
    r = client.post(
        f"/api/config/profiles/{a_profile_with_skills}/parse/apply", json=proposal
    )
    assert r.status_code == 200
    body = r.json()
    # Only the merge counts; skip is not counted.
    assert body["applied"] == 1

    skills = _skills_values(db_session, a_profile_with_skills)
    skills_lower = {v.casefold() for v in skills}
    assert "go" in skills_lower
    assert "rust" in skills_lower
    assert len(skills) == 2, f"Expected 2 unique skills, got {skills}"


def _get_tree_root(db, pid: int):
    """Return the stored RootNode for a profile, or None."""
    row = db.query(UserProfileModel).filter_by(id=pid).first()
    data = json.loads(row.data) if row.data else {}
    tree_dict = data.get("profile_tree")
    if not tree_dict:
        return None
    return RootNode.model_validate(tree_dict)


def test_onboarding_no_skills_section_in_tree(client, db_session, a_profile_with_resume):
    """Onboarding apply with no skills in parse → no skills-role section in stored tree."""
    proposal = {
        "builtin": {
            "first_name": "Alice",
            "last_name": "Smith",
            "skills": [],
            "work_history": [
                {"company": "Acme", "title": "Engineer", "start": "2020", "end": "2023", "summary": "Built things."}
            ],
            "education": [],
            "projects": [],
        },
        "extra_sections": [],
        "is_onboarding": True,
        "sections": [
            {
                "name": "Experience",
                "kind": "list",
                "origin": "builtin",
                "builtin_role": "experience",
                "extra_index": -1,
                "matches_existing": False,
                "existing_has_data": False,
                "default_action": "replace",
                "allowed_actions": ["replace", "skip"],
                "preview": {},
                "action": "replace",
                "customize": False,
                "prompt": "",
            },
        ],
    }
    r = client.post(
        f"/api/config/profiles/{a_profile_with_resume}/parse/apply", json=proposal
    )
    assert r.status_code == 200
    root = _get_tree_root(db_session, a_profile_with_resume)
    assert root is not None
    roles = [s.role for s in root.children]
    assert "skills" not in roles, f"skills section unexpectedly present; roles={roles}"


def test_onboarding_customize_flips_llm_output(client, db_session, a_profile_with_resume):
    """Onboarding apply: customize=True sets writable fields llm_output=True; False keeps False."""
    proposal = {
        "builtin": {
            "first_name": "Bob",
            "last_name": "Jones",
            "skills": ["Python", "SQL"],
            "work_history": [
                {"company": "Corp", "title": "Dev", "start": "2019", "end": "2022", "summary": "Did stuff."}
            ],
            "education": [],
            "projects": [],
        },
        "extra_sections": [],
        "is_onboarding": True,
        "sections": [
            {
                "name": "Experience",
                "kind": "list",
                "origin": "builtin",
                "builtin_role": "experience",
                "extra_index": -1,
                "matches_existing": False,
                "existing_has_data": False,
                "default_action": "replace",
                "allowed_actions": ["replace", "skip"],
                "preview": {},
                "action": "replace",
                "customize": True,
                "prompt": "Tailor experience to the job.",
            },
            {
                "name": "Skills",
                "kind": "taglist",
                "origin": "builtin",
                "builtin_role": "skills",
                "extra_index": -1,
                "matches_existing": False,
                "existing_has_data": False,
                "default_action": "replace",
                "allowed_actions": ["replace", "skip"],
                "preview": {},
                "action": "replace",
                "customize": False,
                "prompt": "",
            },
        ],
    }
    r = client.post(
        f"/api/config/profiles/{a_profile_with_resume}/parse/apply", json=proposal
    )
    assert r.status_code == 200, r.json()
    root = _get_tree_root(db_session, a_profile_with_resume)
    assert root is not None

    from core.parsed_sections import iter_leaf_fields, find_section

    # (b) experience writable fields → llm_output=True
    exp = find_section(root, role="experience")
    assert exp is not None, "experience section missing from tree"
    exp_writable = [f for f in iter_leaf_fields(exp) if f.kind in {"markdown", "bullets", "taglist"}]
    assert exp_writable, "no writable fields found in experience section"
    assert all(f.llm_output for f in exp_writable), (
        f"expected all experience writable fields llm_output=True; got {[(f.name, f.llm_output) for f in exp_writable]}"
    )

    # (c) skills writable fields → llm_output=False
    skl = find_section(root, role="skills")
    assert skl is not None, "skills section missing from tree"
    skl_writable = [f for f in iter_leaf_fields(skl) if f.kind in {"markdown", "bullets", "taglist"}]
    assert skl_writable, "no writable fields found in skills section"
    assert all(not f.llm_output for f in skl_writable), (
        f"expected all skills writable fields llm_output=False; got {[(f.name, f.llm_output) for f in skl_writable]}"
    )


def test_forged_onboarding_flag_cannot_wipe_populated_tree(client, db_session, a_profile_with_skills):
    """Audit S3: is_onboarding=True from the client is ignored when stored sections hold data.

    The onboarding branch rebuilds the tree wholesale; a forged/stale True against
    a populated profile must fall through to the per-section merge path instead.
    """
    proposal = {
        "builtin": {
            "first_name": "Mallory",
            "skills": [],
            "work_history": [],
            "education": [],
            "projects": [],
        },
        "extra_sections": [
            {
                "name": "Certifications",
                "kind": "list",
                "entries": [{"fields": [{"label": "Name", "value": "AWS"}]}],
            },
        ],
        "is_onboarding": True,  # forged — stored Skills already holds ["Go"]
        "sections": [
            {
                "name": "Certifications",
                "kind": "list",
                "origin": "novel",
                "builtin_role": "",
                "extra_index": 0,
                "matches_existing": False,
                "existing_has_data": False,
                "default_action": "add",
                "allowed_actions": ["add", "skip", "merge"],
                "preview": {},
                "action": "add",
            },
        ],
    }
    r = client.post(
        f"/api/config/profiles/{a_profile_with_skills}/parse/apply", json=proposal
    )
    assert r.status_code == 200
    # Existing data survived: the onboarding wipe did NOT run.
    assert "Go" in _skills_values(db_session, a_profile_with_skills)
    # And the per-section path still applied the requested add.
    names = _profile_tree_section_names(db_session, a_profile_with_skills)
    assert "Certifications" in names


def test_apply_caps_returns_422(client, db_session, a_profile_with_resume):
    """A proposal that would push the tree past 500 nodes returns 422."""
    # Build extra_sections with enough list entries to blow the node cap.
    # Each list entry is a GroupNode with several FieldNodes; pile on many.
    many_entries = [
        {"fields": [{"label": f"Field{j}", "value": "x"} for j in range(5)]}
        for _ in range(200)
    ]
    # Repeat novel add sections to maximise node count.
    extra_sections = [
        {"name": f"Section{i}", "kind": "list", "entries": many_entries}
        for i in range(5)
    ]
    sections = [
        {
            "name": f"Section{i}",
            "kind": "list",
            "origin": "novel",
            "builtin_role": "",
            "extra_index": i,
            "matches_existing": False,
            "existing_has_data": False,
            "default_action": "add",
            "allowed_actions": ["add", "skip"],
            "preview": {},
            "action": "add",
        }
        for i in range(5)
    ]
    proposal = {
        "builtin": {"skills": [], "work_history": [], "education": [], "projects": []},
        "extra_sections": extra_sections,
        "is_onboarding": True,
        "sections": sections,
    }
    r = client.post(
        f"/api/config/profiles/{a_profile_with_resume}/parse/apply", json=proposal
    )
    assert r.status_code == 422
