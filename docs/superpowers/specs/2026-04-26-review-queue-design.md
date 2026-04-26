# Review Queue Design Spec

**Stage 3a of the auto-apply pipeline.** A local FastAPI web app that lets the user review `PENDING_REVIEW` jobs and approve or reject them with one click.

This sub-project covers: the FastAPI app skeleton, the Review Queue page, and the jobs API. Dashboard, Config Panel, and Application Review are separate sub-projects.

---

## Goal

Display `PENDING_REVIEW` jobs as cards sorted by final score. One click approves or rejects each job, transitioning its state in the DB. Approving a job does **not** trigger generation in this phase — that integration happens when Stage 4 (Generator) is built.

---

## Architecture

FastAPI app with a REST API and a static HTML/JS frontend. No templating engine. No JS framework. No build step.

```
web/
├── __init__.py
├── main.py              # FastAPI app, mounts static files, includes routers
├── routers/
│   ├── __init__.py
│   └── jobs.py          # GET /api/jobs, PATCH /api/jobs/{job_key}/state
└── static/
    ├── index.html       # App shell + Review Queue page (vanilla JS)
    └── style.css        # Layout, card styles, score colors, fade animation

tests/web/
├── __init__.py
└── test_jobs_api.py
```

`main.py` creates the FastAPI app, mounts `static/` at `/static`, serves `index.html` at `/`, and includes the jobs router. DB sessions come from `db.database.get_db` — the same dependency used throughout the project.

Run with:
```bash
uvicorn web.main:app --reload
```

---

## API

### `GET /api/jobs`

Query params:
- `state` (optional, default: `pending_review`) — filter jobs by `JobState` value

Response: JSON array of job objects, sorted by `final_score` descending.

Each job object:
```json
{
  "job_key": "indeed_12345",
  "title": "Senior Software Engineer",
  "company": "Acme Corp",
  "location": "Remote · New York, NY",
  "salary": "$140,000–$170,000",
  "desirability_score": 0.90,
  "fit_score": 0.78,
  "final_score": 0.84,
  "score_justification": {
    "desirability": "Salary well above target, fully remote, strong title match.",
    "fit": "Python and SQL match well. Requires 5+ years — candidate has 4."
  }
}
```

`score_justification` is parsed from the DB's JSON string into an object. Returns `[]` if no jobs match.

### `PATCH /api/jobs/{job_key}/state`

Body:
```json
{ "state": "approved" }
```

Valid target states: `approved`, `rejected`. Any other value returns 400.

Returns:
- `200` — updated job object (same shape as GET)
- `400` — invalid state value
- `404` — job_key not found

---

## Frontend

### Nav Bar

Top nav bar with:
- App name: "Auto Apply"
- Links: Dashboard · Review Queue · Config (Dashboard and Config are placeholder `<a>` tags — no pages yet)
- Badge on Review Queue showing count of `pending_review` jobs (fetched on load)

### Review Queue Page

On load: `GET /api/jobs?state=pending_review` → render one card per job.

**Card layout (top to bottom):**
1. Approve / Reject buttons (full width, side by side)
2. Job title (large, bold) + final score (right-aligned, color-coded)
3. Company · location (secondary text)
4. Salary · employment type · posted date
5. Desirability score pill + Fit score pill
6. Justification block (desirability line, fit line)

**Score color coding:**
- `final_score >= 0.8` → green
- `0.5 <= final_score < 0.8` → amber
- `final_score < 0.5` → red

Cards are sorted by `final_score` descending (API handles ordering).

### Card Interaction

1. User clicks Approve or Reject
2. Both buttons disable immediately (prevent double-click)
3. `PATCH /api/jobs/{job_key}/state` is called
4. On success: card briefly shows "Approved ✓" or "Rejected ✗", then fades out and is removed from the DOM
5. Nav badge count decrements by 1
6. On failure: buttons re-enable, small error message appears on the card ("Action failed — try again")
7. 404 response treated as success (job already gone — fade out)

---

## Error Handling

| Scenario | Behavior |
|---|---|
| `GET /api/jobs` network failure | Show inline message: "Failed to load jobs. Is the server running?" |
| `PATCH` network failure | Re-enable buttons, show on-card error: "Action failed — try again" |
| `PATCH` returns 404 | Treat as success — card fades out |
| `PATCH` returns 400 | Re-enable buttons, show on-card error |

---

## Testing

`tests/web/test_jobs_api.py` uses FastAPI's `TestClient` with an in-memory SQLite DB.

**GET /api/jobs tests:**
- `test_get_jobs_returns_pending_review` — insert 2 `pending_review` + 1 `approved` job, assert only 2 returned
- `test_get_jobs_sorted_by_score` — insert jobs with varying scores, assert descending order
- `test_get_jobs_empty` — no jobs in DB, assert `[]`
- `test_get_jobs_justification_parsed` — assert `score_justification` is a dict with `desirability` and `fit` keys (not a raw string)

**PATCH /api/jobs/{job_key}/state tests:**
- `test_patch_approve` — assert state transitions to `approved`, response contains updated job
- `test_patch_reject` — assert state transitions to `rejected`
- `test_patch_invalid_state` — assert 400 on disallowed target state
- `test_patch_not_found` — assert 404 for unknown `job_key`

No browser/JS tests in this phase.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `web/__init__.py` | Create | Package marker |
| `web/main.py` | Create | FastAPI app, static mount, router registration, serves index.html at `/` |
| `web/routers/__init__.py` | Create | Package marker |
| `web/routers/jobs.py` | Create | `GET /api/jobs` and `PATCH /api/jobs/{job_key}/state` |
| `web/static/index.html` | Create | Nav bar + Review Queue page with vanilla JS |
| `web/static/style.css` | Create | Card layout, score colors, fade animation |
| `tests/web/__init__.py` | Create | Package marker |
| `tests/web/test_jobs_api.py` | Create | All API tests |
