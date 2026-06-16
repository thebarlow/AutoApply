from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, ExtensionToken


def test_extension_token_persists():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    tok = ExtensionToken(account_id=1, token_hash="abc", created_at="2026-06-16T00:00:00+00:00")
    session.add(tok)
    session.commit()
    row = session.query(ExtensionToken).filter_by(token_hash="abc").first()
    assert row.account_id == 1
    assert row.revoked is False
    assert row.last_used_at is None
