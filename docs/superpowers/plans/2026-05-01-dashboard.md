# Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Review Queue with an Alpine.js dashboard that lists all jobs, supports sorting, and provides a details overlay with scoring, generation, and state-transition actions.

**Architecture:** Simplify the state machine from 8 states to 4 (`pending`, `applied`, `rejected`, `failed`), update all backend consumers, add new API endpoints for scoring/generation/deletion, then rewrite the frontend as a single Alpine.js page.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite, Alpine.js v3 (CDN), vanilla HTML/CSS, pytest + FastAPI TestClient

---

## File Map

| File | Action | What changes |
|---|---|---|
| `core/types.py` | Modify | Drop retired enum members; add `PENDING` |
| `core/scorer.py` | Modify | Remove `determine_state()`; `score_job()` no longer sets state; `run_scorer()` targets `pending` |
| `scraper/runner.py` | Modify | `state=JobState.SCRAPED.value` → `state=JobState.PENDING.value` |
| `generator/generator.py` | Modify | Remove `GENERATED` state transition on success; add `generate_resume_for_job()` and `generate_cover_for_job()` |
| `db/models.py` | Modify | Add `default="pending"` to state column |
| `scripts/migrate_states.py` | Create | One-time migration for existing DB rows |
| `web/routers/jobs.py` | Modify | Update GET, PATCH; add DELETE, POST score, POST generate/resume, POST generate/cover, GET resume, GET cover |
| `web/static/index.html` | Rewrite | Alpine.js dashboard |
| `web/static/style.css` | Rewrite | Table, overlay, badges |
| `web/CONTEXT.md` | Create | Known issues and future goals |
| `tests/core/test_types.py` | Modify | Update state enum test |
| `tests/scorer/test_scorer.py` | Modify | Remove `determine_state` tests; update `score_job` and `run_scorer` tests |
| `tests/web/test_jobs_api.py` | Modify | Update GET test; add DELETE, PATCH, score, generate, serve tests |

---

### Task 1: Update JobState enum and fix all direct references

**Files:**
- Modify: `core/types.py`
- Modify: `generator/generator.py:240` (remove GENERATED reference)
- Modify: `scraper/runner.py:61` (SCRAPED → PENDING)
- Modify: `tests/core/test_types.py`

- [ ] **Step 1: Update the enum**

Replace the body of `JobState` in `core/types.py`:

```python
class JobState(str, Enum):
    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"
    FAILED = "failed"
```

- [ ] **Step 2: Fix generator.py — remove GENERATED state transition**

In `generator/generator.py`, line 240 sets `job.state = JobState.GENERATED.value`. Replace that block:

Old (lines 238–241):
```python
        job.resume_path = str(resume_pdf_path)
        job.cover_path = str(cover_pdf_path)
        job.state = JobState.GENERATED.value
        db.commit()
```

New:
```python
        job.resume_path = str(resume_pdf_path)
        job.cover_path = str(cover_pdf_path)
        db.commit()
```

- [ ] **Step 3: Fix scraper/runner.py — update default state**

In `scraper/runner.py`, line 61, change:
```python
            state=JobState.SCRAPED.value,
```
to:
```python
            state=JobState.PENDING.value,
```

- [ ] **Step 4: Update the types test**

Replace `test_job_state_values` in `tests/core/test_types.py`:

```python
def test_job_state_values():
    assert JobState.PENDING == "pending"
    assert JobState.APPLIED == "applied"
    assert JobState.REJECTED == "rejected"
    assert JobState.FAILED == "failed"
    assert len(JobState) == 4
```

- [ ] **Step 5: Run the types test**

```
pytest tests/core/test_types.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```
git add core/types.py generator/generator.py scraper/runner.py tests/core/test_types.py
git commit -m "[refactor] Simplify JobState to pending/applied/rejected/failed"
```

---

### Task 2: Update scorer — remove state transitions

**Files:**
- Modify: `core/scorer.py`
- Modify: `tests/scorer/test_scorer.py`

- [ ] **Step 1: Remove `determine_state()` and update `score_job()`**

In `core/scorer.py`:

1. Delete the entire `determine_state()` function (lines 26–34).

2. In `score_job()`, remove the line `job.state = determine_state(...)`. The function body after this change ends with:

```python
    job.desirability_score = desirability
    job.fit_score = fit
    job.final_score = final
    job.score_justification = json.dumps({
        "desirability": parsed["desirability_justification"],
        "fit": parsed["fit_justification"],
    })
    db.commit()
```

- [ ] **Step 2: Update `run_scorer()` to target `pending` jobs**

In `run_scorer()`, change both filter calls from `JobState.SCRAPED` to `JobState.PENDING`:

```python
def run_scorer(
    db: Session,
    client: anthropic.Anthropic,
    job_key: Optional[str] = None,
) -> None:
    """Score all PENDING jobs, or a single job if job_key is provided."""
    profile = load_user_profile(db)
    config = load_config(db)

    if job_key:
        jobs = db.query(Job).filter_by(job_key=job_key, state=JobState.PENDING).all()
    else:
        jobs = db.query(Job).filter_by(state=JobState.PENDING).all()

    if not jobs:
        print("No PENDING jobs found.")
        return

    for job in jobs:
        score_job(job, profile, config, client, db)
        db.refresh(job)
        score_str = f"{job.final_score:.2f}" if job.final_score is not None else "N/A"
        print(f"[{job.state.upper()}] {job.job_key} (final={score_str})")
```

- [ ] **Step 3: Update scorer tests**

Replace the affected tests in `tests/scorer/test_scorer.py`.

Remove these tests entirely (they test the deleted function):
- `test_determine_state_approved`
- `test_determine_state_rejected`
- `test_determine_state_pending_review`
- `test_determine_state_boundary_reject`
- `test_determine_state_boundary_approve`

Remove the import line:
```python
from core.scorer import compute_final_score, determine_state
```
Replace with:
```python
from core.scorer import compute_final_score
```

Update `make_job()` — it defaults to `JobState.SCRAPED`, change to `JobState.PENDING`:
```python
def make_job(job_key: str, state: JobState = JobState.PENDING) -> Job:
    return Job(
        job_key=job_key,
        source="indeed",
        title="Software Engineer",
        company="TechCorp",
        location="Remote",
        salary="$130k",
        description="Python and SQL required.",
        url=f"https://example.com/{job_key}",
        state=state,
    )
