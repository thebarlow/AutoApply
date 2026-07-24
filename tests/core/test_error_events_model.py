from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.database import Base, ErrorEvent


def test_error_event_roundtrip():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[ErrorEvent.__table__])
    Session = sessionmaker(bind=engine)
    db = Session()
    ev = ErrorEvent(
        created_at="2026-07-23T00:00:00+00:00",
        last_seen="2026-07-23T00:00:00+00:00",
        count=1,
        level="ERROR",
        logger="x",
        message="boom",
        traceback="Traceback...",
        route="/r",
        profile_id=2,
        request_id="rid",
        fingerprint="fp",
    )
    db.add(ev)
    db.commit()
    got = db.query(ErrorEvent).one()
    assert got.fingerprint == "fp"
    assert got.count == 1
    db.close()
