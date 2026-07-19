# ATS Detection & Apply-URL Resolution — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect, per LinkedIn/Indeed-scraped job, whether it is an in-platform "easy apply" or an external application, resolve the external apply URL, classify the hosting ATS server-side, and surface a chip in the review queue.

**Architecture:** The extension flags `easy_apply` at scrape time (DOM read) and, only after a successful `stage-job`, resolves external jobs by opening the apply link in a background tab, letting redirects settle, and PATCHing the final URL back. The server classifies the URL by domain (`core/ats.py`) and persists five new nullable columns on `jobs`. A single React chip renders the result.

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy / Alembic (Postgres prod, SQLite tests via `create_all`); pytest; MV3 browser extension (vanilla JS, `xb.*` shim); React + Vite + Vitest + Tailwind.

## Global Constraints

- **Scope:** LinkedIn + Indeed extension jobs only. API scrapers (Remotive/RemoteOK) are untouched.
- **Tenant safety:** every job fetch/PATCH resolves `(profile_id, job_key)` via `Job.get(job_key, db, profile_id=profile_id)` — never `job_key` alone.
- **New columns are nullable** so existing rows are unaffected; `ats_type = null` means "external, unresolved"; `ats_type = "easy_apply"` is set server-side when `easy_apply` is true.
- **Migrations:** production is **Alembic-only** (`init_db()` runs `alembic upgrade head`). Add columns to the model AND write an Alembic migration. Do NOT hand-write `ALTER TABLE` in `database.py`. Tests use `Base.metadata.create_all`, so they pick up model columns automatically; `tests/db/test_alembic_parity.py` gates that model and migration agree.
- **Recognized ATS set:** `greenhouse`, `lever`, `ashby`, `workday`, `icims`, `taleo`, `smartrecruiters`, `jobvite`, `bamboohr`; else `other`. Plus `easy_apply` (in-platform) and `null` (unresolved).
- **Commit format:** `[type] Imperative subject` (`feat`/`fix`/`refactor`/`docs`/`test`/`chore`). No Claude attribution.
- **Python style:** type hints, Google-style docstrings, black.

---

## File Structure

- **Create** `core/ats.py` — pure domain→ATS classifier. One responsibility: URL → `(ats_type, hostname)`.
- **Create** `tests/core/test_ats.py` — classifier unit tests.
- **Modify** `core/job.py` — 5 new `Job` columns; add them to `from_scraped` (from ScrapedJob) and `serialize`.
- **Modify** `scraper/base.py` — `ScrapedJob` gains `easy_apply`, `apply_url_raw`.
- **Create** `alembic/versions/aa12atsdetect01_add_ats_columns.py` — the migration.
- **Modify** `web/routers/scraper.py` — `StageJobRequest` + `stage_job` persist the new fields and set `easy_apply` → `ats_type`; new `PATCH /api/scraper/jobs/{job_key}/ats-resolution`.
- **Create** `tests/web/test_ats_resolution.py` — endpoint + stage-job field tests.
- **Modify** `browser-extension/manifest.json` — add `"tabs"` permission.
- **Modify** `browser-extension/content/linkedin.js`, `content/indeed.js` — add `getApplyInfo()`.
- **Modify** `browser-extension/content/injector.js` — include apply info in payload; enqueue resolution on success.
- **Modify** `browser-extension/background/service_worker.js` — resolution queue.
- **Create** `react-dashboard/src/components/shared/AtsChip.jsx` + `AtsChip.test.jsx` — chip.
- **Modify** `react-dashboard/src/components/shared/JobCard.jsx` — render `<AtsChip>`.
- **Modify** `browser-extension/CONTEXT.md`, `db/CONTEXT.md`, `web/CONTEXT.md` — document the additions (final task).

---

## Task 1: ATS classifier (`core/ats.py`)

**Files:**
- Create: `core/ats.py`
- Test: `tests/core/test_ats.py`

**Interfaces:**
- Produces: `classify_ats(url: str) -> tuple[str, str]` returning `(ats_type, hostname)`. `ats_type` is one of the recognized set or `"other"`; malformed/empty URL → `("other", "")`. Never raises.

- [ ] **Step 1: Write the failing tests**

