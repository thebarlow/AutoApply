"""Tests for parse schema fields: section headings and per-section customize."""

from core.schemas import ParseResponse, ProposedSection


def test_parse_response_has_heading_fields_defaulting_empty():
    """ParseResponse heading fields should default to empty strings."""
    pr = ParseResponse()
    assert pr.work_history_heading == ""
    assert pr.skills_heading == ""


def test_parse_response_accepts_headings():
    """ParseResponse should accept and store heading values."""
    pr = ParseResponse.model_validate({"work_history_heading": "Employment History"})
    assert pr.work_history_heading == "Employment History"


def test_proposed_section_customize_defaults():
    """ProposedSection customize and prompt should default to False and empty string."""
    ps = ProposedSection(
        name="Skills",
        kind="taglist",
        origin="builtin",
        matches_existing=True,
        existing_has_data=True,
        default_action="add",
        allowed_actions=["add", "skip"],
    )
    assert ps.customize is False
    assert ps.prompt == ""
