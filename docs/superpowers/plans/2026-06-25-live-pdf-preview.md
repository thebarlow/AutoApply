# Live in-dashboard PDF preview (#6A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the real generated PDF beside the document editor in the DocumentModal, refreshing on save, for both résumés and cover letters.

**Architecture:** A new read-only `DocumentPreview` component renders a same-origin `<iframe>` pointed at the existing PDF endpoint (`/api/jobs/{key}/{docType}`) with a cache-busting `?v={version}` param. `DocumentModal` owns a `previewVersion` counter, lays the editor and preview out side-by-side, and bumps the counter after each successful save (the PUT already re-renders the PDF synchronously) so the iframe refetches the fresh PDF.

**Tech Stack:** React, Vitest + React Testing Library, Tailwind CSS. No new dependencies.

## Global Constraints

- No new npm dependencies (no PDF.js); use a native `<iframe>` and the browser's built-in PDF rendering. (Spec: "Display mechanism: native `<iframe>` … No new dependencies (no PDF.js).")
- Show the **real PDF**, not an HTML approximation. (Spec: "Fidelity: show the real PDF, embedded.")
- Refresh **on save** only — no per-keystroke or debounced re-render. (Spec: "Refresh trigger: on save.")
- Layout is **side-by-side** (editor left, preview right), collapsing to stacked below Tailwind `lg`. (Spec: "Layout: side-by-side.")
- Applies to **both** résumé and cover letters. (Spec: "Scope: both.")
- The preview is **read-only**; editing stays in the tree/cover editor beside it. (Spec out-of-scope: no edit-on-the-PDF.)
- Backend is unchanged: the document PUT already re-renders both PDFs (`web/routers/jobs.py:567` résumé tree-v1, `:589` legacy résumé, `:592` cover). No new endpoints, no schema/migration.
- Release constraint: merges to LOCAL `main` only — do NOT push `main`.

**Reference patterns (read before starting):**
- API base is root-relative: `react-dashboard/src/api.js:1` (`const BASE = ''`), so an iframe `src` of `/api/jobs/...` resolves in dev (Vite proxy) and prod.
- PDF endpoints: `web/routers/jobs.py:405` (`GET /{job_key}/resume`) and `:418` (`GET /{job_key}/cover`), mounted under `/api/jobs`. Full paths: `/api/jobs/{key}/resume` and `/api/jobs/{key}/cover`.
- Modal current shape: `react-dashboard/src/components/widgets/DocumentModal.jsx` — `reload` (`:55`), `handleTreeSave` (`:66`), cover `onSave` (`:105`), body container `:90`, shell `max-w-4xl` `:83`.
- Vitest mock pattern: `react-dashboard/src/components/widgets/DocumentModal.test.jsx:5-10`.

---

### Task 1: `DocumentPreview` component

**Files:**
- Create: `react-dashboard/src/components/widgets/document/DocumentPreview.jsx`
- Test: `react-dashboard/src/components/widgets/document/DocumentPreview.test.jsx`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `export default function DocumentPreview({ jobKey, docType, version, refreshing })` — renders an `<iframe title="PDF preview">` whose `src` is `/api/jobs/${jobKey}/${docType}?v=${version}`. When `refreshing` is truthy, also renders an overlay element with text `Refreshing…`. Task 2 mounts this in the modal's right column.

- [ ] **Step 1: Write the failing test**

Create `react-dashboard/src/components/widgets/document/DocumentPreview.test.jsx`:

```jsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import DocumentPreview from './DocumentPreview'

describe('DocumentPreview', () => {
  it('renders an iframe pointed at the versioned PDF endpoint', () => {
    render(<DocumentPreview jobKey="jk" docType="resume" version={3} />)
    const frame = screen.getByTitle('PDF preview')
    expect(frame.tagName).toBe('IFRAME')
    expect(frame.getAttribute('src')).toBe('/api/jobs/jk/resume?v=3')
  })

  it('uses the cover endpoint for cover docs', () => {
    render(<DocumentPreview jobKey="jk" docType="cover" version={1} />)
    expect(screen.getByTitle('PDF preview').getAttribute('src')).toBe('/api/jobs/jk/cover?v=1')
  })

  it('changing version changes the iframe src (forces refetch)', () => {
    const { rerender } = render(<DocumentPreview jobKey="jk" docType="resume" version={1} />)
    expect(screen.getByTitle('PDF preview').getAttribute('src')).toBe('/api/jobs/jk/resume?v=1')
    rerender(<DocumentPreview jobKey="jk" docType="resume" version={2} />)
    expect(screen.getByTitle('PDF preview').getAttribute('src')).toBe('/api/jobs/jk/resume?v=2')
  })

  it('shows a refreshing overlay only while refreshing', () => {
    const { rerender } = render(<DocumentPreview jobKey="jk" docType="resume" version={1} />)
    expect(screen.queryByText('Refreshing…')).toBeNull()
    rerender(<DocumentPreview jobKey="jk" docType="resume" version={1} refreshing />)
    expect(screen.getByText('Refreshing…')).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `react-dashboard/`): `npm run test -- DocumentPreview`
Expected: FAIL — cannot resolve `./DocumentPreview`.

- [ ] **Step 3: Write the component**

Create `react-dashboard/src/components/widgets/document/DocumentPreview.jsx`:

```jsx
// Read-only PDF preview: embeds the real generated PDF from the existing
// endpoint. `version` is a cache-busting counter — bumping it (after a save
// re-renders the PDF) changes the src so the browser refetches the fresh file.
export default function DocumentPreview({ jobKey, docType, version, refreshing }) {
  const src = `/api/jobs/${jobKey}/${docType}?v=${version}`
  return (
    <div className="relative w-full h-full">
      <iframe
        title="PDF preview"
        src={src}
        className="w-full h-full rounded border border-space-border bg-white"
      />
      {refreshing && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/30 rounded">
          <span className="text-xs text-white bg-black/60 px-2 py-1 rounded">Refreshing…</span>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `react-dashboard/`): `npm run test -- DocumentPreview`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/widgets/document/DocumentPreview.jsx react-dashboard/src/components/widgets/document/DocumentPreview.test.jsx
git commit -m "[feat] Add DocumentPreview read-only PDF iframe component"
```

---

### Task 2: Wire the preview into `DocumentModal` (side-by-side, save-to-refresh)

**Files:**
- Modify: `react-dashboard/src/components/widgets/DocumentModal.jsx`
- Modify: `react-dashboard/src/components/widgets/DocumentModal.test.jsx`

**Interfaces:**
- Consumes: `DocumentPreview` from Task 1 (`./document/DocumentPreview`), props `{ jobKey, docType, version, refreshing }`.
- Produces: no exports for later tasks (terminal task).

**Behavior to implement:**
1. Widen the modal shell `max-w-4xl` → `max-w-6xl`.
2. Add state: `const [previewVersion, setPreviewVersion] = useState(0)` and `const [refreshing, setRefreshing] = useState(false)`.
3. Bump `previewVersion` in `reload` (covers initial open and the cover save, which calls `reload`) and at the end of a successful `handleTreeSave` (the résumé live-edit loop does not call `reload`).
4. Set `refreshing` true around the `handleTreeSave` PUT and false after (success or failure).
5. Split the modal body into a responsive two-column layout: editor column (existing content) on the left, preview column on the right. The preview column renders `DocumentPreview` when a document exists, otherwise the placeholder text `Generate this document to see a preview.`
6. On a failed save, do **not** bump `previewVersion` (keep the last good PDF); the existing `loadError` text already surfaces the failure.

- [ ] **Step 1: Write the failing tests**

Append to `react-dashboard/src/components/widgets/DocumentModal.test.jsx` (inside the existing `describe`, after the legacy test). Note the existing mock at the top of the file already mocks `getDocument`, `putDocument`, `submitFeedback`; add `putDocument` import:

```jsx
  it('renders a PDF preview iframe beside a tree-v1 résumé', async () => {
    getDocument.mockResolvedValue({
      schema: 'tree-v1', type: 'root', id: 'r', children: [
        { type: 'section', id: 's1', name: 'Summary', locked: false, children: [
          { type: 'field', id: 'f1', name: 'Summary', kind: 'text', value: 'Hi' }] }],
    })
    render(<DocumentModal job={job} docType="resume" processing={false} onClose={vi.fn()} />)
    const frame = await screen.findByTitle('PDF preview')
    expect(frame.getAttribute('src')).toBe('/api/jobs/jk/resume?v=1')
  })

  it('renders a PDF preview iframe for a cover letter', async () => {
    getDocument.mockResolvedValue({ body: 'Dear team', section_order: [] })
    render(<DocumentModal job={job} docType="cover" processing={false} onClose={vi.fn()} />)
    const frame = await screen.findByTitle('PDF preview')
    expect(frame.getAttribute('src')).toBe('/api/jobs/jk/cover?v=1')
  })

  it('shows a placeholder instead of an iframe when there is no document', async () => {
    getDocument.mockRejectedValue(new Error('GET /api/jobs/jk/resume/document → 404'))
    render(<DocumentModal job={job} docType="resume" processing={false} onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/Generate this document to see a preview/i)).toBeTruthy())
    expect(screen.queryByTitle('PDF preview')).toBeNull()
  })

  it('bumps the preview version after a successful tree save', async () => {
    getDocument.mockResolvedValue({
      schema: 'tree-v1', type: 'root', id: 'r', children: [
        { type: 'section', id: 's1', name: 'Summary', locked: false, children: [
          { type: 'field', id: 'f1', name: 'Summary', kind: 'text', value: 'Hi' }] }],
    })
    render(<DocumentModal job={job} docType="resume" processing={false} onClose={vi.fn()} />)
    const frame = await screen.findByTitle('PDF preview')
    expect(frame.getAttribute('src')).toBe('/api/jobs/jk/resume?v=1')
    fireEvent.click(screen.getByText('Summary'))            // expand the section
    const input = screen.getByDisplayValue('Hi')
    fireEvent.change(input, { target: { value: 'Hello' } }) // edits trigger handleTreeSave (PUT)
    await waitFor(() =>
      expect(screen.getByTitle('PDF preview').getAttribute('src')).toBe('/api/jobs/jk/resume?v=2'))
  })
