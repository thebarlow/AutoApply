from __future__ import annotations

import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, SkillAlias
from fastapi.testclient import TestClient
from db.database import get_db
from web.main import app
import core.user  # noqa: F401


@pytest.fixture
def db_session():
    import core.job  # noqa: F401
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


def test_skill_alias_row_roundtrips(db_session):
    db_session.add(SkillAlias(profile_id=1, alias_key="fastapi", canonical="FastAPI"))
    db_session.commit()
    row = db_session.query(SkillAlias).filter_by(alias_key="fastapi").one()
    assert row.canonical == "FastAPI"


def test_seed_skill_aliases_is_idempotent(db_session):
    from db.seed import seed_skill_aliases
    seed_skill_aliases(db_session)
    first = db_session.query(SkillAlias).count()
    # Known curated alias maps to its canonical.
    assert db_session.query(SkillAlias).filter_by(alias_key="js").one().canonical == "JavaScript"
    # Canonical self-row exists.
    assert db_session.query(SkillAlias).filter_by(alias_key="javascript").one().canonical == "JavaScript"
    seed_skill_aliases(db_session)
    assert db_session.query(SkillAlias).count() == first


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed_profile(db, skills):
    import json
    from core.user import User
    from db.database import Config
    u = User(name="Test", data=json.dumps({"skills": skills}))
    db.add(u)
    db.flush()
    db.add(Config(key="active_profile_id", value=str(u.id)))
    db.commit()
    return u


def test_assign_creates_group(client, db_session):
    from db.seed import seed_skill_aliases
    seed_skill_aliases(db_session)
    r = client.post("/api/skills/aliases/assign", json={"skill": "FastAPI", "canonical": "FastAPI"})
    assert r.status_code == 200
    r2 = client.post("/api/skills/aliases/assign", json={"skill": "fast api", "canonical": "FastAPI"})
    assert set(r2.json()["members"]) >= {"fastapi", "fast api"}


def test_assign_moves_member_between_groups(client, db_session):
    client.post("/api/skills/aliases/assign", json={"skill": "rtk", "canonical": "Redux"})
    client.post("/api/skills/aliases/assign", json={"skill": "rtk", "canonical": "Redux Toolkit"})
    r = client.get("/api/skills/aliases")
    groups = {g["canonical"]: g["members"] for g in r.json()["groups"]}
    assert "rtk" in groups["Redux Toolkit"]
    assert "rtk" not in groups.get("Redux", [])


def test_search_matches_members(client, db_session):
    client.post("/api/skills/aliases/assign", json={"skill": "k8s", "canonical": "Kubernetes"})
    r = client.get("/api/skills/aliases/search", params={"q": "k8"})
    assert "Kubernetes" in r.json()["canonicals"]


def test_remove_member(client, db_session):
    client.post("/api/skills/aliases/assign", json={"skill": "Kubernetes", "canonical": "Kubernetes"})
    client.post("/api/skills/aliases/assign", json={"skill": "k8s", "canonical": "Kubernetes"})
    r = client.request("DELETE", "/api/skills/aliases/member", json={"skill": "k8s"})
    assert r.status_code == 204
    r2 = client.get("/api/skills/aliases")
    groups = {g["canonical"]: g["members"] for g in r2.json()["groups"]}
    assert "k8s" not in groups["Kubernetes"]


def test_cannot_remove_canonical_self_row(client, db_session):
    client.post("/api/skills/aliases/assign", json={"skill": "Kubernetes", "canonical": "Kubernetes"})
    r = client.request("DELETE", "/api/skills/aliases/member", json={"skill": "Kubernetes"})
    assert r.status_code == 400


def test_profile_add_and_remove(client, db_session):
    _seed_profile(db_session, [])
    r = client.post("/api/skills/profile", json={"skill": "Python"})
    assert "Python" in r.json()["skills"]
    r2 = client.post("/api/skills/profile", json={"skill": "python"})
    assert r2.json()["skills"].count("Python") == 1
    r3 = client.request("DELETE", "/api/skills/profile", json={"skill": "Python"})
    assert "Python" not in r3.json()["skills"]