```python
# tests/core/test_ats.py
import pytest
from core.ats import classify_ats


@pytest.mark.parametrize("url,expected_type,expected_host", [
    ("https://boards.greenhouse.io/acme/jobs/123", "greenhouse", "boards.greenhouse.io"),
    ("https://acme.greenhouse.io/jobs/123", "greenhouse", "acme.greenhouse.io"),
    ("https://jobs.lever.co/acme/abc-def", "lever", "jobs.lever.co"),
    ("https://jobs.ashbyhq.com/acme/uuid", "ashby", "jobs.ashbyhq.com"),
    ("https://acme.wd1.myworkdayjobs.com/careers/job/123", "workday", "acme.wd1.myworkdayjobs.com"),
    ("https://acme.workday.com/en-US/careers", "workday", "acme.workday.com"),
    ("https://careers-acme.icims.com/jobs/456/apply", "icims", "careers-acme.icims.com"),
    ("https://acme.taleo.net/careersection/2/jobapply.ftl", "taleo", "acme.taleo.net"),
    ("https://jobs.smartrecruiters.com/Acme/12345", "smartrecruiters", "jobs.smartrecruiters.com"),
    ("https://jobs.jobvite.com/acme/job/xyz", "jobvite", "jobs.jobvite.com"),
    ("https://acme.bamboohr.com/careers/42", "bamboohr", "acme.bamboohr.com"),
    ("https://careers.acmecorp.com/apply/9", "other", "careers.acmecorp.com"),
    ("HTTPS://Jobs.Lever.CO/acme/x", "lever", "jobs.lever.co"),  # case-insensitive host
    ("", "other", ""),
    ("not a url", "other", ""),
    ("javascript:void(0)", "other", ""),
])
def test_classify_ats(url, expected_type, expected_host):
    assert classify_ats(url) == (expected_type, expected_host)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/core/test_ats.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.ats'`.

- [ ] **Step 3: Implement `core/ats.py`**

```python
"""Classify a resolved job-application URL to its hosting ATS by domain.

Pure, no network, no LLM. The domain-signature table below is the single
source of truth for the recognized-ATS set (see the ATS-detection spec).
"""
from __future__ import annotations

from urllib.parse import urlparse

# Ordered list of (host-suffix, ats_type). First matching suffix wins.
# Suffixes match the END of the hostname, so "greenhouse.io" catches both
# "boards.greenhouse.io" and "acme.greenhouse.io".
_ATS_SUFFIXES: list[tuple[str, str]] = [
    ("greenhouse.io", "greenhouse"),
    ("lever.co", "lever"),
    ("ashbyhq.com", "ashby"),
    ("myworkdayjobs.com", "workday"),
    ("workday.com", "workday"),
    ("icims.com", "icims"),
    ("taleo.net", "taleo"),
    ("smartrecruiters.com", "smartrecruiters"),
    ("jobvite.com", "jobvite"),
    ("bamboohr.com", "bamboohr"),
]


def classify_ats(url: str) -> tuple[str, str]:
    """Return (ats_type, hostname) for a resolved apply URL.

    Args:
        url: The final apply-destination URL after redirects.

    Returns:
        A tuple of the ATS type (a recognized key or ``"other"``) and the
        lowercased hostname. Malformed or empty input yields ``("other", "")``.
    """
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return ("other", "")
    if not host:
        return ("other", "")
    for suffix, ats_type in _ATS_SUFFIXES:
        if host == suffix or host.endswith("." + suffix):
            return (ats_type, host)
    return ("other", host)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/core/test_ats.py -v`
Expected: PASS (all parametrized cases).

- [ ] **Step 5: Commit**

```bash
git add core/ats.py tests/core/test_ats.py
git commit -m "[feat] Add domain-based ATS classifier (core/ats.py)"
```

---

## Task 2: Job columns, serialize, and migration

**Files:**
- Modify: `core/job.py` (columns near line 266; `from_scraped` ~line 328; `serialize` ~line 1353)
- Modify: `scraper/base.py` (`ScrapedJob` dataclass, line 23)
- Create: `alembic/versions/aa12atsdetect01_add_ats_columns.py`
- Test: `tests/core/test_ats_columns.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `Job.easy_apply` (Boolean), `Job.apply_url_raw` (String), `Job.apply_url_resolved` (String), `Job.ats_type` (String), `Job.ats_domain` (String), all nullable. `ScrapedJob.easy_apply: bool | None = None`, `ScrapedJob.apply_url_raw: str = ""`. `serialize()` includes keys `easy_apply`, `apply_url_raw`, `apply_url_resolved`, `ats_type`, `ats_domain`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_ats_columns.py
from scraper.base import ScrapedJob
from core.job import Job


def test_from_scraped_carries_apply_fields():
    sj = ScrapedJob(
        source="linkedin", job_key="k1", title="T", company="C",
        url="https://x/1", description="d", easy_apply=False,
        apply_url_raw="https://apply/1",
    )
    job = Job.from_scraped(sj)
    assert job.easy_apply is False
    assert job.apply_url_raw == "https://apply/1"


def test_serialize_exposes_ats_fields():
    job = Job.from_scraped(ScrapedJob(
        source="linkedin", job_key="k2", title="T", company="C",
        url="https://x/2", description="d",
    ))
    job.ats_type = "greenhouse"
    job.ats_domain = "boards.greenhouse.io"
    data = job.serialize()
    for key in ("easy_apply", "apply_url_raw", "apply_url_resolved", "ats_type", "ats_domain"):
        assert key in data
    assert data["ats_type"] == "greenhouse"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_ats_columns.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'easy_apply'` (ScrapedJob) / missing column.

