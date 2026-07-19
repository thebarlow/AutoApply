"""Server-side clamping of user-supplied refinement settings.

Refinement turns run unmetered inside the flat generation price, so the stored
values must be clamped on load — otherwise a tenant could write an arbitrarily
high turn count into their profile blob and mint free LLM calls.
"""
from __future__ import annotations

from core.user import MAX_REFINE_TURNS, _clamp_pass_score, _clamp_refine_turns


def test_turns_above_cap_clamped():
    assert _clamp_refine_turns(500) == MAX_REFINE_TURNS


def test_turns_negative_clamped_to_zero():
    assert _clamp_refine_turns(-3) == 0


def test_turns_missing_uses_default():
    assert _clamp_refine_turns(None) == 3


def test_turns_garbage_uses_default():
    assert _clamp_refine_turns("lots") == 3


def test_turns_valid_passthrough():
    assert _clamp_refine_turns(2) == 2


def test_pass_score_above_one_clamped():
    assert _clamp_pass_score(2.5) == 1.0


def test_pass_score_negative_clamped():
    assert _clamp_pass_score(-1) == 0.0


def test_pass_score_missing_uses_default():
    assert _clamp_pass_score(None) == 0.80


def test_user_hydrate_clamps():
    import json

    from core.user import User

    u = User(id=1, name="t")
    u.data = json.dumps({
        "resume_refine_max_turns": 999,
        "resume_refine_pass_score": 5.0,
        "cover_refine_max_turns": -1,
        "cover_refine_pass_score": -0.5,
    })
    u._hydrate()
    assert u.resume_refine_max_turns == MAX_REFINE_TURNS
    assert u.resume_refine_pass_score == 1.0
    assert u.cover_refine_max_turns == 0
    assert u.cover_refine_pass_score == 0.0
