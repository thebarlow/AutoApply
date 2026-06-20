from __future__ import annotations

import web.routers.dev as devmod


class _Job:
    job_key = "k"
    def build_resume_prompt(self, user, prompt, db):
        return "RESUME_PROMPT"
    def evaluate_resume_body(self, body, eval_prompt, user, client, model):
        return {"score": 0.7 if "ONE" in body else 0.9, "issues": []}


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
