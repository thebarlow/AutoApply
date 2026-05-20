# React Dashboard Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the existing react-dashboard Vite/React prototype to the FastAPI backend, replacing the Alpine.js dashboard with a live, SSE-powered pipeline view.

**Architecture:** FastAPI serves the React build from `react-dashboard/dist/`. A new SSE endpoint at `GET /api/events` pushes full job objects to connected clients on every DB write. React owns `jobs`, `selectedJob`, `processingKeys`, and `settingsTab` state at the App level and passes them down as props. The Pipeline widget renders 4 tabs (Inbox / Processing / Outbound / Archives) filtered from a shared job list. The Settings widget gains a Preview tab that activates when a job card is clicked.

**Tech Stack:** Python 3.x, FastAPI, SQLAlchemy, Vite 5, React 18, Tailwind CSS v3, Framer Motion

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `core/job.py` | Modify | Update `JobState` enum, `from_scraped`, `all_draft`, `serialize` |
| `db/migrate_states.py` | Create | One-time script to rewrite legacy state values in the DB |
| `web/sse.py` | Create | Thread-safe SSE broadcaster (subscribe / unsubscribe / broadcast) |
| `web/routers/events.py` | Create | `GET /api/events` SSE streaming endpoint |
| `web/routers/jobs.py` | Modify | Add `broadcast` calls after every DB write |
| `web/routers/scraper.py` | Modify | Add `broadcast` calls for newly scraped jobs |
| `scraper/runner.py` | Modify | Return new `Job` objects from `run_scraper` instead of a count |
| `web/main.py` | Modify | Register events router; serve React build; add SPA catch-all |
| `react-dashboard/vite.config.js` | Modify | Add `/api` dev proxy; set `build.outDir` |
| `react-dashboard/index.html` | Modify | Add favicon `<link>` tags |
| `react-dashboard/src/api.js` | Create | Centralized fetch wrappers (no raw fetch in components) |
| `react-dashboard/src/App.jsx` | Rewrite | Own app-level state; subscribe to SSE; wire props |
| `react-dashboard/src/components/widgets/Pipeline.jsx` | Rewrite | 4-tab layout; filter jobs; job card click handler |
| `react-dashboard/src/components/widgets/Settings.jsx` | Rewrite | Add Preview tab; wire User / Tasks / Advanced to real API |

---

### Task 1: Update `JobState` enum and all references in `core/job.py`

**Files:**
- Modify: `core/job.py`

- [ ] **Step 1: Replace the `JobState` enum**

In `core/job.py`, replace lines 56–62:

```python
class JobState(str, Enum):
    """Valid states for a job in the pipeline."""

    NEW = "new"
    PENDING_REVIEW = "pending_review"
    READY = "ready"
    APPLIED = "applied"
    CONTACT = "contact"
    REJECTED = "rejected"
```

- [ ] **Step 2: Fix the `state` column default**

On the `state` column (line ~88), change the default:

```python
state = Column(String, nullable=False, default="new")
```

- [ ] **Step 3: Fix `from_scraped`**

Change `state=JobState.DRAFT.value` to `state=JobState.NEW.value` (line ~137).

- [ ] **Step 4: Fix `all_draft`**

Rename the method to `all_inbox` and update the filter:

```python
@classmethod
def all_inbox(cls, db: Session) -> list["Job"]:
    """Return all Inbox jobs (new or pending_review) ordered by final_score descending."""
    return (
        db.query(cls)
        .filter(cls.state.in_([JobState.NEW.value, JobState.PENDING_REVIEW.value]))
        .order_by(cls.final_score.desc())
        .all()
    )
```

- [ ] **Step 5: Fix `mark_applied`**

`mark_applied` already uses `JobState.APPLIED.value` — no change needed. Verify it still reads correctly.

- [ ] **Step 6: Update `serialize` to include extraction data**

In the `serialize` method, replace the final `return` dict. Add an `extraction` key after `extraction_json_exists`:

```python
return {
    "job_key": self.job_key,
    "title": self.title,
    "company": self.company,
    "location": self.location,
    "salary": self.salary,
    "url": self.url,
    "description": self.description,
    "remote": self.remote,
    "state": self.state,
    "desirability_score": self.desirability_score,
    "fit_score": self.fit_score,
    "final_score": self.final_score,
    "score_justification": justification,
    "resume_path": self.resume_path,
    "cover_path": self.cover_path,
    "resume_md_exists": (_OUTPUTS_DIR / f"{self.job_key}_resume.md").exists(),
    "cover_md_exists": (_OUTPUTS_DIR / f"{self.job_key}_cover.md").exists(),
    "extraction_json_exists": bool(self.ext_required_skills or self.ext_seniority),
    "extraction": {
        "seniority": self.ext_seniority,
        "role_type": self.ext_role_type,
        "domain": self.ext_domain,
        "work_arrangement": self.ext_work_arrangement,
        "employment_type": self.ext_employment_type,
        "required_skills": [s.strip() for s in (self.ext_required_skills or "").split(",") if s.strip()],
        "preferred_skills": [s.strip() for s in (self.ext_preferred_skills or "").split(",") if s.strip()],
        "tech_stack": [s.strip() for s in (self.ext_tech_stack or "").split(",") if s.strip()],
        "key_responsibilities": [s.strip() for s in (self.ext_key_responsibilities or "").split(",") if s.strip()],
        "company_signals": [s.strip() for s in (self.ext_company_signals or "").split(",") if s.strip()],
    } if bool(self.ext_required_skills or self.ext_seniority) else None,
    "scraped_at": self.scraped_at or "",
}
```

