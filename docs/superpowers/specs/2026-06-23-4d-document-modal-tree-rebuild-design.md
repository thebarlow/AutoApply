# 4D — DocumentModal generic rebuild + tree feedback-refine (Profile Schema Engine #4D)

**Date:** 2026-06-23
**Status:** Design approved, spec under review
**Parent:** Profile Schema Engine #4 (full tree swap) → 4D
**Prior:** 4A (pure foundation), 4B-1 (tree-v1 in production), 4B-2 (per-section refinement), 4C (ATS gate rework)
**Release constraint:** merges to LOCAL `main` only — do NOT push `main` until the whole swap (#4–#6 and #5) is complete.

## Problem

4B-1 made tree-v1 the résumé source of truth, but the document modal was never rewired.
`react-dashboard/src/components/widgets/document/` (`InteractiveResume`, `ResumeSection`,
`items`, `ItemPopover`, `ItemEditor`) is hardwired to the legacy `ResumeDocument` shape
(`profile_summary`, `experience[]`, `projects[]`, `skills[]` via `SECTION_FIELD`).
`GET /{job}/{doc_type}/document` returns the raw `structured_json`, so for a tree-v1
résumé the modal receives a serialized `RootNode` it cannot render — inline editing and
section-anchored feedback are effectively dead for every résumé generated since 4B-1.
`PUT /document` and `run_user_feedback_refine` are likewise legacy-shaped (the latter still
runs the 4B-1 interim "re-author all sections" path for tree-v1 feedback).

4D rebuilds the document surface to render and edit a tree-v1 document generically, wires
the backend value-PUT and feedback-refine to the tree, and retargets feedback to drive
4B-2's selective per-section regeneration. Cover letters are untouched. Legacy
`ResumeDocument` rows are not editable (a graceful guard, not a second editor).

## Scope

- **In:**
  - New generic tree document renderer/editor under
    `react-dashboard/src/components/widgets/document/`, replacing the legacy résumé
    components. Reuses the **pure** field widgets from `profile-tree/fieldWidgets.jsx`.
  - `DocumentModal.jsx` rewired to branch on the loaded doc's `schema` discriminator.
  - `PUT /{job}/{doc_type}/document` tree-v1 résumé branch (validate `RootNode`, persist
    tree-v1, re-render via `write_resume_markdown(RootNode)` + PDF, re-run ATS gate).
  - `run_user_feedback_refine` + `build_feedback_issues` retargeted to node-anchored
    feedback that drives 4B-2 selective regen for tree-v1 résumés.
- **Out / unchanged:**
  - **Cover letters:** `CoverView` and the cover PUT/feedback paths stay as-is.
  - **Legacy `ResumeDocument` résumé rows:** not editable via the new renderer — a
    non-crashing "regenerate to edit" guard replaces inline editing. No legacy editor UI
    is retained.
  - **Structural editing of documents:** no add/remove/rename/reorder/lock/visibility in
    the document modal — those remain the profile editor's job (`profile-tree/`). The
    document is a value snapshot; 4D edits values only.
  - The auto-refine loop (4B-2) and `_refine_doc_md`'s legacy/cover branches.
  - User-formatted PDF / live preview (#6); onboarding parse (#5).

## Decisions (from brainstorming)

- **Edit scope: values only.** The user edits the generated text of present fields
  (text/markdown/bullets/taglist). No per-document structural changes.
- **Legacy rows: tree-only, assume legacy gone.** The new renderer handles tree-v1 only.
  A non-tree-v1 résumé row renders a graceful guard ("Regenerate this résumé to edit it"),
  never a crash and never the old editor.
- **Feedback → 4B-2 selective regen.** A note anchors to a node; the backend maps the node
  to its owning section and regenerates **only** the commented sections (with the notes as
  per-section critique), carrying the rest forward via `authored_values_from_tree`.
- **One plan** (not phased): render + value-edit + PUT + feedback-refine ship together.

## Components

### Frontend

The document tree is the serialized tree-v1 `RootNode` (see `core/profile_tree.py`):
`RootNode → SectionNode[] → (ListNode | GroupNode | FieldNode)`. A `ListNode` has
`children: GroupNode[]` (entries); a `GroupNode` has `children: FieldNode[]`; a
`FieldNode` carries `kind` (`text|markdown|bullets|taglist`), `value` (`str | list[str]`),
`name`, `key`, `locked`-via-parent, `llm_output`. The document tree is already pruned
(invisible + `context_only` nodes removed at build time), so the renderer shows exactly
what the PDF shows.

1. **`document/DocumentTree.jsx` (new)** — recursive renderer. Walks the root's sections;
   for each section renders a heading (`SectionNode.name`) and its children. Field values
   render through the existing **pure** widgets in `profile-tree/fieldWidgets.jsx` (the
   same text/markdown/bullets/taglist editors the profile editor uses), in a read-display
   → click-to-edit mode. List entries (`GroupNode`s under a `ListNode`) render as grouped
   blocks of their fields. No structural controls.

2. **`document/feedbackAnchors.js` (new, pure)** — helpers to compute, for any node, its
   owning section (the ancestor `SectionNode`) and a human anchor label
   (`"<Section> › <field/entry name>"`), and to tell whether a section is `locked`. Used
   to build the feedback note payload and to gate the feedback affordance.

3. **`document/DocumentModal` wiring** (`DocumentModal.jsx`) — on load, branch on
   `doc.schema`:
   - `"tree-v1"` → `DocumentTree` (resume).
   - cover (`docType === "cover"`) → `CoverView` (unchanged).
   - otherwise (legacy résumé row, no `schema`) → guard panel: "Regenerate this résumé to
     edit it." Feedback footer disabled.
   Value edits call `onSave(updatedRoot)` → `PUT /document` with the full tree (the modal
   already does a deep-copy-then-PUT pattern for legacy; the tree version replaces the
   `SECTION_FIELD` mutation with an immutable node-value update keyed by node `id`).
   Feedback notes are keyed by node `id`, each `{ node_id, section, label, note }`.

4. **Field value updates** — a small pure helper (in `DocumentTree.jsx` or a sibling
   `docTreeOps.js`) `setFieldValue(root, fieldId, value) -> newRoot` performing an
   immutable update of the matching `FieldNode.value`. (Mirrors `profile-tree/treeOps.js`
   immutability, but value-only.)

5. **Editing & feedback rules:**
   - Value editing is allowed on any present field, regardless of lock (lock governs LLM
     regen, not manual edits).
   - The feedback affordance is shown on sections and on individual fields/entries; all
     anchor to the owning section for regen. It is **hidden/disabled on locked sections**
     (they won't regenerate).
   - Escape handling (exit inner edit/feedback before closing the modal), the two-column
     modal chrome, and the "Regenerate with feedback (N)" footer are preserved.

### Backend

6. **`PUT /{job}/{doc_type}/document` (`web/routers/jobs.py`)** — add a tree-v1 résumé
   branch ahead of the legacy `_doc_model` validation:
   - If `doc_type == "resume"` and the **payload** is tree-v1 (`is_tree_v1(payload)`),
     deserialize to `RootNode` (`deserialize_document_tree`), persist via
     `serialize_document_tree`, re-render with `job.write_resume_markdown(root)` and
     `generate_resume_pdf`, then spawn the ATS gate. Return the serialized tree.
   - Legacy résumé and cover branches unchanged (validate `_doc_model`, `resume_section_order`,
     etc.). `get_document` needs no change (already returns raw `structured_json`).

7. **`build_feedback_issues` (`web/intake_pipeline.py`)** — accept node-anchored notes
   `{node_id?, section, label, note}`. Each output issue keeps its current shape and gains
   a `section` key: `{"category":"user_feedback","description":"<label>: <note>",
   "section":"<section name>"}`. The legacy/cover consumers ignore the extra key (they only
   read `category`/`description`); the tree-v1 refine groups on it. Blank-note dropping is
   unchanged.

8. **`run_user_feedback_refine` (`web/intake_pipeline.py`)** — for a **tree-v1 résumé**,
   replace the `_refine_doc_md` re-author-all call with 4B-2 selective regen:
   - Load the stored tree, seed `authored = authored_values_from_tree(root_doc)`.
   - Group the user notes by owning section name → `failing = {sections}`,
     `critiques = {section: [issue dicts]}`.
   - `new_vals = generate_resume_by_section(profile_root, job_ctx, client, model,
     resolve=resolve, only_sections=failing, critiques=critiques)`; `authored.update`;
     `build_resume_document_tree` → persist tree-v1 → `write_resume_markdown` + PDF.
   - Then eval-for-score (the existing Step B; no restore-best) and the ATS gate, exactly
     as today. (The cover and legacy résumé feedback paths keep calling `refine_*_md`.)
   - Notes whose section is not regenerable (locked / not visible / no unlocked
     `llm_output` field) are dropped before the call (defensive; mirrors 4B-2). If no
     regenerable section remains, skip the regen call but still run the eval-for-score and
     ATS gate so the stored score/report stay fresh (no crash, no wasted generation).

This reuses the 4B-2 building blocks (`authored_values_from_tree`,
`generate_resume_by_section(only_sections, critiques)`, `build_resume_document_tree`,
`serialize_document_tree`) rather than introducing new refine machinery.

## Data flow

```
Load:  GET /document → raw structured_json → DocumentModal branches on doc.schema
       tree-v1 → DocumentTree ; cover → CoverView ; else → guard
Edit:  field edit → setFieldValue(root,id,val) → PUT /document (tree-v1 branch)
       → persist tree-v1 → write_resume_markdown(root)+PDF → ATS gate
Feedback: node notes {node_id,section,label,note} → build_feedback_issues (section-grouped)
       → run_user_feedback_refine (tree-v1): seed authored → group by section
       → generate_resume_by_section(only_sections, critiques) → rebuild/persist tree-v1
       → re-render → eval-for-score (no restore-best) → ATS gate
```

## Error handling

- Non-tree-v1 résumé row in the modal → guard panel, no crash, no legacy editor.
- PUT tree-v1 validation failure → 400 (as legacy); render failure → 500 (as today).
- Feedback note → no regenerable section → dropped; empty result → eval/ATS still refresh
  (no spurious crash).
- `run_user_feedback_refine` keeps its daemon-thread, log-not-raise contract.

## Back-compat

- Cover letters and legacy résumé rows: PUT/feedback behavior unchanged (legacy résumé
  rows simply lose inline editing in the new modal — by decision).
- Tree-v1 storage format, the discriminator, and 4B-2's auto-refine loop are unchanged.
- No schema/DB migration.

## Testing

- **Frontend (Vitest/RTL):**
  - `DocumentTree` renders a tree-v1 doc's sections/fields (headings + values present).
  - Editing a field value and saving calls `onSave` with a root whose matching
    `FieldNode.value` is updated and all other nodes unchanged (immutability).
  - `setFieldValue` updates only the targeted field id.
  - Feedback collected on a field/section produces a note carrying the owning `section` and
    a `node_id`.
  - A locked section shows no feedback affordance; value editing on its fields still works.
  - A legacy (no-`schema`) résumé doc renders the guard, not a crash.
- **Backend (pytest, in-memory StaticPool per existing patterns):**
  - `PUT /document` with a tree-v1 résumé payload persists a tree-v1 row and re-renders
    (assert the stored row `is_tree_v1` and the `.md` is frontmatter-free).
  - `run_user_feedback_refine` for a tree-v1 résumé with a note on section "Summary"
    regenerates only "Summary" (stub `generate_resume_by_section`, assert `only_sections`
    and `critiques` carry the note; other sections carried forward).
  - Node→section grouping in `build_feedback_issues` / the refine helper.
  - A note on a locked/non-regenerable section is dropped.
  - Cover feedback and a legacy résumé feedback still call `refine_*_md` (unchanged path).

## Out of scope

- Per-document structural editing; document-vs-profile divergence.
- A diff/preview before applying feedback; per-note accept/reject; multi-turn feedback
  (these live in the separate "Improve the document feedback system" TODO).
- User-formatted PDF / live preview (#6); onboarding parse (#5).
- Cover-letter sectioning or tree conversion.
