# Sort, Salary, Date/Cards, Search Persistence — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add sort-by (Score/Date/Salary), salary parsing in description extraction, salary+date on job cards, and fix search to persist across tab switches.

**Architecture:** Backend adds two Float columns (`ext_salary_min`, `ext_salary_max`) to the Job model and parses them from the LLM extraction JSON. `serialize()` gains `applied_at`, `ext_salary_min`, `ext_salary_max`. Frontend adds a sort control above the search bar, a `parseSalary` fallback utility, a metadata row on job cards, and removes the search-clear-on-tab-switch behaviour.

**Tech Stack:** Python/SQLAlchemy/SQLite (backend), React + Tailwind (frontend).

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `core/job.py` | Modify | Add `ext_salary_min`, `ext_salary_max` columns; add `applied_at`, `ext_salary_min`, `ext_salary_max` to `serialize()` |
| `web/routers/jobs.py` | Modify | Parse `salary_min`/`salary_max` from extraction JSON in `_do_extract_description` |
| `react-dashboard/src/components/shared/JobCard.jsx` | Modify | Add salary + date metadata row; accept new props |
| `react-dashboard/src/components/widgets/Pipeline.jsx` | Modify | Add sort control + `sortedJobs` useMemo; pass new props; remove search-clear on tab switch |
| `auto_apply.db` | Migrate | `ALTER TABLE jobs ADD COLUMN ext_salary_min REAL` and `ext_salary_max REAL` |

---

## Task 1: Add salary columns to Job model and serialize()

**Files:**
- Modify: `core/job.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/core/test_job.py`:

```python
def test_job_has_ext_salary_columns(db_session):
    """ext_salary_min and ext_salary_max exist on the model."""
    from core.job import Job, JobState
    job = Job(
        job_key="sal-test",
        source="test",
        url="https://example.com/sal",
        state=JobState.NEW.value,
        ext_salary_min=80000.0,
        ext_salary_max=100000.0,
    )
    db_session.add(job)
    db_session.commit()
    fetched = db_session.query(Job).filter_by(job_key="sal-test").first()
    assert fetched.ext_salary_min == 80000.0
    assert fetched.ext_salary_max == 100000.0


def test_serialize_includes_salary_and_applied_at(db_session):
    """serialize() includes ext_salary_min, ext_salary_max, and applied_at."""
    from core.job import Job, JobState
    job = Job(
        job_key="ser-sal-test",
        source="test",
        url="https://example.com/ser-sal",
        state=JobState.NEW.value,
        ext_salary_min=70000.0,
        ext_salary_max=90000.0,
        applied_at="2026-05-01T12:00:00+00:00",
    )
    db_session.add(job)
    db_session.commit()
    result = job.serialize()
    assert result["ext_salary_min"] == 70000.0
    assert result["ext_salary_max"] == 90000.0
    assert result["applied_at"] == "2026-05-01T12:00:00+00:00"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd C:\Users\barlo\Projects\auto_apply && .venv\Scripts\python -m pytest tests/core/test_job.py::test_job_has_ext_salary_columns tests/core/test_job.py::test_serialize_includes_salary_and_applied_at -v
```

Expected: FAIL — `ext_salary_min` attribute error or column missing.

- [ ] **Step 3: Add columns to Job model**

In `core/job.py`, after the `ext_company_signals` line (around line 113), add:

```python
    ext_salary_min = Column(Float)
    ext_salary_max = Column(Float)
```

- [ ] **Step 4: Add fields to serialize()**

In `core/job.py`, in the `serialize()` method, add these three entries (after `"score_justification": justification,` is fine):

```python
            "applied_at": self.applied_at or "",
            "ext_salary_min": self.ext_salary_min,
            "ext_salary_max": self.ext_salary_max,
```

- [ ] **Step 5: Run tests**

```bash
cd C:\Users\barlo\Projects\auto_apply && .venv\Scripts\python -m pytest tests/core/test_job.py::test_job_has_ext_salary_columns tests/core/test_job.py::test_serialize_includes_salary_and_applied_at -v
```

Expected: PASS. If they fail with a DB column error, run the migration in Task 2 first then re-run.

- [ ] **Step 6: Commit**

```bash
git add core/job.py tests/core/test_job.py
git commit -m "[feat] Add ext_salary_min/max columns and applied_at to Job model and serialize"
```

---

## Task 2: Migrate the live database

**Files:**
- Modify: `auto_apply.db` (via Python one-liner)

> **Note:** This must run against the actual `auto_apply.db` file in the project root. It is safe to run multiple times — SQLite will error on the second run if the column already exists, which you can ignore.

- [ ] **Step 1: Run the migration**

