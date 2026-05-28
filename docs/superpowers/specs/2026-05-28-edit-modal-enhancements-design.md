# Edit Modal Enhancements — Design Spec

**Date:** 2026-05-28
**Status:** Approved

## Overview

Four targeted fixes to the job editing flow:

1. Fix a 500 error on PUT markdown endpoints (async/sync Playwright conflict)
2. Add a description pop-out in EditFieldsModal (matching ProfileDetail pattern)
3. Fix Esc key behavior so it closes the modal without exiting job preview
4. Move the Edit button from the tab bar to below the Apply/View Post button

---

## 1. Bug Fix — PUT Markdown 500 Error

**Root cause:** `put_resume_markdown` and `put_cover_markdown` are `async def` FastAPI handlers. They call `generate_resume_pdf` / `generate_cover_pdf`, which calls `render_pdf`, which calls `sync_playwright()`. Playwright's `sync_playwright()` calls `asyncio.run()` internally, which raises `RuntimeError: This event loop is already running` when called from within an active event loop.

**Fix:** Convert both PUT handlers from `async def` to `def`. FastAPI runs sync route handlers in a thread pool via `anyio.to_thread.run_sync`, where there is no active event loop, making `sync_playwright()` safe.

The problem: sync routes cannot `await request.body()`. Solution: extract body reading into an `async def` Depends that runs before the sync route.

**New code in `web/routers/jobs.py`:**

```python
async def _read_body_text(request: Request) -> str:
    raw = await request.body()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Request body must be valid UTF-8 text")

def _put_document_markdown_sync(job_key: str, doc_type: str, content: str, db: Session) -> dict:
    # ... (existing logic, fully sync, no await)

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

**`core/job.py` change:** Add `max_pages: int | None = 1` parameter to `generate_resume_pdf`. The PUT path passes `max_pages=None` to silently allow multi-page documents (Option A — no error, no truncation).

---

## 2. Description Pop-Out in EditFieldsModal

**File:** `react-dashboard/src/components/widgets/Settings.jsx`

**Pattern:** Identical to `ProfileDetail.jsx`'s prompt pop-out.

### `useEscape` hook

Add to top of `Settings.jsx` (copied verbatim from ProfileDetail):

```js
function useEscape(active, handler) {
  useEffect(() => {
    if (!active) return
    const onKey = (e) => { if (e.key === 'Escape') handler() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [active, handler])
}
```

### State

Add to `EditFieldsModal`:
```js
const [popOut, setPopOut] = useState(false)
```

### Esc behavior (layered)

```js
const handleClose = useCallback(() => onClose(), [onClose])
useEscape(popOut, () => setPopOut(false))
useEscape(!popOut, handleClose)
```

- Esc while pop-out open → closes pop-out only
- Esc while pop-out closed → closes modal (returns to job preview)
- Esc does NOT exit the job preview from within the modal

### Pop-out trigger

Small expand icon button next to the Description label:

```jsx
<label>Description</label>
<button onClick={() => setPopOut(true)} title="Expand description">
  <ArrowsPointingOutIcon className="w-4 h-4" />
</button>
```

### Pop-out overlay

Full-screen overlay at `z-[60]` (above modal's z-50):

```jsx
{popOut && (
  <div className="fixed inset-0 z-[60] flex flex-col bg-[#0a0a14]">
    <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
      <span className="text-white font-semibold">Description</span>
      <button onClick={() => setPopOut(false)}>
        <XMarkIcon className="w-5 h-5 text-space-dim hover:text-white" />
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
```

---

## 3. Edit Button Relocation

**Current:** Edit button is in the content tab bar (`ml-auto` position alongside Inbox/Resume/Cover tabs).

**New:** Stacked below the Apply / View Posting button in the info block.

```
┌─────────────────────────────┐
│  Job title                  │
│  Company • Location         │
│  Salary                     │
│  [Apply / View Posting   ]  │
│  [Edit                   ]  │
└─────────────────────────────┘
```

The Apply button is already rendered as `shrink-0` in the info block. The Edit button becomes a second button in the same column, below it:

```jsx
<button
  onClick={() => setShowEditFields(true)}
  className="w-full px-4 py-2 rounded text-sm font-medium bg-space-card border border-white/10 text-space-dim hover:text-white hover:border-white/30 transition-colors"
>
  Edit
</button>
```

Remove the Edit button from its current position in the tab bar.

---

## Affected Files

| File | Change |
|------|--------|
| `web/routers/jobs.py` | Convert PUT handlers to sync; add `_read_body_text` Depends |
| `core/job.py` | Add `max_pages: int | None = 1` to `generate_resume_pdf` |
| `react-dashboard/src/components/widgets/Settings.jsx` | `useEscape` hook, pop-out overlay, Esc behavior, Edit button relocation |

## Out of Scope

- No changes to `DocumentEditOverlay` (already implemented)
- No changes to `generate_cover_pdf` (no max_pages constraint there)
- No new tests for the UI changes (pure frontend, no testable logic)
- The PUT markdown backend tests already exist and should continue passing after the fix
