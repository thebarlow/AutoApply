import sys
import pytest
from fastapi.testclient import TestClient

from web.main import app


@pytest.fixture(autouse=True)
def reset_cost():
    import core.session_cost as sc
    sc.reset()
    yield
    sc.reset()


@pytest.fixture
def client():
    return TestClient(app)


def test_session_cost_starts_at_zero(client):
    resp = client.get("/api/session-cost")
    assert resp.status_code == 200
    assert resp.json() == {"total": 0.0}


def test_session_cost_reflects_accumulated_cost(client):
    import core.session_cost as sc
    sc.add_cost(0.00123456)
    resp = client.get("/api/session-cost")
    assert resp.status_code == 200
    assert abs(resp.json()["total"] - 0.00123456) < 1e-10
