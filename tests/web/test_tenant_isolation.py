"""Two tenants with the same job URL must not see or collide with each other."""
from core.job import Job
from db.database import Document


def test_no_cross_read_and_no_unique_collision(tenant_db, seed_tenant):
    db = tenant_db
    a = seed_tenant(1, "Alice")
    b = seed_tenant(2, "Bob")

    # Same job_key AND same url under two tenants — must not collide.
    db.add(Job(job_key="shared", source="s", url="http://same", state="new", profile_id=a))
    db.add(Job(job_key="shared", source="s", url="http://same", state="new", profile_id=b))
    db.commit()

    # Each tenant generates a resume document for the same job_key.
    Document.upsert(db, "shared", "resume", '{"owner":"A"}', profile_id=a)
    Document.upsert(db, "shared", "resume", '{"owner":"B"}', profile_id=b)

    # No cross-read.
    assert Job.get("shared", db, profile_id=a).profile_id == 1
    assert Job.get("shared", db, profile_id=b).profile_id == 2
    assert Document.fetch(db, "shared", "resume", profile_id=a).structured_json == '{"owner":"A"}'
    assert Document.fetch(db, "shared", "resume", profile_id=b).structured_json == '{"owner":"B"}'
