import logging

from core.log_context import ContextFilter, bind, clear, snapshot


def test_snapshot_defaults_to_none():
    clear()
    assert snapshot() == {"request_id": None, "route": None, "profile_id": None}


def test_bind_then_snapshot():
    clear()
    bind(request_id="abc", route="/api/x", profile_id=7)
    assert snapshot() == {"request_id": "abc", "route": "/api/x", "profile_id": 7}
    clear()
    assert snapshot()["request_id"] is None


def test_filter_injects_attributes():
    clear()
    bind(request_id="rid", route="/r", profile_id=3)
    rec = logging.LogRecord("n", logging.ERROR, __file__, 1, "msg", None, None)
    assert ContextFilter().filter(rec) is True
    assert rec.request_id == "rid"
    assert rec.route == "/r"
    assert rec.profile_id == 3
    clear()
