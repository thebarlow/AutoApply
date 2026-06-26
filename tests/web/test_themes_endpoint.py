from fastapi.testclient import TestClient

from web.main import app

client = TestClient(app)


def test_themes_endpoint_lists_three():
    r = client.get("/api/themes")
    assert r.status_code == 200
    body = r.json()
    assert [t["id"] for t in body] == ["classic", "modern", "compact"]
    assert [t["label"] for t in body] == ["Classic", "Modern", "Compact"]