```bash
cd C:\Users\barlo\Projects\auto_apply && .venv\Scripts\python -c "
import sqlite3
conn = sqlite3.connect('auto_apply.db')
try:
    conn.execute('ALTER TABLE jobs ADD COLUMN ext_salary_min REAL')
    print('Added ext_salary_min')
except Exception as e:
    print(f'ext_salary_min: {e}')
try:
    conn.execute('ALTER TABLE jobs ADD COLUMN ext_salary_max REAL')
    print('Added ext_salary_max')
except Exception as e:
    print(f'ext_salary_max: {e}')
conn.commit()
conn.close()
print('Done')
"
```

Expected output: `Added ext_salary_min`, `Added ext_salary_max`, `Done`

- [ ] **Step 2: Update db/CONTEXT.md migration history**

In `db/CONTEXT.md`, add two rows to the migration history table:

```markdown
| `ext_salary_min` | `jobs` | REAL | 2026-05-26 |
| `ext_salary_max` | `jobs` | REAL | 2026-05-26 |
```

- [ ] **Step 3: Commit**

```bash
git add db/CONTEXT.md
git commit -m "[chore] Migrate jobs table: add ext_salary_min, ext_salary_max columns"
```

---

## Task 3: Parse salary from extraction JSON in `_do_extract_description`

**Files:**
- Modify: `web/routers/jobs.py`
- Test: `tests/web/test_jobs_api.py`

- [ ] **Step 1: Write failing test**

Add to `tests/web/test_jobs_api.py`:

```python
def test_do_extract_description_parses_salary(db_session, monkeypatch):
    """_do_extract_description sets ext_salary_min and ext_salary_max from JSON."""
    from web.routers.jobs import _do_extract_description
    from core.job import Job, JobState
    from unittest.mock import MagicMock

    job = _make_job(db_session, "salparse", JobState.NEW)

    # Patch User, client, and the LLM call
    mock_user = MagicMock()
    mock_user.resolve_prompt.return_value = "extract this"
    mock_user.prompt_extraction_model = "gpt-4"
    monkeypatch.setattr("web.routers.jobs.User.load", lambda db: mock_user)
    monkeypatch.setattr(
        "web.routers.jobs.get_client_for_profile",
        lambda user, model: (MagicMock(), "gpt-4"),
    )
    monkeypatch.setattr(
        "web.routers.jobs._call_llm_for_extraction",
        lambda client, model, prompt: '{"seniority":"mid","role_type":"engineer","domain":"software","work_arrangement":"remote","employment_type":"full-time","required_skills":[],"preferred_skills":[],"tech_stack":[],"key_responsibilities":[],"company_signals":[],"salary_min":80000,"salary_max":120000}',
    )

    _do_extract_description(job, db_session)

    db_session.refresh(job)
    assert job.ext_salary_min == 80000.0
    assert job.ext_salary_max == 120000.0


def test_do_extract_description_handles_null_salary(db_session, monkeypatch):
    """_do_extract_description sets salary to None when undisclosed."""
    from web.routers.jobs import _do_extract_description
    from core.job import Job, JobState
    from unittest.mock import MagicMock

    job = _make_job(db_session, "salnull", JobState.NEW)

    mock_user = MagicMock()
    mock_user.resolve_prompt.return_value = "extract this"
    mock_user.prompt_extraction_model = "gpt-4"
    monkeypatch.setattr("web.routers.jobs.User.load", lambda db: mock_user)
    monkeypatch.setattr(
        "web.routers.jobs.get_client_for_profile",
        lambda user, model: (MagicMock(), "gpt-4"),
    )
    monkeypatch.setattr(
        "web.routers.jobs._call_llm_for_extraction",
        lambda client, model, prompt: '{"seniority":"mid","role_type":"engineer","domain":"software","work_arrangement":"remote","employment_type":"full-time","required_skills":[],"preferred_skills":[],"tech_stack":[],"key_responsibilities":[],"company_signals":[]}',
    )

    _do_extract_description(job, db_session)

    db_session.refresh(job)
    assert job.ext_salary_min is None
    assert job.ext_salary_max is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd C:\Users\barlo\Projects\auto_apply && .venv\Scripts\python -m pytest tests/web/test_jobs_api.py::test_do_extract_description_parses_salary tests/web/test_jobs_api.py::test_do_extract_description_handles_null_salary -v
```

Expected: FAIL — `ext_salary_min` not set.

- [ ] **Step 3: Add salary parsing to `_do_extract_description`**

In `web/routers/jobs.py`, in the `_do_extract_description` function, after the `ext_company_signals` line (after line 352), add:

```python
    salary_min = data.get("salary_min")
    salary_max = data.get("salary_max")
    job.ext_salary_min = float(salary_min) if salary_min is not None else None
    job.ext_salary_max = float(salary_max) if salary_max is not None else None
```

- [ ] **Step 4: Run tests**

```bash
cd C:\Users\barlo\Projects\auto_apply && .venv\Scripts\python -m pytest tests/web/test_jobs_api.py::test_do_extract_description_parses_salary tests/web/test_jobs_api.py::test_do_extract_description_handles_null_salary -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/routers/jobs.py tests/web/test_jobs_api.py
git commit -m "[feat] Parse salary_min/salary_max from description extraction JSON"
```

---

## Task 4: Add salary + date metadata row to JobCard

**Files:**
- Modify: `react-dashboard/src/components/shared/JobCard.jsx`

- [ ] **Step 1: Update JobCard with new props and metadata row**

Read the current file, then replace the `export default function JobCard` with the following. The changes are: (a) add `appliedAt`, `scrapedAt`, `salaryMin`, `salaryMax`, `salaryRaw` props; (b) add helper functions `formatSalary` and `formatDate`; (c) render a metadata row.

```jsx
export default function JobCard({ title, company, statusIcon, docs = {}, selected = false, state, score, appliedAt, scrapedAt, salaryMin, salaryMax, salaryRaw }) {
  const hasResume = docs.resume
  const hasCoverLetter = docs.coverLetter

  function ScorePill() {
    if (score == null) return null
    const pct = Math.round(score * 100)
    const color = pct >= 70 ? 'text-green-400' : pct >= 40 ? 'text-yellow-400' : 'text-red-400'
    return <span className={`text-xs font-semibold shrink-0 ${color}`}>{pct}%</span>
  }

  function formatSalary() {
    // Use processed ext values if available
    if (salaryMin != null) {
      const fmt = (n) => n >= 1000 ? `$${Math.round(n / 1000)}K` : `$${n}`
      if (salaryMax != null && salaryMax !== salaryMin) return `${fmt(salaryMin)}–${fmt(salaryMax)}`
      return fmt(salaryMin)
    }
    // Fall back to parsing raw scraped salary string
    if (salaryRaw) {
      const nums = salaryRaw.replace(/,/g, '').match(/\d+(?:\.\d+)?[kK]?/g)
      if (nums && nums.length > 0) {
        const toNum = (s) => parseFloat(s) * (/[kK]$/.test(s) ? 1000 : 1)
        const values = nums.map(toNum).filter(n => n > 0)
        if (values.length === 0) return salaryRaw
        const min = Math.min(...values)
        const max = Math.max(...values)
        const fmt = (n) => n >= 1000 ? `$${Math.round(n / 1000)}K` : `$${n}`
        return min === max ? fmt(min) : `${fmt(min)}–${fmt(max)}`
      }
      // Non-numeric string (e.g. "Competitive") — show as-is if short enough
      if (salaryRaw.length <= 20) return salaryRaw
    }
    return null
  }

  function formatDate() {
    const iso = appliedAt || scrapedAt
    if (!iso) return null
    const label = appliedAt ? 'Applied' : 'Added'
    const d = new Date(iso)
    const formatted = d.toLocaleDateString('en-US', { month: 'numeric', day: 'numeric', year: '2-digit' })
    return `${label} ${formatted}`
  }

  const salaryText = formatSalary()
  const dateText = formatDate()
  const hasMetadata = salaryText || dateText

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
        {hasMetadata && (
          <div className="flex justify-between mt-0.5">
            <span className="text-xs text-space-dim">{salaryText ?? ''}</span>
            <span className="text-xs text-space-dim">{dateText ?? ''}</span>
          </div>
        )}
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
git commit -m "[feat] Add salary and date metadata row to JobCard"
```

---

## Task 5: Pass new props from Pipeline to JobCard

**Files:**
- Modify: `react-dashboard/src/components/widgets/Pipeline.jsx`

- [ ] **Step 1: Add new props to JobCard render in JobList**

In `Pipeline.jsx`, inside the `JobList` function, update the `<JobCard ...>` element to pass the five new props. The full updated `<JobCard>` element:

```jsx
<JobCard
  title={job.title || '(no title)'}
  company={job.company || ''}
  state={job.state}
  score={job.final_score ?? null}
  appliedAt={job.applied_at || null}
  scrapedAt={job.scraped_at || null}
  salaryMin={job.ext_salary_min ?? null}
  salaryMax={job.ext_salary_max ?? null}
  salaryRaw={job.salary || null}
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
git commit -m "[feat] Pass salary and date props from Pipeline to JobCard"
```

---

## Task 6: Add sort control and fix search persistence in Pipeline

