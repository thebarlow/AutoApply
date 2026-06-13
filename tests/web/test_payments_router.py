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
    TestingSession = sessionmaker(bind=engine)
    db = TestingSession()
    db.add(Account(id=1, email="u@x.com", is_admin=False, profile_id=7,
                   created_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                   credit_balance=0, credit_rate=1.5))
    db.commit()

    app = FastAPI()
    app.include_router(payments_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_profile_id] = lambda: 7

    monkeypatch.setenv("STRIPE_PACKS", '{"price_a": 5000}')
    return TestClient(app), db, monkeypatch


def test_packs_lists_configured(client, monkeypatch):
    c, _db, mp = client
    monkeypatch.setattr(payments_router.stripe_client, "retrieve_price",
                        lambda pid: type("P", (), {"unit_amount": 500, "currency": "usd"})())
    r = c.get("/api/payments/packs")
    assert r.status_code == 200
    assert r.json() == [{"price_id": "price_a", "credits": 5000,
                         "amount_usd": 5.0, "currency": "usd"}]


def test_checkout_unknown_price_400(client):
    c, _db, _mp = client
    r = c.post("/api/payments/checkout", json={"price_id": "nope"})
    assert r.status_code == 400


def test_checkout_creates_session_and_pending_row(client, monkeypatch):
    c, db, mp = client
    monkeypatch.setattr(payments_router.stripe_client, "create_customer",
                        lambda email: "cus_123")
    monkeypatch.setattr(payments_router.stripe_client, "create_checkout_session",
                        lambda **kw: type("S", (), {"id": "cs_1", "url": "https://stripe/cs_1"})())
    monkeypatch.setattr(payments_router.stripe_client, "retrieve_price",
                        lambda pid: type("P", (), {"unit_amount": 500, "currency": "usd"})())
    r = c.post("/api/payments/checkout", json={"price_id": "price_a"})
    assert r.status_code == 200
    assert r.json()["url"] == "https://stripe/cs_1"
    row = db.query(Purchase).filter_by(stripe_session_id="cs_1").one()
    assert row.status == "pending" and row.credits == 5000 and row.profile_id == 7
    assert db.query(Account).filter_by(profile_id=7).one().stripe_customer_id == "cus_123"


def test_history_lists_profile_purchases(client):
    c, db, _mp = client
    from db.database import Purchase
    import datetime as dt
    db.add(Purchase(profile_id=7, stripe_session_id="cs_h", price_id="price_a",
                    credits=5000, amount_usd=5.0, status="completed",
                    created_at=dt.datetime.now(dt.timezone.utc).isoformat()))
    db.add(Purchase(profile_id=99, stripe_session_id="cs_other", price_id="price_a",
                    credits=5000, amount_usd=5.0, status="completed",
                    created_at=dt.datetime.now(dt.timezone.utc).isoformat()))
    db.commit()
    r = c.get("/api/payments/history")
    assert r.status_code == 200
    rows = r.json()
    assert [x["stripe_session_id"] for x in rows] == ["cs_h"]
    assert rows[0]["credits"] == 5000 and rows[0]["status"] == "completed"
