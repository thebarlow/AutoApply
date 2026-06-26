from __future__ import annotations

from core.profile_tree import FieldNode, GroupNode, ListNode, RootNode, SectionNode
from core.section_generator import _format_block, _coerce_to_format


def _exp_section():
    item = GroupNode(name="Experience Item", children=[
        FieldNode(name="Company", key="company", kind="text", value="Acme"),
        FieldNode(name="Summary", key="summary", kind="bullets",
                  llm_output=True, output_format="bullets"),
    ])
    return SectionNode(name="Experience", role="experience", children=[
        ListNode(name="Experience", item_template=item, children=[item.model_copy(deep=True)]),
    ])


def test_format_block_lists_outputable_formatted_fields():
    fields = _exp_section().children[0].children[0].children
    block = _format_block(fields)
    assert "# Output Format" in block
    assert '"summary"' in block
    assert "array of concise bullet strings" in block
    # non-output / unformatted fields are not listed
    assert '"company"' not in block


def test_format_block_empty_when_no_formats():
    fields = [FieldNode(name="X", key="x", kind="markdown", llm_output=True)]
    assert _format_block(fields) == ""


def test_coerce_bullets_splits_string_into_list():
    f = FieldNode(name="S", key="summary", kind="bullets", llm_output=True, output_format="bullets")
    assert _coerce_to_format("- did A\n- did B", f) == ["did A", "did B"]
    assert _coerce_to_format(["x", " y "], f) == ["x", "y"]


def test_coerce_paragraph_joins_list_into_string():
    f = FieldNode(name="H", key="hero", kind="markdown", llm_output=True, output_format="paragraph")
    assert _coerce_to_format(["one", "two"], f) == "one\ntwo"
    assert _coerce_to_format("hello", f) == "hello"


def test_coerce_passthrough_when_no_format():
    f = FieldNode(name="H", key="hero", kind="markdown", llm_output=True)
    assert _coerce_to_format("hello", f) == "hello"
    assert _coerce_to_format(["a"], f) == ["a"]
