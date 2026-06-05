# tests/db/test_ats_report_migration.py
from sqlalchemy import text


def test_ats_report_columns_added(monkeypatch, tmp_path):
    import db.database as dbmod
    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{tmp_path/'t.db'}")
    monkeypatch.setattr(dbmod, "engine", engine, raising=True)
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE jobs (job_key TEXT PRIMARY KEY, resume_path TEXT)"))
        conn.commit()

    dbmod._migrate_ats_report_columns()

    with engine.connect() as conn:
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(jobs)")).fetchall()]
    for name in ("ats_passed", "ats_score", "ats_report_json", "ats_checked_at"):
        assert name in cols

    # Idempotent: second run does not raise.
    dbmod._migrate_ats_report_columns()
