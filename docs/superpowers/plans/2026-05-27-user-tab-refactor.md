# User Tab Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the User tab to show a personalized home view (welcome, activity bar charts, pie chart, switch-user button) when an active profile exists; fall back to the profile list when no active profile is set.

**Architecture:** Add two new DB columns (`resume_generated_at`, `cover_generated_at`) to Job; add a session-start timestamp to `core/session_cost`; create `GET /api/stats?window=...` that returns pre-aggregated daily buckets; build a self-contained `UserHome` React component (using recharts) that fetches its own data and replaces the raw `ProfileCards` render in Settings.

**Tech Stack:** Python/FastAPI/SQLAlchemy (backend), React/recharts/Tailwind (frontend), SQLite ISO string date filtering

---

> **Note:** `tests/web/test_jobs_api.py::test_get_description_html_returns_html` has a pre-existing failure unrelated to this work. Do not fix it here.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `core/session_cost.py` | Add `_session_start` datetime + `get_session_start()` |
| Modify | `core/job.py` | Add `resume_generated_at`, `cover_generated_at` columns; set in `generate_resume_pdf`/`generate_cover_pdf`; include in `serialize()` |
| Create | `web/routers/stats.py` | `GET /api/stats?window=` endpoint |
| Modify | `web/main.py` | Register stats router |
| Modify | `react-dashboard/src/api.js` | Add `getStats(window)` |
| Create | `react-dashboard/src/components/widgets/UserHome.jsx` | Welcome heading, time toggle, bar chart, pie chart, switch-user flow |
| Modify | `react-dashboard/src/components/widgets/Settings.jsx` | Replace `ProfileCards` direct render with `UserHome` in the User tab |
| Create | `tests/web/test_stats_api.py` | Stats endpoint tests |

---

### Task 1: Add session_start to core/session_cost.py

**Files:**
- Modify: `core/session_cost.py`
- Test: `tests/core/test_session_cost.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/core/test_session_cost.py`:

```python
from datetime import datetime, timezone

def test_get_session_start_returns_datetime():
    start = sc.get_session_start()
    assert isinstance(start, datetime)
    assert start.tzinfo is not None

def test_get_session_start_is_stable():
    assert sc.get_session_start() is sc.get_session_start()
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/core/test_session_cost.py::test_get_session_start_returns_datetime tests/core/test_session_cost.py::test_get_session_start_is_stable -v
```

Expected: FAIL with `AttributeError: module 'core.session_cost' has no attribute 'get_session_start'`

- [ ] **Step 3: Implement**

Replace the full contents of `core/session_cost.py`:

```python
from __future__ import annotations

import threading
from datetime import datetime, timezone

_lock = threading.Lock()
_total: float = 0.0
_session_start: datetime = datetime.now(timezone.utc)


def add_cost(cost: float) -> None:
    global _total
    with _lock:
        _total += cost


def get_total() -> float:
    with _lock:
        return _total


def get_session_start() -> datetime:
    return _session_start


def reset() -> None:
    global _total
    with _lock:
        _total = 0.0
```

- [ ] **Step 4: Run all session_cost tests**

```
pytest tests/core/test_session_cost.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```
git add core/session_cost.py tests/core/test_session_cost.py
git commit -m "[feat] Add session_start timestamp to session_cost module"
```

---

### Task 2: Add resume_generated_at and cover_generated_at to Job

**Files:**
- Modify: `core/job.py`
- Test: `tests/core/test_job.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/core/test_job.py` (find the existing `db_session` fixture in that file and add alongside it):

```python
def test_resume_generated_at_set_on_generate_pdf(db_session, tmp_path):
    """generate_resume_pdf sets resume_generated_at to a UTC ISO string."""
    from core.job import Job
    job = Job(
        job_key="test-rga-1",
        source="test",
        url="https://example.com/1",
        state="new",
    )
    db_session.add(job)
    db_session.commit()
    # Simulate what generate_resume_pdf does (without running actual PDF render)
    from datetime import datetime, timezone
    job.resume_path = str(tmp_path / "test.pdf")
    job.resume_generated_at = datetime.now(timezone.utc).isoformat()
    db_session.commit()
    db_session.refresh(job)
    assert job.resume_generated_at is not None
    assert "T" in job.resume_generated_at


