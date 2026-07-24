import logging

from core.log_context import ContextFilter, bind, clear, snapshot


def test_snapshot_defaults_to_none():
    clear()
    assert snapshot() == {
        "request_id": None,
        "route": None,
        "method": None,
        "profile_id": None,
        "account_email": None,
    }


def test_bind_then_snapshot():
    clear()
    bind(request_id="abc", route="/api/x", profile_id=7)
    assert snapshot() == {
        "request_id": "abc",
        "route": "/api/x",
        "method": None,
        "profile_id": 7,
        "account_email": None,
    }
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


def test_bind_method_and_email_stamped_on_record():
    from core import log_context

    log_context.bind(method="POST", account_email="a@b.com")
    try:
        rec = logging.LogRecord("l", 40, "a.py", 1, "m", None, None)
        log_context.ContextFilter().filter(rec)
        assert rec.method == "POST"
        assert rec.account_email == "a@b.com"
    finally:
        log_context.clear()


def test_fmt_formats_without_bound_context():
    import logging
    from core.logging_config import _FMT
    from core.log_context import ContextFilter, clear

    clear()
    rec = logging.LogRecord("l", 20, "a.py", 1, "hello", None, None)
    ContextFilter().filter(rec)
    line = logging.Formatter(_FMT).format(rec)
    assert "hello" in line
    assert "None" in line  # unbound context renders as None, not a KeyError