```

Replace `test_score_job_approved`, `test_score_job_rejected`, `test_score_job_pending_review` with a single test that verifies scores are set but state is unchanged:

```python
def test_score_job_sets_scores_not_state(seeded_db):
    job = make_job("job_001")
    seeded_db.add(job)
    seeded_db.commit()

    profile = load_user_profile(seeded_db)
    config = load_config(seeded_db)
    client = mock_client(MOCK_CLAUDE_RESPONSE)

    score_job(job, profile, config, client, seeded_db)
    seeded_db.refresh(job)

    assert job.state == JobState.PENDING
    assert job.desirability_score == pytest.approx(0.85)
    assert job.fit_score == pytest.approx(0.75)
    assert job.final_score == pytest.approx(0.8)
    justification = _json.loads(job.score_justification)
    assert "desirability" in justification
    assert "fit" in justification
```

Update `test_malformed_claude_response` — state stays `pending`:
```python
def test_malformed_claude_response(seeded_db):
    job = make_job("job_004")
    seeded_db.add(job)
    seeded_db.commit()

    profile = load_user_profile(seeded_db)
    config = load_config(seeded_db)
    client = mock_client("not valid json")

    score_job(job, profile, config, client, seeded_db)
    seeded_db.refresh(job)

    assert job.state == JobState.PENDING
    assert job.final_score is None
```

Update `test_score_batch_skips_non_scraped` — now skips non-pending:
```python
def test_score_batch_skips_non_pending(seeded_db):
    pending1 = make_job("batch_001", JobState.PENDING)
    pending2 = make_job("batch_002", JobState.PENDING)
    already_applied = make_job("batch_003", JobState.APPLIED)
    seeded_db.add_all([pending1, pending2, already_applied])
    seeded_db.commit()

    client = mock_client(MOCK_CLAUDE_RESPONSE)
    run_scorer(seeded_db, client, job_key=None)

    seeded_db.refresh(pending1)
    seeded_db.refresh(pending2)
    seeded_db.refresh(already_applied)

    assert pending1.state == JobState.PENDING
    assert pending2.state == JobState.PENDING
    assert already_applied.state == JobState.APPLIED
    assert client.messages.create.call_count == 2
```

Update `test_single_job_key_flag`:
```python
def test_single_job_key_flag(seeded_db):
    target = make_job("single_001", JobState.PENDING)
    other = make_job("single_002", JobState.PENDING)
    seeded_db.add_all([target, other])
    seeded_db.commit()

    client = mock_client(MOCK_CLAUDE_RESPONSE)
    run_scorer(seeded_db, client, job_key="single_001")

    seeded_db.refresh(target)
    seeded_db.refresh(other)

    assert target.final_score == pytest.approx(0.8)
    assert other.final_score is None
    assert client.messages.create.call_count == 1
```

Also update `test_build_prompt_contains_job_fields` — job state is now `pending`:
```python
    job = Job(
        job_key="test_001",
        source="indeed",
        title="Backend Engineer",
        company="TechCorp",
        location="Remote",
        salary="$130k-$150k",
        description="We need a Python expert.",
        url="https://example.com/job/1",
        state=JobState.PENDING,
    )
```

- [ ] **Step 4: Run scorer tests**

```
pytest tests/scorer/test_scorer.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```
git add core/scorer.py tests/scorer/test_scorer.py
git commit -m "[refactor] Remove determine_state; scoring no longer transitions job state"
```

---

### Task 3: Add default state to db model and write migration script

**Files:**
- Modify: `db/models.py`
- Create: `scripts/migrate_states.py`

- [ ] **Step 1: Add default state to model**

In `db/models.py`, update the state column:

```python
    state = Column(String, nullable=False, default="pending")
```

- [ ] **Step 2: Write the migration script**

Create `scripts/migrate_states.py`:

```python
"""One-time migration: map retired job states to their new equivalents."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.database import SessionLocal
from db.models import Job

RETIRED_TO_PENDING = {"scraped", "scored", "pending_review", "approved", "generated", "rejected"}

def migrate(db) -> None:
    jobs = db.query(Job).all()
    updated = 0
    for job in jobs:
        if job.state in RETIRED_TO_PENDING:
            job.state = "pending"
            updated += 1
    db.commit()
    print(f"Migrated {updated} of {len(jobs)} jobs to 'pending'.")

if __name__ == "__main__":
    db = SessionLocal()
    try:
        migrate(db)
    finally:
        db.close()
```

- [ ] **Step 3: Run the migration**

```
python scripts/migrate_states.py
```

Expected output: something like `Migrated N of M jobs to 'pending'.`

- [ ] **Step 4: Commit**

```
git add db/models.py scripts/migrate_states.py
git commit -m "[feat] Add default state to Job model; add state migration script"
```

---

### Task 4: Update `_serialize` and `GET /api/jobs`

**Files:**
- Modify: `web/routers/jobs.py`
- Modify: `tests/web/test_jobs_api.py`

- [ ] **Step 1: Write failing tests**

In `tests/web/test_jobs_api.py`, update `_make_job` to use `JobState.PENDING` and update the GET tests:

Replace the `_make_job` helper's default state:
```python
def _make_job(
    db_session,
    job_key: str,
    state: JobState = JobState.PENDING,
    final_score: float = 0.75,
    description: str | None = None,
    remote: bool | None = None,
    resume_path: str | None = None,
    cover_path: str | None = None,
) -> Job:
    job = Job(
        job_key=job_key,
        source="indeed",
        title="Software Engineer",
        company="Acme Corp",
        location="Remote",
        salary="$120,000",
        url=f"https://indeed.com/job/{job_key}",
        state=state.value,
        desirability_score=0.80,
        fit_score=0.70,
        final_score=final_score,
        score_justification=json.dumps({
            "desirability": "Good salary and remote.",
            "fit": "Strong Python match.",
        }),
        description=description,
        remote=remote,
        resume_path=resume_path,
        cover_path=cover_path,
    )
    db_session.add(job)
    db_session.commit()
    return job
```