def test_cover_generated_at_set_on_generate_pdf(db_session, tmp_path):
    """generate_cover_pdf sets cover_generated_at to a UTC ISO string."""
    from core.job import Job
    job = Job(
        job_key="test-cga-1",
        source="test",
        url="https://example.com/2",
        state="new",
    )
    db_session.add(job)
    db_session.commit()
    from datetime import datetime, timezone
    job.cover_path = str(tmp_path / "test.pdf")
    job.cover_generated_at = datetime.now(timezone.utc).isoformat()
    db_session.commit()
    db_session.refresh(job)
    assert job.cover_generated_at is not None
    assert "T" in job.cover_generated_at
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/core/test_job.py::test_resume_generated_at_set_on_generate_pdf tests/core/test_job.py::test_cover_generated_at_set_on_generate_pdf -v
```

Expected: FAIL with `AttributeError` or column error

- [ ] **Step 3: Add columns to Job model in core/job.py**

Find the block containing `resume_path` and `cover_path` (around line 118) and add two lines after `cover_path`:

```python
    resume_path = Column(String)
    cover_path = Column(String)
    resume_generated_at = Column(String)
    cover_generated_at = Column(String)
```

- [ ] **Step 4: Set resume_generated_at in generate_resume_pdf**

In `generate_resume_pdf` (around line 610), find `self.resume_path = str(pdf_path)` and add the timestamp line immediately after it, before `db.commit()`:

```python
        self.resume_path = str(pdf_path)
        self.resume_generated_at = datetime.now(timezone.utc).isoformat()
        db.commit()
```

- [ ] **Step 5: Set cover_generated_at in generate_cover_pdf**

In `generate_cover_pdf` (around line 634), find `self.cover_path = str(pdf_path)` and add the timestamp line immediately after it, before `db.commit()`:

```python
        self.cover_path = str(pdf_path)
        self.cover_generated_at = datetime.now(timezone.utc).isoformat()
        db.commit()
```

- [ ] **Step 6: Add fields to serialize()**

In `serialize()` (around line 745), add after `"cover_path": self.cover_path,`:

```python
            "resume_path": self.resume_path,
            "cover_path": self.cover_path,
            "resume_generated_at": self.resume_generated_at or "",
            "cover_generated_at": self.cover_generated_at or "",
```

(Replace the existing `resume_path`/`cover_path` lines — don't duplicate them.)

- [ ] **Step 7: Run tests**

```
pytest tests/core/test_job.py -v
```

Expected: all PASS

- [ ] **Step 8: Commit**

```
git add core/job.py tests/core/test_job.py
git commit -m "[feat] Add resume_generated_at and cover_generated_at to Job model"
```

---

### Task 3: Create GET /api/stats endpoint

**Files:**
- Create: `web/routers/stats.py`
- Modify: `web/main.py`
- Test: `tests/web/test_stats_api.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/web/test_stats_api.py`:

```python
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db, Base
from core.job import Job
import core.user  # noqa: F401
from web.main import app


@pytest.fixture
def db_session():
    import core.job  # noqa: F401
    import core.user  # noqa: F401
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_job(db, key, scraped_at, state="new", resume_gen=None, cover_gen=None):
    job = Job(
        job_key=key,
        source="test",
        url=f"https://example.com/{key}",
        state=state,
        scraped_at=scraped_at,
        resume_generated_at=resume_gen,
        cover_generated_at=cover_gen,
    )
    db.add(job)
    db.flush()
    return job


