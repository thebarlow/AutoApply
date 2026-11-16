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

    # Both call sites raise via the same shared helper, so the top-of-stack
    # frame (where the exception is actually raised) is identical for both
    # occurrences -- they share a fingerprint and dedup into one row. But the
    # *caller* differs (_boom_first vs _boom_second), so the full formatted
    # traceback text differs between the two occurrences, letting us tell
    # whether the stored traceback was refreshed to the second occurrence or
    # left as the first.
    def _raise(msg):
        raise ValueError(msg)

    def _boom_first():
        _raise("same")

    def _boom_second():
        _raise("same")

    def _info(fn):
        try:
            fn()
        except ValueError:
            return sys.exc_info()

    _emit("boom", _info(_boom_first))
    _emit("boom", _info(_boom_second))
    db = sink()
    rows = db.query(ErrorEvent).all()
    assert len(rows) == 1  # same fingerprint -> deduped, not two rows
    row = rows[0]
    assert row.count == 2
    assert row.traceback
    assert "_boom_second" in row.traceback
    assert "_boom_first" not in row.traceback
    db.close()


def test_dedup_bump_does_not_prune(monkeypatch, sink):
    # Insert two distinct rows under a high cap so both survive.
    monkeypatch.setenv("ERROR_LOG_MAX_ROWS", "1000")
    _emit("keep-a")
    _emit("keep-b")
    # Now lower the cap below the current row count and bump an *existing*
    # fingerprint. If the bump path incorrectly ran prune (the pre-fix
    # behavior), it would delete down to 1 row; the correct behavior only
    # prunes on the insert path, so both rows must survive the bump.
    monkeypatch.setenv("ERROR_LOG_MAX_ROWS", "1")
    _emit("keep-a")
    db = sink()
    assert db.query(ErrorEvent).count() == 2
    db.close()


def test_emit_swallows_db_errors(monkeypatch):
    monkeypatch.setattr(
        dbmod, "SessionLocal", lambda: (_ for _ in ()).throw(RuntimeError("down"))
    )
    _emit("boom")  # must not raise


def test_fingerprint_stable_across_line_numbers():
    fp1 = fingerprint(logging.LogRecord("l", 40, "a.py", 10, "m", None, None))
    fp2 = fingerprint(logging.LogRecord("l", 40, "a.py", 99, "m", None, None))
    assert fp1 == fp2  # message-only fingerprint ignores lineno


def test_fingerprint_ignores_ids_in_message():
    fp1 = fingerprint(
        logging.LogRecord("l", 40, "a.py", 1, "user 1234 not found", None, None)
    )
    fp2 = fingerprint(
        logging.LogRecord("l", 40, "a.py", 1, "user 9876 not found", None, None)
    )
    assert fp1 == fp2


def test_fingerprint_keeps_three_digit_codes():
    fp1 = fingerprint(
        logging.LogRecord("l", 40, "a.py", 1, "HTTP 500 from upstream", None, None)
    )
    fp2 = fingerprint(
        logging.LogRecord("l", 40, "a.py", 1, "HTTP 404 from upstream", None, None)
    )
    assert fp1 != fp2


def test_fingerprint_ignores_uuid_and_quotes():
    m1 = "job '4a1f2c3d-0000-4000-8000-000000000001' failed"
    m2 = "job '9c2b7e10-0000-4000-8000-000000000002' failed"
    fp1 = fingerprint(logging.LogRecord("l", 40, "a.py", 1, m1, None, None))
    fp2 = fingerprint(logging.LogRecord("l", 40, "a.py", 1, m2, None, None))
    assert fp1 == fp2


def test_upsert_increments_instead_of_duplicating(sink):
    for _ in range(5):
        _emit("same-error")
    db = sink()
    rows = db.query(ErrorEvent).all()
    assert len(rows) == 1
    assert rows[0].count == 5
    db.close()


def test_fingerprint_is_unique_in_schema():
    idx = {i.name: i for i in ErrorEvent.__table__.indexes}
    assert idx["ix_error_events_fingerprint"].unique


def test_concurrent_emits_same_fingerprint_yield_one_row(tmp_path, monkeypatch):
    """Two handlers on two sessions/connections racing the same fingerprint.

    Pre-fix, both could miss the SELECT and insert duplicate rows; the upsert
    + UNIQUE index must collapse them into one row with count 2.
    """
    import threading

    engine = create_engine(
        f"sqlite:///{tmp_path / 'race.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(engine, tables=[ErrorEvent.__table__])
    monkeypatch.setattr(dbmod, "SessionLocal", sessionmaker(bind=engine))

    barrier = threading.Barrier(2)

    def worker():
        barrier.wait()
        _emit("raced-error")

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    db = sessionmaker(bind=engine)()
    rows = db.query(ErrorEvent).all()
    assert len(rows) == 1
    assert rows[0].count == 2
    db.close()
    engine.dispose()


def _backdate(sink, message, days):
    from datetime import datetime, timedelta, timezone

    old = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    db = sink()
    db.query(ErrorEvent).filter(ErrorEvent.message == message).update(
        {"last_seen": old}
    )
    db.commit()
    db.close()


def test_age_prune_runs_on_bump_after_gate_interval(monkeypatch, sink):
    import core.error_sink as es

    now = [1_000_000.0]
    monkeypatch.setattr(es, "_clock", lambda: now[0])
    monkeypatch.setenv("ERROR_LOG_MAX_AGE_DAYS", "30")
    _emit("hot-error")
    _emit("stale-error")  # insert -> prunes + arms the gate at `now`
    _backdate(sink, "stale-error", 60)

    # Within the gate interval: a bump does not age-prune.
    now[0] += 60
    _emit("hot-error")
    db = sink()
    assert db.query(ErrorEvent).count() == 2
    db.close()

    # After the interval: a pure bump enforces ERROR_LOG_MAX_AGE_DAYS.
    now[0] += es._AGE_PRUNE_INTERVAL_S
    _emit("hot-error")
    db = sink()
    rows = db.query(ErrorEvent).all()
    assert [r.message for r in rows] == ["hot-error"]
    assert rows[0].count == 3
    db.close()
