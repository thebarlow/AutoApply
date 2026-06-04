from __future__ import annotations

import pytest

import core.job as jobmod
from core.job import _llm_json_with_retry
from core.schemas import ResumeGeneration

_GOOD = '{"profile_summary": "ok"}'
# A description value broken out of its JSON string — the real DeepSeek/Haiku
# failure mode ("Expecting value" at the value position).
_BAD = '{\n  "profile_summary": "ok",\n  "experience": [\n    {"ref": 0, "description":\n- broke out}\n  ]\n}'


def _stub(responses):
    """Return a call_llm stub yielding successive responses and recording prompts."""
    state = {"i": 0, "prompts": []}

    def stub(prompt, client, model, max_tokens=8192):
        state["prompts"].append(prompt)
        r = responses[min(state["i"], len(responses) - 1)]
        state["i"] += 1
        return r

    return stub, state


def test_retries_once_then_succeeds(monkeypatch):
    stub, state = _stub([_BAD, _GOOD])
    monkeypatch.setattr(jobmod, "call_llm", stub)
    out = _llm_json_with_retry("base", None, "m", ResumeGeneration,
                               max_tokens=100, empty_msg="empty")
    assert isinstance(out, ResumeGeneration)
    assert out.profile_summary == "ok"
    assert state["i"] == 2  # one retry happened


def test_succeeds_first_try_no_retry(monkeypatch):
    stub, state = _stub([_GOOD])
    monkeypatch.setattr(jobmod, "call_llm", stub)
    _llm_json_with_retry("base", None, "m", ResumeGeneration, max_tokens=100, empty_msg="empty")
    assert state["i"] == 1  # no retry


def test_raises_after_exhausting_retries(monkeypatch):
    stub, state = _stub([_BAD, _BAD])
    monkeypatch.setattr(jobmod, "call_llm", stub)
    with pytest.raises(RuntimeError, match="not valid JSON"):
        _llm_json_with_retry("base", None, "m", ResumeGeneration, max_tokens=100, empty_msg="empty")
    assert state["i"] == 2  # initial + 1 retry, then give up


def test_empty_response_raises_empty_msg(monkeypatch):
    stub, _ = _stub([""])
    monkeypatch.setattr(jobmod, "call_llm", stub)
    with pytest.raises(RuntimeError, match="my-empty-msg"):
        _llm_json_with_retry("base", None, "m", ResumeGeneration, max_tokens=100, empty_msg="my-empty-msg")


def test_first_call_hardens_prompt(monkeypatch):
    stub, state = _stub([_GOOD])
    monkeypatch.setattr(jobmod, "call_llm", stub)
    _llm_json_with_retry("BASEPROMPT", None, "m", ResumeGeneration, max_tokens=100, empty_msg="empty")
    sent = state["prompts"][0]
    assert "BASEPROMPT" in sent
    assert "valid JSON" in sent  # strict-JSON instruction appended
