# Flag / Cover Fix / Save As Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add job flagging (DB + API + UI), fix the double greeting line in generated cover letters, and add a "Save As" button to the prompt editor.

**Architecture:** Three independent changes — a DB column + REST endpoint + React toggle for flagging; a one-line prompt edit for the cover fix; an inline filename input wired to the existing `createPromptFile` API for Save As.

**Tech Stack:** Python/FastAPI/SQLAlchemy (backend), React/Tailwind/Framer Motion (frontend), SQLite migrations via raw `ALTER TABLE`.

---

## File Map

| File | Change |
|------|--------|
| `core/job.py` | Add `flagged` column; add `flagged` to `serialize()` |
| `db/database.py` | Add `_migrate_flagged_column()`; call from `init_db()` |
| `web/routers/jobs.py` | Add `PATCH /{job_key}/flag` endpoint |
| `react-dashboard/src/api.js` | Add `flagJob()` helper |
| `react-dashboard/src/components/shared/JobCard.jsx` | Accept `flagged` prop; render flag icon |
| `react-dashboard/src/components/widgets/Pipeline.jsx` | Pass `flagged` prop to `JobCard` |
| `react-dashboard/src/components/widgets/Settings.jsx` | Add flag toggle button in `PreviewTab` info block |
| `prompts/defaults/cover.md` | Remove "address it to" line; add "no greeting" instruction |
| `react-dashboard/src/components/widgets/ProfileDetail.jsx` | Add Save As UI to `PromptModal` footer |
| `tests/web/test_jobs_api.py` | Tests for flag endpoint |

---

## Task 1: Add `flagged` column to Job model and serialize

**Files:**
- Modify: `core/job.py`

- [ ] **Open `core/job.py`.** After line `pending_review_actions = Column(Text, ...)` (the last column in the Artifacts block, around line 126), add:

```python
flagged = Column(Boolean, default=False, nullable=False)
```

The full artifacts block tail should look like:

```python
    pending_review_actions = Column(Text)  # JSON list of action names awaiting review
    flagged = Column(Boolean, default=False, nullable=False)
```

- [ ] **Add `flagged` to `serialize()`.** In `Job.serialize()` (around line 775, just before the closing brace), add the key after `pending_review_actions`:

```python
            "pending_review_actions": json.loads(self.pending_review_actions or "[]"),
            "flagged": bool(self.flagged),
```

- [ ] **Commit.**

```
git add core/job.py
git commit -m "[feat] Add flagged column to Job model"
```

---

## Task 2: DB migration for `flagged`

**Files:**
- Modify: `db/database.py`

- [ ] **Add migration function.** Insert after `_migrate_generated_at_columns()` (around line 153):

```python
def _migrate_flagged_column() -> None:
    """Add flagged column to jobs table if it does not exist."""
    with engine.connect() as conn:
        existing = [r[1] for r in conn.execute(text("PRAGMA table_info(jobs)")).fetchall()]
        if "flagged" not in existing:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN flagged BOOLEAN NOT NULL DEFAULT 0"))
        conn.commit()
```

- [ ] **Call it from `init_db()`.** Add the call after `_migrate_generated_at_columns()`:

```python
    _migrate_generated_at_columns()
    _migrate_flagged_column()
```

- [ ] **Commit.**

```
git add db/database.py
git commit -m "[feat] Add migration for flagged column"
```

---

## Task 3: `PATCH /api/jobs/{job_key}/flag` endpoint

**Files:**
- Modify: `web/routers/jobs.py`
- Test: `tests/web/test_jobs_api.py`

- [ ] **Write the failing tests.** Append to `tests/web/test_jobs_api.py`:

```python
# --- PATCH /api/jobs/{job_key}/flag ---

def test_flag_job(client, db_session):
    _make_job(db_session, "job_flag")
    resp = client.patch("/api/jobs/job_flag/flag", json={"flagged": True})
    assert resp.status_code == 200
    assert resp.json()["flagged"] is True


def test_unflag_job(client, db_session):
    job = _make_job(db_session, "job_unflag")
    job.flagged = True
    db_session.commit()
    resp = client.patch("/api/jobs/job_unflag/flag", json={"flagged": False})
    assert resp.status_code == 200
    assert resp.json()["flagged"] is False


def test_flag_job_not_found(client):
    resp = client.patch("/api/jobs/nonexistent/flag", json={"flagged": True})
    assert resp.status_code == 404


def test_get_jobs_includes_flagged_field(client, db_session):
    _make_job(db_session, "job_f")
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    assert "flagged" in resp.json()[0]
    assert resp.json()[0]["flagged"] is False
```

- [ ] **Run tests to confirm they fail.**

```
cd C:/Users/barlo/Projects/auto_apply
python -m pytest tests/web/test_jobs_api.py::test_flag_job tests/web/test_jobs_api.py::test_unflag_job tests/web/test_jobs_api.py::test_flag_job_not_found tests/web/test_jobs_api.py::test_get_jobs_includes_flagged_field -v
```

Expected: all four FAIL (no `flag` route, `flagged` not in serialize).

- [ ] **Add the endpoint to `web/routers/jobs.py`.** After the `update_job_fields` endpoint (around line 157), add:

```python
class FlagUpdate(BaseModel):
    flagged: bool


@router.patch("/{job_key}/flag")
def update_job_flag(job_key: str, body: FlagUpdate, db: Session = Depends(get_db)):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    job.flagged = body.flagged
    db.commit()
    db.refresh(job)
    _emit(job)
    return job.serialize()
```

- [ ] **Run tests to confirm they pass.**

```
python -m pytest tests/web/test_jobs_api.py::test_flag_job tests/web/test_jobs_api.py::test_unflag_job tests/web/test_jobs_api.py::test_flag_job_not_found tests/web/test_jobs_api.py::test_get_jobs_includes_flagged_field -v
```

Expected: all four PASS.

- [ ] **Run full test suite to check for regressions.**

```
python -m pytest tests/web/test_jobs_api.py -v
```

Expected: all tests PASS.

- [ ] **Commit.**

```
git add web/routers/jobs.py tests/web/test_jobs_api.py
git commit -m "[feat] Add PATCH /api/jobs/{job_key}/flag endpoint"
```

---

## Task 4: Frontend — `flagJob` API helper + JobCard flag icon

**Files:**
- Modify: `react-dashboard/src/api.js`
- Modify: `react-dashboard/src/components/shared/JobCard.jsx`
- Modify: `react-dashboard/src/components/widgets/Pipeline.jsx`

- [ ] **Add `flagJob` to `api.js`.** Append after `updateJobFields`:

```js
export const flagJob = (jobKey, flagged) =>
  _fetch(`/api/jobs/${jobKey}/flag`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ flagged }),
  })
```

- [ ] **Add a `FlagIcon` component to `JobCard.jsx`.** Add after the `WarningIcon` function (around line 136):

```jsx
function FlagIconFilled() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="#ef4444" stroke="#ef4444" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="shrink-0">
      <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/>
      <line x1="4" y1="22" x2="4" y2="15"/>
    </svg>
  )
}
```

- [ ] **Add `flagged` to `JobCard` props and render the icon.** Change the export signature from:

```jsx
export default function JobCard({ title, company, statusIcon, docs = {}, selected = false, state, score, appliedAt, scrapedAt, salaryMin, salaryMax, salaryRaw }) {
```

to:

```jsx
export default function JobCard({ title, company, statusIcon, docs = {}, selected = false, state, score, appliedAt, scrapedAt, salaryMin, salaryMax, salaryRaw, flagged = false }) {
```

Then in the right-side icon cluster (the `div` containing `ScorePill` and `statusIcon`, around line 110), add the flag icon before `ScorePill`:

```jsx
      <div className="flex items-center self-stretch gap-1.5">
        {flagged && <FlagIconFilled />}
        <ScorePill />
        {state === 'deleted' && <TrashIcon />}
        {statusIcon}
      </div>
```

- [ ] **Pass `flagged` in `Pipeline.jsx`.** In the `JobList` component's `JobCard` render (around line 60), add `flagged={job.flagged ?? false}` to the props:

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
            flagged={job.flagged ?? false}
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

- [ ] **Commit.**

```
git add react-dashboard/src/api.js react-dashboard/src/components/shared/JobCard.jsx react-dashboard/src/components/widgets/Pipeline.jsx
git commit -m "[feat] Add flag icon to JobCard and flagJob API helper"
```

---

## Task 5: Flag toggle button in PreviewTab

**Files:**
- Modify: `react-dashboard/src/components/widgets/Settings.jsx`

- [ ] **Add `FlagButton` component** to `Settings.jsx`. Add after the `WarningIcon` import block (after `function BackArrow`, around line 20):

```jsx
function FlagButton({ flagged, onClick }) {
  return (
    <button
      onClick={onClick}
      title={flagged ? 'Remove flag' : 'Flag this job'}
      className="shrink-0 text-space-dim hover:text-red-400 transition-colors"
    >
      {flagged ? (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="#ef4444" stroke="#ef4444" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/>
          <line x1="4" y1="22" x2="4" y2="15"/>
        </svg>
      ) : (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/>
          <line x1="4" y1="22" x2="4" y2="15"/>
        </svg>
      )}
    </button>
  )
}
```

- [ ] **Import `flagJob` at the top of `Settings.jsx`.** The import line (line 4) currently reads:

```js
import { getProfiles, createProfile, getProfile, updateProfile, setActiveProfile, uploadProfileResume, parseProfileResume, markJobActionSeen, deleteJob, updateJobState, updateJobFields, putDocumentMarkdown } from '../../api'
```

Add `flagJob` to it:

```js
import { getProfiles, createProfile, getProfile, updateProfile, setActiveProfile, uploadProfileResume, parseProfileResume, markJobActionSeen, deleteJob, updateJobState, updateJobFields, putDocumentMarkdown, flagJob } from '../../api'
```

- [ ] **Add flag state and handler to `PreviewTab`.** In the `PreviewTab` function body, after the existing state declarations (around line 503), add:

```jsx
  const [flagging, setFlagging] = useState(false)

  const handleFlag = async () => {
    if (!job || flagging) return
    setFlagging(true)
    try {
      await flagJob(job.job_key, !job.flagged)
    } catch { /* SSE will sync; ignore */ }
    finally {
      setFlagging(false)
    }
  }
```

- [ ] **Render the flag button in the info block.** The info block starts around line 637 with `{/* Info */}`. The `<h2>` title line is:

```jsx
          <h2 className="text-base font-semibold text-space-text leading-tight">{job.title || '(no title)'}</h2>
```

Wrap the title and flag button together:

```jsx
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-2">
            <h2 className="text-base font-semibold text-space-text leading-tight flex-1">{job.title || '(no title)'}</h2>
            <FlagButton flagged={!!job.flagged} onClick={handleFlag} />
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1.5">
```

- [ ] **Reset `flagging` state on job change.** Find the `useEffect` that resets state on `job?.job_key` change (around line 544). Add `setFlagging(false)` to its body:

```jsx
  useEffect(() => {
    setContentTab('description')
    setDescView(job?.extraction_json_exists ? 'extracted' : 'raw')
    setArtifactView(job?.resume_path ? 'pdf' : 'markdown')
    setLocalLoadingTabs(new Set())
    setActionError(null)
    setArtifactNonce({ resume: 0, cover: 0 })
    prevInFlight.current = new Set()
    setConfirmDelete(false)
    setDeleting(false)
    setDeleteError(null)
    setStateChanging(false)
    setShowEditFields(false)
    setEditDoc(null)
    setFlagging(false)
  }, [job?.job_key])
```

