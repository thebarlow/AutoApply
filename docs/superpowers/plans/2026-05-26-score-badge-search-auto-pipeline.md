# Score Badge, Search, and Auto Intake Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show color-coded score percentages on job cards, add per-tab search to the dashboard, and automatically run description extraction + scoring on every newly ingested job.

**Architecture:** Two independent frontend changes to `JobCard` and `Pipeline` (no API changes); one backend refactor to extract description logic into a helper, plus a new `intake_pipeline.py` module wired into both scraper intake paths.

**Tech Stack:** React + Tailwind (frontend), Python/FastAPI + SQLAlchemy (backend), existing `llm_status` + SSE pattern for progress visibility.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `react-dashboard/src/components/shared/JobCard.jsx` | Modify | Accepts `score` prop, renders color-coded percentage pill |
| `react-dashboard/src/components/widgets/Pipeline.jsx` | Modify | Passes `score` to `JobCard`; adds per-tab search state + filtering |
| `web/routers/jobs.py` | Modify | Extracts `_do_extract_description` helper; route handler delegates to it |
| `web/intake_pipeline.py` | Create | `run_pipeline(job_key)` — sequential description → scoring with SSE |
| `web/routers/scraper.py` | Modify | Calls `run_pipeline` after intake in both paths |

---

## Task 1: Score badge on JobCard

**Files:**
- Modify: `react-dashboard/src/components/shared/JobCard.jsx`

- [ ] **Step 1: Add `score` prop and render the pill**

Open `react-dashboard/src/components/shared/JobCard.jsx`. Replace the `export default function JobCard` signature and the inner flex row so the pill appears between the doc icons and the status icon:

```jsx
export default function JobCard({ title, company, statusIcon, docs = {}, selected = false, state, score }) {
  const hasResume = docs.resume
  const hasCoverLetter = docs.coverLetter

  function ScorePill() {
    if (score == null) return null
    const pct = Math.round(score * 100)
    const color = pct >= 70 ? 'text-green-400' : pct >= 40 ? 'text-yellow-400' : 'text-red-400'
    return <span className={`text-xs font-semibold shrink-0 ${color}`}>{pct}%</span>
  }

  return (
    <motion.div
      whileHover={{ scale: 1.01, backgroundColor: 'rgba(255,255,255,0.06)' }}
      transition={{ duration: 0.15 }}
      className={`flex items-stretch justify-between rounded-lg px-3 py-2 border gap-3 transition-colors
        ${selected
          ? 'bg-purple-900/30 border-purple-500/50'
          : 'bg-white/[0.03] border-white/5'
        }`}
    >
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-space-text truncate">{title}</p>
        <p className="text-xs text-space-dim">{company}</p>
      </div>

      {(hasResume || hasCoverLetter) && (
        <div className="flex items-center gap-1.5">
          {hasResume && (
            <img src="/assets/resume_icon_64.png" alt="Resume" className="h-7 w-auto object-contain opacity-80" />
          )}
          {hasCoverLetter && (
            <img src="/assets/coverletter_icon_64.png" alt="Cover Letter" className="h-7 w-auto object-contain opacity-80" />
          )}
        </div>
      )}

      <div className="flex items-center self-stretch gap-1.5">
        <ScorePill />
        {state === 'deleted' && <TrashIcon />}
        {statusIcon}
      </div>
    </motion.div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add react-dashboard/src/components/shared/JobCard.jsx
git commit -m "[feat] Add color-coded score percentage pill to JobCard"
```

---

## Task 2: Pass score from Pipeline to JobCard

**Files:**
- Modify: `react-dashboard/src/components/widgets/Pipeline.jsx`

- [ ] **Step 1: Pass `score` prop in JobList**

In `Pipeline.jsx`, the `JobList` function renders `JobCard`. Add `score={job.final_score}` to the `JobCard` element:

```jsx
<JobCard
  title={job.title || '(no title)'}
  company={job.company || ''}
  state={job.state}
  score={job.final_score ?? null}
  docs={{
    resume: !!(job.resume_path || job.resume_md_exists),
    coverLetter: !!(job.cover_path || job.cover_md_exists),
  }}
  statusIcon={
    showArchiveBadge
      ? archiveBadge(job.state)
      : statusIconFor(job, processingKeys)
  }
  selected={selectedJob?.job_key === job.job_key}
/>
```

- [ ] **Step 2: Commit**

```bash
git add react-dashboard/src/components/widgets/Pipeline.jsx
git commit -m "[feat] Pass final_score to JobCard for score badge display"
```

---

## Task 3: Per-tab search in Pipeline

**Files:**
- Modify: `react-dashboard/src/components/widgets/Pipeline.jsx`

- [ ] **Step 1: Add search state and filtered job list**

Replace the top of `Pipeline.jsx`'s `export default function Pipeline` with the following. The key changes are: (a) two search state values, (b) clear on tab switch, (c) filtered list via `useMemo`, (d) search input rendered above the job list.

```jsx
export default function Pipeline({ jobs = [], processingKeys = new Set(), selectedJob, onJobSelect }) {
  const [activeTab, setActiveTab] = useState('Inbox')
  const [searchInbox, setSearchInbox] = useState('')
  const [searchArchives, setSearchArchives] = useState('')

  const tabJobs = useMemo(() => ({
    Inbox: jobs.filter((j) => INBOX_STATES.has(j.state)),
    Archives: jobs.filter((j) => ARCHIVE_STATES.has(j.state)),
  }), [jobs])

  const searchQuery = activeTab === 'Inbox' ? searchInbox : searchArchives
  const setSearchQuery = activeTab === 'Inbox' ? setSearchInbox : setSearchArchives

  const visibleJobs = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return tabJobs[activeTab]
    return tabJobs[activeTab].filter((j) =>
      (j.title || '').toLowerCase().includes(q) ||
      (j.company || '').toLowerCase().includes(q)
    )
  }, [tabJobs, activeTab, searchQuery])

  function handleTabChange(tab) {
    setActiveTab(tab)
    setSearchInbox('')
    setSearchArchives('')
  }
```

- [ ] **Step 2: Update tab click handler and render search input**

Replace the tab button's `onClick` to use `handleTabChange`, and add the search input between the tab bar and the content area. Here is the full updated return:

```jsx
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      whileHover={{ boxShadow: '0 0 24px 2px rgba(109,40,217,0.15)' }}
      className="bg-white/5 border border-space-border rounded-xl flex flex-col overflow-hidden h-full"
    >
      {/* Tab bar */}
      <div className="flex border-b border-space-border shrink-0">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => handleTabChange(tab)}
            className={`flex-1 py-2.5 text-xs font-semibold uppercase tracking-widest transition-colors
              ${activeTab === tab
                ? 'text-purple-400 border-b-2 border-purple-400 bg-white/5'
                : 'text-space-dim hover:text-space-text'
              }`}
          >
            {tab}
            {tabJobs[tab].length > 0 && (
              <span className="ml-1 text-[10px] opacity-50">({tabJobs[tab].length})</span>
            )}
          </button>
        ))}
      </div>

      {/* Search */}
      <div className="px-4 pt-3 shrink-0">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search jobs…"
          className="w-full bg-white/5 border border-white/10 rounded-md px-3 py-1.5 text-xs text-space-text placeholder-space-dim outline-none focus:border-purple-500/50 transition-colors"
        />
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        <JobList
          jobs={visibleJobs}
          processingKeys={processingKeys}
          selectedJob={selectedJob}
          onJobSelect={onJobSelect}
          showArchiveBadge={activeTab === 'Archives'}
          activeTab={activeTab}
        />
      </div>
    </motion.div>
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add react-dashboard/src/components/widgets/Pipeline.jsx
git commit -m "[feat] Add per-tab search to Inbox and Archives"
```

---

## Task 4: Extract `_do_extract_description` helper in jobs.py

**Files:**
- Modify: `web/routers/jobs.py`

