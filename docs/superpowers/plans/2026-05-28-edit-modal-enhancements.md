# Edit Modal Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the PUT markdown 500 error, add a description pop-out to EditFieldsModal, fix Esc key behavior, and move the Edit button to the job info block.

**Architecture:** Three independent changes — a backend sync/async fix in `web/routers/jobs.py` and `core/job.py`, and two frontend changes in `react-dashboard/src/components/widgets/Settings.jsx`. No new files needed.

**Tech Stack:** FastAPI (Python), React 18, Tailwind CSS

---

## File Map

| File | Change |
|------|--------|
| `web/routers/jobs.py` | Replace async PUT handlers with sync handlers + async body-reading Depends |
| `core/job.py` | Add `max_pages: int \| None = 1` parameter to `generate_resume_pdf` |
| `react-dashboard/src/components/widgets/Settings.jsx` | `useEscape` hook, description pop-out, Edit button move |
| `tests/web/test_jobs_api.py` | One new regression test for sync handler |

---

## Task 1: Fix PUT Markdown 500 Error (Backend)

**Root cause:** `put_resume_markdown` and `put_cover_markdown` are `async def` FastAPI handlers. They call `generate_resume_pdf` → `render_pdf` → `sync_playwright()`. Playwright's `sync_playwright()` calls `asyncio.run()` internally, which raises `RuntimeError: This event loop is already running` when called from inside an `async def` handler. The fix is to make the handlers `def` (sync); FastAPI runs sync handlers in a thread pool where there is no active event loop. Since sync routes can't `await request.body()`, body reading is extracted into an `async def` Depends that FastAPI resolves in the event loop before handing off to the sync route.

Additionally, `generate_resume_pdf` currently hardcodes `max_pages=1`. The PUT edit path should silently allow multi-page documents (Option A), so we add a `max_pages: int | None = 1` parameter and pass `None` from the PUT path.

**Files:**
- Modify: `web/routers/jobs.py:349-396`
- Modify: `core/job.py:606-630` (the `generate_resume_pdf` method)
- Test: `tests/web/test_jobs_api.py`

- [ ] **Step 1: Write the failing regression test**

In `tests/web/test_jobs_api.py`, add after the last existing test (after line 701):

```python
def test_put_resume_markdown_handler_is_sync():
    """PUT handler must be a plain function, not a coroutine — sync_playwright requires no event loop."""
    import asyncio
    import web.routers.jobs as jobs_mod
    assert not asyncio.iscoroutinefunction(jobs_mod.put_resume_markdown)
    assert not asyncio.iscoroutinefunction(jobs_mod.put_cover_markdown)
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/web/test_jobs_api.py::test_put_resume_markdown_handler_is_sync -v
```

Expected output: `FAILED` — both handlers are currently `async def`.

- [ ] **Step 3: Update `generate_resume_pdf` in `core/job.py`**

Find line 606. Change the signature and the `render_pdf` call:

**Before (line 606):**
```python
def generate_resume_pdf(self, template_path: Path, db: Session) -> None:
```

**After:**
```python
def generate_resume_pdf(self, template_path: Path, db: Session, max_pages: int | None = 1) -> None:
```

Find line 627. Change:

**Before:**
```python
render_pdf(md_path, pdf_path, template_path, max_pages=1, meta=meta)
```

**After:**
```python
render_pdf(md_path, pdf_path, template_path, max_pages=max_pages, meta=meta)
```

- [ ] **Step 4: Replace the async PUT machinery in `web/routers/jobs.py`**

Replace lines 349–396 (the `_put_document_markdown` async helper and the two `async def` PUT handlers) with:

