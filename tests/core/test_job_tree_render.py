# tests/core/test_job_tree_render.py
from pathlib import Path

from core.job import Job, _OUTPUTS_DIR
from core.profile_tree import FieldNode, GroupNode, RootNode, SectionNode


def _tree() -> RootNode:
    return RootNode(children=[
        SectionNode(name="Header", role="header", order=0, children=[
            GroupNode(name="Contact", children=[
                FieldNode(name="First Name", key="first_name", kind="text", value="Jane"),
                FieldNode(name="Last Name", key="last_name", kind="text", value="Doe"),
                FieldNode(name="Email", key="email", kind="text", value="j@x.co"),
            ]),
        ]),
        SectionNode(name="Patents", order=1, children=[
            GroupNode(name="g", children=[
                FieldNode(name="Detail", key="detail", kind="markdown", value="A patent."),
            ]),
        ]),
    ])


def test_write_resume_markdown_tree_has_no_frontmatter(tmp_path, monkeypatch):
    job = Job(job_key="jk1", title="t", company="c")
    job.write_resume_markdown(_tree())
    md = (_OUTPUTS_DIR / "jk1_resume.md").read_text(encoding="utf-8")
    assert not md.startswith("---")        # no YAML frontmatter
    assert "# Jane Doe" in md
    assert "## Patents" in md              # custom section reaches the .md