- [ ] **Step 7: Update the test suite**

`tests/web/test_jobs_api.py` uses the old state names. Make these changes:

1. Change the default in `_make_job`: `state: JobState = JobState.NEW`
2. Replace every `JobState.DRAFT` with `JobState.NEW`
3. Line ~147: change `"in_contact"` → `"contact"` in both the PATCH body and the assertion
4. Line ~154: change `"draft"` → `"new"` in both the PATCH body and the assertion
5. Line ~249: change `assert data["state"] == "draft"` → `assert data["state"] == "new"`

In `tests/core/test_job.py` line ~43: change `assert job.state == "draft"` → `assert job.state == "new"`

In `tests/scraper/test_runner.py` line ~86: change `assert job.state == JobState.DRAFT.value` → `assert job.state == JobState.NEW.value`

- [ ] **Step 8: Run the test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass. If any test still references the old state names it will fail with an `AttributeError` on `JobState.DRAFT` — fix the remaining reference and re-run.

- [ ] **Step 9: Verify the server still starts**

```bash
python -m uvicorn web.main:app --port 8080
```

Expected: server starts without import errors. Stop with Ctrl+C.

- [ ] **Step 10: Commit**

```bash
git add core/job.py tests/
git commit -m "[feat] Update JobState enum to new pipeline states and fix tests"
```

---

### Task 2: DB migration for legacy state values

**Files:**
- Create: `db/migrate_states.py`

- [ ] **Step 1: Create the migration script**

```python
"""One-time migration: rewrite legacy job state values to the new pipeline states.

Run once from the project root:
    python -m db.migrate_states
"""
from __future__ import annotations

from db.database import SessionLocal


def migrate() -> None:
    db = SessionLocal()
    try:
        updated = db.execute(
            "UPDATE jobs SET state = 'new' WHERE state = 'draft'"
        ).rowcount
        print(f"  draft -> new:        {updated} rows")

        updated = db.execute(
            "UPDATE jobs SET state = 'contact' WHERE state = 'in_contact'"
        ).rowcount
        print(f"  in_contact -> contact: {updated} rows")

        db.commit()
        print("Migration complete.")
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
```

- [ ] **Step 2: Run the migration**

```bash
python -m db.migrate_states
```

Expected output (row counts will vary):
```
  draft -> new:        N rows
  in_contact -> contact: N rows
Migration complete.
```

- [ ] **Step 3: Verify**

```bash
python -c "from db.database import SessionLocal; db=SessionLocal(); from core.job import Job; print(set(j.state for j in db.query(Job).all()))"
```

Expected: only values from `{'new', 'pending_review', 'ready', 'applied', 'contact', 'rejected'}` appear (no `draft` or `in_contact`).

- [ ] **Step 4: Commit**

```bash
git add db/migrate_states.py
git commit -m "[chore] Add DB migration script for new pipeline states"
```

---

### Task 3: SSE broadcaster module

**Files:**
- Create: `web/sse.py`

- [ ] **Step 1: Create `web/sse.py`**

```python
"""Thread-safe SSE broadcaster.

Sync route handlers call broadcast() to push a JSON payload to all connected
clients. Each SSE client holds its own SimpleQueue. broadcast() posts to every
queue synchronously — safe to call from FastAPI's threadpool workers.
"""
from __future__ import annotations

import queue
from typing import List


_clients: List[queue.SimpleQueue] = []


def subscribe() -> queue.SimpleQueue:
    """Register a new SSE client and return its queue."""
    q: queue.SimpleQueue = queue.SimpleQueue()
    _clients.append(q)
    return q


def unsubscribe(q: queue.SimpleQueue) -> None:
    """Remove a client queue when its connection closes."""
    try:
        _clients.remove(q)
    except ValueError:
        pass


def broadcast(payload: str) -> None:
    """Send a JSON string to every connected SSE client."""
    for q in list(_clients):
        try:
            q.put_nowait(payload)
        except Exception:
            pass
```

- [ ] **Step 2: Verify import**

```bash
python -c "from web.sse import subscribe, unsubscribe, broadcast; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add web/sse.py
git commit -m "[feat] Add thread-safe SSE broadcaster"
```

---

### Task 4: SSE endpoint

**Files:**
- Create: `web/routers/events.py`

- [ ] **Step 1: Create `web/routers/events.py`**

```python
"""SSE streaming endpoint — `GET /api/events`.

Clients receive a `data: <json>\n\n` event whenever a job is written to the DB.
The event payload is the full serialized job object.
"""
from __future__ import annotations

import asyncio
import queue as _queue

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from web.sse import subscribe, unsubscribe

router = APIRouter(prefix="/api")


@router.get("/events")
async def sse_events():
    q = subscribe()

    async def generate():
        try:
            while True:
                try:
                    payload = q.get_nowait()
                    yield f"data: {payload}\n\n"
                except _queue.Empty:
                    await asyncio.sleep(0.05)
        finally:
            unsubscribe(q)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 2: Commit**

```bash
git add web/routers/events.py
git commit -m "[feat] Add SSE events endpoint"
```

---

### Task 5: Wire broadcast into job writes and scraper

**Files:**
- Modify: `web/routers/jobs.py`
- Modify: `web/routers/scraper.py`
- Modify: `scraper/runner.py`

- [ ] **Step 1: Add broadcast import to `web/routers/jobs.py`**

After the existing imports at the top of the file, add:

```python
from web.sse import broadcast as _broadcast
```

- [ ] **Step 2: Add a helper to broadcast a job**

After the `_VALID_STATES` line in `jobs.py`, add:

```python
def _emit(job: Job) -> None:
    """Serialize job and push to all SSE clients."""
    import json as _json
    _broadcast(_json.dumps(job.serialize()))
