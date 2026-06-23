from core.schemas import SectionEvalResponse, parse_llm_json


def test_parses_per_section_scores():
    raw = (
        '{"sections": [{"section": "Summary", "score": 0.9, "issues": []},'
        '{"section": "Experience", "score": 0.4, '
        '"issues": [{"category": "tailoring", "description": "too generic"}]}]}'
    )
    resp = parse_llm_json(raw, SectionEvalResponse)
    assert len(resp.sections) == 2
    assert resp.sections[0].section == "Summary"
    assert resp.sections[1].score == 0.4
    assert resp.sections[1].issues[0].category == "tailoring"


def test_score_clamped_to_unit_interval():
    resp = parse_llm_json(
        '{"sections": [{"section": "S", "score": 1.7, "issues": []}]}',
        SectionEvalResponse,
    )
    assert resp.sections[0].score == 1.0


def test_empty_sections_default():
    resp = parse_llm_json("{}", SectionEvalResponse)
    assert resp.sections == []