Replace `test_get_jobs_returns_pending_review` with:
```python
def test_get_jobs_returns_all_states(client, db_session):
    _make_job(db_session, "job_a", JobState.PENDING)
    _make_job(db_session, "job_b", JobState.APPLIED)
    _make_job(db_session, "job_c", JobState.REJECTED)

    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    keys = [j["job_key"] for j in resp.json()]
    assert "job_a" in keys
    assert "job_b" in keys
    assert "job_c" in keys
```

Add a test for `resume_path` and `cover_path` in the response:
```python
def test_get_jobs_includes_artifact_paths(client, db_session):
    _make_job(db_session, "job_paths", resume_path="/outputs/job_paths_resume.pdf")

    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    job = resp.json()[0]
    assert job["resume_path"] == "/outputs/job_paths_resume.pdf"
    assert job["cover_path"] is None
```

Update any remaining tests that use `JobState.PENDING_REVIEW` to use `JobState.PENDING`.

- [ ] **Step 2: Run tests — expect failures**

```
pytest tests/web/test_jobs_api.py::test_get_jobs_returns_all_states tests/web/test_jobs_api.py::test_get_jobs_includes_artifact_paths -v
```

Expected: both FAIL (old filter + missing fields in serialize).

- [ ] **Step 3: Update `_serialize` and `GET /api/jobs`**

In `web/routers/jobs.py`, update `_serialize` to include artifact paths:

```python
def _serialize(job: Job) -> dict[str, Any]:
    justification = job.score_justification
    if isinstance(justification, str):
        try:
            justification = json.loads(justification)
        except (json.JSONDecodeError, TypeError):
            justification = {}

    return {
        "job_key": job.job_key,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "salary": job.salary,
        "url": job.url,
        "description": job.description,
        "remote": job.remote,
        "state": job.state,
        "desirability_score": job.desirability_score,
        "fit_score": job.fit_score,
        "final_score": job.final_score,
        "score_justification": justification,
        "resume_path": job.resume_path,
        "cover_path": job.cover_path,
    }
```

Update `get_jobs` to remove the state filter:

```python
@router.get("")
def get_jobs(db: Session = Depends(get_db)):
    jobs = db.query(Job).order_by(Job.final_score.desc()).all()
    return [_serialize(j) for j in jobs]
```

- [ ] **Step 4: Run GET tests**

```
pytest tests/web/test_jobs_api.py -k "get_jobs" -v
```

Expected: all GET tests pass.

- [ ] **Step 5: Commit**

```
git add web/routers/jobs.py tests/web/test_jobs_api.py
git commit -m "[feat] GET /api/jobs returns all jobs; serialize includes artifact paths"
```

---

### Task 5: Update PATCH state endpoint (applied only, no threading)

**Files:**
- Modify: `web/routers/jobs.py`
- Modify: `tests/web/test_jobs_api.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/web/test_jobs_api.py`:

```python
def test_patch_applied(client, db_session):
    _make_job(db_session, "job_apply")

    resp = client.patch("/api/jobs/job_apply/state", json={"state": "applied"})
    assert resp.status_code == 200
    assert resp.json()["state"] == "applied"


def test_patch_invalid_state_rejected_by_api(client, db_session):
    _make_job(db_session, "job_bad")

    resp = client.patch("/api/jobs/job_bad/state", json={"state": "approved"})
    assert resp.status_code == 400


def test_patch_state_not_found(client):
    resp = client.patch("/api/jobs/nonexistent/state", json={"state": "applied"})
    assert resp.status_code == 404
```

- [ ] **Step 2: Run — expect failures**

```
pytest tests/web/test_jobs_api.py::test_patch_applied tests/web/test_jobs_api.py::test_patch_invalid_state_rejected_by_api tests/web/test_jobs_api.py::test_patch_state_not_found -v
```

Expected: all FAIL.

- [ ] **Step 3: Replace the PATCH endpoint**

In `web/routers/jobs.py`, remove the `threading` import and replace the PATCH endpoint. Also remove the old `_ALLOWED_PATCH_STATES` line if still present. The new router header becomes:

```python
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Job

router = APIRouter(prefix="/api/jobs")


class StateUpdate(BaseModel):
    state: str
```

New PATCH endpoint:
```python
@router.patch("/{job_key}/state")
def update_job_state(job_key: str, body: StateUpdate, db: Session = Depends(get_db)):
    if body.state != "applied":
        raise HTTPException(status_code=400, detail=f"Invalid state: {body.state!r}")

    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    job.state = body.state
    db.commit()
    db.refresh(job)
    return _serialize(job)
```

- [ ] **Step 4: Delete the old PATCH tests**

Remove from `tests/web/test_jobs_api.py`:
- `test_patch_approve`
- `test_patch_reject`
- `test_patch_invalid_state`
- `test_patch_not_found`
- `test_approve_spawns_generation_thread`
- `test_reject_does_not_spawn_thread`

- [ ] **Step 5: Run PATCH tests**

```
pytest tests/web/test_jobs_api.py -k "patch" -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```
git add web/routers/jobs.py tests/web/test_jobs_api.py
git commit -m "[refactor] PATCH state accepts only 'applied'; remove approve/reject threading"
```

---

### Task 6: Add DELETE endpoint

**Files:**
- Modify: `web/routers/jobs.py`
- Modify: `tests/web/test_jobs_api.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/web/test_jobs_api.py`:

```python
def test_delete_job(client, db_session):
    _make_job(db_session, "job_del")

    resp = client.delete("/api/jobs/job_del")
    assert resp.status_code == 200
    assert resp.json() == {"deleted": "job_del"}

    get_resp = client.get("/api/jobs")
    keys = [j["job_key"] for j in get_resp.json()]
    assert "job_del" not in keys