```

- [ ] **Step 3: Call `_emit` in `update_job_state`**

In the `update_job_state` function, add `_emit(job)` after `db.refresh(job)` and before `return`:

```python
    job.state = body.state
    db.commit()
    db.refresh(job)
    _emit(job)
    return job.serialize()
```

- [ ] **Step 4: Call `_emit` in score, generate, and extract endpoints**

Add `_emit(job)` after `db.refresh(job)` in each of these functions (just before the final `return job.serialize()`):
- `score_job_endpoint`
- `generate_job_endpoint`
- `generate_resume_endpoint`
- `generate_resume_md_endpoint`
- `generate_resume_pdf_endpoint`
- `generate_cover_endpoint`
- `generate_cover_md_endpoint`
- `generate_cover_pdf_endpoint`
- `extract_description`

For each one, the pattern is the same:
```python
    db.refresh(job)
    _emit(job)
    return job.serialize()
```

- [ ] **Step 5: Modify `scraper/runner.py` to return new Job objects**

Replace the return type in `run_scraper` and update the body to collect and return new jobs:

```python
def run_scraper(db: Session, sources: list[JobSource]) -> list[Job]:
    """Fetch jobs from all sources and persist new ones.

    Args:
        db: SQLAlchemy session.
        sources: List of JobSource instances to fetch from.

    Returns:
        List of newly inserted Job objects.
    """
    config = load_search_config(db)
    max_jobs = load_max_jobs(db)

    all_scraped = []
    for source in sources:
        try:
            jobs = source.fetch(config, max_jobs)
            print(f"[scraper] {source.source_id}: fetched {len(jobs)} jobs")
            all_scraped.extend(jobs)
        except Exception as e:
            warnings.warn(f"[scraper] {source.source_id} failed: {e}")

    new_jobs = Job.save_batch_returning(all_scraped, db)
    print(f"[scraper] saved {len(new_jobs)} new jobs (skipped {len(all_scraped) - len(new_jobs)} duplicates)")
    return new_jobs
```

- [ ] **Step 6: Add `save_batch_returning` to `core/job.py`**

In `core/job.py`, after the existing `save_batch` method, add:

```python
@classmethod
def save_batch_returning(cls, scraped_jobs: list[Any], db: Session) -> list["Job"]:
    """Persist new jobs and return the inserted Job objects.

    Args:
        scraped_jobs: List of ScrapedJob instances from a scraper source.
        db: SQLAlchemy session.

    Returns:
        List of newly inserted Job instances.
    """
    new_jobs: list["Job"] = []
    for scraped in scraped_jobs:
        if db.query(cls).filter_by(url=scraped.url).first():
            continue
        job = cls.from_scraped(scraped)
        db.add(job)
        new_jobs.append(job)
    db.commit()
    for job in new_jobs:
        db.refresh(job)
    return new_jobs
```

- [ ] **Step 7: Wire broadcast in `web/routers/scraper.py`**

Add imports at the top of `web/routers/scraper.py`:

```python
import json as _json
from web.sse import broadcast as _broadcast
```

Then update `_run_in_background` to broadcast each new job:

```python
def _run_in_background(source_ids: list[str]) -> None:
    db = SessionLocal()
    try:
        sources = [_SOURCES[sid]() for sid in source_ids]
        new_jobs = run_scraper(db, sources)
        for job in new_jobs:
            _broadcast(_json.dumps(job.serialize()))
    finally:
        db.close()
```

- [ ] **Step 8: Verify server starts cleanly**

```bash
python -m uvicorn web.main:app --port 8080
```

Expected: starts without import errors. Stop with Ctrl+C.

- [ ] **Step 9: Commit**

```bash
git add web/routers/jobs.py web/routers/scraper.py scraper/runner.py core/job.py
git commit -m "[feat] Wire SSE broadcast into all job write endpoints and scraper"
```

---

### Task 6: Register events router and serve React build in FastAPI

**Files:**
- Modify: `web/main.py`

- [ ] **Step 1: Update `web/main.py`**

Replace the entire file:

```python
from __future__ import annotations

import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from db.database import init_db
from web.routers import jobs
from web.routers import scraper
from web.routers import config
from web.routers import events


def _timed(label: str, fn):
    t = time.perf_counter()
    result = fn()
    print(f"  [startup] {label} — {time.perf_counter() - t:.1f}s")
    return result