- [ ] **Step 3a: Add `ScrapedJob` fields** in `scraper/base.py` after `posted_at` (line 35):

```python
    posted_at: str = ""
    easy_apply: Optional[bool] = None
    apply_url_raw: str = ""
```

(`Optional` is already imported in `scraper/base.py`.)

- [ ] **Step 3b: Add `Job` columns** in `core/job.py` immediately after `state = Column(...)` (line 266):

```python
    # ── Apply / ATS detection ───────────────────────────────────────────────────
    easy_apply = Column(Boolean)          # True=in-platform, False=external, None=unknown
    apply_url_raw = Column(String)        # apply link seen in the card DOM (pre-redirect)
    apply_url_resolved = Column(String)   # final URL after following redirects
    ats_type = Column(String)             # classifier output; None=external-unresolved
    ats_domain = Column(String)           # resolved hostname (kept for `other`)
```

- [ ] **Step 3c: Map fields in `from_scraped`** — add to the `cls(...)` call in `core/job.py` (before `state=...`, line 339):

```python
            easy_apply=getattr(scraped, "easy_apply", None),
            apply_url_raw=getattr(scraped, "apply_url_raw", "") or "",
```

- [ ] **Step 3d: Expose in `serialize`** — add to the returned dict in `core/job.py` (e.g. after the `"remote": self.remote,` line):

```python
            "easy_apply": self.easy_apply,
            "apply_url_raw": self.apply_url_raw or "",
            "apply_url_resolved": self.apply_url_resolved or "",
            "ats_type": self.ats_type,
            "ats_domain": self.ats_domain or "",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_ats_columns.py -v`
Expected: PASS.

- [ ] **Step 5: Write the Alembic migration**

First find the current head revision:

Run: `python -m alembic heads`
Expected: prints one revision id (the down_revision for the new migration). Use that value in place of `<HEAD_REV>` below.

Create `alembic/versions/aa12atsdetect01_add_ats_columns.py`:

```python
"""add ats detection columns to jobs

Revision ID: aa12atsdetect01
Revises: <HEAD_REV>
Create Date: 2026-07-19
"""
from alembic import op
import sqlalchemy as sa

revision = "aa12atsdetect01"
down_revision = "<HEAD_REV>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("easy_apply", sa.Boolean(), nullable=True))
    op.add_column("jobs", sa.Column("apply_url_raw", sa.String(), nullable=True))
    op.add_column("jobs", sa.Column("apply_url_resolved", sa.String(), nullable=True))
    op.add_column("jobs", sa.Column("ats_type", sa.String(), nullable=True))
    op.add_column("jobs", sa.Column("ats_domain", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "ats_domain")
    op.drop_column("jobs", "ats_type")
    op.drop_column("jobs", "apply_url_resolved")
    op.drop_column("jobs", "apply_url_raw")
    op.drop_column("jobs", "easy_apply")
```

- [ ] **Step 6: Verify migration applies and parity holds**

Run: `python -m alembic upgrade head`
Expected: applies `aa12atsdetect01` with no error.

Run: `python -m pytest tests/db/test_alembic_parity.py -v`
Expected: PASS (model and migrated schema match).

- [ ] **Step 7: Commit**

```bash
git add core/job.py scraper/base.py alembic/versions/aa12atsdetect01_add_ats_columns.py tests/core/test_ats_columns.py
git commit -m "[feat] Add ATS-detection columns to jobs and migration"
```

---

## Task 3: Persist apply fields through stage-job

**Files:**
- Modify: `web/routers/scraper.py` (`StageJobRequest` line 29; `stage_job` line 44)
- Test: `tests/web/test_ats_resolution.py` (create; first test only)

