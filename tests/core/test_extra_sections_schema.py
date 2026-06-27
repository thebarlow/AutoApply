from core.schemas import ParseResponse, ExtraSection, ParsedField, ParsedEntry


def test_extra_sections_defaults_empty():
    r = ParseResponse()
    assert r.extra_sections == []


def test_parse_response_with_extra_sections_round_trips():
    payload = {
        "first_name": "Ada",
        "extra_sections": [
            {"name": "Certifications", "kind": "list",
             "entries": [{"fields": [{"label": "Name", "value": "AWS SAA"},
                                     {"label": "Year", "value": "2023"}]}]},
            {"name": "Languages", "kind": "taglist", "items": ["English", "Spanish"]},
            {"name": "About", "kind": "markdown", "markdown": "Engineer."},
        ],
    }
    r = ParseResponse.model_validate(payload)
    assert r.first_name == "Ada"
    assert [s.kind for s in r.extra_sections] == ["list", "taglist", "markdown"]
    assert r.extra_sections[0].entries[0].fields[1].value == "2023"
    assert r.extra_sections[1].items == ["English", "Spanish"]


def test_invalid_kind_rejected():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ExtraSection(name="X", kind="paragraph")
