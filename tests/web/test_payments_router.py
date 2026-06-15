import datetime as dt

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, Account, Purchase, get_db
from web.tenancy import current_profile_id
import web.routers.payments as payments_router


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(Account(id=1, email="u@x.com", is_admin=False, profile_id=7,
                   created_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                   credit_balance=0, credit_rate=1.0, tier="standard"))
    db.commit()

    app = FastAPI()
    app.include_router(payments_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_profile_id] = lambda: 7

    monkeypatch.setenv("STRIPE_PRICE_IDS",
                       '{"1":"price_1","5":"price_5","10":"price_10","20":"price_20"}')
    for k in ("CREDIT_TIER_MARGINS", "CREDIT_PRICE_TIERS", "CREDIT_TIER_VISIBILITY",
              "STRIPE_FEE_PCT", "STRIPE_FEE_FIXED", "TAX_RATE"):
        monkeypatch.delenv(k, raising=False)
    return TestClient(app), db, monkeypatch


def test_packs_returns_tier_filtered_computed_credits(client):
    c, _db, _mp = client  # account is standard
    r = c.get("/api/payments/packs")
    assert r.status_code == 200
    packs = r.json()
    assert [p["amount_usd"] for p in packs] == [1, 5, 10, 20]
    by_amt = {p["amount_usd"]: p["credits"] for p in packs}
    assert by_amt == {1: 25, 5: 250, 10: 525, 20: 1100}


def test_packs_beta_only_dollar_one(client):
    c, db, _mp = client
    db.query(Account).filter_by(profile_id=7).one().tier = "beta"
    db.commit()
    r = c.get("/api/payments/packs")
    packs = r.json()
    assert [p["amount_usd"] for p in packs] == [1]
    assert packs[0]["credits"] == 450


def test_checkout_unknown_price_400(client):
    c, _db, _mp = client
    r = c.post("/api/payments/checkout", json={"price_id": "nope"})
    assert r.status_code == 400


def test_checkout_price_not_visible_to_tier_400(client):
    c, db, _mp = client
    db.query(Account).filter_by(profile_id=7).one().tier = "beta"
    db.commit()
    r = c.post("/api/payments/checkout", json={"price_id": "price_20"})
    assert r.status_code == 400


def test_checkout_computes_credits_from_tier(client, monkeypatch):
    c, db, _mp = client  # standard tier
    monkeypatch.setattr(payments_router.stripe_client, "create_customer",
                        lambda email: "cus_123")
    monkeypatch.setattr(payments_router.stripe_client, "create_checkout_session",
                        lambda **kw: type("S", (), {"id": "cs_1", "url": "https://s/cs_1"})())
    r = c.post("/api/payments/checkout", json={"price_id": "price_5"})
    assert r.status_code == 200
    assert r.json()["url"] == "https://s/cs_1"
    row = db.query(Purchase).filter_by(stripe_session_id="cs_1").one()
    assert row.status == "pending"
    assert row.credits == 250          # standard $5
    assert row.amount_usd == 5.0
    assert row.tier == "standard"
    assert row.profile_id == 7


def test_history_lists_profile_purchases(client):
    c, db, _mp = client
    db.add(Purchase(profile_id=7, stripe_session_id="cs_h", price_id="price_5",
                    credits=250, amount_usd=5.0, status="completed", tier="standard",
                    created_at=dt.datetime.now(dt.timezone.utc).isoformat()))
    db.add(Purchase(profile_id=99, stripe_session_id="cs_other", price_id="price_5",
                    credits=250, amount_usd=5.0, status="completed", tier="standard",
                    created_at=dt.datetime.now(dt.timezone.utc).isoformat()))
    db.commit()
    r = c.get("/api/payments/history")
    rows = r.json()
    assert [x["stripe_session_id"] for x in rows] == ["cs_h"]
    assert rows[0]["credits"] == 250


def test_packs_misconfigured_pricing_500(client, monkeypatch):
    c, _db, _mp = client
    # Margin large enough that the profit guard reduces credits to <=0 -> ValueError.
    monkeypatch.setenv("CREDIT_TIER_MARGINS", '{"standard": 1000}')
    r = c.get("/api/payments/packs")
    assert r.status_code == 500


def test_checkout_misconfigured_pricing_500(client, monkeypatch):
    c, _db, _mp = client
    monkeypatch.setenv("CREDIT_TIER_MARGINS", '{"standard": 1000}')
    r = c.post("/api/payments/checkout", json={"price_id": "price_5"})
    assert r.status_code == 500