**Interfaces:**
- Consumes: `Job.easy_apply`, `Job.ats_type` (Task 2).
- Produces: `stage-job` accepts `easy_apply: bool | None` and `apply_url_raw: str` in the body; when `easy_apply` is true, the stored job has `ats_type == "easy_apply"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_ats_resolution.py
from core.job import Job

# Assumes the project's standard FastAPI test client + in-memory DB fixture.
# Follow the pattern in tests/web/test_profile_api.py (client, db_session,
# get_db override, and the bearer/session auth stub used there).

def test_stage_job_sets_easy_apply_ats_type(client, db_session):
    resp = client.post("/api/scraper/stage-job", json={
        "source": "linkedin", "job_key": "ea1", "title": "T",
        "company": "C", "url": "https://li/ea1", "description": "d",
        "easy_apply": True,
    })
    assert resp.status_code == 200
    job = Job.get("ea1", db_session, profile_id=1)
    assert job.easy_apply is True
    assert job.ats_type == "easy_apply"


def test_stage_job_external_leaves_ats_type_null(client, db_session):
    resp = client.post("/api/scraper/stage-job", json={
        "source": "indeed", "job_key": "ex1", "title": "T",
        "company": "C", "url": "https://in/ex1", "description": "d",
        "easy_apply": False, "apply_url_raw": "https://apply/ex1",
    })
    assert resp.status_code == 200
    job = Job.get("ex1", db_session, profile_id=1)
    assert job.easy_apply is False
    assert job.ats_type is None
    assert job.apply_url_raw == "https://apply/ex1"
```

> Note: use whatever client/db fixtures the existing `tests/web/` files use (check `tests/web/conftest.py` and `tests/web/test_profile_api.py`). The default test profile id in this suite is `1`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/web/test_ats_resolution.py -v`
Expected: FAIL — `easy_apply`/`apply_url_raw` rejected or not persisted; `ats_type` not set.

- [ ] **Step 3a: Extend `StageJobRequest`** in `web/routers/scraper.py` (after `scraped_at`, line 40):

```python
    easy_apply: bool | None = None
    apply_url_raw: str = ""
```

- [ ] **Step 3b: Pass the fields into `ScrapedJob`** inside `stage_job` (line 62 block) and set `ats_type`. Replace the `scraped = ScrapedJob(...)` construction and the insert loop:

```python
    scraped = ScrapedJob(
        source=body.source,
        job_key=body.job_key,
        title=body.title,
        company=body.company,
        url=body.url,
        description=body.description,
        location=body.location,
        salary=body.salary,
        remote=body.remote,
        posted_at=body.posted_at,
        easy_apply=body.easy_apply,
        apply_url_raw=body.apply_url_raw,
    )
    inserted_jobs = Job.save_batch_returning([scraped], db, profile_id)
    status = "staged" if inserted_jobs else "duplicate"
    for job in inserted_jobs:
        if job.easy_apply:
            job.ats_type = "easy_apply"
            db.commit()
        job.intake()
```

(Leave the existing `_sse_send` + `run_pipeline` thread lines that follow unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/web/test_ats_resolution.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add web/routers/scraper.py tests/web/test_ats_resolution.py
git commit -m "[feat] Persist easy_apply/apply_url through stage-job"
```

---

## Task 4: ATS-resolution PATCH endpoint

**Files:**
- Modify: `web/routers/scraper.py` (add endpoint + request model; it already imports `bearer_or_session_profile`, `Job`, `HTTPException`, `_sse_send`)
- Test: `tests/web/test_ats_resolution.py` (append)

**Interfaces:**
- Consumes: `classify_ats` (Task 1); `Job.get`, `Job.ats_type/ats_domain/apply_url_resolved` (Task 2); `stage-job` (Task 3) to create rows under test.
- Produces: `PATCH /api/scraper/jobs/{job_key}/ats-resolution`, body `{apply_url_resolved: str}`, bearer-or-session authed, tenant-scoped. Classifies, persists, SSE-broadcasts, returns the updated fields. 404 if the job does not exist for the caller's profile.

- [ ] **Step 1: Write the failing tests** (append to `tests/web/test_ats_resolution.py`)