def test_delete_job_not_found(client):
    resp = client.delete("/api/jobs/nonexistent")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run — expect failures**

```
pytest tests/web/test_jobs_api.py::test_delete_job tests/web/test_jobs_api.py::test_delete_job_not_found -v
```

Expected: both FAIL with 405 Method Not Allowed.

- [ ] **Step 3: Add DELETE endpoint**

Add to `web/routers/jobs.py`:

```python
@router.delete("/{job_key}")
def delete_job(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    db.delete(job)
    db.commit()
    return {"deleted": job_key}
```

- [ ] **Step 4: Run DELETE tests**

```
pytest tests/web/test_jobs_api.py::test_delete_job tests/web/test_jobs_api.py::test_delete_job_not_found -v
```

Expected: both pass.

- [ ] **Step 5: Commit**

```
git add web/routers/jobs.py tests/web/test_jobs_api.py
git commit -m "[feat] Add DELETE /api/jobs/{job_key}"
```

---

### Task 7: Add POST score endpoint

**Files:**
- Modify: `web/routers/jobs.py`
- Modify: `tests/web/test_jobs_api.py`

- [ ] **Step 1: Write failing test**

Add to `tests/web/test_jobs_api.py`:

```python
def test_score_job_endpoint(client, db_session, monkeypatch):
    import web.routers.jobs as jobs_router

    _make_job(db_session, "job_score")

    scored_fields = {}

    def mock_score_job(job, profile, config, claude_client, db):
        job.desirability_score = 0.9
        job.fit_score = 0.8
        job.final_score = 0.85
        import json
        job.score_justification = json.dumps({"desirability": "Great.", "fit": "Perfect."})
        db.commit()

    monkeypatch.setattr(jobs_router, "_score_job", mock_score_job)
    monkeypatch.setattr(jobs_router, "_load_user_profile", lambda db: None)
    monkeypatch.setattr(jobs_router, "_load_config", lambda db: {})
    monkeypatch.setattr(jobs_router, "_make_anthropic_client", lambda: None)

    resp = client.post("/api/jobs/job_score/score")
    assert resp.status_code == 200
    data = resp.json()
    assert data["final_score"] == pytest.approx(0.85)
    assert data["state"] == "pending"


def test_score_job_endpoint_not_found(client):
    resp = client.post("/api/jobs/nonexistent/score")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run — expect failures**

```
pytest tests/web/test_jobs_api.py::test_score_job_endpoint tests/web/test_jobs_api.py::test_score_job_endpoint_not_found -v
```

Expected: both FAIL.

- [ ] **Step 3: Add score imports and endpoint to `web/routers/jobs.py`**

Add imports at the top of `web/routers/jobs.py`:

```python
import anthropic as _anthropic

from core.scorer import load_config as _load_config
from core.scorer import load_user_profile as _load_user_profile
from core.scorer import score_job as _score_job


def _make_anthropic_client() -> _anthropic.Anthropic:
    return _anthropic.Anthropic()
