from core.schemas import AtsIssue, AtsReport, PdfText, AtsParsedFields


def test_ats_issue_defaults_and_fields():
    issue = AtsIssue(layer="mechanical", severity="critical", code="contact_missing", message="email missing")
    assert issue.layer == "mechanical"
    assert issue.severity == "critical"
    assert issue.code == "contact_missing"


def test_ats_report_passed_computed_from_issues():
    crit = AtsIssue(layer="mechanical", severity="critical", code="x", message="m")
    warn = AtsIssue(layer="semantic", severity="warning", code="y", message="m")
    report = AtsReport.build(score=0.4, issues=[crit, warn], extracted_text="abc")
    assert report.passed is False
    report2 = AtsReport.build(score=0.9, issues=[warn], extracted_text="abc")
    assert report2.passed is True


def test_pdf_text_holds_text_and_lines():
    pt = PdfText(text="a\nb", lines=["a", "b"])
    assert pt.lines == ["a", "b"]


def test_ats_parsed_fields_defaults():
    f = AtsParsedFields()
    assert f.name == "" and f.skills == [] and f.sections == []
