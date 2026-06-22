from __future__ import annotations

from core.profile_tree import (
    FieldNode, GroupNode, ListNode, RootNode, SectionNode,
)
from core.tree_render import render_tree_markdown


def _f(key, value, *, output=False, ctx=False, kind="markdown", visible=True):
    return FieldNode(name=key.title(), key=key, kind=kind, value=value, visible=visible,
                     llm_output=output, llm_input=ctx)


def test_renders_sections_overlays_authored_and_omits_context_only():
    blurb = _f("blurb", "stored", output=True)
    root = RootNode(children=[
        SectionNode(name="Leadership", role=None, children=[
            GroupNode(name="Leadership", children=[
                _f("org", "Acme"),                       # immutable → rendered
                blurb,                                    # outputable → overlaid
                _f("note", "secret", ctx=True),           # context-only → omitted
            ])
        ]),
        SectionNode(name="Skills", role="skills", children=[
            _f("skills", ["Python", "SQL"], kind="taglist")
        ]),
    ])
    md = render_tree_markdown(root, {blurb.id: "authored blurb"})
    assert "## Leadership" in md
    assert "authored blurb" in md       # overlay applied
    assert "stored" not in md           # stored outputable value replaced
    assert "Acme" in md                 # immutable rendered
    assert "secret" not in md           # context-only omitted
    assert "## Skills" in md
    assert "Python" in md and "SQL" in md


def test_locked_outputable_uses_stored_value_when_absent_from_authored():
    f = _f("b", "kept", output=True)
    root = RootNode(children=[SectionNode(name="X", role=None, children=[
        GroupNode(name="X", children=[f])])])
    md = render_tree_markdown(root, {})  # nothing authored
    assert "kept" in md


def test_hidden_section_skipped():
    root = RootNode(children=[SectionNode(name="Hidden", role=None, visible=False, children=[
        GroupNode(name="Hidden", children=[_f("a", "x")])])])
    assert "Hidden" not in render_tree_markdown(root, {})


def test_list_entries_render():
    root = RootNode(children=[SectionNode(name="Experience", role="experience", children=[
        ListNode(name="Experience", item_template=GroupNode(name="E", children=[_f("company", "")]),
                 children=[
                     GroupNode(name="E", children=[_f("company", "Acme"), _f("summary", "did things")]),
                     GroupNode(name="E", children=[_f("company", "Beta"), _f("summary", "more things")]),
                 ])])])
    md = render_tree_markdown(root, {})
    assert "Acme" in md and "Beta" in md and "did things" in md
