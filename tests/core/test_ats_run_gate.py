# tests/core/test_ats_run_gate.py
import json
from unittest.mock import patch

from core.ats_gate import run_gate
from core.schemas import PdfText, ResumeDocument, ResumeHeader


def _doc():
    return ResumeDocument(
        header=ResumeHeader(name="Jane Doe", email="jane@x.com", phone="555-1212", location="NYC"),
        section_order=["experience"],
    )


def _clean_pt():
    full = "Jane Doe\njane@x.com • 555-1212 • NYC\nEXPERIENCE\nPython\n"
    return PdfText(text=full, lines=[ln.strip() for ln in full.splitlines() if ln.strip()])


_PARSED_OK = json.dumps({"name": "Jane Doe", "email": "jane@x.com", "phone": "",
                         "sections": [], "skills": [], "experience_dates": []})


def test_clean_resume_passes_with_high_score():
    with patch("core.ats_gate.call_llm", return_value=_PARSED_OK):
        report = run_gate(_clean_pt(), _doc(), [], [], [], "PROMPT {extracted_text}", object(), "m")
    assert report.passed is True
    assert report.score >= 0.9


def test_critical_issue_fails_and_lowers_score():
    bad = PdfText(text="   ", lines=[])
    with patch("core.ats_gate.call_llm", return_value=_PARSED_OK):
        report = run_gate(bad, _doc(), [], [], [], "PROMPT {extracted_text}", object(), "m")
    assert report.passed is False
    assert report.score < 1.0


def test_custom_section_names_pass_without_section_missing():
    # A résumé with arbitrary user-defined sections (no canonical "experience"):
    # 4C removed the fixed-heading hard-block, so this passes cleanly.
    doc = ResumeDocument(
        header=ResumeHeader(name="Jane Doe", email="jane@x.com", phone="555-1212", location="NYC"),
        section_order=["passion projects", "volunteering"],
    )
    full = "Jane Doe\njane@x.com • 555-1212 • NYC\nPASSION PROJECTS\nBuilt things\n"
    pt = PdfText(text=full, lines=[ln.strip() for ln in full.splitlines() if ln.strip()])
    with patch("core.ats_gate.call_llm", return_value=_PARSED_OK):
        report = run_gate(pt, doc, [], [], [], "PROMPT {extracted_text}", object(), "m")
    assert report.passed is True
    assert not any(i.code == "section_missing" for i in report.issues)
