from core.schemas import ResumeDocument, ResumeExperience, ResumeProject, ResumeSkillGroup, EducationItem, ResumeHeader
from core.document_assembler import assemble_resume_markdown
from core.document_parser import reconstruct_resume_document_from_markdown


def _frontmatter():
    # Minimal YAML front matter as written by generation.
    return (
        "---\n"
        "name: Jane Doe\n"
        "email: jane@x.com\n"
        "location: Austin, TX\n"
        "github: https://github.com/jane\n"
        "education:\n"
        "- degree: B.S.\n"
        "  field: CS\n"
        "  institution: UT Austin\n"
        "  graduated: '2019'\n"
        "---\n"
    )


def test_reconstruct_parses_all_body_sections():
    doc = ResumeDocument(
        profile_summary="Engineer who ships.",
        experience=[ResumeExperience(title="Senior Eng", company="Acme", start="2020", end="2024",
                                     description="- Built things\n- Shipped more")],
        projects=[ResumeProject(name="Widget", description="A useful widget.")],
        skills=[ResumeSkillGroup(category="Languages", items=["Python", "Go"])],
    )
    md = _frontmatter() + assemble_resume_markdown(doc)

    out = reconstruct_resume_document_from_markdown(md)

    assert out.profile_summary == "Engineer who ships."
    assert len(out.experience) == 1
    e = out.experience[0]
    assert (e.title, e.company, e.start, e.end) == ("Senior Eng", "Acme", "2020", "2024")
    assert "Built things" in e.description and "Shipped more" in e.description
    assert out.projects[0].name == "Widget" and out.projects[0].description == "A useful widget."
    assert out.skills[0].category == "Languages" and out.skills[0].items == ["Python", "Go"]


def test_reconstruct_takes_header_and_education_from_frontmatter():
    md = _frontmatter() + "## Profile\n\nHi.\n"
    out = reconstruct_resume_document_from_markdown(md)
    assert out.header.name == "Jane Doe"
    assert out.header.email == "jane@x.com"
    assert out.header.github == "https://github.com/jane"
    assert len(out.education) == 1
    assert out.education[0].institution == "UT Austin"
    assert out.education[0].degree == "B.S." and out.education[0].field == "CS"


def test_reconstruct_empty_input_is_safe():
    out = reconstruct_resume_document_from_markdown("")
    assert isinstance(out, ResumeDocument)
    assert out.profile_summary == "" and out.experience == [] and out.skills == []