```python
async def _read_body_text(request: Request) -> str:
    raw = await request.body()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Request body must be valid UTF-8 text")


def _put_document_markdown_sync(
    job_key: str,
    doc_type: str,  # "resume" or "cover"
    content: str,
    db: Session,
):
    job = Job.get(job_key, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    suffix = "_resume.md" if doc_type == "resume" else "_cover.md"
    md_path = _GENERATOR_OUTPUTS / f"{job_key}{suffix}"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    old_content = md_path.read_text(encoding="utf-8") if md_path.exists() else None
    md_path.write_text(content, encoding="utf-8")

    try:
        if doc_type == "resume":
            job.generate_resume_pdf(_RESUME_TEMPLATE, db, max_pages=None)
        else:
            job.generate_cover_pdf(_COVER_TEMPLATE, db)
    except Exception as exc:
        if old_content is not None:
            md_path.write_text(old_content, encoding="utf-8")
        else:
            md_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"PDF render failed: {exc}")

    db.commit()
    db.refresh(job)
    _emit(job)
    return job.serialize()


@router.put("/{job_key}/resume/markdown")
def put_resume_markdown(
    job_key: str,
    content: str = Depends(_read_body_text),
    db: Session = Depends(get_db),
):
    return _put_document_markdown_sync(job_key, "resume", content, db)


@router.put("/{job_key}/cover/markdown")
def put_cover_markdown(
    job_key: str,
    content: str = Depends(_read_body_text),
    db: Session = Depends(get_db),
):
    return _put_document_markdown_sync(job_key, "cover", content, db)
```

- [ ] **Step 5: Run all PUT markdown tests to verify they pass**

```
pytest tests/web/test_jobs_api.py -k "markdown" -v
```

Expected: All 4 markdown tests pass (3 existing + 1 new regression test).

- [ ] **Step 6: Run full test suite to verify no regressions**