- [ ] **Step 1: Write failing test for the extracted helper**

Add to `tests/web/test_jobs_api.py`:

```python
def test_extract_description_endpoint_delegates_to_helper(client, db_session, monkeypatch):
    """_do_extract_description is called by the route handler."""
    job = _make_job(db_session, "exttest", JobState.NEW)

    called = {}

    def fake_helper(j, db):
        called["job_key"] = j.job_key

    monkeypatch.setattr("web.routers.jobs._do_extract_description", fake_helper)
    monkeypatch.setattr("web.llm_status.start", lambda *a: None)
    monkeypatch.setattr("web.llm_status.finish", lambda *a: None)

    resp = client.post(f"/api/jobs/{job.job_key}/description/extract")
    assert resp.status_code == 200
    assert called.get("job_key") == job.job_key
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/web/test_jobs_api.py::test_extract_description_endpoint_delegates_to_helper -v
```

Expected: FAIL — `_do_extract_description` does not exist yet.

- [ ] **Step 3: Extract `_do_extract_description` and update the route handler**

In `web/routers/jobs.py`, add this function before `extract_description`:

```python
def _do_extract_description(job: Job, db: Session) -> None:
    """Run description extraction LLM call and persist structured fields."""
    user = User.load(db)
    try:
        prompt_content = user.resolve_prompt("extraction")
    except PromptNotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        client, model = get_client_for_profile(user, user.prompt_extraction_model)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    actual_prompt = job.build_description_prompt(prompt_content)
    try:
        raw = _call_llm_for_extraction(client, model, actual_prompt)
    except Exception as exc:
        raise RuntimeError(f"Description extraction failed: {exc}") from exc
    try:
        data = _json.loads(raw)
    except (_json.JSONDecodeError, TypeError):
        raise RuntimeError("Description extraction failed: LLM returned invalid JSON")

    job.ext_seniority = data.get("seniority", "")
    job.ext_role_type = data.get("role_type", "")
    job.ext_domain = data.get("domain", "")
    job.ext_work_arrangement = data.get("work_arrangement", "")
    job.ext_employment_type = data.get("employment_type", "")
    job.ext_required_skills = ", ".join(data.get("required_skills") or [])
    job.ext_preferred_skills = ", ".join(data.get("preferred_skills") or [])
    job.ext_tech_stack = ", ".join(data.get("tech_stack") or [])
    job.ext_key_responsibilities = ", ".join(data.get("key_responsibilities") or [])
    job.ext_company_signals = ", ".join(data.get("company_signals") or [])
    _add_pending_review(job, "description")
    job.unread_indicator = "ok"
    job.last_result_error = None
    db.commit()
```

Then replace the body of `extract_description` to delegate:

```python
@router.post("/{job_key}/description/extract")
def extract_description(job_key: str, db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    llm_status.start(job_key, "description")
    try:
        _do_extract_description(job, db)
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        job = Job.get(job_key, db)
        job.unread_indicator = "error"
        job.last_result_error = str(exc)
        db.commit()
        db.refresh(job)
        _emit(job)
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        llm_status.finish(job_key, "description")
    db.refresh(job)
    _emit(job)
    return job.serialize()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/web/test_jobs_api.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add web/routers/jobs.py tests/web/test_jobs_api.py
git commit -m "[refactor] Extract _do_extract_description helper from route handler"
```

---

## Task 5: Create `web/intake_pipeline.py`

**Files:**
- Create: `web/intake_pipeline.py`
- Test: `tests/web/test_intake_pipeline.py`

- [ ] **Step 1: Write failing tests**

Create `tests/web/test_intake_pipeline.py`:

```python
from unittest.mock import patch, MagicMock
import pytest

from web.intake_pipeline import run_pipeline


def _make_db_job(job_key="abc123"):
    job = MagicMock()
    job.job_key = job_key
    return job


def test_run_pipeline_calls_extraction_then_scoring(monkeypatch):
    """Both steps run in order on success."""
    calls = []

    mock_job = _make_db_job()
    mock_db = MagicMock()
    mock_db.query.return_value.filter_by.return_value.first.return_value = mock_job

    with patch("web.intake_pipeline.SessionLocal", return_value=mock_db), \
         patch("web.intake_pipeline.Job") as MockJob, \
         patch("web.intake_pipeline._do_extract_description", side_effect=lambda j, db: calls.append("extract")), \
         patch("web.intake_pipeline._do_score", side_effect=lambda j, db: calls.append("score")), \
         patch("web.intake_pipeline.llm_status") as mock_llm_status, \
         patch("web.intake_pipeline._emit"):

        MockJob.get.return_value = mock_job
        run_pipeline("abc123")

    assert calls == ["extract", "score"]


def test_run_pipeline_skips_scoring_if_extraction_fails(monkeypatch):
    """Scoring is skipped when extraction raises."""
    calls = []

    mock_job = _make_db_job()
    mock_db = MagicMock()

    with patch("web.intake_pipeline.SessionLocal", return_value=mock_db), \
         patch("web.intake_pipeline.Job") as MockJob, \
         patch("web.intake_pipeline._do_extract_description", side_effect=RuntimeError("boom")), \
         patch("web.intake_pipeline._do_score", side_effect=lambda j, db: calls.append("score")), \
         patch("web.intake_pipeline.llm_status"), \
         patch("web.intake_pipeline._emit"):

        MockJob.get.return_value = mock_job
        run_pipeline("abc123")

    assert calls == []


def test_run_pipeline_closes_db_session_on_error(monkeypatch):
    """DB session is always closed."""
    mock_db = MagicMock()

    with patch("web.intake_pipeline.SessionLocal", return_value=mock_db), \
         patch("web.intake_pipeline.Job") as MockJob, \
         patch("web.intake_pipeline._do_extract_description", side_effect=RuntimeError("fail")), \
         patch("web.intake_pipeline._do_score"), \
         patch("web.intake_pipeline.llm_status"), \
         patch("web.intake_pipeline._emit"):

        MockJob.get.return_value = _make_db_job()
        run_pipeline("abc123")

    mock_db.close.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/web/test_intake_pipeline.py -v
```

Expected: FAIL — `web.intake_pipeline` module does not exist.

- [ ] **Step 3: Create `web/intake_pipeline.py`**

```python
from __future__ import annotations

from db.database import SessionLocal
from core.job import Job
from web.sse import send as _sse_send
from web import llm_status
from web.routers.jobs import _do_extract_description, _load_score_config
from core.user import User, PromptNotConfiguredError
from core.llm import get_client_for_profile


def _emit(job: Job) -> None:
    try:
        _sse_send("job", job.serialize())
    except Exception as exc:
        print(f"[intake_pipeline] SSE emit failed for {job.job_key}: {exc}", flush=True)


def _do_score(job: Job, db) -> None:
    """Run scoring and persist results."""
    user = User.load(db)
    try:
        prompt_content = user.resolve_prompt("scoring")
    except PromptNotConfiguredError as exc:
        raise RuntimeError(str(exc)) from exc
    try:
        client, model = get_client_for_profile(user, user.prompt_scoring_model)
    except RuntimeError:
        raise

    config = _load_score_config(db)
    job.score(user, config, client, model, db, prompt_content)
    job.unread_indicator = "ok"
    job.last_result_error = None
    db.commit()


def run_pipeline(job_key: str) -> None:
    """Run description extraction then scoring for a newly ingested job."""
    db = SessionLocal()
    try:
        job = Job.get(job_key, db)
        if job is None:
            return

        # Step 1: description extraction
        llm_status.start(job_key, "description")
        extraction_ok = False
        try:
            _do_extract_description(job, db)
            extraction_ok = True
        except Exception as exc:
            db.rollback()
            job = Job.get(job_key, db)
            job.unread_indicator = "error"
            job.last_result_error = str(exc)
            db.commit()
        finally:
            llm_status.finish(job_key, "description")
        db.refresh(job)
        _emit(job)

        if not extraction_ok:
            return

        # Step 2: scoring
        llm_status.start(job_key, "score")
        try:
            _do_score(job, db)
        except Exception as exc:
            db.rollback()
            job = Job.get(job_key, db)
            job.unread_indicator = "error"
            job.last_result_error = str(exc)
            db.commit()
        finally:
            llm_status.finish(job_key, "score")
        db.refresh(job)
        _emit(job)
    finally:
        db.close()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/web/test_intake_pipeline.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add web/intake_pipeline.py tests/web/test_intake_pipeline.py
git commit -m "[feat] Add intake_pipeline module for auto description+score on ingest"
```