```python
def _stage_external(client, job_key):
    return client.post("/api/scraper/stage-job", json={
        "source": "linkedin", "job_key": job_key, "title": "T",
        "company": "C", "url": f"https://li/{job_key}", "description": "d",
        "easy_apply": False, "apply_url_raw": "https://li/redir",
    })


def test_ats_resolution_classifies_and_persists(client, db_session):
    _stage_external(client, "r1")
    resp = client.patch("/api/scraper/jobs/r1/ats-resolution", json={
        "apply_url_resolved": "https://boards.greenhouse.io/acme/jobs/9",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["ats_type"] == "greenhouse"
    assert body["ats_domain"] == "boards.greenhouse.io"
    job = Job.get("r1", db_session, profile_id=1)
    assert job.ats_type == "greenhouse"
    assert job.apply_url_resolved == "https://boards.greenhouse.io/acme/jobs/9"


def test_ats_resolution_unknown_job_404(client):
    resp = client.patch("/api/scraper/jobs/nope/ats-resolution", json={
        "apply_url_resolved": "https://x/1",
    })
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/web/test_ats_resolution.py -v`
Expected: FAIL — 404/405 (route missing).

- [ ] **Step 3: Add the endpoint** to `web/routers/scraper.py` (add `from core.ats import classify_ats` to the imports, then append):

```python
class AtsResolutionRequest(BaseModel):
    apply_url_resolved: str


@router.patch("/jobs/{job_key}/ats-resolution")
def resolve_ats(
    job_key: str,
    body: AtsResolutionRequest,
    db: Session = Depends(get_db),
    profile_id: int = Depends(bearer_or_session_profile),
) -> dict[str, Any]:
    """Classify a resolved apply URL and store the ATS result on the job.

    Called by the browser extension after it follows an external job's apply
    redirect to its final destination.

    Args:
        job_key: The job to update.
        body: The resolved apply URL.
        db: SQLAlchemy session.
        profile_id: Owning tenant's profile id (bearer or session).

    Returns:
        Dict with the updated ats_type, ats_domain, and apply_url_resolved.
    """
    job = Job.get(job_key, db, profile_id=profile_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    ats_type, host = classify_ats(body.apply_url_resolved)
    job.apply_url_resolved = body.apply_url_resolved
    job.ats_type = ats_type
    job.ats_domain = host
    db.commit()
    db.refresh(job)
    try:
        _sse_send("job", job.serialize(), profile_id=profile_id)
    except Exception:
        logger.exception("[resolve_ats] broadcast failed for %s", job_key)
    return {
        "job_key": job_key,
        "ats_type": job.ats_type,
        "ats_domain": job.ats_domain,
        "apply_url_resolved": job.apply_url_resolved,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/web/test_ats_resolution.py -v`
Expected: PASS (all four tests in the file).

- [ ] **Step 5: Commit**

```bash
git add web/routers/scraper.py tests/web/test_ats_resolution.py
git commit -m "[feat] Add ATS-resolution PATCH endpoint"
```

---

## Task 5: Extension DOM apply-info + manifest permission

**Files:**
- Modify: `browser-extension/manifest.json` (permissions array)
- Modify: `browser-extension/content/linkedin.js`, `browser-extension/content/indeed.js` (add `getApplyInfo`)
- Modify: `browser-extension/content/injector.js` (include apply info in the scrape payload)

**Interfaces:**
- Consumes: `stage-job` now accepts `easy_apply`/`apply_url_raw` (Task 3).
- Produces: each source module exposes `getApplyInfo()` → `{ easy_apply: boolean, apply_url_raw: string }`. `injector.js` merges this into the `SCRAPE_JOB` payload. Manifest grants `"tabs"`.

> No automated tests — extension DOM code is validated by manual smoke test, consistent with the existing extension testing posture. Steps below end in a manual verification, then a commit.

- [ ] **Step 1: Add `"tabs"` permission** in `browser-extension/manifest.json` — add `"tabs"` to the existing `"permissions"` array (keep `"storage"` etc.).

- [ ] **Step 2: Add `getApplyInfo()` to `content/linkedin.js`**

LinkedIn shows a native **Easy Apply** button (in-platform) or an **Apply** button that opens the employer site in a new tab. Detection is text-based (classes are hashed — see CONTEXT):

```javascript
// Returns {easy_apply, apply_url_raw} for the currently open job detail pane.
function getApplyInfo() {
  const buttons = Array.from(document.querySelectorAll('button, a'));
  const easyBtn = buttons.find(b => /easy apply/i.test(b.textContent || ''));
  if (easyBtn) return { easy_apply: true, apply_url_raw: '' };
  const applyBtn = buttons.find(b => {
    const t = (b.textContent || '').trim();
    return /^apply\b/i.test(t) && !/easy apply/i.test(t);
  });
  const href = applyBtn && applyBtn.tagName === 'A' ? applyBtn.href : '';
  return { easy_apply: applyBtn ? false : null, apply_url_raw: href || '' };
}
```