def _warm_lazy_imports() -> None:
    """Import heavy modules in the background so the first real request isn't slow."""
    print("[startup] Warming lazy imports in background...")
    _timed("openai", lambda: __import__("openai"))
    _timed("pdfplumber", lambda: __import__("pdfplumber"))
    print("[startup] Background warm-up complete — all imports ready.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[startup] Initialising database...")
    _timed("init_db", init_db)

    t = threading.Thread(target=_warm_lazy_imports, daemon=True)
    t.start()

    print("[startup] Open http://localhost:8080 in your browser")

    yield

    print("[shutdown] Waiting for background thread...")
    t.join(timeout=5)


app = FastAPI(title="Auto Apply", lifespan=lifespan)

_STATIC = Path(__file__).parent / "static"
_DIST = Path(__file__).parent.parent / "react-dashboard" / "dist"

app.include_router(jobs.router)
app.include_router(scraper.router)
app.include_router(config.router)
app.include_router(events.router)

# Serve legacy static assets (favicons, images)
app.mount("/static", StaticFiles(directory=_STATIC), name="static")

# Serve Vite-compiled JS/CSS bundles (only when built)
if (_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")


def _spa_index() -> FileResponse:
    return FileResponse(_DIST / "index.html")


@app.get("/")
def index():
    if (_DIST / "index.html").exists():
        return _spa_index()
    return FileResponse(_STATIC / "index.html")


@app.get("/config")
def config_page():
    if (_DIST / "index.html").exists():
        return _spa_index()
    return FileResponse(_STATIC / "config.html")


@app.get("/setup")
def setup_page():
    if (_DIST / "index.html").exists():
        return _spa_index()
    return FileResponse(_STATIC / "setup.html")


@app.get("/help")
def help_page():
    return FileResponse(Path(__file__).parent.parent / "docs" / "index.html")


@app.get("/{full_path:path}")
def spa_catchall(full_path: str):
    """Serve React SPA for any unmatched non-API route."""
    if (_DIST / "index.html").exists():
        return _spa_index()
    return FileResponse(_STATIC / "index.html")
```

- [ ] **Step 2: Verify the server starts**

```bash
python -m uvicorn web.main:app --port 8080
```

Expected: starts cleanly. `/` serves the old Alpine.js index (React dist not built yet — fallback works). Stop with Ctrl+C.

- [ ] **Step 3: Commit**

```bash
git add web/main.py
git commit -m "[feat] Register events router and add React build serving with SPA fallback"
```

---

### Task 7: Vite config and index.html

**Files:**
- Modify: `react-dashboard/vite.config.js`
- Modify: `react-dashboard/index.html`

- [ ] **Step 1: Update `react-dashboard/vite.config.js`**

```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
})
```

- [ ] **Step 2: Update `react-dashboard/index.html`**

Add favicon links in the `<head>`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Auto Apply</title>
    <link rel="icon" type="image/png" sizes="32x32" href="/static/images/favicon-32x32.png" />
    <link rel="icon" type="image/png" sizes="16x16" href="/static/images/favicon-16x16.png" />
    <link rel="apple-touch-icon" sizes="180x180" href="/static/images/apple-touch-icon.png" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

- [ ] **Step 3: Verify `tailwind.config.js` exists and has the space theme**

```bash
cat react-dashboard/tailwind.config.js
```

Expected: file exists and has a `space` color block. If missing, create it:

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        space: {
          bg: '#0a0a1a',
          card: '#0f0f2a',
          border: '#2d1b69',
          accent: '#6d28d9',
          blue: '#1d4ed8',
          muted: '#6b7280',
          text: '#e2e8f0',
          dim: '#94a3b8',
        },
      },
    },
  },
  plugins: [],
}
```

- [ ] **Step 4: Commit**

```bash
git add react-dashboard/vite.config.js react-dashboard/index.html
git commit -m "[chore] Configure Vite dev proxy and add favicon links"
```

---

### Task 8: API layer

**Files:**
- Create: `react-dashboard/src/api.js`

- [ ] **Step 1: Create `react-dashboard/src/api.js`**

```js
const BASE = ''

async function _fetch(url, options) {
  const res = await fetch(BASE + url, options)
  if (!res.ok) throw new Error(`${options?.method ?? 'GET'} ${url} → ${res.status}`)
  return res.json()
}

export const getJobs = () => _fetch('/api/jobs')

export const getProfiles = () => _fetch('/api/config/profiles')

export const createProfile = (name) =>
  _fetch('/api/config/profiles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })

export const getProviders = () => _fetch('/api/config/providers')

export const saveProvider = (id, body) =>
  _fetch(`/api/config/providers/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
```

- [ ] **Step 2: Commit**

```bash
git add react-dashboard/src/api.js
git commit -m "[feat] Add centralized API layer"
```

---

### Task 9: App-level state and SSE subscription

**Files:**
- Rewrite: `react-dashboard/src/App.jsx`

- [ ] **Step 1: Rewrite `react-dashboard/src/App.jsx`**

```jsx
import { useState, useEffect, useCallback } from 'react'
import Navbar from './components/Navbar'
import Dashboard from './components/Dashboard'
import Pipeline from './components/widgets/Pipeline'
import Settings from './components/widgets/Settings'
import { getJobs } from './api'

