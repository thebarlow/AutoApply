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
    r = c.post("/api/payments/webhook", content=b"{}",
               headers={"stripe-signature": "x"})
    assert r.status_code == 200
    assert db.query(Account).filter_by(profile_id=7).one().credit_balance == 5000
    assert db.query(Purchase).filter_by(stripe_session_id="cs_1").one().status == "completed"
    assert db.query(CreditLedger).filter_by(profile_id=7, reason="purchase").count() == 1


def test_webhook_idempotent_on_event_id(client):
    c, db, mp = client
    mp.setattr(payments_router.stripe_client, "construct_event",
               lambda payload, sig: _event("cs_1", "evt_1"))
    c.post("/api/payments/webhook", content=b"{}", headers={"stripe-signature": "x"})
    c.post("/api/payments/webhook", content=b"{}", headers={"stripe-signature": "x"})
    assert db.query(CreditLedger).filter_by(reason="purchase").count() == 1
    assert db.query(Account).filter_by(profile_id=7).one().credit_balance == 5000


def test_webhook_bad_signature_400(client):
    c, _db, mp = client
    def _raise(payload, sig):
        raise ValueError("bad sig")
    mp.setattr(payments_router.stripe_client, "construct_event", _raise)
    r = c.post("/api/payments/webhook", content=b"{}", headers={"stripe-signature": "x"})
    assert r.status_code == 400


def test_webhook_missing_session_id_returns_bad_payload(client):
    c, db, mp = client
    bad = type("E", (), {"id": "evt_x", "type": "checkout.session.completed",
                         "data": type("D", (), {"object": {}})()})()
    mp.setattr(payments_router.stripe_client, "construct_event",
               lambda payload, sig: bad)
    r = c.post("/api/payments/webhook", content=b"{}", headers={"stripe-signature": "x"})
    assert r.status_code == 200
    assert r.json()["status"] == "bad_payload"
    assert db.query(CreditLedger).filter_by(reason="purchase").count() == 0


def _session(payment_status="paid"):
    return {"id": "cs_1", "payment_status": payment_status}


def test_verify_then_webhook_credits_once(client):
    """Cross-path idempotency: success-redirect verify followed by the real
    webhook must grant exactly one set of credits."""
    c, db, mp = client
    from web.tenancy import current_profile_id
    c.app.dependency_overrides[current_profile_id] = lambda: 7
    mp.setattr(payments_router.stripe_client, "retrieve_checkout_session",
               lambda sid: _session("paid"))
    mp.setattr(payments_router.stripe_client, "construct_event",
               lambda payload, sig: _event("cs_1"))

    r1 = c.get("/api/payments/verify", params={"session_id": "cs_1"})
    assert r1.json()["status"] == "ok"
    r2 = c.post("/api/payments/webhook", content=b"{}", headers={"stripe-signature": "x"})
    assert r2.json()["status"] == "already_completed"

    assert db.query(CreditLedger).filter_by(reason="purchase").count() == 1
    assert db.query(Account).filter_by(profile_id=7).one().credit_balance == 5000


def test_verify_repeated_credits_once(client):
    c, db, mp = client
    from web.tenancy import current_profile_id
    c.app.dependency_overrides[current_profile_id] = lambda: 7
    mp.setattr(payments_router.stripe_client, "retrieve_checkout_session",
               lambda sid: _session("paid"))
    for _ in range(3):
        c.get("/api/payments/verify", params={"session_id": "cs_1"})
    assert db.query(CreditLedger).filter_by(reason="purchase").count() == 1
    assert db.query(Account).filter_by(profile_id=7).one().credit_balance == 5000


def test_verify_unpaid_does_not_grant(client):
    c, db, mp = client
    from web.tenancy import current_profile_id
    c.app.dependency_overrides[current_profile_id] = lambda: 7
    mp.setattr(payments_router.stripe_client, "retrieve_checkout_session",
               lambda sid: _session("unpaid"))
    r = c.get("/api/payments/verify", params={"session_id": "cs_1"})
    assert r.json()["status"] == "unpaid"
    assert db.query(CreditLedger).filter_by(reason="purchase").count() == 0
    assert db.query(Purchase).filter_by(stripe_session_id="cs_1").one().status == "pending"


def test_verify_other_tenant_forbidden(client):
    """A logged-in user cannot fulfill a purchase belonging to another tenant."""
    c, db, mp = client
    from web.tenancy import current_profile_id
    c.app.dependency_overrides[current_profile_id] = lambda: 999
    mp.setattr(payments_router.stripe_client, "retrieve_checkout_session",
               lambda sid: _session("paid"))
    r = c.get("/api/payments/verify", params={"session_id": "cs_1"})
    assert r.status_code == 403
    assert db.query(CreditLedger).filter_by(reason="purchase").count() == 0


def test_webhook_no_account_does_not_complete(client):
    c, db, mp = client
    # Remove the account so grant returns None; purchase must NOT be marked completed.
    db.query(Account).delete()
    db.commit()
    mp.setattr(payments_router.stripe_client, "construct_event",
               lambda payload, sig: _event("cs_1"))
    r = c.post("/api/payments/webhook", content=b"{}", headers={"stripe-signature": "x"})
    assert r.status_code == 200
    assert r.json()["status"] == "no_account"
    assert db.query(Purchase).filter_by(stripe_session_id="cs_1").one().status == "pending"
    assert db.query(Purchase).filter_by(stripe_session_id="cs_1").one().stripe_event_id is None
