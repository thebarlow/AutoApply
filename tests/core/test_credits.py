import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.database import Base, Account, CreditLedger
import core.credits as credits


def _session():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def _acct(db, profile_id=1, rate=1.5, balance=0):
    a = Account(email=f"u{profile_id}@x.c", is_admin=False, profile_id=profile_id,
                created_at="now", credit_balance=balance, credit_rate=rate)
    db.add(a); db.commit(); return a


def test_to_credits_rounds():
    assert credits.to_credits(0.0046, 1.5) == 7      # 0.0046*1.5*1000=6.9 -> 7
    assert credits.to_credits(0.0046, 10.0) == 46
    assert credits.to_credits(0.0046, 0) == 0


def test_grant_credits_inserts_row_and_bumps_balance():
    db = _session(); _acct(db, balance=0)
    credits.grant_credits(db, 1, 100, reason="signup_grant")
    assert db.query(Account).filter_by(profile_id=1).first().credit_balance == 100
    row = db.query(CreditLedger).filter_by(reason="signup_grant").first()
    assert row.delta == 100


def test_debit_for_action_decrements_and_logs():
    db = _session(); _acct(db, rate=1.5, balance=100)
    row = credits.debit_for_action(db, 1, action="generate", job_key="j1",
                                   raw_cost_usd=0.0046, meta={"model": "x"})
    assert row.delta == -7
    assert db.query(Account).filter_by(profile_id=1).first().credit_balance == 93


def test_debit_noop_without_account():
    db = _session()  # no account row for profile 1
    assert credits.debit_for_action(db, 1, action="generate", job_key="j1",
                                    raw_cost_usd=0.005, meta={}) is None


def test_reconcile_balance_matches_ledger_sum():
    db = _session(); _acct(db, balance=0)
    credits.grant_credits(db, 1, 100, reason="admin_grant")
    credits.debit_for_action(db, 1, action="score", job_key="j", raw_cost_usd=0.01, meta={})
    assert credits.reconcile_balance(db, 1) == db.query(Account).filter_by(profile_id=1).first().credit_balance
