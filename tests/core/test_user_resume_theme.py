import json

from core.user import User


def _user_from_data(d: dict) -> User:
    u = User(name="Test", data=json.dumps(d))
    u._hydrate()
    return u


def test_missing_key_defaults_to_classic():
    u = _user_from_data({})
    assert u.resume_theme == "classic"


def test_explicit_theme_loads():
    u = _user_from_data({"resume_theme": "modern"})
    assert u.resume_theme == "modern"


def test_round_trips_through_to_dict():
    u = _user_from_data({"resume_theme": "compact"})
    assert u._to_dict()["resume_theme"] == "compact"
