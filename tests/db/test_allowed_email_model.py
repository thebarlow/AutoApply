from db.database import AllowedEmail


def test_allowed_email_columns():
    cols = {c.name for c in AllowedEmail.__table__.columns}
    assert cols == {"id", "email", "invited_by", "created_at", "tier", "is_admin"}
    assert AllowedEmail.__table__.c.email.unique is True
