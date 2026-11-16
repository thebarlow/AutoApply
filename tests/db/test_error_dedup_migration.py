import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError


def test_aa16_collapses_duplicate_fingerprints_and_enforces_unique(
    tmp_path, monkeypatch
):
    from alembic import command
    from alembic.config import Config as AlembicConfig

    url = f"sqlite:///{tmp_path / 'm.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    engine = create_engine(url)
    cols = (
        "id, created_at, last_seen, count, level, logger, message, traceback, "
        "route, method, profile_id, account_email, request_id, fingerprint"
    )
    with engine.begin() as conn:
        # Minimal pre-migration state: error_events as of aa15errlog02.
        conn.execute(
            text(
                "CREATE TABLE error_events (id INTEGER PRIMARY KEY, "
                "created_at VARCHAR NOT NULL, last_seen VARCHAR NOT NULL, "
                "count INTEGER NOT NULL, level VARCHAR NOT NULL, "
                "logger VARCHAR NOT NULL, message TEXT NOT NULL, traceback TEXT, "
                "route VARCHAR, method VARCHAR, profile_id INTEGER, "
                "account_email VARCHAR, request_id VARCHAR, "
                "fingerprint VARCHAR NOT NULL)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX ix_error_events_fingerprint ON error_events (fingerprint)"
            )
        )
        rows = [
            (1, "2026-01-01", "2026-01-05", 2, "ERROR", "l", "old", None, None,
             None, None, None, None, "fpA"),
            (2, "2026-01-02", "2026-01-09", 3, "ERROR", "l", "newest", "tb", "/r",
             "GET", 7, "a@b.c", "rid", "fpA"),
            (3, "2026-01-03", "2026-01-04", 1, "ERROR", "l", "mid", None, None,
             None, None, None, None, "fpA"),
            (4, "2026-01-01", "2026-01-01", 4, "ERROR", "l", "solo", None, None,
             None, None, None, None, "fpB"),
        ]  # fmt: skip
        for r in rows:
            conn.execute(
                text(
                    f"INSERT INTO error_events ({cols}) VALUES ({', '.join(':p%d' % i for i in range(14))})"
                ),
                {f"p{i}": v for i, v in enumerate(r)},
            )
        conn.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR NOT NULL)")
        )
        conn.execute(text("INSERT INTO alembic_version VALUES ('aa15errlog02')"))

    cfg = AlembicConfig("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "aa16errdedup01")

    with engine.begin() as conn:
        got = conn.execute(
            text(
                "SELECT id, created_at, last_seen, count, message, traceback, "
                "route, method, profile_id, account_email, request_id "
                "FROM error_events WHERE fingerprint = 'fpA'"
            )
        ).all()
        assert got == [
            (2, "2026-01-01", "2026-01-09", 6, "newest", "tb", "/r", "GET", 7,
             "a@b.c", "rid"),
        ]  # fmt: skip
        assert (
            conn.execute(
                text("SELECT count FROM error_events WHERE fingerprint = 'fpB'")
            ).scalar()
            == 4
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO error_events (created_at, last_seen, count, level, "
                    "logger, message, fingerprint) "
                    "VALUES ('x', 'x', 1, 'ERROR', 'l', 'm', 'fpB')"
                )
            )
    engine.dispose()