export default function App() {
  const [jobs, setJobs] = useState([])
  const [selectedJob, setSelectedJob] = useState(null)
  const [processingKeys, setProcessingKeys] = useState(new Set())
  const [settingsTab, setSettingsTab] = useState('User')

  // Upsert a single job into the jobs list
  const upsertJob = useCallback((job) => {
    setJobs((prev) => {
      const idx = prev.findIndex((j) => j.job_key === job.job_key)
      if (idx === -1) return [...prev, job]
      const next = [...prev]
      next[idx] = job
      return next
    })
    // Keep selectedJob in sync
    setSelectedJob((prev) => (prev?.job_key === job.job_key ? job : prev))
  }, [])

  // Initial load + SSE subscription
  useEffect(() => {
    getJobs().then(setJobs).catch(console.error)

    const es = new EventSource('/api/events')
    es.onmessage = (e) => {
      try {
        upsertJob(JSON.parse(e.data))
      } catch { /* malformed event — ignore */ }
    }
    es.onerror = () => {
      getJobs().then(setJobs).catch(console.error)
    }
    return () => es.close()
  }, [upsertJob])

  // Escape key clears selection
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape' && selectedJob) {
        setSelectedJob(null)
        setSettingsTab('User')
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [selectedJob])

  const handleJobSelect = (job) => {
    setSelectedJob(job)
    setSettingsTab('Preview')
  }

  return (
    <div className="min-h-screen text-space-text">
      <Navbar />
      <Dashboard>
        <div className="col-span-3 overflow-hidden h-full">
          <Pipeline
            jobs={jobs}
            processingKeys={processingKeys}
            selectedJob={selectedJob}
            onJobSelect={handleJobSelect}
          />
        </div>
        <div className="col-span-2 overflow-hidden h-full">
          <Settings
            selectedJob={selectedJob}
            activeTab={settingsTab}
            onTabChange={setSettingsTab}
            jobs={jobs}
            processingKeys={processingKeys}
          />
        </div>
      </Dashboard>
    </div>
  )
}
```

- [ ] **Step 2: Start dev server and verify the page loads**

With the FastAPI server running on `:8080`:

```bash
cd react-dashboard
npm run dev
```

Open `http://localhost:5173`. Expected: page loads, no console errors, job list fetches from the real API (may be empty if DB is empty).

- [ ] **Step 3: Commit**

```bash
git add react-dashboard/src/App.jsx
git commit -m "[feat] Wire App-level state and SSE subscription"
```

---

### Task 10: Pipeline widget — 4 tabs

**Files:**
- Rewrite: `react-dashboard/src/components/widgets/Pipeline.jsx`

- [ ] **Step 1: Rewrite `react-dashboard/src/components/widgets/Pipeline.jsx`**

```jsx
import { useState } from 'react'
import { motion } from 'framer-motion'
import JobCard, { NewIcon, ProcessingIcon } from '../shared/JobCard'

const TABS = ['Inbox', 'Processing', 'Outbound', 'Archives']

const INBOX_STATES = new Set(['new', 'pending_review'])
const OUTBOUND_STATES = new Set(['ready'])
const ARCHIVE_STATES = new Set(['applied', 'contact', 'rejected'])

const ARCHIVE_LABELS = { applied: 'Applied', contact: 'In Contact', rejected: 'Rejected' }
const ARCHIVE_COLORS = { applied: 'text-green-400', contact: 'text-blue-400', rejected: 'text-red-400' }

function statusIconFor(job, processingKeys) {
  if (processingKeys.has(job.job_key)) return <ProcessingIcon />
  if (job.state === 'new') return <NewIcon />
  return null
}

function archiveBadge(state) {
  return (
    <span className={`text-xs font-medium shrink-0 ${ARCHIVE_COLORS[state] ?? 'text-space-dim'}`}>
      {ARCHIVE_LABELS[state] ?? state}
    </span>
  )
}

function JobList({ jobs, processingKeys, selectedJob, onJobSelect, showArchiveBadge }) {
  if (jobs.length === 0) {
    return <p className="text-xs text-space-dim py-1">Empty</p>
  }
  return (
    <div className="flex flex-col gap-2">
      {jobs.map((job) => (
        <div key={job.job_key} onClick={() => onJobSelect(job)} className="cursor-pointer">
          <JobCard
            title={job.title || '(no title)'}
            company={job.company || ''}
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
        </div>
      ))}
    </div>
  )
}

export default function Pipeline({ jobs, processingKeys, selectedJob, onJobSelect }) {
  const [activeTab, setActiveTab] = useState('Inbox')

  const tabJobs = {
    Inbox: jobs.filter((j) => INBOX_STATES.has(j.state) && !processingKeys.has(j.job_key)),
    Processing: jobs.filter((j) => processingKeys.has(j.job_key)),
    Outbound: jobs.filter((j) => OUTBOUND_STATES.has(j.state)),
    Archives: jobs.filter((j) => ARCHIVE_STATES.has(j.state)),
  }

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
            onClick={() => setActiveTab(tab)}
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

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        <JobList
          jobs={tabJobs[activeTab]}
          processingKeys={processingKeys}
          selectedJob={selectedJob}
          onJobSelect={onJobSelect}
          showArchiveBadge={activeTab === 'Archives'}
        />
      </div>
    </motion.div>
  )
}
```

- [ ] **Step 2: Add `selected` prop handling to `JobCard`**

In `react-dashboard/src/components/shared/JobCard.jsx`, update the component signature and add a selected highlight:

```jsx
import { motion } from 'framer-motion'

function NewIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" className="shrink-0">
      <circle cx="9" cy="9" r="8.5" stroke="#EAB308" strokeWidth="1" />
      <text x="9" y="13.5" textAnchor="middle" fontSize="11" fontWeight="700" fill="#EAB308">!</text>
    </svg>
  )
}

function ProcessingIcon() {
  const dots = Array.from({ length: 8 }, (_, i) => {
    const angle = (i / 8) * 2 * Math.PI
    const cx = 9 + 6 * Math.cos(angle)
    const cy = 9 + 6 * Math.sin(angle)
    return <circle key={i} cx={cx} cy={cy} r="1.4" fill="#a78bfa" />
  })
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 18 18"
      className="shrink-0 animate-spin"
      style={{ animationDuration: '1.4s' }}
    >
      {dots}
    </svg>
  )
}

export default function JobCard({ title, company, statusIcon, docs = {}, selected = false }) {
  const hasResume = docs.resume
  const hasCoverLetter = docs.coverLetter

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

      <div className="flex items-center self-stretch">
        {statusIcon}
      </div>
    </motion.div>
  )
}

export { NewIcon, ProcessingIcon }
```

- [ ] **Step 3: Check in browser**

With both servers running, open `http://localhost:5173`. Expected: Pipeline widget shows 4 tabs, jobs sorted into correct tabs by state, count badges on non-empty tabs, selected job card highlights purple.

- [ ] **Step 4: Commit**

```bash
git add react-dashboard/src/components/widgets/Pipeline.jsx react-dashboard/src/components/shared/JobCard.jsx
git commit -m "[feat] Rewrite Pipeline with 4 tabs wired to real job data"
```

---

### Task 11: Settings widget — Preview tab + wired User/Tasks/Advanced

**Files:**
- Rewrite: `react-dashboard/src/components/widgets/Settings.jsx`

- [ ] **Step 1: Rewrite `react-dashboard/src/components/widgets/Settings.jsx`**

