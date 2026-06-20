from __future__ import annotations

import core.job as jobmod
from core.job import Job


def test_evaluate_body_scores_a_markdown_string(monkeypatch):
    monkeypatch.setattr(jobmod, "call_llm",
                        lambda *a, **k: '{"score": 0.82, "issues": []}')
    job = Job(job_key="k", profile_id=1)
    out = job.evaluate_resume_body("## Experience\n\n- did things",
                                   "EVAL {current_document}", user=None, client=None, model="m")
    assert out["score"] == 0.82
    assert out["issues"] == []


def test_evaluate_body_empty_is_hard_fail(monkeypatch):
    monkeypatch.setattr(jobmod, "call_llm", lambda *a, **k: '{"score": 1.0, "issues": []}')
    job = Job(job_key="k", profile_id=1)
    out = job.evaluate_resume_body("   ", "EVAL {current_document}",
                                   user=None, client=None, model="m")
    assert out["score"] == 0.0  # empty body short-circuits, never scored by LLM
