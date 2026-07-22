from fastapi.testclient import TestClient
from web.main import app
from core.job import Job
from db.database import get_db

client = TestClient(app)


def test_seed_ats_job_creates_scraped_job():
    r = client.post("/api/dev/login")
    assert r.status_code == 200
    profile_id = r.json()["profile_id"]

    body = {
        "job_key": "e2e-ats-fixture-greenhouse",
        "apply_url": "https://boards.greenhouse.io/acme/jobs/123",
        "ats_type": "greenhouse",
    }
    r = client.post("/api/dev/seed-ats-job", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["job_key"] == body["job_key"]

    db = next(get_db())
    job = Job.get(body["job_key"], db, profile_id)
    assert job is not None
    assert job.state == "scraped"
    assert job.ats_type == "greenhouse"
    assert job.apply_url_resolved == body["apply_url"]


def test_seed_ats_job_is_idempotent():
    client.post("/api/dev/login")
    body = {
        "job_key": "e2e-ats-fixture-greenhouse",
        "apply_url": "https://boards.greenhouse.io/acme/jobs/123",
        "ats_type": "greenhouse",
    }
    assert client.post("/api/dev/seed-ats-job", json=body).status_code == 200
    assert client.post("/api/dev/seed-ats-job", json=body).status_code == 200
