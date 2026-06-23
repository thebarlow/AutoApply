from core.profile_tree import FieldNode, GroupNode, RootNode, SectionNode
from core.section_generator import generate_resume_by_section


class _FakeResp:
    def __init__(self, fields): self.fields = fields; self.entries = {}


def _root():
    return RootNode(children=[
        SectionNode(name="Summary", role="summary", order=0, children=[
            GroupNode(name="g", children=[
                FieldNode(name="Hero", key="hero", kind="markdown", value="", llm_output=True),
            ]),
        ]),
        SectionNode(name="Skills", role="skills", order=1, children=[
            GroupNode(name="g2", children=[
                FieldNode(name="Skills", key="skills", kind="taglist", value=[], llm_output=True),
            ]),
        ]),
    ])


def test_only_sections_limits_regeneration(monkeypatch):
    root = _root()
    seen_prompts = []

    def fake_call(prompt, client, model, schema, **kw):
        seen_prompts.append(prompt)
        return _FakeResp({"hero": "new", "skills": ["x"]})

    monkeypatch.setattr("core.job._llm_json_with_retry", fake_call)
    out = generate_resume_by_section(root, "ctx", object(), "m", only_sections={"Summary"})

    hero_id = root.children[0].children[0].children[0].id
    skills_id = root.children[1].children[0].children[0].id
    assert hero_id in out          # Summary regenerated
    assert skills_id not in out    # Skills skipped
    assert len(seen_prompts) == 1  # only one section called


def test_critique_block_injected(monkeypatch):
    root = _root()
    seen = []

    def fake_call(prompt, client, model, schema, **kw):
        seen.append(prompt); return _FakeResp({"hero": "new"})

    monkeypatch.setattr("core.job._llm_json_with_retry", fake_call)
    generate_resume_by_section(
        root, "ctx", object(), "m",
        only_sections={"Summary"},
        critiques={"Summary": [{"category": "tailoring", "description": "too generic"}]},
    )
    assert "FIX THESE ISSUES" in seen[0]
    assert "too generic" in seen[0]
