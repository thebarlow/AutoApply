from types import SimpleNamespace
import core.metering as metering
import core.llm as llm


class _FakeClient:
    def __init__(self, cost):
        usage = SimpleNamespace(cost=cost, prompt_tokens=10, completion_tokens=5)
        msg = SimpleNamespace(content="hi")
        choice = SimpleNamespace(message=msg, finish_reason="stop")
        self._resp = SimpleNamespace(usage=usage, choices=[choice])
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **k: self._resp))


def test_call_llm_records_into_active_meter():
    captured = []
    token = metering._meter.set(captured)
    try:
        out = llm.call_llm("p", _FakeClient(0.0033), "modelZ")
    finally:
        metering._meter.reset(token)
    assert out == "hi"
    assert len(captured) == 1
    assert captured[0]["cost"] == 0.0033
    assert captured[0]["model"] == "modelZ"