def test_stats_all_time_returns_bars_and_by_state(client, db_session):
    now = datetime.now(timezone.utc)
    _make_job(db_session, "j1", now.isoformat(), state="applied",
              resume_gen=now.isoformat(), cover_gen=now.isoformat())
    _make_job(db_session, "j2", now.isoformat(), state="new")
    db_session.commit()

    r = client.get("/api/stats?window=all_time")
    assert r.status_code == 200
    data = r.json()
    assert "bars" in data
    assert "by_state" in data
    total_scraped = sum(b["scraped"] for b in data["bars"])
    assert total_scraped == 2
    total_resumes = sum(b["resumes"] for b in data["bars"])
    assert total_resumes == 1
    total_covers = sum(b["covers"] for b in data["bars"])
    assert total_covers == 1


def test_stats_by_state_counts_correctly(client, db_session):
    now = datetime.now(timezone.utc).isoformat()
    _make_job(db_session, "s1", now, state="new")
    _make_job(db_session, "s2", now, state="new")
    _make_job(db_session, "s3", now, state="applied")
    db_session.commit()

    r = client.get("/api/stats?window=all_time")
    data = r.json()
    assert data["by_state"]["new"] == 2
    assert data["by_state"]["applied"] == 1


def test_stats_today_filters_by_day(client, db_session):
    today = datetime.now(timezone.utc)
    old = (today - timedelta(days=3)).isoformat()
    _make_job(db_session, "t1", today.isoformat(), state="new")
    _make_job(db_session, "t2", old, state="new")
    db_session.commit()

    r = client.get("/api/stats?window=today")
    data = r.json()
    total = sum(b["scraped"] for b in data["bars"])
    assert total == 1


def test_stats_week_filters_last_7_days(client, db_session):
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(days=3)).isoformat()
    old = (now - timedelta(days=10)).isoformat()
    _make_job(db_session, "w1", recent, state="new")
    _make_job(db_session, "w2", old, state="new")
    db_session.commit()

    r = client.get("/api/stats?window=week")
    data = r.json()
    total = sum(b["scraped"] for b in data["bars"])
    assert total == 1


def test_stats_invalid_window_returns_400(client):
    r = client.get("/api/stats?window=bogus")
    assert r.status_code == 400


def test_stats_empty_db_returns_empty_bars(client):
    r = client.get("/api/stats?window=all_time")
    assert r.status_code == 200
    data = r.json()
    assert data["bars"] == []
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/web/test_stats_api.py -v
```

Expected: FAIL (router doesn't exist yet)

- [ ] **Step 3: Create web/routers/stats.py**

```python
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from core.job import Job
from core.session_cost import get_session_start
from db.database import get_db

router = APIRouter(prefix="/api")

_VALID_WINDOWS = {"session", "today", "week", "all_time"}
_ALL_STATES = ["new", "pending_review", "ready", "applied", "contact", "rejected"]


def _date_label(iso: str) -> str:
    """Extract 'Mon DD' label from ISO datetime string."""
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%b %-d")
    except (ValueError, TypeError):
        return iso[:10]