**Files:**
- Modify: `react-dashboard/src/components/widgets/Pipeline.jsx`

- [ ] **Step 1: Add `parseSalaryForSort` utility, `sortBy` state, `sortedJobs` useMemo, sort UI, and fix `handleTabChange`**

Read the current file first. Then replace the entire `export default function Pipeline` with the following:

```jsx
const SORT_OPTIONS = ['Score', 'Date', 'Salary']

function parseSalaryForSort(job) {
  if (job.ext_salary_min != null) return job.ext_salary_min
  if (!job.salary) return null
  const nums = job.salary.replace(/,/g, '').match(/\d+(?:\.\d+)?[kK]?/g)
  if (!nums || nums.length === 0) return null
  const toNum = (s) => parseFloat(s) * (/[kK]$/i.test(s) ? 1000 : 1)
  const values = nums.map(toNum).filter(n => n > 0)
  return values.length > 0 ? Math.min(...values) : null
}

export default function Pipeline({ jobs = [], processingKeys = new Set(), selectedJob, onJobSelect }) {
  const [activeTab, setActiveTab] = useState('Inbox')
  const [searchInbox, setSearchInbox] = useState('')
  const [searchArchives, setSearchArchives] = useState('')
  const [sortBy, setSortBy] = useState('Score')

  const tabJobs = useMemo(() => ({
    Inbox: jobs.filter((j) => INBOX_STATES.has(j.state)),
    Archives: jobs.filter((j) => ARCHIVE_STATES.has(j.state)),
  }), [jobs])

  const sortedJobs = useMemo(() => {
    const list = [...(tabJobs[activeTab] || [])]
    if (sortBy === 'Score') {
      return list.sort((a, b) => {
        if (a.final_score == null && b.final_score == null) return 0
        if (a.final_score == null) return 1
        if (b.final_score == null) return -1
        return b.final_score - a.final_score
      })
    }
    if (sortBy === 'Date') {
      return list.sort((a, b) => {
        const da = a.applied_at || a.scraped_at || ''
        const db_ = b.applied_at || b.scraped_at || ''
        if (!da && !db_) return 0
        if (!da) return 1
        if (!db_) return -1
        return da < db_ ? 1 : da > db_ ? -1 : 0
      })
    }
    if (sortBy === 'Salary') {
      return list.sort((a, b) => {
        const sa = parseSalaryForSort(a)
        const sb = parseSalaryForSort(b)
        if (sa == null && sb == null) return 0
        if (sa == null) return 1
        if (sb == null) return -1
        return sb - sa
      })
    }
    return list
  }, [tabJobs, activeTab, sortBy])

  const searchQuery = activeTab === 'Inbox' ? searchInbox : searchArchives
  const setSearchQuery = activeTab === 'Inbox' ? setSearchInbox : setSearchArchives

  const visibleJobs = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return sortedJobs
    return sortedJobs.filter((j) =>
      (j.title || '').toLowerCase().includes(q) ||
      (j.company || '').toLowerCase().includes(q)
    )
  }, [sortedJobs, searchQuery])

  function handleTabChange(tab) {
    setActiveTab(tab)
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

      {/* Sort */}
      <div className="flex gap-3 px-4 pt-3 shrink-0">
        {SORT_OPTIONS.map((opt) => (
          <button
            key={opt}
            onClick={() => setSortBy(opt)}
            className={`text-xs font-medium pb-0.5 transition-colors
              ${sortBy === opt
                ? 'text-purple-400 border-b border-purple-400'
                : 'text-space-dim hover:text-space-text'
              }`}
          >
            {opt}
          </button>
        ))}
      </div>

      {/* Search */}
      <div className="px-4 pt-2 shrink-0">
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

- [ ] **Step 2: Commit**

```bash
git add react-dashboard/src/components/widgets/Pipeline.jsx
git commit -m "[feat] Add sort control (Score/Date/Salary), fix search persistence on tab switch"
```

---

## Done

Verify end-to-end:
1. Start the app (`start.bat`) and open the dashboard.
2. **Sort:** Click Score / Date / Salary — confirm list reorders. Scored jobs sort by score, most recent jobs sort by date, salary-bearing jobs sort by salary, nulls go to the bottom.
3. **Date on cards:** Each card shows "Applied MM/DD/YY" or "Added MM/DD/YY".
4. **Salary on cards:** Jobs with a raw salary string show a formatted value. Jobs with `ext_salary_min` set (after description extraction runs) show the processed value.
5. **Search persistence:** Type a query in Inbox, switch to Archives and back — query is retained.
6. **Extraction salary:** Stage a job with a salary in the description, run description extraction, confirm `ext_salary_min`/`ext_salary_max` populate on the card.