Attach it to the same object/namespace the module already exports (mirror how `getJobData`/`getDescription` are exposed in this file).

- [ ] **Step 3: Add `getApplyInfo()` to `content/indeed.js`**

Indeed shows "Apply now" (Indeed-hosted) vs. "Apply on company site" (external):

```javascript
function getApplyInfo() {
  const buttons = Array.from(document.querySelectorAll('button, a'));
  const companySite = buttons.find(b => /apply on company site/i.test(b.textContent || ''));
  if (companySite) {
    const href = companySite.tagName === 'A' ? companySite.href : '';
    return { easy_apply: false, apply_url_raw: href || '' };
  }
  const applyNow = buttons.find(b => /apply now|apply\b/i.test(b.textContent || ''));
  return { easy_apply: applyNow ? true : null, apply_url_raw: '' };
}
```

Attach it the same way as in `linkedin.js`.

- [ ] **Step 4: Merge apply info into the scrape payload** in `content/injector.js`

Where the scrape handler builds the payload from `getJobData()`/`getDescription()` (both `_handleScrape` and `_handleViewScrape`), add the apply info:

```javascript
const applyInfo = (typeof mod.getApplyInfo === 'function')
  ? mod.getApplyInfo()
  : { easy_apply: null, apply_url_raw: '' };
payload.easy_apply = applyInfo.easy_apply;
payload.apply_url_raw = applyInfo.apply_url_raw;
```

(Use the same `mod`/source-module reference the surrounding code already uses to call `getJobData`.)

- [ ] **Step 5: Manual smoke test**

