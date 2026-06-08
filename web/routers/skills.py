from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.skill_analytics import skill_key
from core.user import User
from db.database import SkillAlias, get_db
from web.routers.stats import _load_aliases, invalidate_skill_cache

router = APIRouter(prefix="/api/skills")


class AssignBody(BaseModel):
    skill: str
    canonical: str


class SkillBody(BaseModel):
    skill: str


class SkillsBody(BaseModel):
    skills: list[str]


def _raw_key(token: str) -> str | None:
    """skill_key without built-in _ALIASES so 'k8s' stays 'k8s', not 'kubernetes'."""
    return skill_key(token, aliases={})


def _group_members(db: Session, canonical: str) -> list[str]:
    return sorted(
        r.alias_key for r in db.query(SkillAlias).filter_by(canonical=canonical).all()
    )


@router.get("/aliases")
def list_aliases(db: Session = Depends(get_db)) -> dict:
    groups: dict[str, list[str]] = {}
    for row in db.query(SkillAlias).all():
        groups.setdefault(row.canonical, []).append(row.alias_key)
    return {
        "groups": [
            {"canonical": c, "members": sorted(m)}
            for c, m in sorted(groups.items(), key=lambda kv: kv[0].lower())
        ]
    }


@router.get("/aliases/search")
def search_aliases(q: str = Query(..., min_length=1), db: Session = Depends(get_db)) -> dict:
    ql = q.strip().lower()
    hits: set[str] = set()
    for row in db.query(SkillAlias).all():
        if ql in row.canonical.lower() or ql in row.alias_key:
            hits.add(row.canonical)
    return {"canonicals": sorted(hits, key=str.lower)}


@router.post("/aliases/assign")
def assign_alias(body: AssignBody, db: Session = Depends(get_db)) -> dict:
    if not body.skill.strip() or not body.canonical.strip():
        raise HTTPException(status_code=400, detail="skill and canonical are required")
    key = _raw_key(body.skill)
    if key is None:
        raise HTTPException(status_code=400, detail="skill is not a valid token")
    canonical = body.canonical.strip()
    ckey = canonical.lower()
    existing_canonical_row = db.query(SkillAlias).filter_by(alias_key=ckey).first()
    if existing_canonical_row:
        # The typed canonical collides with an existing alias key — adopt that
        # row's established group identity so "react" merges into "React" rather
        # than forking a second, lowercased group.
        canonical = existing_canonical_row.canonical
    else:
        db.add(SkillAlias(alias_key=ckey, canonical=canonical))
    row = db.query(SkillAlias).filter_by(alias_key=key).first()
    if row:
        row.canonical = canonical
    else:
        db.add(SkillAlias(alias_key=key, canonical=canonical))
    db.commit()
    invalidate_skill_cache()
    return {"canonical": canonical, "members": _group_members(db, canonical)}


@router.delete("/aliases/member", status_code=204)
def remove_member(body: SkillBody, db: Session = Depends(get_db)):
    key = _raw_key(body.skill)
    if key is None:
        raise HTTPException(status_code=400, detail="skill is not a valid token")
    row = db.query(SkillAlias).filter_by(alias_key=key).first()
    if row is None:
        return
    if row.alias_key == row.canonical.lower():
        raise HTTPException(status_code=400, detail="cannot remove a group's canonical")
    db.delete(row)
    db.commit()
    invalidate_skill_cache()


@router.post("/owned")
def owned_skills(body: SkillsBody, db: Session = Depends(get_db)) -> dict:
    """Return the subset of the given skill tokens the active profile possesses.

    Matching is case- and alias-aware (built-in + DB aliases), so a "k8s" token
    is owned when the profile lists "Kubernetes". Echoes back the original input
    strings so the caller can map results straight onto its chips.
    """
    aliases = _load_aliases(db)
    try:
        user = User.load(db)
    except Exception:
        return {"owned": []}
    profile_keys = {
        k for k in (skill_key(s, aliases) for s in (user.skills or [])) if k
    }
    owned = [s for s in body.skills if skill_key(s, aliases) in profile_keys]
    return {"owned": owned}


@router.post("/profile")
def add_profile_skill(body: SkillBody, db: Session = Depends(get_db)) -> dict:
    skill = body.skill.strip()
    if not skill:
        raise HTTPException(status_code=400, detail="skill is required")
    user = User.load(db)
    if not any(s.lower() == skill.lower() for s in user.skills):
        user.skills = [*user.skills, skill]
        user.save(db)
    invalidate_skill_cache()
    return {"skills": user.skills}


@router.delete("/profile")
def remove_profile_skill(body: SkillBody, db: Session = Depends(get_db)) -> dict:
    skill = body.skill.strip()
    user = User.load(db)
    user.skills = [s for s in user.skills if s.lower() != skill.lower()]
    user.save(db)
    invalidate_skill_cache()
    return {"skills": user.skills}
