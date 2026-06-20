from __future__ import annotations

import core.job as jobmod
from core.profile_tree import (
    FieldNode, GroupNode, ListNode, RootNode, SectionNode,
)
from core.section_generator import generate_resume_by_section


def _field(key, *, output=False, ctx=False, lock=False, value="", kind="markdown"):
    return FieldNode(
        name=key.title(), key=key, kind=kind, value=value,
        llm_output=output, llm_input=ctx, regen_lock=lock,
        llm_instructions=("write " + key) if output else "",
    )


def _scalar_section():
    # Custom section with a group: one outputable field + one immutable anchor.
    return SectionNode(name="Leadership", role=None, children=[
        GroupNode(name="Leadership", children=[
            _field("org", value="Acme"),                         # immutable
            _field("blurb", output=True, value="old blurb"),     # outputable
        ])
    ])


def _list_section():
    tmpl = GroupNode(name="E", children=[_field("company"), _field("summary", output=True)])
    return SectionNode(name="Experience", role="experience", children=[
        ListNode(name="Experience", item_template=tmpl, children=[
            GroupNode(name="E", id="e0", children=[
                _field("company", value="Acme"), _field("summary", output=True, value="old0")]),
            GroupNode(name="E", id="e1", children=[
                _field("company", value="Beta"), _field("summary", output=True, value="old1")]),
        ])
    ])


def _stub(map_by_call):
    """call_llm stub: returns successive JSON strings, recording prompts."""
    state = {"i": 0, "prompts": []}

    def stub(prompt, client, model, max_tokens=8192):
        state["prompts"].append(prompt)
        r = map_by_call[min(state["i"], len(map_by_call) - 1)]
        state["i"] += 1
        return r

    return stub, state


def test_scalar_section_authors_outputable_only(monkeypatch):
    root = RootNode(children=[_scalar_section()])
    blurb_id = root.children[0].children[0].children[1].id
    stub, state = _stub(['{"fields": {"blurb": "new blurb"}}'])
    monkeypatch.setattr(jobmod, "call_llm", stub)
    out = generate_resume_by_section(root, "JOB", client=None, model="m")
    assert out == {blurb_id: "new blurb"}
    # immutable anchor value was provided as context to the LLM
    assert "Acme" in state["prompts"][0]


def test_list_section_keys_by_entry(monkeypatch):
    root = RootNode(children=[_list_section()])
    s0 = root.children[0].children[0].children[0].children[1].id  # e0.summary
    s1 = root.children[0].children[0].children[1].children[1].id  # e1.summary
    stub, _ = _stub(['{"entries": {"e0": {"summary": "n0"}, "e1": {"summary": "n1"}}}'])
    monkeypatch.setattr(jobmod, "call_llm", stub)
    out = generate_resume_by_section(root, "JOB", client=None, model="m")
    assert out == {s0: "n0", s1: "n1"}


def test_regen_lock_excludes_field_and_skips_call_when_all_locked(monkeypatch):
    sec = SectionNode(name="X", role=None, children=[
        GroupNode(name="X", children=[_field("b", output=True, lock=True, value="keep")])])
    root = RootNode(children=[sec])
    stub, state = _stub(['{"fields": {}}'])
    monkeypatch.setattr(jobmod, "call_llm", stub)
    out = generate_resume_by_section(root, "JOB", client=None, model="m")
    assert out == {}
    assert state["i"] == 0  # no outputable-unlocked fields → no LLM call


def test_section_failure_falls_back_and_continues(monkeypatch):
    root = RootNode(children=[_scalar_section(), _list_section()])
    s0 = root.children[1].children[0].children[0].children[1].id
    s1 = root.children[1].children[0].children[1].children[1].id
    # First section returns garbage (unparseable both times), second succeeds.
    stub, _ = _stub(['not json', 'still not json',
                     '{"entries": {"e0": {"summary": "n0"}, "e1": {"summary": "n1"}}}'])
    monkeypatch.setattr(jobmod, "call_llm", stub)
    out = generate_resume_by_section(root, "JOB", client=None, model="m")
    # Failed scalar section contributes nothing; list section still authored.
    assert out == {s0: "n0", s1: "n1"}