- [ ] **Commit.**

```
git add react-dashboard/src/components/widgets/Settings.jsx
git commit -m "[feat] Add flag toggle button to job preview"
```

---

## Task 6: Fix cover letter double greeting

**Files:**
- Modify: `prompts/defaults/cover.md`

- [ ] **Open `prompts/defaults/cover.md`.** The current instructions block ends with:

```
- Address it to the hiring team at {job.company}.
- Do not include a sign-off, name, or contact information at the end — those are added automatically.
- Do not invent experience or skills not in the master resume.
```

Replace those three lines with:

```
- Do not include a greeting, salutation, or "Dear..." line at the top — it is prepended automatically.
- Do not include a sign-off, name, or contact information at the end — those are added automatically.
- Do not invent experience or skills not in the master resume.
```

The full file after edit:

```markdown
You are writing a concise cover letter in Markdown for a job application.

# Master Resume
{user_profile.master_resume}

# Job Posting
Title: {job.title}
Company: {job.company}
Location: {job.location}
Description:
{job.description}

# Instructions
- Output ONLY the cover letter Markdown. No preamble, no explanation.
- Do not use `---` horizontal rules anywhere in the output.
- Exactly 3 paragraphs: (1) fit and interest, (2) specific value-add tied to the job description, (3) close.
- Do not include a greeting, salutation, or "Dear..." line at the top — it is prepended automatically.
- Do not include a sign-off, name, or contact information at the end — those are added automatically.
- Do not invent experience or skills not in the master resume.
```

- [ ] **Commit.**

```
git add prompts/defaults/cover.md
git commit -m "[fix] Remove double greeting from cover letter prompt"
```

---

## Task 7: Prompt Save As button

**Files:**
- Modify: `react-dashboard/src/components/widgets/ProfileDetail.jsx`

- [ ] **Add Save As state to `PromptModal`.** In the `PromptModal` function, after the existing state declarations (around line 788, after `const [uploading, setUploading] = useState(false)`), add:

```jsx
  const [saveAsOpen, setSaveAsOpen] = useState(false)
  const [saveAsName, setSaveAsName] = useState('')
  const [saveAsError, setSaveAsError] = useState(null)
  const [saveAsSubmitting, setSaveAsSubmitting] = useState(false)
```

- [ ] **Add `handleSaveAs` function.** Add after `handleSave` (around line 906):

```jsx
  const suggestSaveAsName = () => {
    const base = selectedFile
      ? selectedFile.split(/[\\/]/).pop().replace(/\.md$/i, '')
      : typeKey
    const isDefault = isDefaultPrompt(selectedFile)
    return isDefault ? `${base}_custom.md` : `${base}_copy.md`
  }

  const openSaveAs = () => {
    setSaveAsName(suggestSaveAsName())
    setSaveAsError(null)
    setSaveAsOpen(true)
  }

  const handleSaveAsConfirm = async () => {
    const filename = saveAsName.trim()
    if (!filename) { setSaveAsError('Filename is required'); return }
    const name = filename.endsWith('.md') ? filename : filename + '.md'
    setSaveAsSubmitting(true)
    setSaveAsError(null)
    try {
      const result = await createPromptFile(name, content)
      const updated = await listPrompts()
      setPromptFiles(updated.prompts || [])
      setSelectedFile(result.path)
      originalContent.current = content
      setSaveAsOpen(false)
      // Also save the profile link pointing to the new file
      const newData = {
        ...profileData,
        [`prompt_${typeKey}`]: result.path,
        [`prompt_${typeKey}_model`]: modelOverride,
      }
      await updateProfile(profileId, { name: profileName || '', data: newData })
      onSaved(typeKey, result.path, modelOverride)
      window.dispatchEvent(new CustomEvent('auto-apply:prompt-status-stale'))
      onClose()
    } catch (e) {
      const msg = e?.message || ''
      setSaveAsError(msg.includes('409') ? 'A file with that name already exists' : 'Save failed')
    } finally {
      setSaveAsSubmitting(false)
    }
  }
```

