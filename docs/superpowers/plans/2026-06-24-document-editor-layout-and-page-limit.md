# Document Editor Layout + Configurable Page Limit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the tree-v1 document editor the profile-editor's grouped/collapsible layout, and make the résumé page limit a per-profile setting.

**Architecture:** Backend resolves a per-profile `resume_max_pages` (absent/null = unlimited) and threads it into every résumé render via a sentinel default on `generate_resume_pdf`. The profile editor gains a toggle + digit control. `DocumentTree.jsx` is rebuilt to render sections as collapsible cards with a 2-col field grid and per-entry sub-cards, with feedback collected at section and entry level only.

**Tech Stack:** Python/FastAPI/pytest (in-memory StaticPool); React/Vitest/RTL.
**Spec:** `docs/superpowers/specs/2026-06-24-document-editor-layout-and-page-limit-design.md`.

## Global Constraints

- Merges to LOCAL `main` only — do NOT push `main` (whole-swap release gate, #4–#6 + #5).
- Page-limit storage in `profile.data.resume_max_pages`: **integer N → cap at N pages; `null` → unlimited; absent → unlimited**. New profiles are **seeded with `resume_max_pages: 1`** at creation. No migration of existing rows.
- The resolver returns `int | None`: positive int → that int; `null`/absent/invalid/≤0 → `None`.
- Document editor is **values-only** — NO add/remove/rename/reorder/lock/visibility (those stay in the profile editor). Locked sections/entries render read-only.
- Feedback in the document editor is collected at **section level and entry level only** — per-field 💬 is removed. Each note carries `{section, label, note}`; the owning section name drives selective regen.
- Cover letters and legacy `ResumeDocument` résumé paths are UNCHANGED.
- Python: type hints, black, Google-style docstrings, prefer stdlib, follow existing file patterns.

---

### Task 1: Backend page-limit resolver + render call-site swap + new-profile seed

**Files:**
- Modify: `core/user.py` (add `_normalize_max_pages`; hydrate `self.resume_max_pages`; round-trip in `_to_dict`)
- Modify: `core/job.py` (`generate_resume_pdf` sentinel default + `_resolve_resume_max_pages`; the 6 render call sites)
- Modify: `web/intake_pipeline.py` (3 render call sites), `web/routers/jobs.py` (2 render call sites)
- Modify: `web/routers/config.py` (`_EMPTY_PROFILE_DATA` seed)
- Test: `tests/core/test_page_limit.py` (create)

**Interfaces:**
- Consumes: `User.load(db, profile_id=...)` → hydrated `User` with `.resume_max_pages: int | None`; `Job.profile_id`.
- Produces: `core.user._normalize_max_pages(value) -> int | None`; `User.resume_max_pages: int | None`; `Job._resolve_resume_max_pages(self, db) -> int | None`; `generate_resume_pdf(..., max_pages=<sentinel>)` resolves from profile when the argument is omitted.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_page_limit.py`. Copy the in-memory StaticPool session + User/Job seeding pattern from `tests/core/test_job.py` (look for its session fixture and how it seeds a `User` row with a `data` JSON string and a `Job` with `profile_id`). Seed the `User` row's `data` with the relevant `resume_max_pages` value for each case.

```python
import pytest
from core.user import _normalize_max_pages


@pytest.mark.parametrize("value,expected", [
    (1, 1), (3, 3), (0, None), (-2, None), (None, None),
    ("2", 2), ("0", None), ("x", None), (True, None), (2.5, None),
])
def test_normalize_max_pages(value, expected):
    assert _normalize_max_pages(value) == expected


def test_resolve_resume_max_pages_integer(db_session, seeded_job_with_profile_data):
    # seeded_job_with_profile_data: a Job whose profile's data has resume_max_pages=2
    job = seeded_job_with_profile_data({"resume_max_pages": 2})
    assert job._resolve_resume_max_pages(db_session) == 2


def test_resolve_resume_max_pages_absent_is_unlimited(db_session, seeded_job_with_profile_data):
    job = seeded_job_with_profile_data({})  # no key
    assert job._resolve_resume_max_pages(db_session) is None


def test_resolve_resume_max_pages_null_is_unlimited(db_session, seeded_job_with_profile_data):
    job = seeded_job_with_profile_data({"resume_max_pages": None})
    assert job._resolve_resume_max_pages(db_session) is None
```

> `seeded_job_with_profile_data` is a fixture you write in this file: given a dict, persist a `User` row whose `data` JSON includes those keys (merged onto whatever minimal valid profile data `tests/core/test_job.py` already uses) at `profile_id=1`, persist a `Job` with `profile_id=1`, and return a function that loads/returns that `Job`. Reuse `tests/core/test_job.py`'s existing helpers rather than inventing new seeding.

Add the new-profile seed assertion (same file):

```python
def test_new_profile_data_seeds_one_page_limit():
    from web.routers.config import _EMPTY_PROFILE_DATA
    assert _EMPTY_PROFILE_DATA.get("resume_max_pages") == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/core/test_page_limit.py -q`
Expected: FAIL — `_normalize_max_pages` and `Job._resolve_resume_max_pages` do not exist; `_EMPTY_PROFILE_DATA` has no `resume_max_pages`.

- [ ] **Step 3: Add `_normalize_max_pages` + hydration + round-trip in `core/user.py`**

Add this module-level helper near the top of `core/user.py` (after the imports):

```python
def _normalize_max_pages(value: object) -> int | None:
    """Normalize a stored résumé page limit to ``int | None`` (None = unlimited).

    A positive integer (or all-digit string) is the page cap; anything else
    (None, null, non-positive, non-numeric, bool) means unlimited.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        n = int(value)
        return n if n > 0 else None
    return None
```

In the hydration method (where `self.resume_refine_pass_score = float(raw.get(...))` is set, ~line 139), add:

```python
        self.resume_max_pages = _normalize_max_pages(raw.get("resume_max_pages"))
```

In `_to_dict` (where `d["resume_refine_pass_score"] = ...` is set, ~line 170), add:

```python
        d["resume_max_pages"] = self.resume_max_pages
```

- [ ] **Step 4: Add `_resolve_resume_max_pages` + sentinel default in `core/job.py`**

Near the top of `core/job.py` (module level, after imports), add the sentinel:

```python
_MAX_PAGES_UNSET = object()  # "resolve the page limit from the job's profile"
```

Add this method to the `Job` class (next to `generate_resume_pdf`):

```python
    def _resolve_resume_max_pages(self, db: Session) -> int | None:
        """Résumé page cap for this job's owning profile (``None`` = unlimited)."""
        from core.user import User

        user = User.load(db, profile_id=self.profile_id)
        return user.resume_max_pages
```

Change `generate_resume_pdf`'s signature and add resolution at the top of its body. Replace:

```python
    def generate_resume_pdf(self, template_path: Path, db: Session, max_pages: int | None = 1) -> None:
```

with:

```python
    def generate_resume_pdf(self, template_path: Path, db: Session, max_pages=_MAX_PAGES_UNSET) -> None:
```

and immediately after the docstring (before `md_path = ...`), insert:

```python
        if max_pages is _MAX_PAGES_UNSET:
            max_pages = self._resolve_resume_max_pages(db)
```

Update the docstring's `max_pages` line to: ``max_pages: Page cap; ``None`` disables the limit. Omit to resolve from the profile's ``resume_max_pages`` setting.``

Then update the in-class call site `core/job.py:735` (inside `refine_resume_md`) from:

```python
        self.generate_resume_pdf(template_path, db, max_pages=1)
```

to:

```python
        self.generate_resume_pdf(template_path, db)
```

- [ ] **Step 5: Drop the hardcoded `max_pages=1` at the remaining render call sites**

In `web/intake_pipeline.py`, change all three occurrences of
`job.generate_resume_pdf(template_path, db, max_pages=1)` to
`job.generate_resume_pdf(template_path, db)` (the sites near lines 34, 279, 633).

In `web/routers/jobs.py`, change both occurrences of
`job.generate_resume_pdf(_RESUME_TEMPLATE, db, max_pages=1)` to
`job.generate_resume_pdf(_RESUME_TEMPLATE, db)` (the tree-v1 branch ~line 567 and the legacy branch ~line 589).

(The cover path `generate_cover_pdf` is unchanged.)

- [ ] **Step 6: Seed new profiles with a 1-page limit in `web/routers/config.py`**

Find `_EMPTY_PROFILE_DATA` (the dict passed as the new profile's `data` in `create_profile`) and add the key:

```python
    "resume_max_pages": 1,
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python -m pytest tests/core/test_page_limit.py -q`
Expected: PASS.

- [ ] **Step 8: Run adjacent backend suites for regressions**

Run: `python -m pytest tests/core/test_job.py tests/web/test_document_api.py tests/web/test_feedback_refine.py -q`
Expected: PASS (the 4D PUT/feedback tests monkeypatch `generate_resume_pdf`, so the sentinel resolution is never reached there).

- [ ] **Step 9: Commit**

```bash
git add core/user.py core/job.py web/intake_pipeline.py web/routers/jobs.py web/routers/config.py tests/core/test_page_limit.py
git commit -m "[feat] Per-profile résumé page limit (absent/null = unlimited; seed new profiles at 1)"
```

---

### Task 2: Profile editor page-limit control (`ResumePageLimit`)

**Files:**
- Modify: `react-dashboard/src/components/widgets/ProfileDetail.jsx` (add + export `ResumePageLimit`; render it in `ProfileDetailView`)
- Test: `react-dashboard/src/components/widgets/ProfileDetail.test.jsx` (create)

**Interfaces:**
- Consumes: `AccordionSection` (already in `ProfileDetail.jsx`); `handleSave(patch)` in `ProfileDetailView` (merges `patch` into `profile.data` and calls `updateProfile`).
- Produces: `export function ResumePageLimit({ value, onSave })` — `value` is `int | null | undefined`; `onSave({ resume_max_pages })` persists `null` (off) or the integer (on).

- [ ] **Step 1: Write the failing tests**

Create `react-dashboard/src/components/widgets/ProfileDetail.test.jsx`:

```javascript
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

vi.mock('../../api', () => ({
  getProfile: vi.fn(), updateProfile: vi.fn(), resetProfile: vi.fn(),
  getPrompt: vi.fn(), putPrompt: vi.fn(), resetPrompt: vi.fn(),
}))
import { ResumePageLimit } from './ProfileDetail'

describe('ResumePageLimit', () => {
  it('initializes on with the stored integer', () => {
    render(<ResumePageLimit value={2} onSave={vi.fn()} />)
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByLabelText('Max pages')).toHaveValue('2')
  })

  it('initializes off (unlimited) when value is absent', () => {
    render(<ResumePageLimit value={undefined} onSave={vi.fn()} />)
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByLabelText('Max pages')).toBeDisabled()
  })

  it('toggling off persists null', () => {
    const onSave = vi.fn()
    render(<ResumePageLimit value={2} onSave={onSave} />)
    fireEvent.click(screen.getByRole('switch'))
    expect(onSave).toHaveBeenCalledWith({ resume_max_pages: null })
  })

  it('changing the page count persists the integer when on', () => {
    const onSave = vi.fn()
    render(<ResumePageLimit value={1} onSave={onSave} />)
    fireEvent.change(screen.getByLabelText('Max pages'), { target: { value: '3' } })
    expect(onSave).toHaveBeenCalledWith({ resume_max_pages: 3 })
  })

  it('rejects non-digits in the page input', () => {
    const onSave = vi.fn()
    render(<ResumePageLimit value={1} onSave={onSave} />)
    fireEvent.change(screen.getByLabelText('Max pages'), { target: { value: 'a' } })
    // non-digit stripped → empty input, no positive integer → falls back to 1
    expect(onSave).toHaveBeenCalledWith({ resume_max_pages: 1 })
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd react-dashboard && npx vitest run src/components/widgets/ProfileDetail.test.jsx`
Expected: FAIL — `ResumePageLimit` is not exported.

- [ ] **Step 3: Implement and export `ResumePageLimit`**

In `react-dashboard/src/components/widgets/ProfileDetail.jsx`, add this component (place it just above `// ─── ProfileDetailView ───`):

```javascript
// Per-profile résumé page limit. `value` is int (cap) | null | undefined
// (null/absent = unlimited). Toggling off persists null; toggling on persists
// the digit input as an integer (≤0 / blank normalizes to 1).
export function ResumePageLimit({ value, onSave }) {
  const [limited, setLimited] = useState(typeof value === 'number')
  const [pages, setPages] = useState(typeof value === 'number' ? String(value) : '1')

  const persist = (nextLimited, nextPages) => {
    if (!nextLimited) { onSave({ resume_max_pages: null }); return }
    const n = parseInt(nextPages, 10)
    onSave({ resume_max_pages: Number.isInteger(n) && n > 0 ? n : 1 })
  }

  const toggle = () => {
    const next = !limited
    setLimited(next)
    persist(next, pages)
  }

  const onPages = (e) => {
    const digits = e.target.value.replace(/[^0-9]/g, '').slice(0, 1)
    setPages(digits)
    if (limited) persist(true, digits)
  }

  return (
    <AccordionSection id="document" title="Document">
      <div className="flex items-center gap-3">
        <button
          type="button" role="switch" aria-checked={limited}
          aria-label="Limit résumé length" onClick={toggle}
          className={`px-2 py-0.5 rounded border text-xs transition-colors ${
            limited ? 'text-emerald-400 border-emerald-500/40' : 'text-space-dim border-space-border'
          }`}
        >{limited ? '✓ On' : '✗ Off'}</button>
        <label className="text-xs text-space-dim">Max pages</label>
        <input
          type="text" inputMode="numeric" aria-label="Max pages"
          className="w-12 bg-white/5 border border-space-border rounded px-2 py-1 text-xs text-space-text disabled:opacity-40"
          value={pages} onChange={onPages} disabled={!limited}
        />
      </div>
    </AccordionSection>
  )
}
```

Render it in `ProfileDetailView`, immediately after `<ProfileTreeEditor profileId={profileId} />`:

```jsx
        <ResumePageLimit value={d.resume_max_pages} onSave={handleSave} />
```

(`d` is `profile.data`; `handleSave` already merges the patch and calls `updateProfile`.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd react-dashboard && npx vitest run src/components/widgets/ProfileDetail.test.jsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/widgets/ProfileDetail.jsx react-dashboard/src/components/widgets/ProfileDetail.test.jsx
git commit -m "[feat] Profile editor résumé page-limit toggle + digit control"
```

---

### Task 3: Rebuild `DocumentTree.jsx` (grouped, collapsible, entry sub-cards; section/entry feedback)

**Files:**
- Modify (rewrite): `react-dashboard/src/components/widgets/document/DocumentTree.jsx`
- Modify (rewrite): `react-dashboard/src/components/widgets/document/DocumentTree.test.jsx`

**Interfaces:**
- Consumes: `FieldWidget({ field, onChange, readOnly, valueOnly })` (`../profile-tree/fieldWidgets`); `setFieldValue(root, fieldId, value)` (`./docTreeOps`).
- Produces: `<DocumentTree doc={root} onSave={(newRoot)=>…} notes={{}} setNote={(nodeId,{section,label,note})=>…} />`. Sections collapsed by default; values-only edits call `onSave`; feedback at section + entry level. The `DocumentModal` contract (tree-v1 → `DocumentTree`, legacy → guard) is unchanged.

- [ ] **Step 1: Write the failing tests**

Replace `react-dashboard/src/components/widgets/document/DocumentTree.test.jsx` with:

```javascript
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import DocumentTree from './DocumentTree'

const doc = {
  type: 'root', id: 'r', children: [
    { type: 'section', id: 's1', name: 'Summary', locked: false, children: [
      { type: 'field', id: 'f1', name: 'Summary', kind: 'text', value: 'Hello' }] },
    { type: 'section', id: 's2', name: 'Experience', locked: false, children: [
      { type: 'list', id: 'l2', name: 'Experience', children: [
        { type: 'group', id: 'g1', name: 'Acme', locked: false, children: [
          { type: 'field', id: 'c1', name: 'Company', kind: 'text', value: 'Acme' },
          { type: 'field', id: 't1', name: 'Title', kind: 'text', value: 'Engineer' }] }] }] },
    { type: 'section', id: 's3', name: 'Certs', locked: true, children: [
      { type: 'group', id: 'g3', name: 'C', children: [
        { type: 'field', id: 'f3', name: 'Cert', kind: 'text', value: 'AWS' }] }] },
  ],
}

const noop = () => {}

describe('DocumentTree', () => {
  it('renders section headings but keeps fields hidden until expanded', () => {
    render(<DocumentTree doc={doc} onSave={vi.fn()} notes={{}} setNote={vi.fn()} />)
    expect(screen.getByText('Summary')).toBeTruthy()
    expect(screen.getByText('Experience')).toBeTruthy()
    expect(screen.queryByDisplayValue('Hello')).toBeNull()
  })

  it('expanding a section reveals an editable field that saves the updated tree', () => {
    const onSave = vi.fn()
    render(<DocumentTree doc={doc} onSave={onSave} notes={{}} setNote={vi.fn()} />)
    fireEvent.click(screen.getByText('Summary'))
    fireEvent.change(screen.getByDisplayValue('Hello'), { target: { value: 'Hi' } })
    expect(onSave.mock.calls.at(-1)[0].children[0].children[0].value).toBe('Hi')
  })

  it('a multi-entry section renders a collapsed sub-card per entry', () => {
    render(<DocumentTree doc={doc} onSave={vi.fn()} notes={{}} setNote={vi.fn()} />)
    fireEvent.click(screen.getByText('Experience'))
    expect(screen.getByText('Acme')).toBeTruthy()            // entry summary label
    expect(screen.queryByDisplayValue('Engineer')).toBeNull() // entry collapsed
    fireEvent.click(screen.getByText('Acme'))
    expect(screen.getByDisplayValue('Engineer')).toBeTruthy()
  })

  it('a locked section renders read-only fields and no feedback control', () => {
    render(<DocumentTree doc={doc} onSave={vi.fn()} notes={{}} setNote={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /Feedback on Certs/i })).toBeNull()
    fireEvent.click(screen.getByText('Certs'))
    expect(screen.getByDisplayValue('AWS')).toBeDisabled()
  })

  it('collects feedback at section and entry level only (no per-field control)', () => {
    render(<DocumentTree doc={doc} onSave={vi.fn()} notes={{}} setNote={vi.fn()} />)
    expect(screen.getByRole('button', { name: /Feedback on Summary/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Feedback on Experience/i })).toBeTruthy()
    fireEvent.click(screen.getByText('Experience'))
    expect(screen.getByRole('button', { name: /Feedback on Acme/i })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Feedback on Company/i })).toBeNull()
  })

  it('section feedback records a note keyed by the section id', () => {
    const setNote = vi.fn()
    render(<DocumentTree doc={doc} onSave={vi.fn()} notes={{}} setNote={setNote} />)
    fireEvent.click(screen.getByRole('button', { name: /Feedback on Summary/i }))
    fireEvent.change(screen.getByPlaceholderText(/change in this section/i), { target: { value: 'punchier' } })
    expect(setNote).toHaveBeenCalledWith('s1', { section: 'Summary', label: 'Summary', note: 'punchier' })
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd react-dashboard && npx vitest run src/components/widgets/document/DocumentTree.test.jsx`
Expected: FAIL (the current flat renderer shows fields immediately / has per-field feedback / no entry cards).

- [ ] **Step 3: Rewrite `DocumentTree.jsx`**

Replace `react-dashboard/src/components/widgets/document/DocumentTree.jsx` with:

```javascript
import { useState } from 'react'
import { FieldWidget } from '../profile-tree/fieldWidgets'
import { setFieldValue } from './docTreeOps'

// First non-empty descendant field value → a collapsed entry's preview label.
function entrySummary(entry) {
  for (const f of entry.children || []) {
    if (typeof f.value === 'string' && f.value.trim()) return f.value.trim()
    if (Array.isArray(f.value) && f.value.length) return f.value.join(', ')
  }
  return ''
}

function FeedbackButton({ label, onToggle }) {
  return (
    <button
      type="button" aria-label={`Feedback on ${label}`}
      className="text-space-dim hover:text-purple-300 text-xs shrink-0"
      onClick={(e) => { e.stopPropagation(); onToggle() }}
    >💬</button>
  )
}

function NoteBox({ value, placeholder, onChange }) {
  return (
    <textarea
      className="mt-1 mb-1 w-full bg-white/5 border border-space-border rounded px-2 py-1 text-xs text-space-text"
      placeholder={placeholder} value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}

// 2-col grid: single-line text fields share rows; multi-line kinds span full width.
function GroupGrid({ root, fields, locked, onSave }) {
  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-3">
      {fields.map((f) => (
        <div key={f.id} className={f.kind === 'text' ? '' : 'col-span-2'}>
          <label className="text-xs text-space-dim">{f.name}</label>
          <FieldWidget
            field={f}
            onChange={locked ? undefined : (v) => onSave(setFieldValue(root, f.id, v))}
            readOnly={locked} valueOnly
          />
        </div>
      ))}
    </div>
  )
}

// One list entry → its own collapsible sub-card with a summary label + feedback.
function EntryCard({ root, entry, sectionName, locked, onSave, notes, setNote }) {
  const [collapsed, setCollapsed] = useState(true)
  const [fbOpen, setFbOpen] = useState(false)
  const label = entry.name || entrySummary(entry) || 'Entry'
  const note = notes[entry.id]?.note || ''
  return (
    <div className="border border-space-border/50 rounded-lg p-3 flex flex-col gap-2">
      <div
        className="flex items-center justify-between gap-2 cursor-pointer"
        onClick={() => setCollapsed((c) => !c)}
      >
        <span className="text-xs text-space-text truncate">{label}</span>
        {!locked && <FeedbackButton label={label} onToggle={() => setFbOpen((v) => !v)} />}
      </div>
      {fbOpen && !locked && (
        <NoteBox
          value={note} placeholder="What should change in this entry?"
          onChange={(t) => setNote(entry.id, { section: sectionName, label, note: t })}
        />
      )}
      {!collapsed && <GroupGrid root={root} fields={entry.children || []} locked={locked} onSave={onSave} />}
    </div>
  )
}

// A section's single child: bare field, group, or list of entries.
function SectionBody({ root, section, locked, onSave, notes, setNote }) {
  const child = (section.children || [])[0]
  if (!child) return null
  if (child.type === 'list') {
    return (
      <div className="flex flex-col gap-3">
        {(child.children || []).map((entry) => (
          <EntryCard
            key={entry.id} root={root} entry={entry} sectionName={section.name}
            locked={locked || !!entry.locked} onSave={onSave} notes={notes} setNote={setNote}
          />
        ))}
      </div>
    )
  }
  if (child.type === 'group') {
    return <GroupGrid root={root} fields={child.children || []} locked={locked} onSave={onSave} />
  }
  return <GroupGrid root={root} fields={[child]} locked={locked} onSave={onSave} />
}

function SectionCard({ root, section, onSave, notes, setNote }) {
  const [collapsed, setCollapsed] = useState(true)
  const [fbOpen, setFbOpen] = useState(false)
  const locked = !!section.locked
  const note = notes[section.id]?.note || ''
  return (
    <div className="border border-space-border rounded-xl p-4 flex flex-col gap-3 mb-4">
      <div
        className="flex items-center justify-between gap-2 cursor-pointer border-b border-space-border pb-2"
        onClick={() => setCollapsed((c) => !c)}
      >
        <h3 className="text-sm font-semibold text-space-text">{section.name}</h3>
        {!locked && <FeedbackButton label={section.name} onToggle={() => setFbOpen((v) => !v)} />}
      </div>
      {fbOpen && !locked && (
        <NoteBox
          value={note} placeholder="What should change in this section?"
          onChange={(t) => setNote(section.id, { section: section.name, label: section.name, note: t })}
        />
      )}
      {!collapsed && (
        <SectionBody root={root} section={section} locked={locked} onSave={onSave} notes={notes} setNote={setNote} />
      )}
    </div>
  )
}

export default function DocumentTree({ doc, onSave, notes, setNote }) {
  return (
    <div>
      {(doc.children || []).map((section) => (
        <SectionCard
          key={section.id} root={doc} section={section}
          onSave={onSave} notes={notes} setNote={setNote}
        />
      ))}
    </div>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd react-dashboard && npx vitest run src/components/widgets/document/DocumentTree.test.jsx`
Expected: PASS.

- [ ] **Step 5: Run the full frontend suite + build**

Run: `cd react-dashboard && npx vitest run && npm run build`
Expected: all tests PASS (including `DocumentModal.test.jsx`, whose contract is unchanged) and the build succeeds. If a `DocumentModal.test.jsx` assertion now fails only because sections are collapsed by default, update that test to expand the section before asserting on a field value — do not change the modal's branching logic.

- [ ] **Step 6: Commit**

```bash
git add react-dashboard/src/components/widgets/document/DocumentTree.jsx react-dashboard/src/components/widgets/document/DocumentTree.test.jsx
git commit -m "[feat] Rebuild DocumentTree: grouped grid, collapsible sections + entry cards, section/entry feedback"
```

---

## Self-Review

- **Spec coverage:** Part A (DocumentTree rebuild — collapsible section cards default-collapsed, 2-col group grid, per-entry sub-cards, read-only locked fields, section+entry feedback, per-field feedback removed) → Task 3. Part B (storage semantics absent/null = unlimited, resolver `int|None`, six call-site swap, new-profile seed=1, ProfileDetail toggle+digit control initialized from stored value) → Tasks 1 & 2. Error handling (malformed/≤0 → default; non-digit stripped) → `_normalize_max_pages` (Task 1) + `onPages`/`persist` (Task 2). All spec sections covered.
- **Placeholder scan:** none — every code step shows complete code; fixtures the implementer must write (`seeded_job_with_profile_data`) are described with the exact pattern to copy.
- **Type consistency:** `_normalize_max_pages(value) -> int | None`, `Job._resolve_resume_max_pages(db) -> int | None`, `generate_resume_pdf(..., max_pages=_MAX_PAGES_UNSET)`, `User.resume_max_pages: int | None` are consistent across Task 1. `ResumePageLimit({ value, onSave })` persists `{ resume_max_pages: null | int }` (Task 2) matching the resolver's read keys (Task 1). `DocumentTree`'s `setNote(nodeId, {section,label,note})` and `FieldWidget({field,onChange,readOnly,valueOnly})` match the existing modal contract and `fieldWidgets.jsx` (Task 3).
- **Deletion guardrail:** none — no files are deleted in this plan.
