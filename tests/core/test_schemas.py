from __future__ import annotations
import pytest


def test_parse_plain_json():
    from core.schemas import parse_llm_json, EvalResponse
    r = parse_llm_json('{"score": 0.5, "issues": []}', EvalResponse)
    assert r.score == 0.5
    assert r.issues == []


def test_parse_fenced_json():
    from core.schemas import parse_llm_json, EvalResponse
    raw = "```json\n{\"score\": 0.7, \"issues\": []}\n```"
    r = parse_llm_json(raw, EvalResponse)
    assert r.score == 0.7


def test_parse_json_with_surrounding_prose():
    from core.schemas import parse_llm_json, EvalResponse
    raw = "Here is the result:\n{\"score\": 0.4, \"issues\": []}\nThanks!"
    r = parse_llm_json(raw, EvalResponse)
    assert r.score == 0.4


def test_parse_malformed_json_raises():
    from core.schemas import parse_llm_json, EvalResponse
    with pytest.raises(RuntimeError):
        parse_llm_json("{not valid json", EvalResponse)


def test_parse_schema_violation_raises():
    from core.schemas import parse_llm_json, ScoreResponse
    with pytest.raises(RuntimeError):
        parse_llm_json('{"fit_score": 0.5}', ScoreResponse)


def test_parse_empty_raises():
    from core.schemas import parse_llm_json, EvalResponse
    with pytest.raises(RuntimeError):
        parse_llm_json("   ", EvalResponse)


def test_score_clamps_out_of_range():
    from core.schemas import ScoreResponse
    r = ScoreResponse.model_validate({
        "fit_score": 1.7, "desirability_score": -0.3,
        "fit_justification": {"raised": [], "lowered": []},
        "desirability_justification": {"raised": [], "lowered": []},
    })
    assert r.fit_score == 1.0
    assert r.desirability_score == 0.0


def test_eval_non_list_issues_coerces_to_empty():
    from core.schemas import parse_llm_json, EvalResponse
    r = parse_llm_json('{"score": 0.5, "issues": "oops"}', EvalResponse)
    assert r.issues == []


def test_extraction_defaults():
    from core.schemas import parse_llm_json, ExtractionResponse
    r = parse_llm_json('{"seniority": "senior"}', ExtractionResponse)
    assert r.seniority == "senior"
    assert r.required_skills == []
    assert r.salary_min is None


def test_parse_no_json_object_raises():
    from core.schemas import parse_llm_json, EvalResponse
    with pytest.raises(RuntimeError):
        parse_llm_json("the model said no", EvalResponse)


def test_parse_value_ending_in_backticks():
    from core.schemas import parse_llm_json, Issue
    # A JSON value whose content ends with backticks must not be corrupted.
    r = parse_llm_json('{"category": "x", "description": "use ```code```"}', Issue)
    assert r.description == "use ```code```"
