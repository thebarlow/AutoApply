"""Data-logic checks for the aa10units01 redenomination (run against SQLite)."""
import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, text

from db.database import Base

_MIG_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic" / "versions" / "aa10units01_redenominate_units.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("aa10units01_redenominate_units", _MIG_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _setup(engine, rows):
    Base.metadata.create_all(engine)
    with engine.begin() as c:
        for r in rows:
            c.execute(text(
                "INSERT INTO account (email, profile_id, is_admin, banned, created_at,"
                " credit_balance, credit_rate, tier)"
                " VALUES (:email, :pid, :adm, 0, 't', :bal, 1.0, :tier)"
            ), r)


def _run_upgrade(engine):
    mig = _load_migration()
    # Execute the same statements via a lightweight op-shim
    from unittest.mock import patch
    with engine.begin() as conn:
        with patch.object(mig, "op") as op_mock:
            op_mock.get_bind.return_value = conn
            mig.upgrade()


def test_conversion_and_topup(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'m.db'}")
    _setup(engine, [
        {"email": "a@x", "pid": 1, "adm": 0, "bal": 100, "tier": "beta"},      # ->5 -> topup 200
        {"email": "b@x", "pid": 2, "adm": 0, "bal": 5000, "tier": "standard"}, # ->250, no topup
        {"email": "c@x", "pid": 3, "adm": 1, "bal": 100, "tier": "standard"},  # admin: ->5, no topup
    ])
    _run_upgrade(engine)
    with engine.connect() as c:
        bals = dict(c.execute(text("SELECT profile_id, credit_balance FROM account")).fetchall())
        assert bals == {1: 200, 2: 250, 3: 5}
        reasons = [r[0] for r in c.execute(text("SELECT reason FROM credit_ledger ORDER BY id")).fetchall()]
        assert "redenomination" in reasons and "redenomination_topup" in reasons
