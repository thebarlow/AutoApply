# tests/web/test_profile_tree_endpoints.py
# Mirrors the fixture pattern in tests/web/test_profile_api.py: a shared
# in-memory db_session, get_db overridden with a lambda, and the dev tenancy
# seam resolving the caller to profile id=1 without any auth setup.
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, get_db
from core.user import User
from web.main import app

SAMPLE = {
    "first_name": "Matt", "last_name": "Barlow", "email": "m@x.com",
    "phone": "555", "location": "Remote", "github": "gh", "linkedin": "li",
    "website": "w", "hero": "Engineer", "skills": ["Python", "SQL"],
    "work_history": [{"company": "Acme", "title": "SWE", "start": "2022",
                      "end": "Now", "summary": "Built."}],
    "education": [{"institution": "Columbia", "degree": "B.S.", "field": "EE",
                   "graduated": "2018", "gpa": 3.5}],
    "projects": [], "target_roles": ["Backend"],
}


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
    session.add(User(id=1, name="Matt", data=json.dumps(SAMPLE)))
    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_get_tree_returns_sections(client):
    r = client.get("/api/config/profiles/1/tree")
    assert r.status_code == 200
    tree = r.json()["tree"]
    roles = [s["role"] for s in tree["children"]]
    assert roles == ["header", "summary", "experience", "education", "projects", "skills"]


def test_put_tree_preserves_ids_and_custom_section(client):
    tree = client.get("/api/config/profiles/1/tree").json()["tree"]
    header_email = next(f for f in tree["children"][0]["children"][0]["children"]
                        if f["key"] == "email")
    header_email["value"] = "edited@x.com"
    email_id = header_email["id"]
    tree["children"].append({
        "type": "section", "id": "cust-uuid", "name": "Awards", "role": None,
        "order": 50, "visible": True,
        "children": [{"type": "group", "id": "g", "name": "Awards", "order": 0,
                      "visible": True, "regen_lock": False, "children": [
                          {"type": "field", "id": "fa", "name": "Award",
                           "key": "award", "order": 0, "visible": True,
                           "kind": "text", "value": "Winner", "llm_output": False,
                           "llm_instructions": "", "llm_input": False,
                           "regen_lock": False, "min": None, "max": None}]}],
    })
    r = client.put("/api/config/profiles/1/tree", json={"tree": tree})
    assert r.status_code == 200

    got = client.get("/api/config/profiles/1/tree").json()["tree"]
    got_email = next(f for f in got["children"][0]["children"][0]["children"]
                     if f["key"] == "email")
    assert got_email["value"] == "edited@x.com"
    assert got_email["id"] == email_id  # preserved
    assert any(s["id"] == "cust-uuid" for s in got["children"])  # custom section persisted
    # flat profile reflects the role-mapped edit
    flat = client.get("/api/config/profiles/1").json()["data"]
    assert flat["email"] == "edited@x.com"


def test_put_tree_rejects_malformed(client):
    # duplicate ids -> validate_tree failure -> 422
    bad = {"type": "root", "id": "r", "children": [
        {"type": "section", "id": "dup", "name": "A", "role": None, "order": 0,
         "visible": True, "children": [
             {"type": "field", "id": "dup", "name": "x", "key": "x", "order": 0,
              "visible": True, "kind": "text", "value": "", "llm_output": False,
              "llm_instructions": "", "llm_input": False, "regen_lock": False,
              "min": None, "max": None}]}]}
    r = client.put("/api/config/profiles/1/tree", json={"tree": bad})
    assert r.status_code == 422


def test_put_tree_rejects_oversized(client):
    tree = client.get("/api/config/profiles/1/tree").json()["tree"]
    # append > 500 trivial custom sections
    for i in range(600):
        tree["children"].append({
            "type": "section", "id": f"s{i}", "name": f"S{i}", "role": None,
            "order": 1000 + i, "visible": True,
            "children": [{"type": "field", "id": f"f{i}", "name": "x", "key": "x",
                          "order": 0, "visible": True, "kind": "text", "value": "",
                          "llm_output": False, "llm_instructions": "",
                          "llm_input": False, "regen_lock": False,
                          "min": None, "max": None}]})
    r = client.put("/api/config/profiles/1/tree", json={"tree": tree})
    assert r.status_code == 422
