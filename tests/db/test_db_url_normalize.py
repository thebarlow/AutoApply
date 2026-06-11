from db.database import _normalize_db_url


def test_bare_postgres_scheme_gets_psycopg_driver():
    assert (
        _normalize_db_url("postgresql://u:p@host:5432/db")
        == "postgresql+psycopg://u:p@host:5432/db"
    )


def test_already_qualified_psycopg_unchanged():
    url = "postgresql+psycopg://u:p@host:5432/db"
    assert _normalize_db_url(url) == url


def test_sqlite_unchanged():
    assert _normalize_db_url("sqlite:///auto_apply.db") == "sqlite:///auto_apply.db"


def test_other_postgres_driver_unchanged():
    # Don't clobber an explicitly chosen driver (e.g. psycopg2).
    url = "postgresql+psycopg2://u:p@host/db"
    assert _normalize_db_url(url) == url
