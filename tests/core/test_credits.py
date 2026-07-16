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


def test_grant_credits_inserts_row_and_bumps_balance():
    db = _session(); _acct(db, balance=0)
    credits.grant_credits(db, 1, 100, reason="signup_grant")
    assert db.query(Account).filter_by(profile_id=1).first().credit_balance == 100
    row = db.query(CreditLedger).filter_by(reason="signup_grant").first()
    assert row.delta == 100


def test_reconcile_balance_matches_ledger_sum():
    db = _session(); _acct(db, balance=0)
    credits.grant_credits(db, 1, 100, reason="admin_grant")
    credits.debit_fixed(db, 1, action="score", job_key="j", price=10)
    assert credits.reconcile_balance(db, 1) == db.query(Account).filter_by(profile_id=1).first().credit_balance


@pytest.fixture
def db_session():
    from db.database import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


def _acct2(db, balance=10, rate=1.0, profile_id=1):
    from db.database import Account
    a = Account(profile_id=profile_id, email=f"u{profile_id}@x.com",
                created_at="now", credit_balance=balance, credit_rate=rate)
    db.add(a)
    db.commit()
    return a


def test_debit_fixed_success_writes_row_and_decrements(db_session):
    from core import credits
    _acct2(db_session, balance=10)
    row = credits.debit_fixed(db_session, 1, action="score", job_key="j1", price=2)
    assert row.delta == -2 and row.reason == "debit" and row.action == "score"
    acct = credits.get_account_for_profile(db_session, 1)
    assert acct.credit_balance == 8


def test_debit_fixed_insufficient_raises_with_price_and_action(db_session):
    from core import credits
    _acct2(db_session, balance=1)
    with pytest.raises(credits.InsufficientCredits) as ei:
        credits.debit_fixed(db_session, 1, action="generate_fresh", job_key="j1", price=4)
    assert ei.value.balance == 1
    assert ei.value.price == 4
    assert ei.value.action == "generate_fresh"
    # balance untouched
    assert credits.get_account_for_profile(db_session, 1).credit_balance == 1


def test_debit_fixed_exact_balance_passes(db_session):
    from core import credits
    _acct2(db_session, balance=4)
    credits.debit_fixed(db_session, 1, action="generate_fresh", job_key="j1", price=4)
    assert credits.get_account_for_profile(db_session, 1).credit_balance == 0


def test_refund_debit_restores_balance(db_session):
    from core import credits
    _acct2(db_session, balance=10)
    row = credits.debit_fixed(db_session, 1, action="regenerate", job_key="j1", price=2)
    refund = credits.refund_debit(db_session, row)
    assert refund.delta == 2 and refund.reason == "refund" and refund.action == "regenerate"
    assert credits.get_account_for_profile(db_session, 1).credit_balance == 10


def test_signup_grant_for_tier_defaults(monkeypatch):
    from core import credits
    monkeypatch.delenv("CREDIT_SIGNUP_GRANTS", raising=False)
    assert credits.signup_grant_for_tier("standard") == 20
    assert credits.signup_grant_for_tier("friends_family") == 50
    assert credits.signup_grant_for_tier("beta") == 200
    assert credits.signup_grant_for_tier("unknown_tier") == 20  # falls back to standard


def test_signup_grant_env_override(monkeypatch):
    from core import credits
    monkeypatch.setenv("CREDIT_SIGNUP_GRANTS", '{"standard": 5}')
    assert credits.signup_grant_for_tier("standard") == 5
