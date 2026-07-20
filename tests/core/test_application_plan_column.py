import json

from core.job import Job


def test_serialize_parses_application_plan_json():
    job = Job.__new__(Job)
    job._hydrate_defaults() if hasattr(job, "_hydrate_defaults") else None
    job.application_plan = json.dumps({"job_key": "j1", "fields": []})
    out = job.serialize()
    assert out["application_plan"] == {"job_key": "j1", "fields": []}


def test_serialize_application_plan_none_when_unset():
    job = Job.__new__(Job)
    job.application_plan = None
    assert job.serialize()["application_plan"] is None
