"""Build structured documents by snapshotting the profile and joining LLM prose.

Structural facts (contact, education, work-history dates/titles, project
names/urls) come from the live profile and are captured at generation time.
Only tailored prose comes from the LLM, keyed by integer ``ref`` into the
profile's work-history / project lists.
"""
from __future__ import annotations

import logging
from typing import Any

from db.database import Config, Session
from core.schemas import (
    CoverDocument,
    EducationItem,
    ResumeDocument,
    ResumeExperience,
    ResumeGeneration,
    ResumeHeader,
    ResumeProject,
    SignOff,
)
from core.document_assembler import resume_section_order

_log = logging.getLogger(__name__)


def _cfg(db: Session, key: str) -> str:
    row = db.query(Config).filter_by(key=key).first()
    return (row.value if row else "") or ""


def build_resume_header(user: Any, db: Session) -> ResumeHeader:
    """Snapshot the profile's contact block (matches Job._frontmatter_data)."""
    first = user.first_name or ""
    last = user.last_name or ""
    name = f"{first} {last}".strip() or user.full_name()
    return ResumeHeader(
        name=name,
        email=user.email or "",
        phone=user.phone or "",
        location=user.location or "",
        github=_cfg(db, "resume_github"),
        linkedin=_cfg(db, "resume_linkedin"),
        website=_cfg(db, "resume_website"),
    )


def _snapshot_education(user: Any) -> list[EducationItem]:
    return [
        EducationItem(
            institution=e.institution,
            degree=e.degree,
            field=e.field,
            graduated=e.graduated,
            gpa=e.gpa,
        )
        for e in (user.education or [])
    ]


def build_resume_document(
    user: Any, generation: ResumeGeneration, db: Session
) -> ResumeDocument:
    """Join LLM prose to profile structural data + a contact/education snapshot."""
    # Experience: ALL profile entries in stored order; prose joined by ref index.
    prose_by_ref: dict[int, str] = {}
    for item in generation.experience:
        if 0 <= item.ref < len(user.work_history) and item.ref not in prose_by_ref:
            prose_by_ref[item.ref] = item.description
        else:
            _log.warning("Ignoring experience ref %s (out of range/duplicate)", item.ref)
    experience = [
        ResumeExperience(
            company=w.company, title=w.title, start=w.start, end=w.end,
            description=prose_by_ref.get(i, ""),
        )
        for i, w in enumerate(user.work_history)
    ]

    # Projects: LLM-selected subset, in LLM order; unknown/duplicate refs ignored.
    projects: list[ResumeProject] = []
    seen: set[int] = set()
    for item in generation.projects:
        if not (0 <= item.ref < len(user.projects)) or item.ref in seen:
            _log.warning("Ignoring project ref %s (out of range/duplicate)", item.ref)
            continue
        seen.add(item.ref)
        p = user.projects[item.ref]
        projects.append(
            ResumeProject(name=p.name, url=p.url, description=item.description)
        )

    doc = ResumeDocument(
        header=build_resume_header(user, db),
        education=_snapshot_education(user),
        profile_summary=generation.profile_summary,
        experience=experience,
        projects=projects,
        skills=generation.skills,
    )
    doc.section_order = resume_section_order(doc)
    return doc


def build_cover_document(user: Any, body: str, db: Session) -> CoverDocument:
    """Build a cover document: snapshot header + LLM body + sign-off."""
    header = build_resume_header(user, db)
    return CoverDocument(header=header, body=body, signoff=SignOff(name=header.name))