```

Add the endpoint:

```python
@router.post("/{job_key}/score")
def score_job_endpoint(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    profile = _load_user_profile(db)
    config = _load_config(db)
    client = _make_anthropic_client()
    _score_job(job, profile, config, client, db)
    db.refresh(job)
    return _serialize(job)
```

- [ ] **Step 4: Run score tests**

```
pytest tests/web/test_jobs_api.py::test_score_job_endpoint tests/web/test_jobs_api.py::test_score_job_endpoint_not_found -v
```

Expected: both pass.

- [ ] **Step 5: Commit**

```
git add web/routers/jobs.py tests/web/test_jobs_api.py
git commit -m "[feat] Add POST /api/jobs/{job_key}/score"
```

---

### Task 8: Add generate functions to generator.py

**Files:**
- Modify: `generator/generator.py`

No tests for this task — the generation functions call Claude and pandoc (external processes). They are exercised through integration when the endpoints are built in Task 9.

- [ ] **Step 1: Add `generate_resume_for_job()` to generator.py**

Add after `generate_job()`:

```python
def generate_resume_for_job(
    job_key: str,
    db: Optional[Session] = None,
    client: Optional[anthropic.Anthropic] = None,
) -> None:
    """Generate resume only for a job. Updates job.resume_path and commits."""
    own_db = db is None
    if own_db:
        db = SessionLocal()
    if client is None:
        client = anthropic.Anthropic()

    try:
        job = db.query(Job).filter_by(job_key=job_key).first()
        if job is None:
            raise ValueError(f"Job not found: {job_key}")

        row = db.query(UserProfileModel).first()
        if not row:
            raise RuntimeError("No user profile found in DB.")
        data = json.loads(row.data)
        data["work_history"] = [WorkHistoryEntry(**e) for e in data.get("work_history", [])]
        data["education"] = [EducationEntry(**e) for e in data.get("education", [])]
        profile = UserProfile(**data)

        resume_tpl = db.query(Config).filter_by(key="resume_prompt_template").first()
        if not resume_tpl:
            raise RuntimeError("resume_prompt_template not seeded in config table.")

        def _cfg(key: str) -> str:
            r = db.query(Config).filter_by(key=key).first()
            return r.value if r else ""

        frontmatter = _build_frontmatter(
            profile,
            github=_cfg("resume_github"),
            linkedin=_cfg("resume_linkedin"),
            website=_cfg("resume_website"),
        )

        outputs = _OUTPUTS_DIR
        outputs.mkdir(parents=True, exist_ok=True)

        resume_md_path = outputs / f"{job_key}_resume.md"
        resume_pdf_path = outputs / f"{job_key}_resume.pdf"
        resume_md = strip_header_block(
            call_claude(build_resume_prompt(job, profile, resume_tpl.value), client)
        )
        resume_md_path.write_text(frontmatter + resume_md, encoding="utf-8")
        render_resume_pdf(resume_md_path, resume_pdf_path, job_key)

        job.resume_path = str(resume_pdf_path)
        db.commit()

    except Exception as e:
        print(f"[generator] ERROR generating resume for {job_key}: {e}", file=sys.stderr)
        raise
    finally:
        if own_db:
            db.close()
```

- [ ] **Step 2: Add `generate_cover_for_job()` to generator.py**

Add immediately after `generate_resume_for_job()`:

```python
def generate_cover_for_job(
    job_key: str,
    db: Optional[Session] = None,
    client: Optional[anthropic.Anthropic] = None,
) -> None:
    """Generate cover letter only for a job. Updates job.cover_path and commits."""
    own_db = db is None
    if own_db:
        db = SessionLocal()
    if client is None:
        client = anthropic.Anthropic()

    try:
        job = db.query(Job).filter_by(job_key=job_key).first()
        if job is None:
            raise ValueError(f"Job not found: {job_key}")

        row = db.query(UserProfileModel).first()
        if not row:
            raise RuntimeError("No user profile found in DB.")
        data = json.loads(row.data)
        data["work_history"] = [WorkHistoryEntry(**e) for e in data.get("work_history", [])]
        data["education"] = [EducationEntry(**e) for e in data.get("education", [])]
        profile = UserProfile(**data)

        cover_tpl = db.query(Config).filter_by(key="cover_prompt_template").first()
        if not cover_tpl:
            raise RuntimeError("cover_prompt_template not seeded in config table.")

        def _cfg(key: str) -> str:
            r = db.query(Config).filter_by(key=key).first()
            return r.value if r else ""

        frontmatter = _build_frontmatter(
            profile,
            github=_cfg("resume_github"),
            linkedin=_cfg("resume_linkedin"),
            website=_cfg("resume_website"),
        )

        outputs = _OUTPUTS_DIR
        outputs.mkdir(parents=True, exist_ok=True)

        cover_md_path = outputs / f"{job_key}_cover.md"
        cover_pdf_path = outputs / f"{job_key}_cover.pdf"
        cover_md = call_claude(build_cover_prompt(job, profile, cover_tpl.value), client)
        cover_md_path.write_text(frontmatter + cover_md, encoding="utf-8")
        render_pdf(cover_md_path, cover_pdf_path, COVER_TEMPLATE_PATH)

        job.cover_path = str(cover_pdf_path)
        db.commit()

    except Exception as e:
        print(f"[generator] ERROR generating cover for {job_key}: {e}", file=sys.stderr)
        raise
    finally:
        if own_db:
            db.close()
```

- [ ] **Step 3: Commit**

```
git add generator/generator.py
git commit -m "[feat] Add generate_resume_for_job() and generate_cover_for_job()"
```

---

### Task 9: Add generate and file-serve endpoints

**Files:**
- Modify: `web/routers/jobs.py`
- Modify: `tests/web/test_jobs_api.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/web/test_jobs_api.py`:

```python
import pytest


def test_generate_resume_endpoint(client, db_session, monkeypatch):
    import web.routers.jobs as jobs_router

    _make_job(db_session, "job_genresume")

    def mock_generate_resume(job_key, db, client):
        job = db.query(Job).filter_by(job_key=job_key).first()
        job.resume_path = f"/outputs/{job_key}_resume.pdf"
        db.commit()

    monkeypatch.setattr(jobs_router, "_generate_resume_for_job", mock_generate_resume)
    monkeypatch.setattr(jobs_router, "_make_anthropic_client", lambda: None)

    resp = client.post("/api/jobs/job_genresume/generate/resume")
    assert resp.status_code == 200
    assert resp.json()["resume_path"] == "/outputs/job_genresume_resume.pdf"


def test_generate_cover_endpoint(client, db_session, monkeypatch):
    import web.routers.jobs as jobs_router

    _make_job(db_session, "job_gencover")

    def mock_generate_cover(job_key, db, client):
        job = db.query(Job).filter_by(job_key=job_key).first()
        job.cover_path = f"/outputs/{job_key}_cover.pdf"
        db.commit()

    monkeypatch.setattr(jobs_router, "_generate_cover_for_job", mock_generate_cover)
    monkeypatch.setattr(jobs_router, "_make_anthropic_client", lambda: None)

    resp = client.post("/api/jobs/job_gencover/generate/cover")
    assert resp.status_code == 200
    assert resp.json()["cover_path"] == "/outputs/job_gencover_cover.pdf"


def test_generate_resume_not_found(client):
    resp = client.post("/api/jobs/nonexistent/generate/resume")
    assert resp.status_code == 404


def test_generate_cover_not_found(client):
    resp = client.post("/api/jobs/nonexistent/generate/cover")
    assert resp.status_code == 404


def test_serve_resume_not_found(client, db_session):
    _make_job(db_session, "job_noresume")
    resp = client.get("/api/jobs/job_noresume/resume")
    assert resp.status_code == 404


def test_serve_cover_not_found(client, db_session):
    _make_job(db_session, "job_nocover")
    resp = client.get("/api/jobs/job_nocover/cover")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run — expect failures**

```
pytest tests/web/test_jobs_api.py -k "generate or serve" -v
```

Expected: all FAIL.

- [ ] **Step 3: Add imports and endpoints to `web/routers/jobs.py`**

Add imports:

```python
from pathlib import Path

from fastapi.responses import FileResponse

from generator.generator import generate_cover_for_job as _generate_cover_for_job
from generator.generator import generate_resume_for_job as _generate_resume_for_job
```

Add endpoints:

```python
@router.post("/{job_key}/generate/resume")
def generate_resume_endpoint(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        _generate_resume_for_job(job_key, db=db, client=_make_anthropic_client())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    db.refresh(job)
    return _serialize(job)


@router.post("/{job_key}/generate/cover")
def generate_cover_endpoint(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        _generate_cover_for_job(job_key, db=db, client=_make_anthropic_client())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    db.refresh(job)
    return _serialize(job)


@router.get("/{job_key}/resume")
def serve_resume(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None or not job.resume_path:
        raise HTTPException(status_code=404, detail="Resume not found")
    path = Path(job.resume_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Resume file missing")
    return FileResponse(path, media_type="application/pdf")


@router.get("/{job_key}/cover")
def serve_cover(job_key: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_key == job_key).first()
    if job is None or not job.cover_path:
        raise HTTPException(status_code=404, detail="Cover letter not found")
    path = Path(job.cover_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Cover letter file missing")
    return FileResponse(path, media_type="application/pdf")
```

- [ ] **Step 4: Run generate and serve tests**

```
pytest tests/web/test_jobs_api.py -k "generate or serve" -v
```

Expected: all pass.

- [ ] **Step 5: Run full test suite**

```
pytest -v
```

Expected: all tests pass. Fix any regressions before proceeding.

- [ ] **Step 6: Commit**

```
git add web/routers/jobs.py tests/web/test_jobs_api.py
git commit -m "[feat] Add generate/resume, generate/cover, and PDF serve endpoints"
```

---

### Task 10: Rewrite index.html

**Files:**
- Rewrite: `web/static/index.html`

No automated tests — verify manually by running the server and opening the browser.

- [ ] **Step 1: Replace `web/static/index.html` entirely**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Auto Apply</title>
  <link rel="stylesheet" href="/static/style.css" />
  <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
</head>
<body x-data="dashboard()" x-init="init()">

<nav>
  <a class="brand" href="/">Auto Apply</a>
  <a href="/" class="nav-active">Dashboard</a>
  <a href="#">Config</a>
</nav>

<main>
  <div class="toolbar">
    <span x-text="sortedJobs.length + ' jobs'"></span>
  </div>

  <table class="job-table">
    <thead>
      <tr>
        <th>Title</th>
        <th>Company</th>
        <th class="sortable" @click="setSort('final_score')">
          Score <span x-show="sortField === 'final_score'" x-text="sortDir === 'desc' ? '▼' : '▲'"></span>
        </th>
        <th>Location</th>
        <th class="sortable" @click="setSort('salary')">
          Salary <span x-show="sortField === 'salary'" x-text="sortDir === 'desc' ? '▼' : '▲'"></span>
        </th>
        <th class="sortable" @click="setSort('state')">
          Status <span x-show="sortField === 'state'" x-text="sortDir === 'desc' ? '▼' : '▲'"></span>
        </th>
      </tr>
    </thead>
    <tbody>
      <template x-for="job in sortedJobs" :key="job.job_key">
        <tr class="job-row" @click="selectJob(job)">
          <td x-text="job.title || '(no title)'"></td>
          <td x-text="job.company || ''"></td>
          <td><span :class="'score-badge ' + scoreClass(job.final_score)" x-text="pct(job.final_score)"></span></td>
          <td x-text="job.location || ''"></td>
          <td x-text="job.salary || ''"></td>
          <td><span :class="'status-badge ' + statusClass(job.state)" x-text="job.state"></span></td>
        </tr>
      </template>
    </tbody>
  </table>

  <p class="empty-msg" x-show="sortedJobs.length === 0 && !loadError" x-text="'No jobs in database.'"></p>
  <p class="empty-msg error" x-show="loadError" x-text="loadError"></p>
</main>

<!-- Overlay backdrop -->
<div class="overlay-backdrop" x-show="selectedJob !== null" @click.self="closeOverlay()">
  <div class="overlay-panel" @keydown.escape.window="closeOverlay()">
    <template x-if="selectedJob">
      <div>
        <div class="overlay-header">
          <h2 x-text="selectedJob.title || '(no title)'"></h2>
          <span :class="'status-badge ' + statusClass(selectedJob.state)" x-text="selectedJob.state"></span>
        </div>

        <div class="overlay-meta">
          <span x-text="selectedJob.company || ''"></span>
          <span :class="'score-badge ' + scoreClass(selectedJob.final_score)" x-text="pct(selectedJob.final_score)"></span>
          <span x-text="selectedJob.location || ''"></span>
          <span x-text="selectedJob.salary || ''"></span>
        </div>

        <div class="action-bar">
          <button class="btn" @click="calculateScore()">Calculate Score</button>

          <!-- Resume: Generate or View▾ dropdown -->
          <template x-if="!selectedJob.resume_path">
            <button class="btn" @click="generateResume()">Generate Resume</button>
          </template>
          <template x-if="selectedJob.resume_path">
            <div class="dropdown" x-data="{ open: false }" @click.outside="open = false">
              <button class="btn btn-dropdown" @click="open = !open">View Resume ▾</button>
              <div class="dropdown-menu" x-show="open">
                <button @click="viewResume(); open = false">View</button>
                <button @click="generateResume(); open = false">Regenerate</button>
              </div>
            </div>
          </template>

          <!-- Cover: Generate or View▾ dropdown -->
          <template x-if="!selectedJob.cover_path">
            <button class="btn" @click="generateCover()">Generate Cover Letter</button>
          </template>
          <template x-if="selectedJob.cover_path">
            <div class="dropdown" x-data="{ open: false }" @click.outside="open = false">
              <button class="btn btn-dropdown" @click="open = !open">View Cover Letter ▾</button>
              <div class="dropdown-menu" x-show="open">
                <button @click="viewCover(); open = false">View</button>
                <button @click="generateCover(); open = false">Regenerate</button>
              </div>
            </div>
          </template>

          <a class="btn" :href="selectedJob.url" target="_blank" rel="noopener noreferrer">View Posting</a>

          <button class="btn" @click="markApplied()" :disabled="selectedJob.state === 'applied'">
            Mark as Applied
          </button>

          <template x-if="!deleteConfirm">
            <button class="btn btn-danger" @click="deleteConfirm = true">Delete</button>
          </template>
          <template x-if="deleteConfirm">
            <button class="btn btn-danger-confirm" @click="deleteJob()">Confirm Delete</button>
          </template>
        </div>

        <hr class="overlay-divider" />
        <div class="overlay-description" x-html="formatDesc(selectedJob.description)"></div>
      </div>
    </template>
  </div>
</div>

<script>
function dashboard() {
  return {
    jobs: [],
    selectedJob: null,
    sortField: 'final_score',
    sortDir: 'desc',
    deleteConfirm: false,
    loadError: null,

    async init() {
      await this.loadJobs();
      document.addEventListener('click', (e) => {
        if (this.deleteConfirm && !e.target.closest('.action-bar')) {
          this.deleteConfirm = false;
        }
      });
    },

    async loadJobs() {
      try {
        const resp = await fetch('/api/jobs');
        if (!resp.ok) throw new Error('Server error');
        this.jobs = await resp.json();
      } catch {
        this.loadError = 'Failed to load jobs. Is the server running?';
      }
    },

    get sortedJobs() {
      return [...this.jobs].sort((a, b) => {
        let av = a[this.sortField];
        let bv = b[this.sortField];

        if (this.sortField === 'salary') {
          av = parseFloat(String(av || '').replace(/[^0-9.]/g, '')) || 0;
          bv = parseFloat(String(bv || '').replace(/[^0-9.]/g, '')) || 0;
        }

        const nullLast = this.sortDir === 'asc' ? Infinity : -Infinity;
        if (av == null) av = nullLast;
        if (bv == null) bv = nullLast;

        if (av < bv) return this.sortDir === 'asc' ? -1 : 1;
        if (av > bv) return this.sortDir === 'asc' ? 1 : -1;
        return 0;
      });
    },

    setSort(field) {
      if (this.sortField === field) {
        this.sortDir = this.sortDir === 'asc' ? 'desc' : 'asc';
      } else {
        this.sortField = field;
        this.sortDir = field === 'state' ? 'asc' : 'desc';
      }
    },

    selectJob(job) {
      this.selectedJob = { ...job };
      this.deleteConfirm = false;
    },

    closeOverlay() {
      this.selectedJob = null;
      this.deleteConfirm = false;
    },

    scoreClass(s) {
      if (s == null) return 'score-none';
      if (s >= 0.8) return 'score-green';
      if (s >= 0.5) return 'score-amber';
      return 'score-red';
    },

    statusClass(state) {
      const map = { pending: 'status-pending', applied: 'status-applied', rejected: 'status-rejected', failed: 'status-failed' };
      return map[state] || 'status-pending';
    },

    pct(v) {
      return v != null ? Math.round(v * 100) + '%' : '—';
    },

    formatDesc(desc) {
      if (!desc) return '<em>No description available.</em>';
      return String(desc)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/\n/g, '<br>');
    },

    _updateJob(updated) {
      const idx = this.jobs.findIndex(j => j.job_key === updated.job_key);
      if (idx !== -1) this.jobs[idx] = updated;
      this.selectedJob = { ...updated };
    },

    async _post(url) {
      const resp = await fetch(url, { method: 'POST' });
      if (!resp.ok) throw new Error(await resp.text());
      return resp.json();
    },

    async calculateScore() {
      try {
        this._updateJob(await this._post(`/api/jobs/${encodeURIComponent(this.selectedJob.job_key)}/score`));
      } catch { alert('Failed to calculate score.'); }
    },

    async generateResume() {
      try {
        this._updateJob(await this._post(`/api/jobs/${encodeURIComponent(this.selectedJob.job_key)}/generate/resume`));
      } catch { alert('Failed to generate resume.'); }
    },

    async generateCover() {
      try {
        this._updateJob(await this._post(`/api/jobs/${encodeURIComponent(this.selectedJob.job_key)}/generate/cover`));
      } catch { alert('Failed to generate cover letter.'); }
    },

    viewResume() {
      window.open(`/api/jobs/${encodeURIComponent(this.selectedJob.job_key)}/resume`, '_blank');
    },

    viewCover() {
      window.open(`/api/jobs/${encodeURIComponent(this.selectedJob.job_key)}/cover`, '_blank');
    },

    async markApplied() {
      try {
        const resp = await fetch(`/api/jobs/${encodeURIComponent(this.selectedJob.job_key)}/state`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ state: 'applied' }),
        });
        if (!resp.ok) throw new Error();
        this._updateJob(await resp.json());
      } catch { alert('Failed to mark as applied.'); }
    },

    async deleteJob() {
      const key = this.selectedJob.job_key;
      try {
        const resp = await fetch(`/api/jobs/${encodeURIComponent(key)}`, { method: 'DELETE' });
        if (!resp.ok) throw new Error();
        this.jobs = this.jobs.filter(j => j.job_key !== key);
        this.closeOverlay();
      } catch { alert('Failed to delete job.'); }
    },
  };
}
</script>

