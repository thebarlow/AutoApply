from db.database import Account


def test_account_has_banned_column():
    col = Account.__table__.c.banned
    assert col is not None
    assert col.nullable is False
