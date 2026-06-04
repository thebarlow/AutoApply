from __future__ import annotations

from core.schemas import (
    ExperienceRef,
    ProjectRef,
    ResumeDocument,
    ResumeExperience,
    ResumeGeneration,
    ResumeProject,
    ResumeSkillGroup,
)
from core.document_builder import apply_resume_patch


def _doc() -> ResumeDocument:
    return ResumeDocument(
        profile_summary="old summary",
        experience=[
            ResumeExperience(company="Acme", title="Eng", start="2020", end="2024", description="old A"),
            ResumeExperience(company="Beta", title="Dev", start="2018", end="2020", description="old B"),
        ],
        projects=[
            ResumeProject(name="P2", url="u2", description="old P2"),
            ResumeProject(name="P0", url="u0", description="old P0"),
        ],
        skills=[ResumeSkillGroup(category="Lang", items=["Python"])],
    )


def test_patch_updates_prose_leaves_only():
    gen = ResumeGeneration(
        profile_summary="new summary",
        experience=[ExperienceRef(ref=0, description="new A")],
        projects=[ProjectRef(ref=1, description="new P0")],
        skills=[ResumeSkillGroup(category="Lang", items=["Go"])],
    )
    out = apply_resume_patch(_doc(), gen)
    assert out.profile_summary == "new summary"
    assert out.experience[0].description == "new A"
    assert out.experience[1].description == "old B"   # untouched ref kept
    assert out.projects[1].description == "new P0"
    assert out.skills[0].items == ["Go"]
    # structural facts never change
    assert [e.company for e in out.experience] == ["Acme", "Beta"]
    assert [p.name for p in out.projects] == ["P2", "P0"]


def test_patch_ignores_unknown_refs():
    gen = ResumeGeneration(experience=[ExperienceRef(ref=9, description="x")],
                           projects=[ProjectRef(ref=-1, description="y")])
    out = apply_resume_patch(_doc(), gen)
    assert out.experience[0].description == "old A"
    assert out.projects[0].description == "old P2"


def test_patch_empty_skills_keeps_existing():
    gen = ResumeGeneration(profile_summary="x")  # skills=[]
    out = apply_resume_patch(_doc(), gen)
    assert out.skills[0].items == ["Python"]


def test_patch_recomputes_section_order():
    gen = ResumeGeneration(profile_summary="")  # blanks the Profile section
    out = apply_resume_patch(_doc(), gen)
    assert "Profile" not in out.section_order
    assert out.section_order[0] == "Experience"
