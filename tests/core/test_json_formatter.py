import json
import logging

from core.logging_config import JsonFormatter


def _record(**kw):
    rec = logging.LogRecord("mylogger", logging.ERROR, __file__, 1, "boom", None, None)
    for k, v in kw.items():
        setattr(rec, k, v)
    return rec


def test_json_formatter_basic_fields():
    out = json.loads(JsonFormatter().format(_record(route="/r", profile_id=2, request_id="x")))
    assert out["level"] == "ERROR"
    assert out["logger"] == "mylogger"
    assert out["msg"] == "boom"
    assert out["route"] == "/r"
    assert out["profile_id"] == 2
    assert out["request_id"] == "x"
    assert "ts" in out
    assert "exc_info" not in out


def test_json_formatter_includes_traceback():
    try:
        raise ValueError("nope")
    except ValueError:
        import sys
        rec = logging.LogRecord(
            "l", logging.ERROR, __file__, 1, "failed", None, sys.exc_info()
        )
    out = json.loads(JsonFormatter().format(rec))
    assert "ValueError: nope" in out["exc_info"]


def test_json_formatter_missing_context_is_none():
    out = json.loads(JsonFormatter().format(_record()))
    assert out["route"] is None
    assert out["profile_id"] is None
    assert out["request_id"] is None
    assert out["method"] is None
    assert out["account_email"] is None


def test_json_formatter_includes_method_and_email():
    rec = logging.LogRecord("l", 40, "a.py", 1, "m", None, None)
    rec.method = "GET"
    rec.account_email = "x@y.com"
    out = json.loads(JsonFormatter().format(rec))
    assert out["method"] == "GET"
    assert out["account_email"] == "x@y.com"
