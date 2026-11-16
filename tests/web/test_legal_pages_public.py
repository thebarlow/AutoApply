"""The /privacy and /terms SPA routes must load without a session in production.

They are linked from the logged-out landing page and the sign-in card, so the
auth gate (which only guards /api/*) must let them through to the SPA catch-all.
"""
import pytest
from fastapi.testclient import TestClient

import web.main as main


@pytest.fixture
def prod_client(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "production")
    # The built SPA may not exist in a test checkout; serve a stub index.html.
    (tmp_path / "index.html").write_text("<!doctype html><div id=root></div>")
    monkeypatch.setattr(main, "_DIST", tmp_path)
    # No context manager: skip the lifespan (DB init, purge thread).
    return TestClient(main.app)


@pytest.mark.parametrize("path", ["/privacy", "/terms"])
def test_legal_pages_public_in_production(prod_client, path):
    r = prod_client.get(path)
    assert r.status_code == 200
    assert "id=root" in r.text


def test_api_still_gated_in_production(prod_client):
    # Sanity check that the fixture really runs the production gate.
    assert prod_client.get("/api/credits").status_code == 401