```
pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: Same pass count as before (244 passing, 9 pre-existing failures in `test_get_description_*` that are unrelated to this change).

- [ ] **Step 7: Commit**

```
git add web/routers/jobs.py core/job.py tests/web/test_jobs_api.py
git commit -m "[fix] Convert PUT markdown handlers to sync to fix sync_playwright conflict"
```

---

## Task 2: Add useEscape Hook + Description Pop-Out to EditFieldsModal

**Context:** `Settings.jsx` currently has no `useEscape` hook. `EditFieldsModal` (lines 129–197) is a simple modal with no keyboard handling. We need to:
1. Add the `useEscape` hook (copy from `ProfileDetail.jsx` pattern)
2. Add a `popOut` state to `EditFieldsModal`
3. Add an expand button next to the Description label that opens a full-screen textarea overlay
4. Wire Esc so: pop-out open → Esc collapses pop-out; pop-out closed → Esc closes modal

The pop-out overlay uses `z-[60]` (above the modal's `z-50`). The `useEscape` hook pattern uses two calls with complementary `active` conditions to achieve the layering.

**Files:**
- Modify: `react-dashboard/src/components/widgets/Settings.jsx:1-197`

- [ ] **Step 1: Add the `useEscape` hook after the existing imports block**

`Settings.jsx` currently starts at line 1 with imports, then `BackArrow` function at line 13, then shared constants. Insert the `useEscape` hook after line 19 (the closing `}` of `BackArrow`):

```jsx
function useEscape(active, handler) {
  useEffect(() => {
    if (!active) return
    const onKey = (e) => { if (e.key === 'Escape') handler() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [active, handler])
}
```

- [ ] **Step 2: Rewrite `EditFieldsModal` with pop-out state + Esc handling + expand button**

Replace the entire `EditFieldsModal` function (lines 129–197) with:

```jsx
function EditFieldsModal({ job, onClose }) {
  const [fields, setFields] = useState({
    title: job.title || '',
    description: job.description || '',
    company: job.company || '',
    location: job.location || '',
    salary: job.salary || '',
    url: job.url || '',
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [popOut, setPopOut] = useState(false)

  const handleClose = useCallback(() => onClose(), [onClose])
  useEscape(popOut, () => setPopOut(false))
  useEscape(!popOut, handleClose)

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      await updateJobFields(job.job_key, fields)
      onClose()
    } catch (e) {
      setError(e?.message || 'Save failed')
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#0f0f1a] border border-space-border rounded-xl w-[90%] max-w-md p-5 flex flex-col gap-3 shadow-2xl max-h-[90vh] overflow-y-auto">
        <p className="text-sm font-semibold text-space-text">Edit job</p>

        <label className="text-xs text-space-dim">Title</label>
        <input
          value={fields.title}
          onChange={(e) => setFields(f => ({ ...f, title: e.target.value }))}
          className={inputClass}
        />

        <div className="flex items-center justify-between">
          <label className="text-xs text-space-dim">Description</label>
          <button
            onClick={() => setPopOut(true)}
            title="Expand description"
            className="text-space-dim hover:text-space-text transition-colors p-0.5"
          >
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-3.5 h-3.5">
              <path d="M1 6V1h5M10 1h5v5M15 10v5h-5M6 15H1v-5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        </div>
        <textarea
          value={fields.description}
          onChange={(e) => setFields(f => ({ ...f, description: e.target.value }))}
          rows={6}
          className={inputClass}
        />

        <label className="text-xs text-space-dim">Company</label>
        <input
          value={fields.company}
          onChange={(e) => setFields(f => ({ ...f, company: e.target.value }))}
          className={inputClass}
        />

        <label className="text-xs text-space-dim">Location</label>
        <input
          value={fields.location}
          onChange={(e) => setFields(f => ({ ...f, location: e.target.value }))}
          className={inputClass}
        />

        <label className="text-xs text-space-dim">Salary</label>
        <input
          value={fields.salary}
          onChange={(e) => setFields(f => ({ ...f, salary: e.target.value }))}
          className={inputClass}
        />

        <label className="text-xs text-space-dim">URL</label>
        <input
          value={fields.url}
          onChange={(e) => setFields(f => ({ ...f, url: e.target.value }))}
          className={inputClass}
        />

        {error && <p className="text-xs text-red-400">{error}</p>}

        <div className="flex gap-2 mt-2">
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex-1 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-sm font-semibold"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button
            onClick={onClose}
            disabled={saving}
            className="px-4 py-2 rounded-lg border border-space-border text-sm text-space-dim hover:text-space-text"
          >
            Cancel
          </button>
        </div>
      </div>

      {popOut && (
        <div className="fixed inset-0 z-[60] flex flex-col bg-[#0a0a14]">
          <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 shrink-0">
            <span className="text-sm font-semibold text-space-text">Description</span>
            <button
              onClick={() => setPopOut(false)}
              className="text-space-dim hover:text-white transition-colors"
              aria-label="Collapse description"
            >
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-4 h-4">
                <path d="M6 1v5H1M15 6h-5V1M1 10h5v5M10 15v-5h5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          </div>
          <textarea
            className="flex-1 w-full bg-transparent text-space-text p-6 resize-none focus:outline-none font-mono text-sm"
            value={fields.description}
            onChange={(e) => setFields(f => ({ ...f, description: e.target.value }))}
            autoFocus
          />
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Verify the app builds without errors**

```
cd react-dashboard && npm run build 2>&1 | tail -20
```

Expected: Build completes with no errors.

- [ ] **Step 4: Manual smoke test**

Start the app (`start.bat`), open any job's Preview tab, click Edit, verify:
- Modal opens
- Esc closes the modal (not the job preview)
- The expand icon appears next to the Description label
- Clicking the expand icon opens the full-screen textarea
- Esc while pop-out is open collapses the pop-out (does NOT close the modal)
- Esc after pop-out closes → closes the modal
- Description text typed in the pop-out syncs back into the modal field

- [ ] **Step 5: Commit**

```
git add react-dashboard/src/components/widgets/Settings.jsx
git commit -m "[feat] Add description pop-out and Esc layering to EditFieldsModal"
```

---

## Task 3: Move Edit Button to Info Block

**Context:** The Edit button that opens `EditFieldsModal` currently sits in the content tab bar (line 612), between the tab buttons and the Delete button. It should move to the info block — stacked below the green Apply/View Post button (lines 576–586) as a second button in the same column.

Removing it from the tab bar means the tab bar row will then only contain the tab buttons and Delete button.

**Files:**
- Modify: `react-dashboard/src/components/widgets/Settings.jsx` (the `PreviewTab` component, lines 576–626)

- [ ] **Step 1: Remove the Edit button from the tab bar**

Find this block in `PreviewTab` (around lines 612–618):

```jsx
        <button
          onClick={() => setShowEditFields(true)}
          title="Edit job fields"
          className="ml-auto px-3 py-1 rounded text-xs font-semibold transition-colors border border-space-border text-space-dim hover:text-space-text"
        >
          Edit
        </button>
```

Delete those 7 lines. The Delete button that follows it should now be the only `ml-auto` element in the tab bar (or you can leave Delete without `ml-auto` and add `ml-auto` to it so it stays right-aligned). Specifically: after removing the Edit button, change the Delete button's className to add `ml-auto`:

**Before:**
```jsx
        <button
          onClick={() => { setDeleteError(null); setConfirmDelete(true) }}
          title="Delete job"
          className="px-3 py-1 rounded text-xs font-semibold transition-colors border border-red-500/30 text-red-400 hover:bg-red-500/10"
        >
          Delete
        </button>
```

**After:**
```jsx
        <button
          onClick={() => { setDeleteError(null); setConfirmDelete(true) }}
          title="Delete job"
          className="ml-auto px-3 py-1 rounded text-xs font-semibold transition-colors border border-red-500/30 text-red-400 hover:bg-red-500/10"
        >
          Delete
        </button>
```

- [ ] **Step 2: Add the Edit button below the Apply/View Post button in the info block**

Find the info block's right column (around lines 576–587). It currently contains the Apply/View Post button alone:

```jsx
        <button
          onClick={() => {
            if (job.url) window.open(job.url, '_blank')
            fetch(`/api/jobs/${job.job_key}/apply`, { method: 'POST' })
              .then(res => { if (!res.ok) console.error(`Apply failed: ${res.status}`) })
              .catch(err => console.error('Apply request failed:', err))
          }}
          className="shrink-0 px-3 py-1 rounded text-xs font-semibold transition-colors bg-[#198754] text-white hover:opacity-90"
        >
          {hasResume ? 'Apply' : 'View Post'}
        </button>
```

Wrap the Apply button and a new Edit button together in a `flex flex-col gap-1` div:

```jsx
        <div className="flex flex-col gap-1 shrink-0">
          <button
            onClick={() => {
              if (job.url) window.open(job.url, '_blank')
              fetch(`/api/jobs/${job.job_key}/apply`, { method: 'POST' })
                .then(res => { if (!res.ok) console.error(`Apply failed: ${res.status}`) })
                .catch(err => console.error('Apply request failed:', err))
            }}
            className="px-3 py-1 rounded text-xs font-semibold transition-colors bg-[#198754] text-white hover:opacity-90"
          >
            {hasResume ? 'Apply' : 'View Post'}
          </button>
          <button
            onClick={() => setShowEditFields(true)}
            title="Edit job fields"
            className="px-3 py-1 rounded text-xs font-semibold transition-colors border border-space-border text-space-dim hover:text-space-text"
          >
            Edit
          </button>
        </div>
```

Note: `shrink-0` moves from the Apply button to the wrapping div.

- [ ] **Step 3: Verify the app builds without errors**

```
cd react-dashboard && npm run build 2>&1 | tail -20
```

Expected: Build completes with no errors.

- [ ] **Step 4: Manual smoke test**

Start the app, open any job's Preview tab, verify:
- Edit button appears below the Apply/View Post button in the header area
- Edit button is NOT in the tab bar
- Delete button is right-aligned in the tab bar on its own
- Clicking Edit opens the EditFieldsModal (same behavior as before the move)

- [ ] **Step 5: Commit**

```
git add react-dashboard/src/components/widgets/Settings.jsx
git commit -m "[feat] Move Edit button to info block below Apply button"
```
