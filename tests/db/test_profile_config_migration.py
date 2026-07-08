from sqlalchemy import create_engine, text


MOVED_KEYS = [
    "w1", "w2", "auto_reject_threshold", "auto_approve_threshold",
    "resume_github", "resume_linkedin", "resume_website",
    "resume_template_path", "cover_template_path",
    "resume_prompt_template", "cover_prompt_template",
    "source_remotive", "source_remoteok",
    "keywords_whitelist", "keywords_blacklist",
    "max_jobs_per_source", "job_searches",
]


def test_backfill_copies_globals_to_every_profile(tmp_path, monkeypatch):
    from alembic.config import Config as AlembicConfig
    from alembic import command

    db_path = tmp_path / "m.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    engine = create_engine(url)
    with engine.begin() as conn:
        # Minimal pre-migration state: config + two profiles.
        conn.execute(text("CREATE TABLE config (key VARCHAR PRIMARY KEY, value TEXT)"))
        conn.execute(text("CREATE TABLE user_profile (id INTEGER PRIMARY KEY, name VARCHAR, data TEXT)"))
        conn.execute(text("INSERT INTO config VALUES ('w1', '0.7')"))
        conn.execute(text("INSERT INTO config VALUES ('dev_tenant_id', '1')"))
        conn.execute(text("INSERT INTO user_profile VALUES (1, 'a', '{}')"))
        conn.execute(text("INSERT INTO user_profile VALUES (2, 'b', '{}')"))
        # Stamp alembic at the prior head so only our migration runs.
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR NOT NULL)"))
        conn.execute(text("INSERT INTO alembic_version VALUES ('866e48bc6219')"))

    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(alembic_cfg, "aa08profcfg01")

    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT profile_id, value FROM profile_config WHERE key='w1' ORDER BY profile_id")
        ).all()
        assert rows == [(1, "0.7"), (2, "0.7")]
        # Moved key removed from global config; global infra key retained.
        assert conn.execute(text("SELECT COUNT(*) FROM config WHERE key='w1'")).scalar() == 0
        assert conn.execute(text("SELECT value FROM config WHERE key='dev_tenant_id'")).scalar() == "1"
