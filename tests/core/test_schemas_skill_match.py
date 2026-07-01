from core.schemas import SkillMatchResponse, parse_llm_json


def test_skill_match_parses_matched_list():
    raw = '{"matched": ["Python", "Bachelors degree"]}'
    parsed = parse_llm_json(raw, SkillMatchResponse)
    assert parsed.matched == ["Python", "Bachelors degree"]


def test_skill_match_defaults_empty():
    parsed = parse_llm_json("{}", SkillMatchResponse)
    assert parsed.matched == []
