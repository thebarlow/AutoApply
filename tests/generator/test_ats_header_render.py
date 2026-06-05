# tests/generator/test_ats_header_render.py
from pathlib import Path

from core.ats_gate import extract_text, check_mechanical
from core.schemas import ResumeDocument, ResumeHeader
from core.utils import render_pdf

_RESUME_TEMPLATE = Path("generator/resume_template.html")


def test_real_template_header_extracts_in_order(tmp_path):
    md = tmp_path / "r.md"
    md.write_text(
        "## Summary\n\nEngineer.\n\n## Experience\n\n**Acme** — Dev (2020–2024)\n",
        encoding="utf-8",
    )
    out = tmp_path / "r.pdf"
    render_pdf(
        md,
        out,
        _RESUME_TEMPLATE,
        meta={
            "name": "Jane Doe",
            "email": "jane@x.com",
            "phone": "555-1212",
            "location": "NYC",
            "github": "github.com/jd",
            "linkedin": "linkedin.com/in/jd",
            "website": "jd.dev",
        },
    )
    pt = extract_text(out)
    doc = ResumeDocument(
        header=ResumeHeader(
            name="Jane Doe",
            email="jane@x.com",
            phone="555-1212",
            location="NYC",
        ),
        section_order=["summary", "experience"],
    )
    issues = check_mechanical(pt, doc, [], [], [])
    contact_order_issues = [i for i in issues if i.code == "contact_order"]
    contact_missing_issues = [i for i in issues if i.code == "contact_missing"]
    assert not contact_order_issues, f"contact_order fired: {contact_order_issues}"
    assert not contact_missing_issues, f"contact_missing fired: {contact_missing_issues}"