```

Update the import line near the top of the test file from `import { getDocument } from '../../api'` to:

```jsx
import { getDocument, putDocument } from '../../api'
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `react-dashboard/`): `npm run test -- DocumentModal`
Expected: FAIL — no element with title `PDF preview` (preview not wired yet).

- [ ] **Step 3: Implement the modal changes**

In `react-dashboard/src/components/widgets/DocumentModal.jsx`:

a) Add the import near the other widget imports:

```jsx
import DocumentPreview from './document/DocumentPreview'
```

b) Add state next to the existing `useState` calls:

```jsx
  const [previewVersion, setPreviewVersion] = useState(0)
  const [refreshing, setRefreshing] = useState(false)
```

c) In `reload`, bump the version when the document resolves:

```jsx
  const reload = () => {
    setDoc(null)  // clear stale content while the new doc loads (job/tab switch)
    getDocument(job.job_key, docType)
      .then((d) => { setDoc(d); setLoadError(null); setPreviewVersion((v) => v + 1) })
      .catch((e) => setLoadError(e?.message || 'Could not load document'))
  }
```

d) In `handleTreeSave`, set `refreshing` around the PUT and bump the version only on success:

```jsx
  const handleTreeSave = async (nextRoot) => {
    setDoc(nextRoot)
    setRefreshing(true)
    try {
      await putDocument(job.job_key, 'resume', nextRoot)
      setLoadError(null)
      setPreviewVersion((v) => v + 1)
    } catch (e) {
      setLoadError(e?.message || 'Failed to save changes')
    } finally {
      setRefreshing(false)
    }
  }
```

e) Widen the shell: change `max-w-4xl` to `max-w-6xl` on the `motion.div` (line ~83).

f) Replace the body container (the `<div className="flex-1 overflow-auto p-5">` block, lines ~90–114) so the existing editor content sits in a left column and the preview sits in a right column. Keep the existing editor children unchanged inside the left column:

```jsx
        <div className="flex-1 overflow-hidden p-5 flex flex-col lg:flex-row gap-4">
          <div className="flex-1 overflow-auto lg:w-1/2">
            {loadError && <p className="text-xs text-red-400">{loadError}</p>}
            {!loadError && !doc && <p className="text-xs text-space-dim">Loading…</p>}
            {doc && docType === 'resume' && isTreeV1 && (
              <DocumentTree doc={doc} onSave={handleTreeSave} notes={notes} setNote={setNote} />
            )}
            {doc && isLegacyResume && (
              <p className="text-sm text-space-dim">
                This résumé was generated before the new editor. Regenerate it to edit inline.
              </p>
            )}
            {doc && docType === 'cover' && (
              <CoverView
                doc={doc}
                escapeRef={escapeRef}
                onSave={async (body) => {
                  const next = { ...doc, body }
                  await putDocument(job.job_key, 'cover', next)
                  reload()
                }}
                feedback={coverFeedback}
                setFeedback={setCoverFeedback}
              />
            )}
          </div>
          <div className="flex-1 lg:w-1/2 min-h-[300px] lg:min-h-0">
            {doc ? (
              <DocumentPreview
                jobKey={job.job_key} docType={docType}
                version={previewVersion} refreshing={refreshing}
              />
            ) : (
              <p className="text-xs text-space-dim">Generate this document to see a preview.</p>
            )}
          </div>
        </div>
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `react-dashboard/`): `npm run test -- DocumentModal`
Expected: PASS (existing 2 tests + 4 new tests). The pre-existing tests still pass because the editor content is unchanged, only relocated into the left column.

- [ ] **Step 5: Run the full frontend suite + build**

Run (from `react-dashboard/`): `npm run test` then `npm run build`
Expected: all suites pass; build succeeds.

- [ ] **Step 6: Commit**

```bash
git add react-dashboard/src/components/widgets/DocumentModal.jsx react-dashboard/src/components/widgets/DocumentModal.test.jsx
git commit -m "[feat] Side-by-side live PDF preview in DocumentModal"
```

---

## Notes for the implementer

- **Why the version starts visible as `v=1`:** `previewVersion` starts at `0`; `reload` runs once on mount (`useEffect(reload, [job.job_key, docType])`) and bumps it to `1` when the document loads. So the first rendered iframe src is `?v=1`. The save tests assert the bump to `?v=2`.
- **Refresh-error handling is intentionally minimal:** a PDF render failure surfaces as a 500 from the PUT (caught in `handleTreeSave` → `loadError`), and because the bump is skipped on failure the iframe keeps showing the last good PDF. There is no separate error UI in `DocumentPreview`.
- **No backend changes:** do not modify `web/routers/jobs.py`. The cover and résumé PUTs already re-render their PDFs synchronously before responding.
- **Do not add per-keystroke refresh.** `FieldWidget`'s text inputs call `onChange` → `handleTreeSave` per edit, which is the project's existing save model; that is the intended "on save" trigger. Do not add debouncing or change the save granularity in this sub-project.
