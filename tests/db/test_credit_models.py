from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.database import Base, Account, CreditLedger


def _session():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def test_account_has_credit_columns():
    db = _session()
    acct = Account(email="a@b.c", is_admin=False, profile_id=1,
                   created_at="now", credit_balance=100, credit_rate=1.5)
    db.add(acct)
    db.commit()
    got = db.query(Account).filter_by(profile_id=1).first()
    assert got.credit_balance == 100
    assert got.credit_rate == 1.5


def test_credit_ledger_row_roundtrips():
    db = _session()
    row = CreditLedger(profile_id=1, delta=-7, reason="debit", action="generate",
                       job_key="job-1", raw_cost_usd=0.0046, meta='{"model":"x"}',
                       created_at="now")
    db.add(row)
    db.commit()
    got = db.query(CreditLedger).first()
    assert got.delta == -7
    assert got.reason == "debit"
    assert got.profile_id == 1
