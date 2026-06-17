# tests/web/test_daily_purge.py
from datetime import datetime
from zoneinfo import ZoneInfo

import web.main as main

ET = ZoneInfo("America/New_York")


def test_seconds_until_next_purge_before_target_same_day():
    now = datetime(2026, 6, 16, 23, 0, 0, tzinfo=ET)  # 11:00pm ET
    assert main._seconds_until_next_purge(now) == 59 * 60  # 59 minutes to 23:59


def test_seconds_until_next_purge_after_target_rolls_to_next_day():
    now = datetime(2026, 6, 17, 0, 0, 0, tzinfo=ET)  # just past midnight
    # next 23:59 is 23h59m away
    assert main._seconds_until_next_purge(now) == (23 * 3600 + 59 * 60)


def test_seconds_until_next_purge_exactly_at_target_rolls_forward():
    now = datetime(2026, 6, 16, 23, 59, 0, tzinfo=ET)
    assert main._seconds_until_next_purge(now) == 24 * 3600


def test_purge_deletes_only_deleted_state(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from db.database import Base
    from core.job import Job

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    def _job(key, state):
        return Job(
            job_key=key,
            state=state,
            profile_id=1,
            source="indeed",
            title="Eng",
            company="Acme",
            url=f"https://indeed.com/v/{key}",
            description="Do.",
        )

    s = Session()
    s.add(_job("a", "deleted"))
    s.add(_job("b", "new"))
    s.commit()
    s.close()

    monkeypatch.setattr(main, "SessionLocal", Session, raising=False)
    # _purge_deleted_jobs imports SessionLocal from db.database; patch there too.
    import db.database as database

    monkeypatch.setattr(database, "SessionLocal", Session)

    count = main._purge_deleted_jobs(context="test")
    assert count == 1

    s = Session()
    remaining = {j.job_key for j in s.query(Job).all()}
    s.close()
    assert remaining == {"b"}
