import json

from core.user import EEO_KEYS, ELIGIBILITY_KEYS, User


def _user(answers):
    u = User.__new__(User)
    # Bypass SQLAlchemy instrumentation by setting __dict__ directly
    u.__dict__["data"] = json.dumps({"application_answers": answers})
    u._hydrate()
    return u


def test_answers_roundtrip_through_to_dict():
    answers = {"eligibility": {"work_authorized": "yes"}, "eeo": {"gender": "Female"}}
    u = _user(answers)
    assert u.application_answers == answers
    # to_dict must carry it back out for persistence
    assert u.to_dict()["application_answers"] == answers


def test_missing_answers_defaults_to_empty():
    u = _user(None)
    assert u.application_answers == {"eligibility": {}, "eeo": {}}


def test_completeness_requires_all_eligibility_and_eeo_choices():
    complete = {
        "eligibility": {k: "yes" for k in ELIGIBILITY_KEYS},
        "eeo": {k: "Decline to self-identify" for k in EEO_KEYS},
    }
    assert _user(complete).application_answers_complete() is True
    partial = {"eligibility": {ELIGIBILITY_KEYS[0]: "yes"}, "eeo": {}}
    assert _user(partial).application_answers_complete() is False