@router.get("/stats")
def get_stats(
    window: str = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    if window not in _VALID_WINDOWS:
        raise HTTPException(status_code=400, detail=f"Invalid window: {window!r}. Must be one of {sorted(_VALID_WINDOWS)}")

    now = datetime.now(timezone.utc)

    if window == "session":
        cutoff = get_session_start()
    elif window == "today":
        cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif window == "week":
        cutoff = now - timedelta(days=7)
    else:  # all_time
        cutoff = None

    # Fetch jobs in window for bar data
    query = db.query(Job)
    if cutoff is not None:
        cutoff_iso = cutoff.isoformat()
        query = query.filter(Job.scraped_at >= cutoff_iso)
    jobs_in_window = query.all()

    # Bucket scraped/resumes/covers by date label
    scraped_by_date: dict[str, int] = defaultdict(int)
    resumes_by_date: dict[str, int] = defaultdict(int)
    covers_by_date: dict[str, int] = defaultdict(int)

    for job in jobs_in_window:
        if not job.scraped_at:
            continue
        label = _date_label(job.scraped_at)
        scraped_by_date[label] += 1

    # Documents bucketed by their own generated_at timestamp
    resume_query = db.query(Job).filter(Job.resume_generated_at.isnot(None))
    cover_query = db.query(Job).filter(Job.cover_generated_at.isnot(None))
    if cutoff is not None:
        cutoff_iso = cutoff.isoformat()
        resume_query = resume_query.filter(Job.resume_generated_at >= cutoff_iso)
        cover_query = cover_query.filter(Job.cover_generated_at >= cutoff_iso)

    for job in resume_query.all():
        label = _date_label(job.resume_generated_at)
        resumes_by_date[label] += 1

    for job in cover_query.all():
        label = _date_label(job.cover_generated_at)
        covers_by_date[label] += 1

    # Merge all date labels and sort chronologically
    all_labels = sorted(
        set(scraped_by_date) | set(resumes_by_date) | set(covers_by_date),
        key=lambda lbl: lbl,
    )

    bars = [
        {
            "label": lbl,
            "scraped": scraped_by_date.get(lbl, 0),
            "resumes": resumes_by_date.get(lbl, 0),
            "covers": covers_by_date.get(lbl, 0),
        }
        for lbl in all_labels
    ]

    # by_state counts across ALL jobs (pipeline snapshot, not window-filtered)
    by_state: dict[str, int] = {s: 0 for s in _ALL_STATES}
    for state, count in db.query(Job.state, db.query(Job).filter(Job.state == Job.state).count.__class__):
        pass  # replaced below
    for s in _ALL_STATES:
        by_state[s] = db.query(Job).filter(Job.state == s).count()

    return {"bars": bars, "by_state": by_state}
```

Wait — the `by_state` block above has dead code. Replace the stats.py with the clean version:

```python
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from core.job import Job
from core.session_cost import get_session_start
from db.database import get_db

router = APIRouter(prefix="/api")

_VALID_WINDOWS = {"session", "today", "week", "all_time"}
_ALL_STATES = ["new", "pending_review", "ready", "applied", "contact", "rejected"]


def _date_label(iso: str) -> str:
    """Return 'Mon D' label from ISO datetime string."""
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%b %-d")
    except (ValueError, TypeError):
        return iso[:10]


@router.get("/stats")
def get_stats(
    window: str = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    if window not in _VALID_WINDOWS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid window: {window!r}. Must be one of {sorted(_VALID_WINDOWS)}",
        )

    now = datetime.now(timezone.utc)
    if window == "session":
        cutoff = get_session_start()
    elif window == "today":
        cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif window == "week":
        cutoff = now - timedelta(days=7)
    else:
        cutoff = None

    cutoff_iso = cutoff.isoformat() if cutoff else None

    # Scraped: bucket by scraped_at date
    scraped_q = db.query(Job)
    if cutoff_iso:
        scraped_q = scraped_q.filter(Job.scraped_at >= cutoff_iso)

    scraped_by_date: dict[str, int] = defaultdict(int)
    for job in scraped_q.all():
        if job.scraped_at:
            scraped_by_date[_date_label(job.scraped_at)] += 1

    # Resumes: bucket by resume_generated_at
    resume_q = db.query(Job).filter(Job.resume_generated_at.isnot(None))
    if cutoff_iso:
        resume_q = resume_q.filter(Job.resume_generated_at >= cutoff_iso)

    resumes_by_date: dict[str, int] = defaultdict(int)
    for job in resume_q.all():
        resumes_by_date[_date_label(job.resume_generated_at)] += 1

    # Covers: bucket by cover_generated_at
    cover_q = db.query(Job).filter(Job.cover_generated_at.isnot(None))
    if cutoff_iso:
        cover_q = cover_q.filter(Job.cover_generated_at >= cutoff_iso)

    covers_by_date: dict[str, int] = defaultdict(int)
    for job in cover_q.all():
        covers_by_date[_date_label(job.cover_generated_at)] += 1

    # Merge and sort labels
    all_labels = sorted(
        set(scraped_by_date) | set(resumes_by_date) | set(covers_by_date)
    )
    bars = [
        {
            "label": lbl,
            "scraped": scraped_by_date.get(lbl, 0),
            "resumes": resumes_by_date.get(lbl, 0),
            "covers": covers_by_date.get(lbl, 0),
        }
        for lbl in all_labels
    ]

    # by_state: pipeline snapshot, not window-filtered
    by_state = {s: db.query(Job).filter(Job.state == s).count() for s in _ALL_STATES}

    return {"bars": bars, "by_state": by_state}
```

- [ ] **Step 4: Register router in web/main.py**

Add import after the existing router imports:

```python
from web.routers import stats as stats_router
```

Add the include after the existing router includes:

```python
app.include_router(stats_router.router)
```

- [ ] **Step 5: Run tests**

```
pytest tests/web/test_stats_api.py -v
```

Expected: all PASS

- [ ] **Step 6: Commit**

```
git add web/routers/stats.py web/main.py tests/web/test_stats_api.py
git commit -m "[feat] Add GET /api/stats endpoint with window filtering"
```

---

### Task 4: Install recharts and add getStats to api.js

**Files:**
- Modify: `react-dashboard/package.json` (via npm install)
- Modify: `react-dashboard/src/api.js`

- [ ] **Step 1: Install recharts**

```
cd react-dashboard && npm install recharts
```

Expected: recharts added to `package.json` dependencies

- [ ] **Step 2: Add getStats to api.js**

Add after the `getLlmStatus` export in `react-dashboard/src/api.js`:

```js
export const getStats = (window) => _fetch(`/api/stats?window=${window}`)
```

- [ ] **Step 3: Commit**

```
git add react-dashboard/package.json react-dashboard/package-lock.json react-dashboard/src/api.js
git commit -m "[feat] Install recharts and add getStats API function"
```

---

### Task 5: Build UserHome.jsx

**Files:**
- Create: `react-dashboard/src/components/widgets/UserHome.jsx`

- [ ] **Step 1: Create the component**

Create `react-dashboard/src/components/widgets/UserHome.jsx`:

```jsx
import { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts'
import { getProfiles, getStats } from '../../api'
import ProfileCards from './ProfileCards'

const WINDOWS = [
  { key: 'session', label: 'Session' },
  { key: 'today', label: 'Today' },
  { key: 'week', label: 'Week' },
  { key: 'all_time', label: 'All Time' },
]

const STATE_LABELS = {
  new: 'New',
  pending_review: 'Pending Review',
  ready: 'Ready',
  applied: 'Applied',
  contact: 'In Contact',
  rejected: 'Rejected',
}

const STATE_COLORS = {
  new: '#7c3aed',
  pending_review: '#f59e0b',
  ready: '#3b82f6',
  applied: '#10b981',
  contact: '#06b6d4',
  rejected: '#ef4444',
}

export default function UserHome({ onSelect, onCreateProfile }) {
  const [activeProfile, setActiveProfile] = useState(null)
  const [profilesLoaded, setProfilesLoaded] = useState(false)
  const [showSwitchUser, setShowSwitchUser] = useState(false)
  const [win, setWin] = useState('session')
  const [stats, setStats] = useState(null)
  const [statsLoading, setStatsLoading] = useState(false)
  const [statsError, setStatsError] = useState(null)

  useEffect(() => {
    getProfiles()
      .then(({ profiles, active_id }) => {
        const active = profiles.find((p) => p.id === active_id) ?? null
        setActiveProfile(active)
      })
      .catch(() => setActiveProfile(null))
      .finally(() => setProfilesLoaded(true))
  }, [])

  useEffect(() => {
    if (!activeProfile) return
    setStatsLoading(true)
    setStatsError(null)
    getStats(win)
      .then(setStats)
      .catch(() => setStatsError('Could not load stats'))
      .finally(() => setStatsLoading(false))
  }, [win, activeProfile])

  if (!profilesLoaded) {
    return <p className="text-xs text-space-dim">Loading…</p>
  }

  // No active profile — show profile list directly
  if (!activeProfile) {
    return <ProfileCards onSelect={onSelect} onCreateProfile={onCreateProfile} />
  }

  // Switch User mode
  if (showSwitchUser) {
    return (
      <div className="flex flex-col gap-3">
        <button
          onClick={() => setShowSwitchUser(false)}
          className="flex items-center gap-1.5 text-xs text-space-dim hover:text-purple-400 transition-colors self-start"
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10 12L6 8l4-4" />
          </svg>
          Back
        </button>
        <ProfileCards onSelect={onSelect} onCreateProfile={onCreateProfile} />
      </div>
    )
  }

  const fullName = [activeProfile.first_name, activeProfile.last_name].filter(Boolean).join(' ')
  const displayName = fullName || activeProfile.name || 'there'

  const pieData = stats
    ? Object.entries(STATE_LABELS)
        .map(([key, label]) => ({ name: label, value: stats.by_state[key] ?? 0 }))
        .filter((d) => d.value > 0)
    : []

  return (
    <div className="flex flex-col gap-5">
      {/* Welcome */}
      <div>
        <p className="text-xs text-space-dim uppercase tracking-widest mb-0.5">Welcome back</p>
        <h2 className="text-lg font-semibold text-space-text">{displayName}</h2>
      </div>

      {/* Time controls */}
      <div className="flex gap-1.5">
        {WINDOWS.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setWin(key)}
            className={`px-3 py-1 rounded text-xs font-semibold transition-colors
              ${win === key ? 'bg-purple-600 text-white' : 'text-space-dim hover:text-space-text border border-space-border'}`}
          >
            {label}
          </button>
        ))}
      </div>

      {statsError && (
        <p className="text-xs text-space-dim/60">{statsError}</p>
      )}

      {!statsError && (
        <>
          {/* Bar chart */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-space-dim mb-2">Activity</p>
            {statsLoading && <p className="text-xs text-space-dim">Loading…</p>}
            {!statsLoading && stats && stats.bars.length === 0 && (
              <p className="text-xs text-space-dim">No activity yet.</p>
            )}
            {!statsLoading && stats && stats.bars.length > 0 && (
              <ResponsiveContainer width="100%" height={160}>
                <BarChart data={stats.bars} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                  <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#8888aa' }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: '#8888aa' }} />
                  <Tooltip
                    contentStyle={{ background: '#0f0f1a', border: '1px solid #2a2a4a', borderRadius: 8, fontSize: 11 }}
                    labelStyle={{ color: '#c8c8e8' }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11, color: '#8888aa' }} />
                  <Bar dataKey="scraped" name="Scraped" fill="#7c3aed" radius={[3, 3, 0, 0]} />
                  <Bar dataKey="resumes" name="Resumes" fill="#3b82f6" radius={[3, 3, 0, 0]} />
                  <Bar dataKey="covers" name="Covers" fill="#0d9488" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Pie chart */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-space-dim mb-2">Pipeline</p>
            {statsLoading && <p className="text-xs text-space-dim">Loading…</p>}
            {!statsLoading && stats && pieData.length === 0 && (
              <p className="text-xs text-space-dim">No jobs yet.</p>
            )}
            {!statsLoading && stats && pieData.length > 0 && (
              <div className="flex items-center gap-3">
                <ResponsiveContainer width={120} height={120}>
                  <PieChart>
                    <Pie
                      data={pieData}
                      cx="50%"
                      cy="50%"
                      innerRadius={30}
                      outerRadius={55}
                      dataKey="value"
                      strokeWidth={0}
                    >
                      {pieData.map((entry) => {
                        const stateKey = Object.keys(STATE_LABELS).find((k) => STATE_LABELS[k] === entry.name)
                        return <Cell key={entry.name} fill={STATE_COLORS[stateKey] ?? '#555'} />
                      })}
                    </Pie>
                    <Tooltip
                      contentStyle={{ background: '#0f0f1a', border: '1px solid #2a2a4a', borderRadius: 8, fontSize: 11 }}
                    />
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex flex-col gap-1">
                  {pieData.map((entry) => {
                    const stateKey = Object.keys(STATE_LABELS).find((k) => STATE_LABELS[k] === entry.name)
                    return (
                      <div key={entry.name} className="flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full shrink-0" style={{ background: STATE_COLORS[stateKey] ?? '#555' }} />
                        <span className="text-xs text-space-dim">{entry.name}</span>
                        <span className="text-xs font-medium text-space-text ml-auto pl-2">{entry.value}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        </>
      )}

      {/* Switch User */}
      <button
        onClick={() => setShowSwitchUser(true)}
        className="w-full py-2 rounded-lg border border-space-border text-sm text-space-dim hover:text-space-text hover:border-purple-500/50 transition-colors mt-2"
      >
        Switch User
      </button>
    </div>
  )
}
```

- [ ] **Step 2: Verify no lint errors**

```
cd react-dashboard && npm run build 2>&1 | tail -20
```

Expected: build completes without errors (warnings about recharts peer deps are fine)

- [ ] **Step 3: Commit**

```
git add react-dashboard/src/components/widgets/UserHome.jsx
git commit -m "[feat] Add UserHome component with stats charts and switch-user flow"
```

---

### Task 6: Wire UserHome into Settings.jsx

**Files:**
- Modify: `react-dashboard/src/components/widgets/Settings.jsx`

- [ ] **Step 1: Add UserHome import**

At the top of `react-dashboard/src/components/widgets/Settings.jsx`, add after the existing imports:

```js
import UserHome from './UserHome'
```

- [ ] **Step 2: Extract ProfileCards into its own export**

`ProfileCards` is currently defined in `Settings.jsx` and referenced only there. `UserHome` needs to import it. The cleanest fix: move `ProfileCards` to its own file.

Create `react-dashboard/src/components/widgets/ProfileCards.jsx` by extracting the `ProfileCards` function (lines 844–929 of `Settings.jsx`) along with its imports:

```jsx
import { useState, useEffect } from 'react'
import { getProfiles, setActiveProfile } from '../../api'

// ─── Icons ────────────────────────────────────────────────────────────────────

function BackArrow() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10 12L6 8l4-4" />
    </svg>
  )
}

export default function ProfileCards({ onSelect, onCreateProfile }) {
  const [profiles, setProfiles] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [settingActive, setSettingActive] = useState(null)

  useEffect(() => {
    getProfiles()
      .then((data) => {
        setProfiles(data.profiles ?? [])
        setActiveId(data.active_id ?? null)
      })
      .catch(() => setError('Failed to load profiles'))
      .finally(() => setLoading(false))
  }, [])

  const handleSetActive = async (id) => {
    setSettingActive(id)
    try {
      await setActiveProfile(id)
      setActiveId(id)
      window.dispatchEvent(new CustomEvent('auto-apply:prompt-status-stale'))
    } finally {
      setSettingActive(null)
    }
  }

  if (loading) return <p className="text-xs text-space-dim">Loading…</p>
  if (error) return <p className="text-xs text-red-400">{error}</p>

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        {profiles.length === 0 && (
          <p className="text-sm text-space-dim text-center py-2">
            A user profile is required to use the app — create one below!
          </p>
        )}
        {profiles.map((profile) => (
          <div
            key={profile.id}
            className={`flex items-center gap-2 rounded-lg border border-white/5 border-l-4 bg-white/[0.03]
              ${activeId === profile.id ? 'border-l-purple-500' : 'border-l-transparent'}`}
          >
            <button
              onClick={() => onSelect(profile.id)}
              className="flex-1 flex flex-col gap-0.5 px-3 py-2.5 text-left hover:bg-white/[0.03] transition-colors rounded-lg min-w-0"
            >
              <p className="text-sm font-medium text-space-text">{profile.name || 'Unnamed'}</p>
              {(profile.first_name || profile.last_name) && (
                <p className="text-xs text-space-dim">
                  {[profile.first_name, profile.last_name].filter(Boolean).join(' ')}
                </p>
              )}
            </button>
            <div className="pr-2 shrink-0">
              {activeId === profile.id
                ? <span className="text-xs font-medium text-purple-400">Active</span>
                : (
                  <button
                    onClick={() => handleSetActive(profile.id)}
                    disabled={settingActive === profile.id}
                    className="text-xs text-space-dim hover:text-space-text border border-space-border hover:border-purple-500/50 rounded px-2 py-0.5 transition-colors disabled:opacity-50"
                  >
                    {settingActive === profile.id ? '…' : 'Set Active'}
                  </button>
                )
              }
            </div>
          </div>
        ))}
      </div>
      <button
        onClick={onCreateProfile}
        className={`w-full py-2 rounded-lg border text-sm transition-colors
          ${profiles.length === 0
            ? 'shiny-border border-transparent bg-[#0a0a14] text-purple-300 hover:text-white'
            : 'border-space-border hover:border-purple-500/50 text-space-dim hover:text-space-text'
          }`}
      >
        + Create Profile
      </button>
    </div>
  )
}
```

- [ ] **Step 3: Update Settings.jsx to import from the new file**

In `Settings.jsx`, remove the `ProfileCards` function definition entirely (lines 844–929). Add this import near the top:

```js
import ProfileCards from './ProfileCards'
import UserHome from './UserHome'
```

Remove the now-unused `BackArrow` from `Settings.jsx` only if it's no longer referenced there (it's used in the header back-arrow — keep it if it's still referenced in the header `view !== 'main'` section).

- [ ] **Step 4: Replace ProfileCards render with UserHome in the User tab**

In `Settings.jsx`, find this block:

```jsx
            {view === 'main' && activeTab === 'User' && (
              <ProfileCards
                onSelect={(id) => { setDetailProfileId(id); setView('profileDetail') }}
                onCreateProfile={() => setView('createProfile')}
              />
            )}
```

Replace it with:

```jsx
            {view === 'main' && activeTab === 'User' && (
              <UserHome
                onSelect={(id) => { setDetailProfileId(id); setView('profileDetail') }}
                onCreateProfile={() => setView('createProfile')}
              />
            )}
```

- [ ] **Step 5: Build to verify no errors**

```
cd react-dashboard && npm run build 2>&1 | tail -20
```

Expected: build completes without errors

- [ ] **Step 6: Commit**

```
git add react-dashboard/src/components/widgets/ProfileCards.jsx react-dashboard/src/components/widgets/UserHome.jsx react-dashboard/src/components/widgets/Settings.jsx
git commit -m "[feat] Refactor User tab: show personalized home with stats when active profile exists"
```

---

## Self-Review

**Spec coverage check:**
- ✅ Welcome back message with profile name — Task 5 `UserHome`
- ✅ Time controls: Session, Today, Week, All Time — Tasks 1, 3, 5
- ✅ Bar chart: scraped / resumes / covers — Tasks 2, 3, 5
- ✅ Pie chart: jobs by state — Tasks 3, 5
- ✅ Switch User button → profile list + create profile — Task 5, 6
- ✅ No active profile → falls through to ProfileCards — Task 5
- ✅ resume_generated_at / cover_generated_at columns — Task 2
- ✅ Session start tracked server-side — Task 1
- ✅ recharts installed — Task 4

**Type/name consistency:**
- `getStats` defined in Task 4, used in Task 5 ✅
- `ProfileCards` extracted in Task 6 Step 2, imported in UserHome (Task 5) ✅
- `get_session_start()` defined in Task 1, used in Task 3 ✅
- `resume_generated_at` / `cover_generated_at` defined in Task 2, queried in Task 3 ✅

**Notes on Windows date format:** `strftime("%-d")` uses platform-specific padding removal. On Windows this may need `%#d`. Since the backend runs on Windows in this project, replace `%-d` with `%#d` in `_date_label` in `web/routers/stats.py`. The label is display-only so cross-platform exact match is not required.
