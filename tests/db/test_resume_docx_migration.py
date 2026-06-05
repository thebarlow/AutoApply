# tests/db/test_resume_docx_migration.py
from sqlalchemy import text


def test_resume_docx_column_added(monkeypatch, tmp_path):
    import db.database as dbmod
    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{tmp_path/'t.db'}")
    monkeypatch.setattr(dbmod, "engine", engine, raising=True)
    # Build a jobs table WITHOUT resume_docx_path.
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE jobs (job_key TEXT PRIMARY KEY, resume_path TEXT)"))
        conn.commit()

    dbmod._migrate_resume_docx_column()

    with engine.connect() as conn:
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(jobs)")).fetchall()]
    assert "resume_docx_path" in cols

    # Idempotent: second run does not raise.
    dbmod._migrate_resume_docx_column()
