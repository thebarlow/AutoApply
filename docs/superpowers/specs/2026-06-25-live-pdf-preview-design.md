# Live in-dashboard PDF preview (#6A)

**Date:** 2026-06-25
**Status:** Design approved
**Sub-project:** Profile Schema Engine #6, phase A (live preview). The
user-customizable template system (#6B) is a separate, later sub-project.
**Release constraint:** merges to LOCAL `main` only — do NOT push `main` until
the whole Profile Schema Engine swap (#4 → #6 → #5) is complete.

## Problem

After generating a résumé or cover letter, the only way to see the rendered PDF
is to download it (`GET /api/jobs/{key}/resume|cover`) and open it externally.
Editing in the DocumentModal (tree-v1 résumé fields, cover body) gives no visual
feedback on how a change affects the actual page — overflow, pagination, the
1-page shrink-to-fit. The user wants an in-dashboard preview that shows the real
PDF and updates as they save edits.

## Decisions (from brainstorming)

- **Fidelity:** show the **real PDF**, embedded — pixel-identical to the
  download, including pagination and shrink-to-fit. Not an HTML approximation.
- **Refresh trigger:** **on save** — the preview refreshes when an edit is
  persisted (and on modal open). No per-keystroke or debounced re-render.
- **Layout:** **side-by-side** — editor left, PDF preview right, within the
  DocumentModal.
- **Scope:** **both** résumé and cover letters.
- **Display mechanism:** **native `<iframe>`** pointed at the existing PDF
  endpoint with a cache-busting query param. No new dependencies (no PDF.js).

## Architecture & data flow

The preview is a same-origin `<iframe>` whose `src` is the existing PDF
endpoint plus a cache-busting version param:
`/api/jobs/{jobKey}/{docType}?v={previewVersion}`. It reuses the PDF that the
save path already produces — there is no new render pipeline.

`DocumentModal` owns a `previewVersion` integer. It increments on:

1. modal open / document (re)load (`reload`),
2. a successful save PUT — `handleTreeSave` (tree-v1 résumé) and the cover
   `onSave`, **after** the PUT promise resolves.

Because the tree-v1 résumé PUT (`web/routers/jobs.py:567`) re-renders the PDF
synchronously before responding, the on-disk PDF is fresh by the time the PUT
resolves; bumping `previewVersion` then changes the iframe `src`, forcing the
browser to refetch and repaint the new PDF. Same-origin session cookies carry
auth, so this works both locally and on the hosted (OAuth-gated) app.

The **feedback-regen path is out of scope for in-modal refresh**: `submitNotes`
calls `onClose()` and the regeneration runs asynchronously in the background, so
the modal is already closed. Reopening the modal triggers `reload`, which loads
the freshly regenerated document and bumps `previewVersion`. No websocket/poll
wiring is added.

## Components

### `react-dashboard/src/components/widgets/document/DocumentPreview.jsx` (new)

Presentation only. Props: `{ jobKey, docType, version }`.

- Renders `<iframe title="PDF preview" src={`/api/jobs/${jobKey}/${docType}?v=${version}`}>`.
- **Not-generated state:** the modal already loads the document JSON
  (`getDocument`) and knows whether the document exists. When there is no
  document, the modal shows "Generate this document to see a preview." in place
  of the iframe — no `onError` handler or endpoint probe is needed. The iframe
  is only mounted once a document exists.
- **Refreshing state:** a subtle overlay while a save is in flight (driven by a
  `refreshing` prop from the modal), so the user sees the preview is updating.
- **Error state:** if a refresh fails (e.g. render overflow → 500), keep showing
  the last successfully loaded PDF and surface a non-blocking
  "Couldn't refresh preview" note. Editing is never blocked by a preview error.

Single responsibility: display the current PDF for one job/doc at one version.
It does not fetch document JSON, save, or know about the tree.

### `react-dashboard/src/components/widgets/DocumentModal.jsx` (modified)

- Widen the modal shell from `max-w-4xl` to `max-w-6xl` to fit two columns.
- Split the scrolling body into a two-column flex: editor (existing
  `DocumentTree` / legacy guard / cover editor) on the left, `DocumentPreview`
  on the right.
- Add `previewVersion` state (and a `refreshing` flag). Bump `previewVersion`:
  in `reload`, after `handleTreeSave`'s `putDocument` resolves, and after the
  cover `onSave`'s PUT resolves. Set `refreshing` true around those saves.
- **Responsive:** below a width breakpoint (Tailwind `lg:`), collapse to a
  stacked layout — editor above, preview below — so the modal stays usable on
  narrow screens. No tab system.

## Backend

No new endpoints, no schema or migration changes. The PDF endpoints
(`serve_resume`, `serve_cover`) and the save-time re-render already exist.

One verification task: confirm the **cover** PUT re-renders the cover PDF on
save the way the résumé PUT does (`web/routers/jobs.py:589–592` indicates it
calls `generate_cover_pdf`). If a gap exists, add the cover re-render so the
cover preview reflects saved edits. This is the only potential backend change,
and only if the gap is real.

## Error handling (summary)

- Not-generated document → friendly "generate to preview" placeholder, not a
  broken iframe.
- Render/refresh failure → last good PDF retained + non-blocking note; editing
  continues.
- Narrow viewport → stacked layout fallback.

## Testing

- **Frontend (Vitest + RTL):**
  - `DocumentPreview` renders an iframe whose `src` targets
    `/api/jobs/{key}/{docType}` with the given `?v=` version.
  - changing the `version` prop changes the iframe `src` (forces refetch).
  - the refresh-error state renders its message; the modal shows the
    not-generated placeholder (and no iframe) when no document exists.
  - `DocumentModal` renders the side-by-side editor+preview for a tree-v1
    résumé and for a cover, and a successful save bumps the preview version
    (asserted via the iframe `src` changing).
- **Backend (pytest):** only if the cover-render-on-save gap is real — a test
  that the cover PUT writes a fresh cover PDF.

## Out of scope

- The user-customizable template system / per-section formatting controls —
  that is sub-project **#6B**, a separate spec.
- Direct "edit-on-the-PDF" / hover-to-highlight-region interactions (clicking
  PDF regions to edit). The preview is read-only; editing stays in the tree
  editor beside it.
- Live preview during the asynchronous feedback-regeneration (modal closes;
  reopen reloads).
- Cover-letter editor redesign (cover editing is unchanged).
- PDF.js or any in-app PDF viewer chrome (page nav, zoom) — rely on the
  browser's native PDF rendering.
