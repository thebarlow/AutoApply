from fastapi.testclient import TestClient
from web.main import app


def test_output_formats_endpoint_lists_registry():
    client = TestClient(app)
    r = client.get("/api/output-formats")
    assert r.status_code == 200
    data = r.json()
    ids = {d["id"] for d in data}
    assert ids == {"bullets", "paragraph"}
    bullets = next(d for d in data if d["id"] == "bullets")
    assert bullets["label"] == "Bullet list"
    assert bullets["kind"] == "bullets"