---

## Task 6: Wire `run_pipeline` into scraper intake paths

**Files:**
- Modify: `web/routers/scraper.py`

- [ ] **Step 1: Write failing test**

Add to `tests/web/test_scraper.py` (create it if it does not exist):

```python
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from web.app import app

client = TestClient(app)


def test_stage_job_triggers_pipeline(monkeypatch):
    """run_pipeline is called in a background thread after a new job is staged."""
    pipeline_calls = []

    with patch("web.routers.scraper.run_pipeline", side_effect=lambda jk: pipeline_calls.append(jk)) as mock_pipe, \
         patch("web.routers.scraper.Job") as MockJob, \
         patch("web.routers.scraper._sse_send"):

        fake_job = MagicMock()
        fake_job.job_key = "test-key-1"
        MockJob.save_batch_returning.return_value = [fake_job]

        resp = client.post("/api/scraper/stage-job", json={
            "source": "linkedin",
            "job_key": "test-key-1",
            "title": "Engineer",
            "company": "Acme",
            "url": "https://example.com/job/1",
            "description": "Do stuff.",
        })

    assert resp.status_code == 200
    # pipeline is dispatched (thread may not have run yet, but it was started)
    mock_pipe.assert_called_once_with("test-key-1")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/web/test_scraper.py::test_stage_job_triggers_pipeline -v
```

Expected: FAIL — `run_pipeline` not yet imported or called.

- [ ] **Step 3: Update `web/routers/scraper.py`**

Add the import at the top:

```python
from web.intake_pipeline import run_pipeline
```

Update `_run_in_background` to call `run_pipeline` for each new job (it's already in a background thread):

```python
def _run_in_background(source_ids: list[str]) -> None:
    db = SessionLocal()
    try:
        sources = [_SOURCES[sid]() for sid in source_ids]
        new_jobs = run_scraper(db, sources)
        for job in new_jobs:
            job.intake()
            try:
                _sse_send("job", job.serialize())
            except Exception as exc:
                print(f"[scraper] broadcast failed for {job.job_key}: {exc}", flush=True)
            run_pipeline(job.job_key)
    finally:
        db.close()
```

Update `stage_job` to spawn a pipeline thread per new job:

```python
@router.post("/stage-job")
def stage_job(body: StageJobRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    from scraper.base import ScrapedJob
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
    )
    inserted_jobs = Job.save_batch_returning([scraped], db)
    status = "staged" if inserted_jobs else "duplicate"
    for job in inserted_jobs:
        job.intake()
        try:
            _sse_send("job", job.serialize())
        except Exception as exc:
            print(f"[stage_job] broadcast failed for {job.job_key}: {exc}", flush=True)
        threading.Thread(target=run_pipeline, args=(job.job_key,), daemon=True).start()
    return {"status": status, "job_key": body.job_key}
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add web/routers/scraper.py tests/web/test_scraper.py
git commit -m "[feat] Trigger auto intake pipeline on job ingest from scraper and browser extension"
```

---

## Done

All features are independently committed and testable. Verify end-to-end by:
1. Starting the app (`start.bat`) and opening the dashboard.
2. Scoring an existing job manually — confirm the percentage pill appears on its card with correct color.
3. Staging a new job via the browser extension — confirm the spinner appears for "description" then "score" in the status bar, and the score pill appears when complete.
4. Searching in Inbox/Archives — confirm filtering works, clears on tab switch.
