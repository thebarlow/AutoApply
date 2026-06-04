from __future__ import annotations


def _full_doc():
    from core.schemas import (
        ResumeDocument, ResumeHeader, ResumeExperience, ResumeProject,
        ResumeSkillGroup, EducationItem,
    )
    return ResumeDocument(
        header=ResumeHeader(name="Jane Doe"),
        education=[EducationItem(institution="MIT", degree="BS", field="EE", graduated="2018")],
        profile_summary="Senior engineer who ships.",
        experience=[
            ResumeExperience(company="Acme", title="Eng", start="2020", end="2024", description="- Built X"),
            ResumeExperience(company="Beta", title="Dev", start="2018", end="2020", description="- Built Y"),
        ],
        projects=[ResumeProject(name="Proj", url="https://p", description="A thing.")],
        skills=[ResumeSkillGroup(category="Languages", items=["Python", "Go"])],
        section_order=[],
    )


def test_canonical_section_order():
    from core.document_assembler import assemble_resume_markdown
    md = assemble_resume_markdown(_full_doc())
    order = [
        md.index("## Profile"),
        md.index("## Experience"),
        md.index("## Education"),
        md.index("## Projects"),
        md.index("## Skills"),
    ]
    assert order == sorted(order)


def test_empty_sections_omitted():
    from core.schemas import ResumeDocument, ResumeHeader
    from core.document_assembler import assemble_resume_markdown
    md = assemble_resume_markdown(
        ResumeDocument(header=ResumeHeader(name="X"), profile_summary="Just a summary.")
    )
    assert "## Profile" in md
    assert "## Experience" not in md
    assert "## Education" not in md
    assert "## Projects" not in md
    assert "## Skills" not in md


def test_experience_renders_structural_and_prose():
    from core.document_assembler import assemble_resume_markdown
    md = assemble_resume_markdown(_full_doc())
    assert "Eng" in md and "Acme" in md and "2020" in md
    assert "- Built X" in md


def test_education_renders_from_snapshot():
    from core.document_assembler import assemble_resume_markdown
    md = assemble_resume_markdown(_full_doc())
    assert "## Education" in md
    assert "MIT" in md and "BS" in md


def test_no_horizontal_rules():
    from core.document_assembler import assemble_resume_markdown
    md = assemble_resume_markdown(_full_doc())
    assert "\n---\n" not in md  # front matter is added elsewhere, not here
