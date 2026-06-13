import datetime as dt

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from db.database import Base, Account, Purchase, CreditLedger, get_db
import web.routers.payments as payments_router


def _event(session_id, event_id="evt_1"):
    return type("E", (), {"id": event_id, "type": "checkout.session.completed",
                          "data": type("D", (), {"object": {"id": session_id}})()})()


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
    db.add(Purchase(profile_id=7, stripe_session_id="cs_1", price_id="price_a",
                    credits=5000, amount_usd=5.0, status="pending",
                    created_at=dt.datetime.now(dt.timezone.utc).isoformat()))
    db.commit()

    app = FastAPI()
    app.include_router(payments_router.router)
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app), db, monkeypatch


def test_webhook_grants_credits_and_completes(client):
    c, db, mp = client
    mp.setattr(payments_router.stripe_client, "construct_event",
               lambda payload, sig: _event("cs_1"))
    r = c.post("/api/payments/webhook", data=b"{}",
               headers={"stripe-signature": "x"})
    assert r.status_code == 200
    assert db.query(Account).filter_by(profile_id=7).one().credit_balance == 5000
    assert db.query(Purchase).filter_by(stripe_session_id="cs_1").one().status == "completed"
    assert db.query(CreditLedger).filter_by(profile_id=7, reason="purchase").count() == 1


def test_webhook_idempotent_on_event_id(client):
    c, db, mp = client
    mp.setattr(payments_router.stripe_client, "construct_event",
               lambda payload, sig: _event("cs_1", "evt_1"))
    c.post("/api/payments/webhook", data=b"{}", headers={"stripe-signature": "x"})
    c.post("/api/payments/webhook", data=b"{}", headers={"stripe-signature": "x"})
    assert db.query(CreditLedger).filter_by(reason="purchase").count() == 1
    assert db.query(Account).filter_by(profile_id=7).one().credit_balance == 5000


def test_webhook_bad_signature_400(client):
    c, _db, mp = client
    def _raise(payload, sig):
        raise ValueError("bad sig")
    mp.setattr(payments_router.stripe_client, "construct_event", _raise)
    r = c.post("/api/payments/webhook", data=b"{}", headers={"stripe-signature": "x"})
    assert r.status_code == 400
