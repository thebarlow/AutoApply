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


def test_locked_section_is_skipped(monkeypatch):
    import core.section_generator as sg

    captured = []

    def _capture_stub(prompt, client, model, schema, **kw):
        captured.append(prompt)
        return sg.SectionOutput(fields={}, entries={})

    monkeypatch.setattr(sg, "_llm_json_with_retry", _capture_stub, raising=False)
    import core.job
    monkeypatch.setattr(core.job, "_llm_json_with_retry", _capture_stub)
    root = RootNode(children=[
        SectionNode(name="Sum", order=0, locked=True, children=[
            FieldNode(name="Hero", key="hero", kind="markdown", value="x", llm_output=True)]),
    ])
    out = generate_resume_by_section(root, "JOB", object(), "m")
    assert out == {}
    assert captured == []  # no call for a locked section


def test_section_and_item_prompts_appear_in_prompt(monkeypatch):
    import core.section_generator as sg

    captured = []
    import core.job
    monkeypatch.setattr(core.job, "_llm_json_with_retry", lambda prompt, client, model, schema, **kw: (captured.append(prompt), sg.SectionOutput(fields={}, entries={}))[1])
    root = RootNode(children=[
        SectionNode(name="Exp", order=0, prompt="SECTION_GUIDE", children=[
            ListNode(name="Exp", item_template=GroupNode(children=[
                FieldNode(name="Bul", key="bul", kind="markdown", value="", llm_output=True)]),
                children=[GroupNode(name="E", prompt="ITEM_GUIDE", children=[
                    FieldNode(name="Bul", key="bul", kind="markdown", value="", llm_output=True)])])]),
    ])
    generate_resume_by_section(root, "JOB", object(), "m", resolve=lambda s: s.replace("GUIDE", "G!"))
    assert len(captured) == 1
    assert "SECTION_G!" in captured[0]
    assert "ITEM_G!" in captured[0]


def test_locked_item_not_authored(monkeypatch):
    import core.section_generator as sg
    import core.job

    def _stub(prompt, client, model, schema, **kw):
        return sg.SectionOutput(entries={"keep": {"bul": "NEW"}, "lock": {"bul": "NEW"}})

    monkeypatch.setattr(core.job, "_llm_json_with_retry", _stub)
    tmpl = GroupNode(children=[FieldNode(name="Bul", key="bul", kind="markdown", llm_output=True)])
    keep = GroupNode(id="keep", name="E", children=[
        FieldNode(id="kf", name="Bul", key="bul", kind="markdown", value="", llm_output=True)])
    lock = GroupNode(id="lock", name="E", locked=True, children=[
        FieldNode(id="lf", name="Bul", key="bul", kind="markdown", value="", llm_output=True)])
    root = RootNode(children=[SectionNode(name="Exp", order=0, children=[
        ListNode(name="Exp", item_template=tmpl, children=[keep, lock])])])
    out = generate_resume_by_section(root, "JOB", object(), "m")
    assert out == {"kf": "NEW"}  # locked entry's field never authored


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


def test_list_prompt_contains_folded_format(monkeypatch):
    import core.job
    from core.section_generator import SectionOutput

    captured = {}

    def fake(prompt, client, model, schema, **kw):
        captured["prompt"] = prompt
        return SectionOutput(entries={})

    monkeypatch.setattr(core.job, "_llm_json_with_retry", fake)

    entry = GroupNode(name="Research Assistant", prompt="stress ML pubs", children=[
        FieldNode(name="Summary", key="summary", kind="markdown",
                  value="old", llm_output=True),
    ])
    lst = ListNode(name="Experience", item_template=GroupNode(), children=[entry])
    sec = SectionNode(name="Experience", role="experience", prompt="Lead with impact",
                      order=0, children=[lst])
    root = RootNode(children=[sec])

    generate_resume_by_section(root, "JOBCTX", client=object(), model="m")
    assert "[Experience: Lead with impact [Research Assistant: stress ML pubs]]" in captured["prompt"]
