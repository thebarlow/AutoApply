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


import json
from unittest.mock import MagicMock, patch


def test_run_user_feedback_refine_keeps_user_version():
    """Applies refine with built issues, appends a user_feedback eval turn,
    sets the score, and never restores a prior 'best' turn."""
    notes = [{"section": "summary", "label": "Profile summary", "note": "punchier"}]

    job = MagicMock()
    job.resume_eval_log = json.dumps([
        {"turn": 1, "score": 0.95, "issues": [], "passed": True},  # a higher prior turn
    ])
    refine_fn = MagicMock()
    job.refine_resume_md = refine_fn
    job.evaluate_resume_md = MagicMock(return_value={"score": 0.50, "issues": [{"category": "x", "description": "y"}]})

    user = MagicMock()
    user.resolve_prompt.return_value = "PROMPT"

    import web.intake_pipeline as ip
    with patch.object(ip, "SessionLocal") as SL, \
         patch.object(ip.Job, "get", return_value=job), \
         patch.object(ip.User, "load", return_value=user), \
         patch.object(ip, "get_client_for_profile", return_value=("client", "model")), \
         patch.object(ip, "run_ats_gate") as ats, \
         patch.object(ip, "_emit"):
        SL.return_value = MagicMock()
        ip.run_user_feedback_refine("k1", "resume", notes)

    # refine called with our built issues
    args, kwargs = refine_fn.call_args
    passed_issues = args[5]  # (user, prompt, client, model, db, issues, template)
    assert passed_issues == [{"category": "user_feedback", "description": "Profile summary: punchier"}]

    # a user_feedback turn was appended with the new (lower) score; no restore to 0.95
    log = json.loads(job.resume_eval_log)
    assert log[-1]["source"] == "user_feedback"
    assert log[-1]["score"] == 0.50
    assert job.resume_eval_score == 0.50  # kept the user-directed result, not 0.95
    ats.assert_called_once_with("k1")