Reload the extension, then reload a LinkedIn job page and an Indeed job page (content scripts do not re-inject into already-open tabs). Scrape one easy-apply and one external job on each site. In the background service-worker console, confirm the outgoing `stage-job` payload carries `easy_apply` (true/false) and `apply_url_raw` (non-empty for external). Note results in `browser-extension/CONTEXT.md` (done in Task 7's doc step).

- [ ] **Step 6: Commit**

```bash
git add browser-extension/manifest.json browser-extension/content/linkedin.js browser-extension/content/indeed.js browser-extension/content/injector.js
git commit -m "[feat] Extension reads easy-apply/apply-url at scrape time"
```

---

## Task 6: Extension background resolution queue

**Files:**
- Modify: `browser-extension/background/service_worker.js`

**Interfaces:**
- Consumes: `PATCH /api/scraper/jobs/{job_key}/ats-resolution` (Task 4); the stored `extToken` (existing); the `stage-job` response `{status, job_key}` (existing).
- Produces: after a successful `stage-job` for an **external** job (`easy_apply === false`), the worker resolves the apply URL in a background tab and PATCHes the final URL. Concurrency ≤ 2.

> Manual smoke test only (extension posture).

- [ ] **Step 1: Trigger resolution on scrape success**

In the `SCRAPE_JOB` handler, after the `stage-job` POST returns `ok` with a `job_key`, enqueue resolution when the payload is external and has a raw URL:

```javascript
if (result.ok && data.status === 'staged'
    && payload.easy_apply === false && payload.apply_url_raw) {
  enqueueResolution(data.job_key, payload.apply_url_raw);
}
```

(Use the base URL / token the worker already reads for `stage-job`.)

- [ ] **Step 2: Implement the bounded queue + resolver**

```javascript
const _resQueue = [];
let _resActive = 0;
const RES_MAX_CONCURRENT = 2;
const RES_SETTLE_MS = 4000;   // quiet period after last navigation
const RES_TIMEOUT_MS = 20000; // hard cap per resolution

function enqueueResolution(jobKey, applyUrl) {
  _resQueue.push({ jobKey, applyUrl });
  _pumpResolution();
}

function _pumpResolution() {
  while (_resActive < RES_MAX_CONCURRENT && _resQueue.length) {
    const task = _resQueue.shift();
    _resActive++;
    _resolveOne(task).finally(() => { _resActive--; _pumpResolution(); });
  }
}

async function _resolveOne({ jobKey, applyUrl }) {
  let tabId = null;
  try {
    const tab = await xb.tabs.create({ url: applyUrl, active: false });
    tabId = tab.id;
    const finalUrl = await _awaitSettled(tabId);
    await _patchResolution(jobKey, finalUrl);
  } catch (e) {
    console.warn('[ats] resolution failed for', jobKey, e);
  } finally {
    if (tabId != null) { try { await xb.tabs.remove(tabId); } catch (_) {} }
  }
}

// Resolve to the tab's URL once navigation has been quiet for RES_SETTLE_MS,
// or when RES_TIMEOUT_MS elapses — whichever comes first.
function _awaitSettled(tabId) {
  return new Promise((resolve) => {
    let lastUrl = '';
    let settleTimer = null;
    const hardTimer = setTimeout(finish, RES_TIMEOUT_MS);

    function onUpdated(id, info, tab) {
      if (id !== tabId) return;
      if (tab && tab.url) lastUrl = tab.url;
      if (settleTimer) clearTimeout(settleTimer);
      settleTimer = setTimeout(finish, RES_SETTLE_MS);
    }
    async function finish() {
      xb.tabs.onUpdated.removeListener(onUpdated);
      clearTimeout(hardTimer);
      if (settleTimer) clearTimeout(settleTimer);
      if (!lastUrl) {
        try { const t = await xb.tabs.get(tabId); lastUrl = t.url || ''; } catch (_) {}
      }
      resolve(lastUrl);
    }
    xb.tabs.onUpdated.addListener(onUpdated);
  });
}

async function _patchResolution(jobKey, finalUrl) {
  const token = (await xb.storage.local.get('extToken')).extToken;
  if (!token) return;
  await fetch(`${BASE_URL}/api/scraper/jobs/${encodeURIComponent(jobKey)}/ats-resolution`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
    body: JSON.stringify({ apply_url_resolved: finalUrl }),
  });
}
```

(Reuse the existing base-URL constant/getter the worker already uses for `stage-job` in place of `BASE_URL`, and the existing `xb` shim. If `xb.tabs` is not yet surfaced in `lib/browser_shim.js`, add a thin `tabs` passthrough there mirroring the existing `storage`/`identity` wrappers.)

- [ ] **Step 3: Manual smoke test**

Reload the extension. Scrape an external LinkedIn job and an external Indeed job. Confirm a background tab briefly opens and closes, and that the job's card in the dashboard flips from "Resolving…" to the correct ATS chip (via SSE). Scrape 3+ external jobs quickly and confirm no more than 2 background tabs are open at once. Record results in `browser-extension/CONTEXT.md` (Task 7 doc step).

- [ ] **Step 4: Commit**

```bash
git add browser-extension/background/service_worker.js browser-extension/lib/browser_shim.js
git commit -m "[feat] Resolve external apply URLs in a background-tab queue"
```

---

## Task 7: AtsChip UI + docs

**Files:**
- Create: `react-dashboard/src/components/shared/AtsChip.jsx`, `react-dashboard/src/components/shared/AtsChip.test.jsx`
- Modify: `react-dashboard/src/components/shared/JobCard.jsx` (title row ~line 103)
- Modify: `browser-extension/CONTEXT.md`, `db/CONTEXT.md`, `web/CONTEXT.md`

**Interfaces:**
- Consumes: the `ats_type` field in the serialized job (Task 2).
- Produces: `<AtsChip atsType={...} easyApply={...} atsDomain={...} />` rendering a small labeled chip.

- [ ] **Step 1: Write the failing test**

```jsx
// react-dashboard/src/components/shared/AtsChip.test.jsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import AtsChip from './AtsChip';

describe('AtsChip', () => {
  it('shows Easy Apply for in-platform jobs', () => {
    render(<AtsChip atsType="easy_apply" easyApply={true} />);
    expect(screen.getByText(/easy apply/i)).toBeInTheDocument();
  });
  it('shows the ATS name for a recognized ATS', () => {
    render(<AtsChip atsType="greenhouse" easyApply={false} />);
    expect(screen.getByText(/greenhouse/i)).toBeInTheDocument();
  });
  it('shows Resolving… for an unresolved external job', () => {
    render(<AtsChip atsType={null} easyApply={false} />);
    expect(screen.getByText(/resolving/i)).toBeInTheDocument();
  });
  it('renders nothing when there is no apply signal', () => {
    const { container } = render(<AtsChip atsType={null} easyApply={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd react-dashboard && npx vitest run src/components/shared/AtsChip.test.jsx`
Expected: FAIL — cannot resolve `./AtsChip`.

- [ ] **Step 3: Implement `AtsChip.jsx`**

```jsx
const LABELS = {
  easy_apply: 'Easy Apply',
  greenhouse: 'Greenhouse',
  lever: 'Lever',
  ashby: 'Ashby',
  workday: 'Workday',
  icims: 'iCIMS',
  taleo: 'Taleo',
  smartrecruiters: 'SmartRecruiters',
  jobvite: 'Jobvite',
  bamboohr: 'BambooHR',
  other: 'External',
};

// Small chip summarizing how a job is applied to.
export default function AtsChip({ atsType, easyApply, atsDomain }) {
  let label;
  if (atsType && LABELS[atsType]) label = LABELS[atsType];
  else if (easyApply === false) label = 'Resolving…';
  else return null; // easyApply == null and no ats_type → no signal yet

  const title = atsType === 'other' && atsDomain ? atsDomain : undefined;
  return (
    <span
      title={title}
      className="text-[10px] px-1.5 py-0.5 rounded bg-space-mid text-space-dim shrink-0"
    >
      {label}
    </span>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd react-dashboard && npx vitest run src/components/shared/AtsChip.test.jsx`
Expected: PASS (4 tests).

- [ ] **Step 5: Render it in `JobCard.jsx`**

Import at the top: `import AtsChip from './AtsChip';`. In the title row (the `<div className="flex items-center gap-1.5">` around line 103 that holds the title `<p>`), add after the title:

```jsx
<AtsChip atsType={job.ats_type} easyApply={job.easy_apply} atsDomain={job.ats_domain} />
```

(Use whatever the job prop is named in this component — confirm it's `job` by reading the component's props/destructuring at the top of `JobCard.jsx`.)

- [ ] **Step 6: Run the frontend test suite for the shared dir**

Run: `cd react-dashboard && npx vitest run src/components/shared`
Expected: PASS (no regressions in JobCard consumers).

- [ ] **Step 7: Update docs**

- `db/CONTEXT.md` — add a row noting the five `jobs` ATS columns and the `aa12atsdetect01` migration.
- `web/CONTEXT.md` — note `PATCH /api/scraper/jobs/{job_key}/ats-resolution` (extension-authed, classifies via `core/ats.py`) and that `stage-job` now carries `easy_apply`/`apply_url_raw`.
- `browser-extension/CONTEXT.md` — document `getApplyInfo()`, the `"tabs"` permission, the background resolution queue, and record the Task 5/6 smoke-test results. Cross-reference the "DOM recalibration tool" TODO item as the mitigation for the added selector fragility.

- [ ] **Step 8: Commit**

```bash
git add react-dashboard/src/components/shared/AtsChip.jsx react-dashboard/src/components/shared/AtsChip.test.jsx react-dashboard/src/components/shared/JobCard.jsx db/CONTEXT.md web/CONTEXT.md browser-extension/CONTEXT.md
git commit -m "[feat] Add ATS chip to job card and document ATS detection"
```

---

## Final verification

- [ ] Run the full Python suite: `python -m pytest -q` — expected: green (modulo the two pre-existing order-dependent failures tracked in TODO).
- [ ] Run the frontend suite: `cd react-dashboard && npx vitest run` — expected: green.
- [ ] Confirm `python -m alembic upgrade head` is clean and `tests/db/test_alembic_parity.py` passes.
- [ ] Update `.claude/TODO.md`: mark sub-project 1 done, leave 2–5 open.

---

## Self-Review Notes

- **Spec coverage:** easy-apply flag (Task 5), external URL resolution (Task 6), server classification (Tasks 1+4), 5 columns + migration (Task 2), `stage-job` extension + `easy_apply`→`ats_type` (Task 3), separate tenant-scoped PATCH keyed on `(profile_id, job_key)` (Task 4), enqueue-only-on-success ordering (Task 6 Step 1), background-tab auto-close + ≤2 concurrency (Task 6), minimal chip, no filter (Task 7), tests per the spec's testing section. All covered.
- **Type consistency:** `classify_ats(url) -> (ats_type, host)` used identically in Tasks 1 and 4; `getApplyInfo() -> {easy_apply, apply_url_raw}` produced in Task 5, consumed in Task 6; column names identical across model, migration, serialize, endpoint, and chip props.
- **Known deviation from spec wording:** the PATCH endpoint lives in `web/routers/scraper.py` (not the jobs router) because that router already wires `bearer_or_session_profile` — the extension authenticates by bearer token, which the jobs router's `current_profile_id` dependency does not accept. Path is `/api/scraper/jobs/{job_key}/ats-resolution`.
