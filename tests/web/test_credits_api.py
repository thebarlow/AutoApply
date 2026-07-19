import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, Account, get_db
import core.user  # noqa: F401
from core.user import User
from web.main import app
from web.tenancy import current_profile_id


@pytest.fixture
def db_session():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    s.add(User(id=1, name="T", data="{}"))
    s.add(User(id=2, name="A", data="{}"))
    s.add(Account(email="u@x.c", is_admin=False, profile_id=1, created_at="now",
                  credit_balance=100, credit_rate=1.5))
    s.add(Account(email="admin@x.c", is_admin=True, profile_id=2, created_at="now",
                  credit_balance=0, credit_rate=0.0))
    s.commit()
    yield s
    s.close()


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[current_profile_id] = lambda: 1
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_get_credits_returns_balance(client):
    r = client.get("/api/credits")
    assert r.status_code == 200
    assert r.json()["balance"] == 100
    assert r.json()["rate"] == 1.5


