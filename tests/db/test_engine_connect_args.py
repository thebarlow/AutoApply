"""Engine construction must only pass SQLite-only connect args to SQLite."""
from db.database import make_connect_args


def test_sqlite_gets_check_same_thread():
    args = make_connect_args("sqlite:///auto_apply.db")
    assert args == {"check_same_thread": False}


def test_sqlite_memory_gets_check_same_thread():
    args = make_connect_args("sqlite:///:memory:")
    assert args == {"check_same_thread": False}


def test_postgres_gets_no_sqlite_args():
    args = make_connect_args("postgresql+psycopg://u:p@localhost:5432/auto_apply")
    assert args == {}