def test_owned_skills_matches_case_and_alias(client, db_session):
    from db.seed import seed_skill_aliases
    seed_skill_aliases(db_session)  # gives k8s -> Kubernetes
    _seed_profile(db_session, ["Python", "Kubernetes"])
    r = client.post(
        "/api/skills/owned",
        json={"skills": ["python", "k8s", "Rust", "FastAPI"]},
    )
    assert r.status_code == 200
    # "python" matches Python (case), "k8s" matches Kubernetes (alias); others not.
    assert set(r.json()["owned"]) == {"python", "k8s"}


def test_owned_skills_empty_when_no_profile(client, db_session):
    r = client.post("/api/skills/owned", json={"skills": ["Python"]})
    assert r.json()["owned"] == []


def test_assign_rejects_empty(client, db_session):
    r = client.post("/api/skills/aliases/assign", json={"skill": "", "canonical": "X"})
    assert r.status_code == 400


def test_assign_canonical_collides_with_existing_alias_key(client, db_session):
    client.post("/api/skills/aliases/assign", json={"skill": "React", "canonical": "React"})
    # Typing the lowercased "react" as the canonical should adopt the existing
    # "React" group rather than fork a second, lowercased group.
    r = client.post("/api/skills/aliases/assign", json={"skill": "reactjs", "canonical": "react"})
    assert r.json()["canonical"] == "React"
    assert "reactjs" in r.json()["members"]


@pytest.fixture
def make_job(db_session):
    """Factory: inserts a Job row owned by profile_id=1."""
    from core.job import Job

    def _factory(job_key: str, ext_required_skills: str = "") -> Job:
        job = Job(
            job_key=job_key,
            profile_id=1,
            source="test",
            title="Test Job",
            company="Acme",
            location="Remote",
            url=f"https://example.com/{job_key}",
            state="new",
            ext_required_skills=ext_required_skills,
        )
        db_session.add(job)
        db_session.commit()
        return job

    return _factory


def test_owned_merges_cached_semantic_match(client, db_session, make_job):
    # Profile has no literal "Bachelors degree" skill, but the cache says satisfied.
    job = make_job(job_key="j1", ext_required_skills="Bachelors degree")
    job.ext_skill_match = json.dumps({"matched": ["Bachelors degree"], "profile_hash": "x"})
    db_session.commit()
    _seed_profile(db_session, [])
    res = client.post(
        "/api/skills/owned",
        json={"skills": ["Bachelors degree"], "job_key": "j1"},
    )
    assert res.json()["owned"] == ["Bachelors degree"]


def test_owned_without_job_key_is_literal_only(client, db_session, make_job):
    # Cache exists on the job but no job_key provided → literal path only → empty.
    job = make_job(job_key="j2", ext_required_skills="Bachelors degree")
    job.ext_skill_match = json.dumps({"matched": ["Bachelors degree"], "profile_hash": "x"})
    db_session.commit()
    _seed_profile(db_session, [])
    res = client.post("/api/skills/owned", json={"skills": ["Bachelors degree"]})
    assert res.json()["owned"] == []


def test_owned_union_literal_and_cache(client, db_session, make_job):
    # Skill is owned both literally (in profile) and in cache → returned exactly once.
    job = make_job(job_key="j3", ext_required_skills="Python")
    job.ext_skill_match = json.dumps({"matched": ["Python"], "profile_hash": "x"})
    db_session.commit()
    _seed_profile(db_session, ["Python"])
    res = client.post(
        "/api/skills/owned",
        json={"skills": ["Python"], "job_key": "j3"},
    )
    assert res.json()["owned"] == ["Python"]


def test_owned_handles_malformed_ext_skill_match(client, db_session, make_job):
    """owned_skills degrades gracefully when ext_skill_match is non-dict JSON (e.g., null, list)."""
    _seed_profile(db_session, [])
    # Non-dict JSON values (null, list, string, number) should not crash endpoint.
    for malformed in ['null', '[]', '"string"', '123']:
        job = make_job(job_key=f"j_{malformed}", ext_required_skills="Skill")
        job.ext_skill_match = malformed
        db_session.commit()
        res = client.post(
            "/api/skills/owned",
            json={"skills": ["Skill"], "job_key": f"j_{malformed}"},
        )
        assert res.status_code == 200
        assert res.json()["owned"] == []