</body>
</html>
```

- [ ] **Step 2: Start the server and verify manually**

```
uvicorn web.main:app --reload
```

Open `http://localhost:8000` and verify:
- Job table loads with all jobs
- Clicking a column header sorts; clicking again reverses
- Clicking a row opens the overlay
- Overlay shows correct job data
- Clicking outside the overlay closes it
- Pressing Escape closes it

- [ ] **Step 3: Commit**

```
git add web/static/index.html
git commit -m "[feat] Rewrite dashboard as Alpine.js table with details overlay"
```

---

### Task 11: Rewrite style.css

**Files:**
- Rewrite: `web/static/style.css`

- [ ] **Step 1: Replace `web/static/style.css` entirely**

```css
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: system-ui, -apple-system, sans-serif;
  font-size: 14px;
  background: #f5f5f5;
  color: #1a1a1a;
}

/* Nav */
nav {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  padding: 0 1.5rem;
  height: 48px;
  background: #1a1a1a;
  color: #fff;
}
nav a { color: #ccc; text-decoration: none; font-size: 14px; }
nav a:hover { color: #fff; }
nav a.nav-active { color: #fff; font-weight: 600; }
nav .brand { font-weight: 700; font-size: 15px; color: #fff; margin-right: auto; }

/* Main */
main { padding: 1.5rem; }
.toolbar { margin-bottom: 0.75rem; color: #555; font-size: 13px; }
.empty-msg { color: #666; padding: 1rem 0; }
.empty-msg.error { color: #c00; }

/* Table */
.job-table {
  width: 100%;
  border-collapse: collapse;
  background: #fff;
  border-radius: 6px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}
.job-table th {
  text-align: left;
  padding: 10px 12px;
  background: #f0f0f0;
  font-weight: 600;
  font-size: 13px;
  border-bottom: 1px solid #e0e0e0;
  user-select: none;
}
.job-table th.sortable { cursor: pointer; }
.job-table th.sortable:hover { background: #e4e4e4; }
.job-table td {
  padding: 9px 12px;
  border-bottom: 1px solid #f0f0f0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 240px;
}
.job-row { cursor: pointer; transition: background 0.1s; }
.job-row:hover { background: #fafafa; }
.job-row:last-child td { border-bottom: none; }

/* Score badge */
.score-badge {
  display: inline-block;
  padding: 2px 7px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
}
.score-green { background: #d4edda; color: #155724; }
.score-amber { background: #fff3cd; color: #856404; }
.score-red   { background: #f8d7da; color: #721c24; }
.score-none  { background: #e9ecef; color: #555; }

/* Status badge */
.status-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  text-transform: capitalize;
}
.status-pending  { background: #e9ecef; color: #555; }
.status-applied  { background: #d4edda; color: #155724; }
.status-rejected { background: #f8d7da; color: #721c24; }
.status-failed   { background: #ffe5d0; color: #7d3c05; }

/* Overlay backdrop */
.overlay-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.45);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 80px;
  z-index: 100;
}

/* Overlay panel */
.overlay-panel {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.18);
  width: min(680px, 92vw);
  max-height: 80vh;
  overflow-y: auto;
  padding: 1.5rem;
}
.overlay-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 0.5rem;
}
.overlay-header h2 { font-size: 17px; font-weight: 700; }
.overlay-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: center;
  font-size: 13px;
  color: #555;
  margin-bottom: 1rem;
}

/* Action bar */
.action-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 1rem;
}
.btn {
  display: inline-block;
  padding: 6px 12px;
  background: #e9ecef;
  color: #1a1a1a;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  text-decoration: none;
  line-height: 1.4;
}
.btn:hover { background: #dee2e6; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-danger { background: #f8d7da; color: #721c24; }
.btn-danger:hover { background: #f1c0c5; }
.btn-danger-confirm { background: #dc3545; color: #fff; }
.btn-danger-confirm:hover { background: #c82333; }

/* Dropdown */
.dropdown { position: relative; display: inline-block; }
.dropdown-menu {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  background: #fff;
  border: 1px solid #ddd;
  border-radius: 4px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  min-width: 120px;
  z-index: 200;
}
.dropdown-menu button {
  display: block;
  width: 100%;
  padding: 8px 12px;
  text-align: left;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 13px;
}
.dropdown-menu button:hover { background: #f5f5f5; }

/* Overlay description */
.overlay-divider { border: none; border-top: 1px solid #e9ecef; margin-bottom: 1rem; }
.overlay-description {
  font-size: 13px;
  line-height: 1.6;
  color: #333;
  max-height: 300px;
  overflow-y: auto;
}
```

