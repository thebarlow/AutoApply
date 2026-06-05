# tests/core/test_ats_mechanical.py
from core.ats_gate import check_mechanical
from core.schemas import PdfText, ResumeDocument, ResumeHeader, ResumeSkillGroup


def _doc() -> ResumeDocument:
    return ResumeDocument(
        header=ResumeHeader(name="Jane Doe", email="jane@x.com", phone="555-1212", location="NYC"),
        section_order=["experience", "education", "skills"],
        skills=[ResumeSkillGroup(category="Lang", items=["Python", "SQL"])],
    )


def _clean_text() -> PdfText:
    full = (
        "Jane Doe\n"
        "jane@x.com • 555-1212 • NYC\n"
        "EXPERIENCE\nBuilt things in Python and SQL\n"
        "EDUCATION\nBS\n"
        "SKILLS\nPython, SQL\n"
    )
    return PdfText(text=full, lines=[l.strip() for l in full.splitlines() if l.strip()])


def _codes(issues):
    return {i.code for i in issues}


def test_clean_resume_has_no_critical_issues():
    issues = check_mechanical(_clean_text(), _doc(), ["Python"], [], ["Python", "SQL"])
    assert not any(i.severity == "critical" for i in issues)


def test_no_text_layer_is_critical():
    issues = check_mechanical(PdfText(text="  ", lines=[]), _doc(), [], [], [])
    assert "no_text_layer" in _codes(issues)
    assert all(i.severity == "critical" for i in issues if i.code == "no_text_layer")


def test_missing_email_is_critical_contact_missing():
    pt = _clean_text()
    pt = PdfText(text=pt.text.replace("jane@x.com", ""), lines=[l for l in pt.lines if "jane@x.com" not in l])
    issues = check_mechanical(pt, _doc(), [], [], [])
    assert "contact_missing" in _codes(issues)


def test_contact_order_scramble_is_critical():
    full = "Jane Doe\n555-1212 • jane@x.com • NYC\nEXPERIENCE\nEDUCATION\nSKILLS\n"
    pt = PdfText(text=full, lines=[l.strip() for l in full.splitlines() if l.strip()])
    issues = check_mechanical(pt, _doc(), [], [], [])
    assert "contact_order" in _codes(issues)


def test_missing_section_is_critical():
    full = "Jane Doe\njane@x.com • 555-1212 • NYC\nEXPERIENCE\nSKILLS\n"  # no EDUCATION
    pt = PdfText(text=full, lines=[l.strip() for l in full.splitlines() if l.strip()])
    issues = check_mechanical(pt, _doc(), [], [], [])
    assert "section_missing" in _codes(issues)


def test_present_relevant_skill_dropped_is_warning():
    full = "Jane Doe\njane@x.com • 555-1212 • NYC\nEXPERIENCE\nEDUCATION\nSKILLS\nPython\n"
    pt = PdfText(text=full, lines=[l.strip() for l in full.splitlines() if l.strip()])
    issues = check_mechanical(pt, _doc(), ["SQL"], [], ["Python", "SQL"])
    dropped = [i for i in issues if i.code == "present_skill_dropped"]
    assert dropped and dropped[0].severity == "warning"
    assert "SQL" in dropped[0].message


def test_skill_not_held_is_not_flagged():
    full = "Jane Doe\njane@x.com • 555-1212 • NYC\nEXPERIENCE\nEDUCATION\nSKILLS\nPython, SQL\n"
    pt = PdfText(text=full, lines=[l.strip() for l in full.splitlines() if l.strip()])
    issues = check_mechanical(pt, _doc(), ["Rust"], [], ["Python", "SQL"])
    assert not any(i.code == "present_skill_dropped" for i in issues)


def test_glyph_junk_is_warning():
    # U+E000 is a Private Use Area glyph — matches the [-] regex
    pua = ""
    full = f"Jane Doe\n{pua}jane@x.com • 555-1212 • NYC\nEXPERIENCE\nEDUCATION\nSKILLS\n"
    pt = PdfText(text=full, lines=[l.strip() for l in full.splitlines() if l.strip()])
    issues = check_mechanical(pt, _doc(), [], [], [])
    assert "glyph_junk" in _codes(issues)
