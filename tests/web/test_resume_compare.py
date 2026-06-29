from __future__ import annotations

import pytest
from fastapi import HTTPException

import web.routers.dev as devmod
from core.job import _apply_template
from core.profile_tree import RootNode, SectionNode, FieldNode, resolve_profile_tokens


class _Job:
    job_key = "k"
    ext_seniority = "Senior"

    def build_resume_prompt(self, user, prompt, db):
        return "RESUME_PROMPT"

    def evaluate_resume_body(self, body, eval_prompt, user, client, model):
        return {"score": 0.7 if "ONE" in body else 0.9, "issues": []}


class _UnextractedJob(_Job):
    ext_seniority = None


def test_run_comparison_returns_both_models(monkeypatch):
    # Model 1 path: stub the building blocks devmod uses.
    monkeypatch.setattr(devmod, "_model1_markdown", lambda job, user, client, model, db: "## M ONE")
    monkeypatch.setattr(devmod, "_model2_markdown", lambda job, user, client, model, db: "## M TWO")
    out = devmod.run_comparison(
        _Job(), user=object(), client=object(), model="m",
        eval_prompt="EVAL {current_document}", db=None,
    )
    assert out["model1"]["markdown"] == "## M ONE"
    assert out["model2"]["markdown"] == "## M TWO"
    assert out["model1"]["score"] == 0.7
    assert out["model2"]["score"] == 0.9


def test_one_model_failure_still_returns_other(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("model1 broke")
    monkeypatch.setattr(devmod, "_model1_markdown", boom)
    monkeypatch.setattr(devmod, "_model2_markdown", lambda *a, **k: "## OK TWO")
    out = devmod.run_comparison(
        _Job(), user=object(), client=object(), model="m",
        eval_prompt="EVAL {current_document}", db=None,
    )
    assert "error" in out["model1"]
    assert out["model2"]["markdown"] == "## OK TWO"


def test_resume_compare_rejects_unextracted_job(monkeypatch):
    """resume_compare must 400 before running either model if the job has not been extracted."""
    comparison_ran = []

    # Patch out everything the endpoint calls so the only thing under test is
    # the ext_seniority guard that must fire before run_comparison is reached.
    monkeypatch.setattr(devmod, "run_comparison", lambda *a, **k: comparison_ran.append(True) or {})
    monkeypatch.setattr(devmod.Job, "get", staticmethod(lambda key, db, pid: _UnextractedJob()))
    monkeypatch.setattr(devmod.User, "load", staticmethod(lambda db, profile_id: object()))
    monkeypatch.setattr(devmod, "get_client_for_profile", lambda user, model: (object(), "m"))

    with pytest.raises(HTTPException) as exc_info:
        devmod.resume_compare("k", db=None, profile_id=1, _admin=None)

    assert exc_info.value.status_code == 400
    assert not comparison_ran, "run_comparison must not be called for an unextracted job"


def test_combined_resolver_substitutes_job_and_profile():
    """Resolver contract: {job.*} and {profile:<id>} tokens are both substituted."""
    skills_field = FieldNode(
        name="T", key="skills", kind="taglist", value=["Python"]
    )
    root = RootNode(
        children=[
            SectionNode(
                name="Skills",
                role="skills",
                order=0,
                children=[skills_field],
            )
        ]
    )

    class _Job:
        title = "Engineer"

    def resolve(text: str) -> str:
        text = resolve_profile_tokens(root, text)
        return _apply_template(text, {"job": _Job()})

    assert (
        resolve("{job.title} knows {profile:%s}" % skills_field.id)
        == "Engineer knows Python"
    )


def test_split_sections_html_header_then_sections():
    html = (
        '<h1>Jane Doe</h1><p>jane@x.com</p>'
        '<h2 id="profile">Profile</h2><p>Summary.</p>'
        '<h2 id="skills">Skills</h2><ul><li>Python</li></ul>'
    )
    out = devmod._split_sections_html(html)
    assert [s["heading"] for s in out] == ["Header", "Profile", "Skills"]
    assert "Jane Doe" in out[0]["html"]
    assert out[1]["html"].startswith("<h2")
    assert "Summary." in out[1]["html"]
    assert "Python" in out[2]["html"]
    # Profile section must not bleed into Skills content.
    assert "Python" not in out[1]["html"]


def test_split_sections_html_no_h2_is_single_header():
    out = devmod._split_sections_html("<p>just a blurb</p>")
    assert out == [{"heading": "Header", "html": "<p>just a blurb</p>"}]


def test_split_sections_html_empty():
    assert devmod._split_sections_html("   ") == []


def test_run_comparison_includes_sections_and_css(monkeypatch):
    monkeypatch.setattr(
        devmod, "_model1_markdown",
        lambda job, user, client, model, db: "## Profile\n\nONE body",
    )
    monkeypatch.setattr(
        devmod, "_model2_markdown",
        lambda job, user, client, model, db: "## Profile\n\nTWO body",
    )
    out = devmod.run_comparison(
        _Job(), user=object(), client=object(), model="m",
        eval_prompt="EVAL {current_document}", db=None,
    )
    assert isinstance(out["css"], str)
    assert out["css"]  # resume.css is non-empty
    headings = [s["heading"] for s in out["model1"]["sections"]]
    assert "Profile" in headings


def test_run_comparison_errored_model_still_has_css(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("nope")
    monkeypatch.setattr(devmod, "_model1_markdown", boom)
    monkeypatch.setattr(
        devmod, "_model2_markdown",
        lambda *a, **k: "## Profile\n\nok",
    )
    out = devmod.run_comparison(
        _Job(), user=object(), client=object(), model="m",
        eval_prompt="EVAL {current_document}", db=None,
    )
    assert "error" in out["model1"]
    assert "sections" not in out["model1"]
    assert isinstance(out["css"], str)