- [ ] **Step 2: Verify in browser**

With the server running, check:
- Table looks clean, headers readable
- Score and status badges are colored correctly
- Row hover highlights
- Overlay is centered with backdrop
- Action bar buttons are styled
- Dropdown menus position correctly below button
- Description is scrollable if long

- [ ] **Step 3: Commit**

```
git add web/static/style.css
git commit -m "[feat] Add dashboard styles: table, overlay, badges, action bar"
```

---

### Task 12: Create web/CONTEXT.md

**Files:**
- Create: `web/CONTEXT.md`

- [ ] **Step 1: Write the file**

```markdown
# Web Context

FastAPI backend + Alpine.js v3 frontend. Single-page dashboard at `/`.

## Architecture

- `main.py` — FastAPI app; mounts static files; includes routers
- `routers/jobs.py` — all job endpoints (GET, DELETE, PATCH state, POST score, POST generate/resume, POST generate/cover, GET resume, GET cover)
- `static/index.html` — Alpine.js dashboard; all state managed client-side in `dashboard()` component
- `static/style.css` — table, overlay, badges, dropdowns

## Running

```
uvicorn web.main:app --reload
```

## Known Issues

- Generation endpoints are synchronous — resume/cover generation blocks the request for 30–60 seconds while Claude and pandoc run. For a single-user local tool this is acceptable.
- Salary sort is lexicographic when salary contains non-numeric characters (e.g., "$120k–$150k"). Values without parseable numbers sort as 0.
- Alpine.js loaded from CDN — requires internet access.

## Future Work

- Config page (`/config`) for editing weights, thresholds, and user profile
- Polling or WebSocket feedback during long-running generation requests
- Filter by status in addition to sorting
- Grouping rows by job title
- Clustering by location
```

- [ ] **Step 2: Commit**

```
git add web/CONTEXT.md
git commit -m "[docs] Add web/CONTEXT.md"
```

---

### Final Verification

- [ ] **Run full test suite**

```
pytest -v
```

Expected: all tests pass.

- [ ] **Manual smoke test**

```
uvicorn web.main:app --reload
```

Verify end-to-end:
1. Dashboard loads and shows all jobs
2. Sorting by Score, Salary, Status works (click header, click again to reverse)
3. Click a row → overlay opens with correct data
4. Status badge is colored correctly
5. Score badge is colored correctly
6. "Calculate Score" button calls POST /score and updates the overlay
7. "Generate Resume" button calls POST /generate/resume; button becomes "View Resume ▾" after success
8. "View Resume ▾" dropdown shows View and Regenerate
9. "View Posting" opens job URL in new tab
10. "Mark as Applied" transitions status to applied; button becomes disabled
11. "Delete" → "Confirm Delete" → job disappears from table
12. Clicking outside overlay closes it; Escape closes it