```jsx
import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { getProfiles, createProfile, getProviders, saveProvider } from '../../api'

// ─── Icons ────────────────────────────────────────────────────────────────────

function BackArrow() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10 12L6 8l4-4" />
    </svg>
  )
}

// ─── Shared ───────────────────────────────────────────────────────────────────

const inputClass =
  'w-full bg-white/5 border border-space-border rounded-lg px-3 py-2 text-sm text-space-text placeholder-space-dim focus:outline-none focus:border-purple-500 transition-colors'

const slideVariants = {
  enter: { x: 40, opacity: 0 },
  center: { x: 0, opacity: 1 },
  exit: { x: -40, opacity: 0 },
}

// ─── Preview tab ──────────────────────────────────────────────────────────────

function ExtractionView({ data }) {
  const fields = [
    { key: 'seniority', label: 'Seniority' },
    { key: 'role_type', label: 'Role Type' },
    { key: 'domain', label: 'Domain' },
    { key: 'work_arrangement', label: 'Work Arrangement' },
    { key: 'employment_type', label: 'Employment Type' },
    { key: 'required_skills', label: 'Required Skills' },
    { key: 'preferred_skills', label: 'Preferred Skills' },
    { key: 'tech_stack', label: 'Tech Stack' },
    { key: 'key_responsibilities', label: 'Responsibilities' },
    { key: 'company_signals', label: 'Company Signals' },
  ]
  return (
    <div className="flex flex-col gap-3">
      {fields.map(({ key, label }) => {
        const val = data[key]
        if (!val || (Array.isArray(val) && val.length === 0)) return null
        return (
          <div key={key}>
            <p className="text-xs font-semibold text-space-dim mb-1">{label}</p>
            {Array.isArray(val)
              ? <ul className="list-disc list-inside text-xs space-y-0.5 text-space-text">{val.map((v, i) => <li key={i}>{v}</li>)}</ul>
              : <p className="text-xs text-space-text">{val}</p>
            }
          </div>
        )
      })}
    </div>
  )
}

function PreviewTab({ job }) {
  const [view, setView] = useState('raw')

  // Reset view when a different job is selected
  useEffect(() => { setView('raw') }, [job?.job_key])

  if (!job) return null

  const score = job.final_score != null ? Math.round(job.final_score * 100) + '%' : '—'
  const stateLabel = { new: 'New', pending_review: 'Pending Review', ready: 'Ready', applied: 'Applied', contact: 'In Contact', rejected: 'Rejected' }[job.state] ?? job.state

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div>
        <h2 className="text-base font-semibold text-space-text leading-tight">{job.title || '(no title)'}</h2>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1.5">
          {job.company && <span className="text-xs text-space-dim">{job.company}</span>}
          {job.location && <span className="text-xs text-space-dim">{job.location}</span>}
          {job.salary && <span className="text-xs text-space-dim">{job.salary}</span>}
          <span className="text-xs font-semibold text-purple-400">{score}</span>
          <span className="text-xs text-space-dim">{stateLabel}</span>
        </div>
      </div>

      <hr className="border-space-border" />

      {/* Toggle */}
      <div className="flex gap-2">
        {['raw', 'extracted'].map((v) => (
          <button
            key={v}
            onClick={() => setView(v)}
            disabled={v === 'extracted' && !job.extraction_json_exists}
            className={`px-3 py-1 rounded text-xs font-semibold capitalize transition-colors
              ${view === v ? 'bg-purple-600 text-white' : 'text-space-dim hover:text-space-text border border-space-border'}
              disabled:opacity-30 disabled:cursor-not-allowed`}
          >
            {v}
          </button>
        ))}
      </div>

      {/* Description */}
      <div>
        {view === 'raw' && (
          <p className="text-xs text-space-dim leading-relaxed whitespace-pre-wrap">
            {job.description || 'No description available.'}
          </p>
        )}
        {view === 'extracted' && (
          job.extraction
            ? <ExtractionView data={job.extraction} />
            : <p className="text-xs text-space-dim">No extraction yet.</p>
        )}
      </div>
    </div>
  )
}

// ─── Tasks tab ────────────────────────────────────────────────────────────────

function TasksTab({ jobs, processingKeys }) {
  const processing = jobs.filter((j) => processingKeys.has(j.job_key))
  if (processing.length === 0) {
    return <p className="text-sm text-space-dim">No active tasks.</p>
  }
  return (
    <div className="flex flex-col gap-2">
      {processing.map((job) => (
        <div key={job.job_key} className="flex items-center gap-2 rounded-lg px-3 py-2 bg-white/[0.03] border border-white/5">
          <svg className="shrink-0 animate-spin text-purple-400" width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
            <circle cx="7" cy="7" r="6" fill="none" stroke="currentColor" strokeWidth="2" strokeDasharray="20 18" />
          </svg>
          <div className="min-w-0">
            <p className="text-sm text-space-text truncate">{job.title || '(no title)'}</p>
            <p className="text-xs text-space-dim">{job.company || ''}</p>
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── User tab ─────────────────────────────────────────────────────────────────

function CreateProfile({ onBack, onCreated }) {
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const handleSave = async () => {
    const trimmed = name.trim()
    if (!trimmed) { setError('Name is required'); return }
    setSaving(true)
    try {
      const profile = await createProfile(trimmed)
      onCreated(profile)
    } catch {
      setError('Failed to create profile')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <label className="text-xs text-space-dim">Profile Name</label>
        <input
          className={inputClass}
          value={name}
          onChange={(e) => { setName(e.target.value); setError(null) }}
          placeholder="e.g. Software Engineer"
        />
        {error && <p className="text-xs text-red-400">{error}</p>}
      </div>
      <div className="flex gap-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex-1 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-sm font-semibold transition-colors"
        >
          {saving ? 'Saving…' : 'Save Profile'}
        </button>
        <button onClick={onBack} className="px-4 py-2 rounded-lg border border-space-border text-sm text-space-dim hover:text-space-text transition-colors">
          Cancel
        </button>
      </div>
    </div>
  )
}

function ProfileList({ onCreateProfile }) {
  const [profiles, setProfiles] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getProfiles()
      .then((data) => setProfiles(data.profiles ?? []))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p className="text-xs text-space-dim">Loading…</p>

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        {profiles.length === 0 && (
          <p className="text-xs text-space-dim">No profiles yet.</p>
        )}
        {profiles.map((profile) => (
          <div
            key={profile.id}
            className="flex items-center gap-3 rounded-lg px-3 py-2.5 bg-white/[0.03] border border-white/5"
          >
            <p className="text-sm font-medium text-space-text">{profile.name || 'Unnamed'}</p>
          </div>
        ))}
      </div>
      <button
        onClick={onCreateProfile}
        className="w-full py-2 rounded-lg border border-space-border hover:border-purple-500/50 text-sm text-space-dim hover:text-space-text transition-colors"
      >
        + Create Profile
      </button>
    </div>
  )
}

function UserTab({ onProfileSettings }) {
  return (
    <div className="flex flex-col gap-4">
      <button
        onClick={onProfileSettings}
        className="w-full py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-sm font-semibold transition-colors"
      >
        Profile Settings
      </button>
    </div>
  )
}

// ─── Advanced tab ─────────────────────────────────────────────────────────────

function AdvancedTab() {
  const [providers, setProviders] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState(null)

  useEffect(() => {
    getProviders()
      .then((data) => setProviders(data.providers ?? []))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const handleSave = async (provider, field, value) => {
    setSaving(true)
    try {
      await saveProvider(provider.id, { ...provider, [field]: value })
      setStatus('Saved ✓')
    } catch {
      setStatus('Save failed')
    } finally {
      setSaving(false)
      setTimeout(() => setStatus(null), 2500)
    }
  }

  if (loading) return <p className="text-xs text-space-dim">Loading…</p>
  if (providers.length === 0) return <p className="text-xs text-space-dim">No providers configured.</p>

  return (
    <div className="flex flex-col gap-6">
      {providers.map((provider) => (
        <div key={provider.id} className="flex flex-col gap-3">
          <p className="text-xs font-semibold uppercase tracking-widest text-space-dim">{provider.name}</p>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-space-dim">Default Model</label>
            <input
              className={inputClass}
              defaultValue={provider.default_model || ''}
              onBlur={(e) => handleSave(provider, 'default_model', e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-space-dim">API Key</label>
            <input
              type="password"
              className={inputClass}
              placeholder="Enter new key to replace existing"
              onBlur={(e) => { if (e.target.value) handleSave(provider, 'api_key', e.target.value) }}
            />
          </div>
        </div>
      ))}
      {status && <p className={`text-xs ${status.includes('failed') ? 'text-red-400' : 'text-green-400'}`}>{status}</p>}
    </div>
  )
}

// ─── Root ─────────────────────────────────────────────────────────────────────

const TABS = ['User', 'Tasks', 'Advanced', 'Preview']

export default function Settings({ selectedJob, activeTab, onTabChange, jobs, processingKeys }) {
  const [view, setView] = useState('main') // 'main' | 'profiles' | 'createProfile'

  const isPreviewDisabled = selectedJob === null

  const handleTabClick = (tab) => {
    if (tab === 'Preview' && isPreviewDisabled) return
    onTabChange(tab)
    setView('main')
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      whileHover={{ boxShadow: '0 0 24px 2px rgba(109,40,217,0.15)' }}
      className="bg-white/5 border border-space-border rounded-xl flex flex-col overflow-hidden h-full"
    >
      {/* Header */}
      {view === 'main' ? (
        <div className="flex border-b border-space-border shrink-0">
          {TABS.map((tab) => {
            const disabled = tab === 'Preview' && isPreviewDisabled
            return (
              <button
                key={tab}
                onClick={() => handleTabClick(tab)}
                disabled={disabled}
                className={`flex-1 py-2.5 text-xs font-semibold uppercase tracking-widest transition-colors
                  ${activeTab === tab && !disabled
                    ? 'text-purple-400 border-b-2 border-purple-400 bg-white/5'
                    : disabled
                    ? 'text-space-dim/30 cursor-not-allowed'
                    : 'text-space-dim hover:text-space-text'
                  }`}
              >
                {tab}
              </button>
            )
          })}
        </div>
      ) : (
        <div className="flex items-center gap-2 px-4 py-3 border-b border-space-border shrink-0">
          <button
            onClick={() => setView(view === 'createProfile' ? 'profiles' : 'main')}
            className="text-space-dim hover:text-purple-400 transition-colors"
          >
            <BackArrow />
          </button>
          <span className="text-xs font-semibold uppercase tracking-widest text-space-dim">
            {view === 'profiles' ? 'Profile Settings' : 'Create Profile'}
          </span>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 relative">
        <AnimatePresence mode="wait">
          <motion.div
            key={view === 'main' ? activeTab : view}
            variants={slideVariants}
            initial="enter"
            animate="center"
            exit="exit"
            transition={{ duration: 0.2 }}
          >
            {view === 'main' && activeTab === 'User' && (
              <UserTab onProfileSettings={() => setView('profiles')} />
            )}
            {view === 'main' && activeTab === 'Tasks' && (
              <TasksTab jobs={jobs} processingKeys={processingKeys} />
            )}
            {view === 'main' && activeTab === 'Advanced' && <AdvancedTab />}
            {view === 'main' && activeTab === 'Preview' && (
              <PreviewTab job={selectedJob} />
            )}
            {view === 'profiles' && (
              <ProfileList
                onCreateProfile={() => setView('createProfile')}
              />
            )}
            {view === 'createProfile' && (
              <CreateProfile
                onBack={() => setView('profiles')}
                onCreated={() => setView('profiles')}
              />
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </motion.div>
  )
}
```

