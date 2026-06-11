from sqlalchemy import create_engine, text

from db.database import Base
import core.job  # noqa: F401 — register Job
import core.user  # noqa: F401 — register User
from scripts.port_sqlite_to_pg import port


def _make_engine(path):
    eng = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    return eng


def test_port_stamps_profile_id_and_preserves_rows(tmp_path):
    src = _make_engine(tmp_path / "src.db")
    dst = _make_engine(tmp_path / "dst.db")

    with src.begin() as c:
        # Source rows carry a placeholder profile_id (99); the port must
        # overwrite it with tenant_id=1. (create_all builds the current schema
        # where profile_id is NOT NULL, so we cannot omit it on the source.)
        c.execute(text(
            "INSERT INTO jobs (job_key, url, source, state, flagged, profile_id) "
            "VALUES ('k1', 'http://x', 'manual', 'new', 0, 99)"
        ))
        c.execute(text("INSERT INTO documents (job_key, doc_type, structured_json, profile_id) VALUES ('k1', 'resume', '{}', 99)"))
        c.execute(text("INSERT INTO skill_aliases (alias_key, canonical, profile_id) VALUES ('py', 'Python', 1)"))
        c.execute(text("INSERT INTO config (key, value) VALUES ('some_flag', '1')"))

    port(src_url=f"sqlite:///{tmp_path/'src.db'}", dst_url=f"sqlite:///{tmp_path/'dst.db'}", tenant_id=1)

    with dst.connect() as c:
        assert c.execute(text("SELECT profile_id FROM jobs WHERE job_key='k1'")).scalar() == 1
        assert c.execute(text("SELECT profile_id FROM documents WHERE job_key='k1'")).scalar() == 1
        assert c.execute(text("SELECT COUNT(*) FROM jobs")).scalar() == 1
        assert c.execute(text("SELECT COUNT(*) FROM documents")).scalar() == 1
        assert c.execute(text("SELECT value FROM config WHERE key='some_flag'")).scalar() == "1"
        assert c.execute(text("SELECT value FROM config WHERE key='dev_tenant_id'")).scalar() == "1"