- [ ] **Update the footer in the modal.** Find the footer block (around line 1043):

```jsx
          {/* Footer */}
          <div className="px-4 py-3 border-t border-space-border shrink-0 flex flex-col gap-2">
            {saveError && <p className="text-xs text-red-400">{saveError}</p>}
            <div className="flex gap-2">
              <button
                onClick={handleSave}
                disabled={saving || loadingContent || !!contentError}
                className="flex-1 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-sm font-semibold transition-colors"
              >
                {saving ? 'Saving…' : 'Save'}
              </button>
              <button
                onClick={onClose}
                className="px-4 py-2 rounded-lg border border-space-border text-sm text-space-dim hover:text-space-text transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
```

Replace it with:

```jsx
          {/* Footer */}
          <div className="px-4 py-3 border-t border-space-border shrink-0 flex flex-col gap-2">
            {saveError && <p className="text-xs text-red-400">{saveError}</p>}
            {saveAsOpen ? (
              <div className="flex flex-col gap-2">
                {saveAsError && <p className="text-xs text-red-400">{saveAsError}</p>}
                <div className="flex gap-2 items-center">
                  <input
                    autoFocus
                    className={inputClass + ' flex-1 text-xs'}
                    value={saveAsName}
                    onChange={(e) => { setSaveAsName(e.target.value); setSaveAsError(null) }}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleSaveAsConfirm(); if (e.key === 'Escape') setSaveAsOpen(false) }}
                    placeholder="filename.md"
                  />
                  <button
                    onClick={handleSaveAsConfirm}
                    disabled={saveAsSubmitting}
                    className="px-3 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-xs font-semibold transition-colors shrink-0"
                  >
                    {saveAsSubmitting ? '…' : 'Confirm'}
                  </button>
                  <button
                    onClick={() => setSaveAsOpen(false)}
                    className="px-3 py-2 rounded-lg border border-space-border text-xs text-space-dim hover:text-space-text transition-colors shrink-0"
                  >
                    ✕
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex gap-2">
                <button
                  onClick={openSaveAs}
                  disabled={saving || loadingContent || !!contentError}
                  className="px-3 py-2 rounded-lg border border-space-border text-xs text-space-dim hover:text-space-text disabled:opacity-50 transition-colors shrink-0"
                >
                  Save As
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving || loadingContent || !!contentError}
                  className="flex-1 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-sm font-semibold transition-colors"
                >
                  {saving ? 'Saving…' : 'Save'}
                </button>
                <button
                  onClick={onClose}
                  className="px-4 py-2 rounded-lg border border-space-border text-sm text-space-dim hover:text-space-text transition-colors"
                >
                  Cancel
                </button>
              </div>
            )}
          </div>
```

- [ ] **Commit.**

```
git add react-dashboard/src/components/widgets/ProfileDetail.jsx
git commit -m "[feat] Add Save As button to prompt editor modal"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Job flagging: DB column (Task 1), migration (Task 2), API endpoint + tests (Task 3), JobCard icon (Task 4), PreviewTab toggle (Task 5)
- [x] Cover letter double intro: prompt fix (Task 6)
- [x] Prompt Save As: inline input + createPromptFile flow (Task 7)

**No placeholders:** Confirmed — all steps have complete code.

**Type consistency:**
- `flagged` column name used consistently across Tasks 1–5
- `FlagButton` component defined in Task 5, used only in Task 5
- `FlagIconFilled` defined in Task 4, used only in Task 4
- `flagJob(jobKey, flagged)` defined in Task 4, imported and called in Task 5
- `handleSaveAs` / `saveAsOpen` / `saveAsName` / `saveAsError` / `saveAsSubmitting` all defined in Task 7 and used only within Task 7
- `createPromptFile` already exported from `api.js` (confirmed) and already imported in `ProfileDetail.jsx` (confirmed)
