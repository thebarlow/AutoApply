# tests/core/test_ats_roundtrip.py
import json
from unittest.mock import patch

from core.ats_gate import check_roundtrip
from core.schemas import PdfText, ResumeDocument, ResumeHeader


def _doc():
    return ResumeDocument(header=ResumeHeader(name="Jane Doe", email="jane@x.com"))


def _pt():
    return PdfText(text="Jane Doe jane@x.com", lines=["Jane Doe jane@x.com"])


def test_roundtrip_flags_name_mismatch():
    parsed = {"name": "Jane Doh", "email": "jane@x.com", "phone": "",
              "sections": [], "skills": [], "experience_dates": []}
    with patch("core.ats_gate.call_llm", return_value=json.dumps(parsed)):
        issues = check_roundtrip(_pt(), _doc(), "PROMPT {extracted_text}", client=object(), model="m")
    assert any(i.code == "roundtrip_name" for i in issues)
    assert all(i.severity == "warning" and i.layer == "semantic" for i in issues)


def test_roundtrip_clean_when_fields_match():
    parsed = {"name": "Jane Doe", "email": "jane@x.com", "phone": "",
              "sections": [], "skills": [], "experience_dates": []}
    with patch("core.ats_gate.call_llm", return_value=json.dumps(parsed)):
        issues = check_roundtrip(_pt(), _doc(), "PROMPT {extracted_text}", client=object(), model="m")
    assert issues == []


def test_roundtrip_returns_empty_on_llm_error():
    with patch("core.ats_gate.call_llm", side_effect=RuntimeError("boom")):
        issues = check_roundtrip(_pt(), _doc(), "PROMPT {extracted_text}", client=object(), model="m")
    assert issues == []


def test_roundtrip_flags_phone_mismatch():
    from core.schemas import ResumeHeader, ResumeDocument, PdfText
    parsed = {"name": "Jane Doe", "email": "jane@x.com", "phone": "555-9999",
              "sections": [], "skills": [], "experience_dates": []}
    doc = ResumeDocument(header=ResumeHeader(name="Jane Doe", email="jane@x.com", phone="555-1212"))
    pt = PdfText(text="Jane Doe jane@x.com 555-1212", lines=["Jane Doe jane@x.com 555-1212"])
    with patch("core.ats_gate.call_llm", return_value=json.dumps(parsed)):
        issues = check_roundtrip(pt, doc, "PROMPT {extracted_text}", client=object(), model="m")
    assert any(i.code == "roundtrip_phone" for i in issues)
