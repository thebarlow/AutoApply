"""Model-level checks for the tier columns and the new credit_rate default."""
import datetime as dt

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, Account, Purchase


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_account_tier_defaults_to_standard():
    db = _session()
    acct = Account(email="a@b.com", profile_id=1,
                   created_at=dt.datetime.now(dt.timezone.utc).isoformat())
    db.add(acct)
    db.commit()
    assert acct.tier == "standard"


def test_account_credit_rate_defaults_to_one():
    db = _session()
    acct = Account(email="c@d.com", profile_id=2,
                   created_at=dt.datetime.now(dt.timezone.utc).isoformat())
    db.add(acct)
    db.commit()
    assert acct.credit_rate == 1.0


def test_purchase_has_tier_column():
    db = _session()
    p = Purchase(profile_id=1, stripe_session_id="cs_x", price_id="price_a",
                 credits=100, amount_usd=1.0, status="pending", tier="beta",
                 created_at=dt.datetime.now(dt.timezone.utc).isoformat())
    db.add(p)
    db.commit()
    assert db.query(Purchase).one().tier == "beta"