- [ ] **Step 2: Check in browser**

Click a job card in the Pipeline. Expected:
- Settings widget switches to Preview tab
- Job title, metadata row, Raw/Extracted toggle visible
- Raw description renders as text
- If the job has extraction data, "Extracted" button is enabled; click it and see structured fields
- Pressing Escape clears selection and dims Preview tab

Check User tab → "Profile Settings" → shows profile list with "+ Create Profile" button.
Check Advanced tab → shows providers (if any configured) with editable fields.
Check Tasks tab → "No active tasks." when processingKeys is empty.

- [ ] **Step 3: Commit**

```bash
git add react-dashboard/src/components/widgets/Settings.jsx
git commit -m "[feat] Rewrite Settings widget with live Preview, User, Tasks, and Advanced tabs"
```

---

### Task 12: Build React app and verify production serving

**Files:**
- No new files — verification only

- [ ] **Step 1: Build the React app**

```bash
cd react-dashboard
npm run build
```

Expected: `react-dashboard/dist/` created with `index.html` and `assets/` directory. No build errors.

- [ ] **Step 2: Verify FastAPI serves the build**

Start the FastAPI server (no Vite dev server):

```bash
cd C:\Users\barlo\Projects\auto_apply
python -m uvicorn web.main:app --port 8080
```

Open `http://localhost:8080`. Expected: React dashboard loads (not the old Alpine.js page). Check browser network tab — `/api/jobs` returns real data, `/api/events` shows as a pending SSE connection.

- [ ] **Step 3: Verify SPA routes**

Navigate to `http://localhost:8080/config` and `http://localhost:8080/setup`. Expected: both serve the same React SPA without a 404.

- [ ] **Step 4: Verify SSE**

Open `http://localhost:8080`, then in a separate terminal trigger the scraper:

```bash
curl -X POST http://localhost:8080/api/scraper/run
```

Expected: new job cards appear in the Inbox tab of the Pipeline without a page refresh.

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/dist
git commit -m "[chore] Add initial React production build"
```

> **Note:** `react-dashboard/dist/` should be added to `.gitignore` for ongoing development if you prefer to build on deploy. Add `react-dashboard/dist/` to `.gitignore` and skip this commit if so.
