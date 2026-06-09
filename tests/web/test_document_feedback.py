from web.intake_pipeline import build_feedback_issues


def test_build_feedback_issues_formats_and_filters():
    notes = [
        {"section": "summary", "label": "Profile summary", "note": "make punchier"},
        {"section": "experience:0", "label": "Experience [0] (Eng at Acme)", "note": "  quantify  "},
        {"section": "skills", "label": "Skills", "note": "   "},   # dropped (empty)
    ]
    issues = build_feedback_issues(notes)
    assert issues == [
        {"category": "user_feedback", "description": "Profile summary: make punchier"},
        {"category": "user_feedback", "description": "Experience [0] (Eng at Acme): quantify"},
    ]


def test_build_feedback_issues_empty():
    assert build_feedback_issues([]) == []
    assert build_feedback_issues([{"label": "x", "note": ""}]) == []
