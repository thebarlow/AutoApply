import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.database import Base, Account, CreditLedger
import core.metering as metering
from core.credits import InsufficientCredits


def _db_with_account(rate=1.5, balance=100):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    db.add(Account(email="u@x.c", is_admin=False, profile_id=1, created_at="now",
                   credit_balance=balance, credit_rate=rate))
    db.commit()
    return db


def test_records_accumulate_and_settle_to_one_debit():
    db = _db_with_account(rate=1.5, balance=100)
    with metering.meter_action(db, 1, action="generate", job_key="j1", floor=10):
        metering.record_call(0.002, "modelA", 100, 50)
        metering.record_call(0.0026, "modelB", 80, 40)  # total 0.0046
    rows = db.query(CreditLedger).filter_by(reason="debit").all()
    assert len(rows) == 1
    assert rows[0].delta == -7          # 0.0046*1.5*1000 = 6.9 -> 7
    assert db.query(Account).first().credit_balance == 93


def test_gate_blocks_below_floor_before_any_call():
    db = _db_with_account(balance=5)
    with pytest.raises(InsufficientCredits):
        with metering.meter_action(db, 1, action="generate", job_key="j1", floor=10):
            pytest.fail("body should not run when gated")


def test_rate_zero_skips_gate_and_debit():
    db = _db_with_account(rate=0.0, balance=0)
    with metering.meter_action(db, 1, action="generate", job_key="j1", floor=10):
        metering.record_call(0.05, "modelA", 100, 50)
    assert db.query(CreditLedger).filter_by(reason="debit").count() == 0


def test_settles_cost_even_when_action_raises():
    db = _db_with_account(rate=1.5, balance=100)
    with pytest.raises(ValueError):
        with metering.meter_action(db, 1, action="generate", job_key="j1", floor=10):
            metering.record_call(0.0046, "modelA", 100, 50)
            raise ValueError("boom")
    assert db.query(CreditLedger).filter_by(reason="debit").count() == 1


def test_admin_bypasses_gate_and_debit_despite_rate_and_zero_balance():
    # Admins draw from the system balance: never gated, never debited, even with a
    # positive credit_rate and a zero balance.
    db = _db_with_account(rate=1.5, balance=0)
    acct = db.query(Account).first()
    acct.is_admin = True
    db.commit()
    with metering.meter_action(db, 1, action="generate", job_key="j1", floor=10):
        metering.record_call(0.05, "modelA", 100, 50)
    assert db.query(CreditLedger).filter_by(reason="debit").count() == 0
    assert db.query(Account).first().credit_balance == 0


def test_record_call_outside_meter_is_noop():
    metering.record_call(0.01, "m", 1, 1)  # must not raise


def test_record_usage_feeds_meter_and_debits():
    """Audit I1: extraction/skill-match do a direct create() and record their
    cost via core.llm.record_usage. Inside a meter that must produce a real
    debit (previously extraction recorded nothing → always a 0 debit)."""
    from core.llm import record_usage

    class _Usage:
        cost = 0.0046
        prompt_tokens = 100
        completion_tokens = 50

    class _Resp:
        usage = _Usage()

    db = _db_with_account(rate=1.5, balance=100)
    with metering.meter_action(db, 1, action="extract", job_key="j1", floor=10):
        record_usage(_Resp(), "modelA")
    rows = db.query(CreditLedger).filter_by(reason="debit").all()
    assert len(rows) == 1
    assert rows[0].delta == -7          # 0.0046*1.5*1000 = 6.9 -> 7
    assert rows[0].action == "extract"


def test_record_usage_without_usage_is_noop():
    """A response with no usage attribute records nothing (no crash, no debit)."""
    from core.llm import record_usage

    class _Resp:
        usage = None

    db = _db_with_account(rate=1.5, balance=100)
    with metering.meter_action(db, 1, action="extract", job_key="j1", floor=10):
        record_usage(_Resp(), "modelA")
    assert db.query(CreditLedger).filter_by(reason="debit").count() == 0


def test_successful_debit_broadcasts_credits_nudge(monkeypatch):
    """Audit I2: a settled debit nudges the tenant's clients to refetch balance."""
    import web.sse as sse
    sent = []
    monkeypatch.setattr(sse, "send", lambda t, d, **k: sent.append((t, d, k)))
    db = _db_with_account(rate=1.5, balance=100)
    with metering.meter_action(db, 1, action="generate", job_key="j1", floor=10):
        metering.record_call(0.0046, "modelA", 100, 50)
    # Scoped to the spending tenant, not a global broadcast.
    assert ("credits", {}, {"profile_id": 1}) in sent


def test_no_debit_does_not_broadcast(monkeypatch):
    """No spend (rate 0) → no credits nudge."""
    import web.sse as sse
    sent = []
    monkeypatch.setattr(sse, "send", lambda t, d, **k: sent.append((t, d, k)))
    db = _db_with_account(rate=0.0, balance=0)
    with metering.meter_action(db, 1, action="generate", job_key="j1", floor=10):
        metering.record_call(0.05, "modelA", 100, 50)
    assert sent == []


def test_notify_failure_never_breaks_action(monkeypatch):
    """A broadcast error must not surface from a billable action."""
    import web.sse as sse

    def _boom(*a, **k):
        raise RuntimeError("sse down")

    monkeypatch.setattr(sse, "send", _boom)
    db = _db_with_account(rate=1.5, balance=100)
    with metering.meter_action(db, 1, action="generate", job_key="j1", floor=10):
        metering.record_call(0.0046, "modelA", 100, 50)
    assert db.query(CreditLedger).filter_by(reason="debit").count() == 1


def test_settle_failure_does_not_mask_body_error(monkeypatch):
    db = _db_with_account(rate=1.5, balance=100)
    import core.metering as m

    def _boom_debit(*a, **k):
        raise RuntimeError("settle exploded")

    monkeypatch.setattr(m, "debit_for_action", _boom_debit)
    with pytest.raises(ValueError, match="body boom"):
        with m.meter_action(db, 1, action="generate", job_key="j1", floor=10):
            m.record_call(0.0046, "modelA", 100, 50)
            raise ValueError("body boom")
