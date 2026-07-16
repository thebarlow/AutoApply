import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from db.database import Base, Account, CreditLedger
import core.metering as metering
from core.credits import InsufficientCredits


@pytest.fixture
def db_session():
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


def _acct(db, profile_id=1, rate=1.5, balance=100):
    a = Account(email=f"u{profile_id}@x.c", is_admin=False, profile_id=profile_id,
                created_at="now", credit_balance=balance, credit_rate=rate)
    db.add(a)
    db.commit()
    return a


def _balance(db, profile_id=1):
    from core import credits
    return credits.get_account_for_profile(db, profile_id).credit_balance


def test_meter_debits_fixed_price_upfront(db_session):
    _acct(db_session, balance=10, rate=1.0)
    with metering.meter_action(db_session, 1, action="score", job_key="j1"):
        pass  # no LLM cost recorded
    rows = db_session.query(CreditLedger).all()
    assert len(rows) == 1 and rows[0].delta == -1 and rows[0].reason == "debit"
    assert _balance(db_session) == 9


def test_meter_blocks_below_price(db_session):
    _acct(db_session, balance=3, rate=1.0)
    with pytest.raises(InsufficientCredits) as ei:
        with metering.meter_action(db_session, 1, action="generate_fresh", job_key="j1"):
            raise AssertionError("body must not run")
    assert ei.value.price == 4 and ei.value.balance == 3


def test_meter_refunds_on_body_exception(db_session):
    _acct(db_session, balance=10, rate=1.0)
    with pytest.raises(RuntimeError):
        with metering.meter_action(db_session, 1, action="regenerate", job_key="j1"):
            raise RuntimeError("llm blew up")
    reasons = [r.reason for r in db_session.query(CreditLedger).all()]
    assert reasons == ["debit", "refund"]
    assert _balance(db_session) == 10


def test_meter_annotates_raw_cost_on_success(db_session):
    _acct(db_session, balance=10, rate=1.0)
    with metering.meter_action(db_session, 1, action="regenerate", job_key="j1"):
        metering.record_call(0.002, "modelA", 100, 50)
        metering.record_call(0.001, "modelB", 80, 40)
    row = db_session.query(CreditLedger).filter_by(reason="debit").one()
    assert row.raw_cost_usd == pytest.approx(0.003)
    import json
    meta = json.loads(row.meta)
    assert meta["calls"] == 2 and meta["prompt_tokens"] == 180


def test_meter_explicit_price_overrides_card(db_session):
    _acct(db_session, balance=10, rate=1.0)
    with metering.meter_action(db_session, 1, action="score", job_key="j1", price=3):
        pass
    assert _balance(db_session) == 7


def test_unmetered_admin_and_rate_zero_pass_through(db_session):
    _acct(db_session, balance=0, rate=0.0)
    with metering.meter_action(db_session, 1, action="generate_fresh", job_key="j1"):
        metering.record_call(0.05, "m", 1, 1)
    assert db_session.query(CreditLedger).count() == 0


def test_admin_bypasses_gate_and_debit_despite_rate_and_zero_balance(db_session):
    # Admins draw from the system balance: never gated, never debited, even with a
    # positive credit_rate and a zero balance.
    _acct(db_session, rate=1.5, balance=0)
    acct = db_session.query(Account).first()
    acct.is_admin = True
    db_session.commit()
    with metering.meter_action(db_session, 1, action="generate_fresh", job_key="j1"):
        metering.record_call(0.05, "modelA", 100, 50)
    assert db_session.query(CreditLedger).filter_by(reason="debit").count() == 0
    assert db_session.query(Account).first().credit_balance == 0


def test_record_call_outside_meter_is_noop():
    metering.record_call(0.01, "m", 1, 1)  # must not raise


def test_record_usage_feeds_meter_and_annotates_debit(db_session):
    """Audit I1: extraction/skill-match do a direct create() and record their
    cost via core.llm.record_usage. Inside a meter the fixed-price debit still
    fires; the observed cost lands on raw_cost_usd for margin tracking."""
    from core.llm import record_usage

    class _Usage:
        cost = 0.0046
        prompt_tokens = 100
        completion_tokens = 50

    class _Resp:
        usage = _Usage()

    _acct(db_session, rate=1.5, balance=100)
    with metering.meter_action(db_session, 1, action="extract", job_key="j1"):
        record_usage(_Resp(), "modelA")
    rows = db_session.query(CreditLedger).filter_by(reason="debit").all()
    assert len(rows) == 1
    assert rows[0].delta == -1  # fixed price for "extract"
    assert rows[0].action == "extract"
    assert rows[0].raw_cost_usd == pytest.approx(0.0046)


def test_record_usage_without_usage_is_noop(db_session):
    """A response with no usage attribute records nothing extra (no crash);
    the fixed-price debit still happens but is not annotated."""
    from core.llm import record_usage

    class _Resp:
        usage = None

    _acct(db_session, rate=1.5, balance=100)
    with metering.meter_action(db_session, 1, action="extract", job_key="j1"):
        record_usage(_Resp(), "modelA")
    row = db_session.query(CreditLedger).filter_by(reason="debit").one()
    assert row.raw_cost_usd is None


def test_successful_debit_broadcasts_credits_nudge(monkeypatch, db_session):
    """Audit I2: a settled debit nudges the tenant's clients to refetch balance."""
    import web.sse as sse
    sent = []
    monkeypatch.setattr(sse, "send", lambda t, d, **k: sent.append((t, d, k)))
    _acct(db_session, rate=1.5, balance=100)
    with metering.meter_action(db_session, 1, action="regenerate", job_key="j1"):
        metering.record_call(0.0046, "modelA", 100, 50)
    # Scoped to the spending tenant, not a global broadcast.
    assert ("credits", {}, {"profile_id": 1}) in sent


def test_no_debit_does_not_broadcast(monkeypatch, db_session):
    """Unmetered account (rate 0) -> no debit, no credits nudge."""
    import web.sse as sse
    sent = []
    monkeypatch.setattr(sse, "send", lambda t, d, **k: sent.append((t, d, k)))
    _acct(db_session, rate=0.0, balance=0)
    with metering.meter_action(db_session, 1, action="generate_fresh", job_key="j1"):
        metering.record_call(0.05, "modelA", 100, 50)
    assert sent == []


def test_notify_failure_never_breaks_action(monkeypatch, db_session):
    """A broadcast error must not surface from a billable action."""
    import web.sse as sse

    def _boom(*a, **k):
        raise RuntimeError("sse down")

    monkeypatch.setattr(sse, "send", _boom)
    _acct(db_session, rate=1.5, balance=100)
    with metering.meter_action(db_session, 1, action="regenerate", job_key="j1"):
        metering.record_call(0.0046, "modelA", 100, 50)
    assert db_session.query(CreditLedger).filter_by(reason="debit").count() == 1


def test_annotation_failure_does_not_mask_success(monkeypatch, db_session):
    """A cost-annotation failure after a successful body must not raise."""
    _acct(db_session, rate=1.5, balance=100)

    def _boom_commit():
        raise RuntimeError("annotate exploded")

    with metering.meter_action(db_session, 1, action="regenerate", job_key="j1"):
        metering.record_call(0.0046, "modelA", 100, 50)
        monkeypatch.setattr(db_session, "commit", _boom_commit)
    assert db_session.query(CreditLedger).filter_by(reason="debit").count() == 1
