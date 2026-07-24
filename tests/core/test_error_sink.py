import logging

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import db.database as dbmod
from db.database import Base, ErrorEvent
from core.error_sink import DbErrorHandler, fingerprint


@pytest.fixture
def sink(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[ErrorEvent.__table__])
    TestSession = sessionmaker(bind=engine)
    monkeypatch.setattr(dbmod, "SessionLocal", TestSession)
    return TestSession


def _emit(msg, exc=None):
    handler = DbErrorHandler()
    rec = logging.LogRecord("l", logging.ERROR, __file__, 1, msg, None, exc)
    handler.emit(rec)


def test_emit_inserts_row(sink):
    _emit("boom")
    db = sink()
    assert db.query(ErrorEvent).count() == 1
    assert db.query(ErrorEvent).one().message == "boom"
    db.close()


def test_identical_errors_dedup_and_increment(sink):
    try:
        raise ValueError("x")
    except ValueError:
        import sys
        info = sys.exc_info()
    _emit("boom", info)
    _emit("boom", info)
    db = sink()
    rows = db.query(ErrorEvent).all()
    assert len(rows) == 1
    assert rows[0].count == 2
    db.close()


def test_prune_respects_max_rows(monkeypatch, sink):
    monkeypatch.setenv("ERROR_LOG_MAX_ROWS", "3")
    for suffix in "abcdef":
        _emit(f"msg-{suffix}")  # distinct, digit-free → distinct fingerprints
    db = sink()
    assert db.query(ErrorEvent).count() == 3
    db.close()


def test_dedup_refreshes_traceback(sink):
    import sys

    def _info():
        try:
            raise ValueError("same")
        except ValueError:
            return sys.exc_info()

    _emit("boom", _info())
    _emit("boom", _info())
    db = sink()
    row = db.query(ErrorEvent).one()
    assert row.count == 2
    assert row.traceback and "ValueError: same" in row.traceback
    db.close()


def test_dedup_bump_does_not_prune(monkeypatch, sink):
    monkeypatch.setenv("ERROR_LOG_MAX_ROWS", "2")
    _emit("keep-a")
    _emit("keep-b")
    # Third distinct insert would prune to 2; but bumping an existing
    # fingerprint must NOT delete other rows.
    _emit("keep-a")
    db = sink()
    assert db.query(ErrorEvent).count() == 2
    db.close()


def test_emit_swallows_db_errors(monkeypatch):
    monkeypatch.setattr(dbmod, "SessionLocal", lambda: (_ for _ in ()).throw(RuntimeError("down")))
    _emit("boom")  # must not raise


def test_fingerprint_stable_across_line_numbers():
    fp1 = fingerprint(logging.LogRecord("l", 40, "a.py", 10, "m", None, None))
    fp2 = fingerprint(logging.LogRecord("l", 40, "a.py", 99, "m", None, None))
    assert fp1 == fp2  # message-only fingerprint ignores lineno


def test_fingerprint_ignores_ids_in_message():
    fp1 = fingerprint(logging.LogRecord("l", 40, "a.py", 1, "user 12 not found", None, None))
    fp2 = fingerprint(logging.LogRecord("l", 40, "a.py", 1, "user 999 not found", None, None))
    assert fp1 == fp2


def test_fingerprint_ignores_uuid_and_quotes():
    m1 = "job '4a1f2c3d-0000-4000-8000-000000000001' failed"
    m2 = "job '9c2b7e10-0000-4000-8000-000000000002' failed"
    fp1 = fingerprint(logging.LogRecord("l", 40, "a.py", 1, m1, None, None))
    fp2 = fingerprint(logging.LogRecord("l", 40, "a.py", 1, m2, None, None))
    assert fp1 == fp2
