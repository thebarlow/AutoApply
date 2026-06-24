# 4D DocumentModal Tree Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make tree-v1 résumés editable in the document modal again and route node-anchored user feedback through 4B-2 selective per-section regeneration.

**Architecture:** Backend gains a tree-v1 branch in `PUT /document` (persist `RootNode`, re-render, re-gate) and a tree-v1 feedback-refine that maps notes→sections and calls `generate_resume_by_section(only_sections, critiques)`. Frontend replaces the legacy `InteractiveResume` family with a generic `DocumentTree` renderer (reusing the pure `profile-tree/fieldWidgets.jsx`) and rewires `DocumentModal` to branch on the `schema` discriminator. Values-only editing; cover unchanged; legacy résumé rows get a non-crashing guard.

**Tech Stack:** Python/FastAPI/pytest (in-memory StaticPool); React/Vitest/RTL. Spec: `docs/superpowers/specs/2026-06-23-4d-document-modal-tree-rebuild-design.md`.

## Global Constraints

- Merges to LOCAL `main` only — do NOT push `main` (whole-swap release gate, #4–#6 + #5).
- Tree-v1 discriminator: a document tree is JSON with top-level `"schema": "tree-v1"`; legacy résumé rows have no `schema` key. Branch with `is_tree_v1` (backend) / `doc.schema === 'tree-v1'` (frontend).
- Values-only editing in the document modal — NO add/remove/rename/reorder/lock/visibility (those stay in the profile editor).
- Cover letters and legacy `ResumeDocument` résumé PUT/feedback paths are UNCHANGED. Legacy résumé rows are not editable (graceful "regenerate to edit" guard, never a crash, never the old editor).
- Feedback drives 4B-2 selective regen: regenerate ONLY commented, regenerable sections (visible, unlocked, ≥1 unlocked `llm_output` field) with the notes as critique; carry the rest forward via `authored_values_from_tree`. No restore-best (user-directed result is kept), matching current feedback semantics. Then eval-for-score + ATS gate.
- Feedback issue dicts keep `{"category":"user_feedback","description":"<label>: <note>"}` and gain a `"section":"<name>"` key.

---

### Task 1: `PUT /document` tree-v1 résumé branch

**Files:**
- Modify: `web/routers/jobs.py` (`put_document`, ~line 542)
- Test: `tests/web/test_document_api.py`

**Interfaces:**
- Consumes: `is_tree_v1`, `deserialize_document_tree`, `serialize_document_tree` (`core/resume_document_io.py`); `job.write_resume_markdown(root: RootNode)`, `job.generate_resume_pdf`.
- Produces: a tree-v1 résumé PUT that persists a tree-v1 row and re-renders; legacy/cover unchanged.

- [ ] **Step 1: Write the failing test**

Add to `tests/web/test_document_api.py` (reuse the file's existing app/client/session fixtures; if a tree-v1 résumé row helper does not exist, build the payload inline from a minimal RootNode dict with `"schema":"tree-v1"`):

```python
def test_put_resume_tree_v1_roundtrip(client, db_session, seeded_job):
    # A minimal tree-v1 résumé payload (header section + one custom section).
    payload = {
        "schema": "tree-v1", "type": "root", "id": "r",
        "children": [
            {"type": "section", "id": "s1", "name": "Summary", "role": "summary",
             "order": 0, "visible": True, "locked": False, "children": [
                {"type": "field", "id": "f1", "name": "Summary", "key": "summary",
                 "order": 0, "visible": True, "kind": "markdown",
                 "value": "Edited summary text.", "llm_output": True}]},
        ],
    }
    r = client.put(f"/api/jobs/{seeded_job}/resume/document", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body.get("schema") == "tree-v1"
    # Stored row is tree-v1 and contains the edited value.
    from db.database import Document
    row = Document.fetch(db_session, seeded_job, "resume", profile_id=1)
    assert row is not None
    from core.resume_document_io import is_tree_v1
    assert is_tree_v1(row.structured_json)
    assert "Edited summary text." in row.structured_json
```

> If `tests/web/test_document_api.py` has no `seeded_job`/`client`/`db_session` fixtures, copy the in-memory StaticPool session + TestClient setup from another `tests/web/` file in this suite and seed a Job with `profile_id=1`; do not invent shared fixtures.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/web/test_document_api.py::test_put_resume_tree_v1_roundtrip -q`
Expected: FAIL (the legacy branch tries to validate the tree payload as `ResumeDocument` → 400).

- [ ] **Step 3: Add the tree-v1 branch to `put_document`**

In `web/routers/jobs.py`, add imports near the other `core.resume_document_io` usages at top of the module:

```python
from core.resume_document_io import is_tree_v1, deserialize_document_tree, serialize_document_tree
```

In `put_document`, immediately after the `job is None` check (before `doc = _doc_model(...)`), insert:

```python
    if doc_type == "resume" and payload.get("schema") == "tree-v1":
        import json as _json2
        try:
            root = deserialize_document_tree(_json2.dumps(payload))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid document: {exc}")
        serialized = serialize_document_tree(root)
        Document.upsert(db, job_key, "resume", serialized, profile_id=profile_id)
        try:
            job.write_resume_markdown(root)
            job.generate_resume_pdf(_RESUME_TEMPLATE, db, max_pages=1)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"PDF render failed: {exc}")
        db.refresh(job)
        _emit(job)
        from web.intake_pipeline import run_ats_gate
        _spawn(run_ats_gate, job_key, profile_id)
        return _json.loads(serialized)
```

(The existing legacy `ResumeDocument`/cover code below is unchanged.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/web/test_document_api.py -q`
Expected: PASS (new test + existing legacy/cover tests).

- [ ] **Step 5: Commit**

```bash
git add web/routers/jobs.py tests/web/test_document_api.py
git commit -m "[feat] PUT /document tree-v1 résumé branch (persist tree, re-render, re-gate)"
```

---

### Task 2: Tree-v1 feedback-refine via 4B-2 selective regen

**Files:**
- Modify: `web/intake_pipeline.py` (`build_feedback_issues`; new `_run_resume_feedback_refine`; dispatch in `run_user_feedback_refine`)
- Test: `tests/web/test_feedback_refine.py` (create if absent)

**Interfaces:**
- Consumes: `Job._regenerable_section_names(db)`, `authored_values_from_tree`, `generate_resume_by_section(root, job_ctx, client, model, resolve=, only_sections=, critiques=)`, `build_resume_document_tree`, `serialize_document_tree`, `deserialize_document_tree`, `resolve_profile_tokens`, `_apply_template`, `user.profile_tree_root()`, `job.build_resume_prompt`.
- Produces: a tree-v1 résumé feedback path that regenerates only commented sections; cover + legacy résumé feedback still call `refine_*_md`.

- [ ] **Step 1: Write the failing tests**

Create `tests/web/test_feedback_refine.py` (copy the StaticPool in-memory session + user/job seeding from `tests/web/` or `tests/core/test_job.py`; seed a tree-v1 résumé Document row for the job):

```python
from unittest.mock import patch
from web.intake_pipeline import build_feedback_issues


def test_build_feedback_issues_carries_section():
    notes = [{"node_id": "f1", "section": "Summary", "label": "Summary", "note": "punchier"}]
    issues = build_feedback_issues(notes)
    assert issues == [{"category": "user_feedback",
                       "description": "Summary: punchier", "section": "Summary"}]


def test_build_feedback_issues_drops_blank():
    assert build_feedback_issues([{"section": "X", "label": "X", "note": "  "}]) == []
```

Add an engine test that stubs the generator and asserts only the commented section regenerates (mirror the 4B-2 engine test in `tests/web/`; seed a tree-v1 résumé row with two regenerable sections "Summary" and "Skills"):

```python
def test_feedback_refine_regenerates_only_commented_section(tree_v1_job, db_session):
    from web.intake_pipeline import _run_resume_feedback_refine
    notes = [{"node_id": "f1", "section": "Summary", "label": "Summary", "note": "punchier"}]
    captured = {}

    def fake_gen(root, ctx, client, model, resolve=None, only_sections=None, critiques=None):
        captured["only"] = set(only_sections or set())
        captured["crit"] = critiques or {}
        return {}  # no field changes; carry-forward keeps prior values

    with patch("web.intake_pipeline.generate_resume_by_section", side_effect=fake_gen), \
         patch("web.intake_pipeline.run_ats_gate"):
        _run_resume_feedback_refine(tree_v1_job, "resume", notes, profile_id=1)

    assert captured["only"] == {"Summary"}
    assert "Summary" in captured["crit"]
    assert captured["crit"]["Summary"][0]["description"] == "Summary: punchier"
```

> `tree_v1_job` is a fixture you write in this file: seed a User (with a profile tree containing visible/unlocked "Summary" and "Skills" sections each with an unlocked `llm_output` field) and a Job, persist a tree-v1 résumé Document row (`serialize_document_tree(build_resume_document_tree(root, authored))`) and a `{job_key}_resume.md` under a monkeypatched `_OUTPUTS_DIR`. Follow the seeding pattern already used by the 4B-2 section-refinement test.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/web/test_feedback_refine.py -q`
Expected: FAIL — `build_feedback_issues` does not yet emit `section`; `_run_resume_feedback_refine` does not exist.

- [ ] **Step 3: Extend `build_feedback_issues`**

In `web/intake_pipeline.py` replace the loop body of `build_feedback_issues`:

```python
    issues = []
    for n in notes:
        text = (n.get("note") or "").strip()
        if not text:
            continue
        label = (n.get("label") or "").strip() or "Document"
        issue = {"category": "user_feedback", "description": f"{label}: {text}"}
        section = (n.get("section") or "").strip()
        if section:
            issue["section"] = section
        issues.append(issue)
    return issues
```

- [ ] **Step 4: Add `_run_resume_feedback_refine` and dispatch**

In `web/intake_pipeline.py`, add this module-level function (model the LLM-client/prompt resolution and the eval-for-score Step B on the existing `run_user_feedback_refine`; no turn loop, no restore-best):

```python
def _run_resume_feedback_refine(job_key: str, doc_type: str, notes: list[dict], profile_id: int) -> None:
    """Tree-v1 résumé user-feedback refine: regenerate only the commented,
    regenerable sections via 4B-2 selective regen, then eval-for-score + ATS.
    No restore-best (the user-directed result is always kept)."""
    import json as _json
    from pathlib import Path
    from core.document_tree import authored_values_from_tree, build_resume_document_tree
    from core.profile_tree import resolve_profile_tokens
    from core.resume_document_io import serialize_document_tree, deserialize_document_tree
    from core.job import Job, _apply_template
    from db.database import Document

    template_path = Path(__file__).parent.parent / "generator" / "resume_template.html"
    issues = build_feedback_issues(notes)
    if not issues:
        return

    db = SessionLocal()
    try:
        job = Job.get(job_key, db, profile_id)
        if job is None:
            return
        user = User.load(db, profile_id)
        row = Document.fetch(db, job_key, "resume", profile_id)
        if row is None:
            return

        # Group notes by owning section, keep only regenerable ones.
        regenerable = set(job._regenerable_section_names(db))
        by_section: dict[str, list[dict]] = {}
        for i in issues:
            sec = i.get("section")
            if sec in regenerable:
                by_section.setdefault(sec, []).append(i)

        if by_section:
            try:
                gen_prompt = user.resolve_prompt("resume")
            except PromptNotConfiguredError as exc:
                print(f"[feedback:resume] {job_key}: prompt not configured — {exc}", flush=True)
                return
            gen_client, gen_model = get_client_for_profile(
                user, getattr(user, "prompt_resume_model", "") or "")
            root = user.profile_tree_root()
            authored = authored_values_from_tree(deserialize_document_tree(row.structured_json))
            job_ctx = job.build_resume_prompt(user, gen_prompt, db)

            def resolve(text: str) -> str:
                return _apply_template(resolve_profile_tokens(root, text), {"job": job, "user": user})

            llm_status.start(job_key, "resume_refine")
            try:
                with meter_action(db, profile_id, action="refine", job_key=job_key):
                    new_vals = generate_resume_by_section(
                        root, job_ctx, gen_client, gen_model, resolve=resolve,
                        only_sections=set(by_section), critiques=by_section)
                authored.update(new_vals)
                doc_tree = build_resume_document_tree(root, authored)
                Document.upsert(db, job_key, "resume",
                                serialize_document_tree(doc_tree), profile_id=profile_id)
                job.write_resume_markdown(doc_tree)
                job.generate_resume_pdf(template_path, db, max_pages=1)
                db.commit(); db.refresh(job); _emit(job)
            except Exception as exc:
                db.rollback()
                job = Job.get(job_key, db, profile_id)
                job.last_result_error = f"Resume feedback refine failed: {exc}"
                job.unread_indicator = "error"
                db.commit(); _emit(job)
                print(f"[feedback:resume] {job_key}: refine failed — {exc}", flush=True)
                return
            finally:
                llm_status.finish(job_key, "resume_refine")

        # Eval-for-score (informational; non-fatal; no restore-best).
        llm_status.start(job_key, "resume_eval")
        try:
            eval_prompt = user.resolve_prompt("resume_eval_sectioned")
            eval_client, eval_model = get_client_for_profile(
                user, getattr(user, "prompt_resume_eval_sectioned_model", "") or "")
            with meter_action(db, profile_id, action="eval", job_key=job_key):
                scores = job.evaluate_resume_sections(eval_prompt, user, eval_client, eval_model, db)
            if scores:
                min_score = min(s["score"] for s in scores.values())
                pass_score = float(getattr(user, "resume_refine_pass_score", 0.80))
                eval_log = _json.loads(job.resume_eval_log or "[]")
                turn = len(eval_log) + 1
                eval_log.append({"turn": turn, "score": min_score,
                                 "issues": [i for s in scores.values() for i in s["issues"]],
                                 "passed": min_score >= pass_score, "source": "user_feedback"})
                job.resume_eval_score = min_score
                job.resume_eval_turns = turn
                job.resume_eval_log = _json.dumps(eval_log)
                db.commit(); db.refresh(job); _emit(job)
        except Exception as exc:
            db.rollback()
            print(f"[feedback:resume] {job_key}: post-feedback eval failed (non-fatal) — {exc}", flush=True)
        finally:
            llm_status.finish(job_key, "resume_eval")
    finally:
        db.close()

    run_ats_gate(job_key, profile_id)
```

Then dispatch in `run_user_feedback_refine`: immediately after its `if doc_type not in ("resume","cover")` guard and the `issues = build_feedback_issues(notes)` / `if not issues: return` lines, add:

```python
    if doc_type == "resume":
        _probe = SessionLocal()
        try:
            from db.database import Document
            from core.resume_document_io import is_tree_v1
            _r = Document.fetch(_probe, job_key, "resume", profile_id)
            _is_tree = _r is not None and is_tree_v1(_r.structured_json)
        finally:
            _probe.close()
        if _is_tree:
            _run_resume_feedback_refine(job_key, "resume", notes, profile_id)
            return
```

(The remainder of `run_user_feedback_refine` — the legacy/cover `refine_*_md` path — is unchanged.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/web/test_feedback_refine.py -q`
Expected: PASS.

- [ ] **Step 6: Run the adjacent backend suites for regressions**

Run: `python -m pytest tests/web/test_document_api.py tests/web/test_feedback_refine.py tests/core/test_job.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add web/intake_pipeline.py tests/web/test_feedback_refine.py
git commit -m "[feat] Tree-v1 résumé feedback-refine via selective per-section regen"
```

---

### Task 3: Pure document-tree value/anchor helpers (`docTreeOps.js`)

**Files:**
- Create: `react-dashboard/src/components/widgets/document/docTreeOps.js`
- Test: `react-dashboard/src/components/widgets/document/docTreeOps.test.js`

**Interfaces:**
- Produces: `setFieldValue(root, fieldId, value) -> newRoot`; `owningSection(root, nodeId) -> section|null`; `anchorLabel(root, nodeId) -> string`; `sectionLocked(root, nodeId) -> boolean`. Pure, immutable.

- [ ] **Step 1: Write the failing tests**

Create `react-dashboard/src/components/widgets/document/docTreeOps.test.js`:

```javascript
import { describe, it, expect } from 'vitest'
import { setFieldValue, owningSection, anchorLabel, sectionLocked } from './docTreeOps'

const root = {
  type: 'root', id: 'r', children: [
    { type: 'section', id: 's1', name: 'Summary', locked: false, children: [
      { type: 'field', id: 'f1', name: 'Summary', kind: 'markdown', value: 'old' }] },
    { type: 'section', id: 's2', name: 'Skills', locked: true, children: [
      { type: 'list', id: 'l2', name: 'Skills', children: [
        { type: 'group', id: 'g2', name: 'G', children: [
          { type: 'field', id: 'f2', name: 'Skill', kind: 'taglist', value: ['a'] }] }] }] },
  ],
}

describe('docTreeOps', () => {
  it('setFieldValue updates only the target field immutably', () => {
    const next = setFieldValue(root, 'f1', 'new')
    expect(next.children[0].children[0].value).toBe('new')
    expect(root.children[0].children[0].value).toBe('old') // original untouched
    expect(next.children[1]).toBe(root.children[1])        // untouched branch shared
  })

  it('owningSection finds the ancestor section for a deep field', () => {
    expect(owningSection(root, 'f2').id).toBe('s2')
    expect(owningSection(root, 's1').id).toBe('s1')
  })

  it('anchorLabel composes section and node names', () => {
    expect(anchorLabel(root, 'f1')).toBe('Summary › Summary')
    expect(anchorLabel(root, 's1')).toBe('Summary')
  })

  it('sectionLocked reflects the owning section lock', () => {
    expect(sectionLocked(root, 'f1')).toBe(false)
    expect(sectionLocked(root, 'f2')).toBe(true)
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd react-dashboard && npx vitest run src/components/widgets/document/docTreeOps.test.js`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `docTreeOps.js`**

Create `react-dashboard/src/components/widgets/document/docTreeOps.js`:

```javascript
// Pure, immutable helpers over a tree-v1 document RootNode. Values-only: no
// structural mutation. A "node" is any object with an `id`; children live on
// `.children` (sections/lists/groups) and fields are leaves with `.kind`/`.value`.

function mapChildren(node, fn) {
  if (!node.children) return node
  let changed = false
  const next = node.children.map((c) => {
    const r = fn(c)
    if (r !== c) changed = true
    return r
  })
  return changed ? { ...node, children: next } : node
}

export function setFieldValue(root, fieldId, value) {
  const visit = (node) => {
    if (node.id === fieldId && node.type === 'field') return { ...node, value }
    return mapChildren(node, visit)
  }
  return visit(root)
}

export function owningSection(root, nodeId) {
  for (const section of root.children || []) {
    if (section.id === nodeId) return section
    const stack = [...(section.children || [])]
    while (stack.length) {
      const n = stack.pop()
      if (n.id === nodeId) return section
      if (n.children) stack.push(...n.children)
    }
  }
  return null
}

function findNode(root, nodeId) {
  const stack = [root]
  while (stack.length) {
    const n = stack.pop()
    if (n.id === nodeId) return n
    if (n.children) stack.push(...n.children)
  }
  return null
}

export function anchorLabel(root, nodeId) {
  const section = owningSection(root, nodeId)
  const node = findNode(root, nodeId)
  if (!section) return node?.name || 'Document'
  if (node && node.id !== section.id && node.name) return `${section.name} › ${node.name}`
  return section.name
}

export function sectionLocked(root, nodeId) {
  return !!owningSection(root, nodeId)?.locked
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd react-dashboard && npx vitest run src/components/widgets/document/docTreeOps.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/widgets/document/docTreeOps.js react-dashboard/src/components/widgets/document/docTreeOps.test.js
git commit -m "[feat] Pure document-tree value/anchor helpers (docTreeOps)"
```

---

### Task 4: `DocumentTree.jsx` generic renderer/editor

**Files:**
- Create: `react-dashboard/src/components/widgets/document/DocumentTree.jsx`
- Test: `react-dashboard/src/components/widgets/document/DocumentTree.test.jsx`

**Interfaces:**
- Consumes: `FieldWidget` (`../profile-tree/fieldWidgets`); `setFieldValue`, `anchorLabel`, `sectionLocked` (`./docTreeOps`).
- Produces: `<DocumentTree doc={root} onSave={(newRoot)=>…} notes={{}} setNote={(id,note)=>…} />`. `onSave(newRoot)` is called after each field value change (modal persists via PUT). `setNote(nodeId, {section,label,note})` records feedback; a node with a feedback box appears only when not in a locked section.

- [ ] **Step 1: Write the failing tests**

Create `react-dashboard/src/components/widgets/document/DocumentTree.test.jsx`:

```javascript
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import DocumentTree from './DocumentTree'

const doc = {
  type: 'root', id: 'r', children: [
    { type: 'section', id: 's1', name: 'Summary', locked: false, children: [
      { type: 'field', id: 'f1', name: 'Summary', kind: 'text', value: 'Hello' }] },
    { type: 'section', id: 's2', name: 'Skills', locked: true, children: [
      { type: 'group', id: 'g2', name: 'G', children: [
        { type: 'field', id: 'f2', name: 'Skill', kind: 'text', value: 'Python' }] }] },
  ],
}

describe('DocumentTree', () => {
  it('renders section headings and field values', () => {
    render(<DocumentTree doc={doc} onSave={vi.fn()} notes={{}} setNote={vi.fn()} />)
    expect(screen.getByText('Summary')).toBeTruthy()
    expect(screen.getByText('Skills')).toBeTruthy()
    expect(screen.getByDisplayValue('Hello')).toBeTruthy()
  })

  it('editing a field calls onSave with the updated tree', () => {
    const onSave = vi.fn()
    render(<DocumentTree doc={doc} onSave={onSave} notes={{}} setNote={vi.fn()} />)
    fireEvent.change(screen.getByDisplayValue('Hello'), { target: { value: 'Hi' } })
    const arg = onSave.mock.calls.at(-1)[0]
    expect(arg.children[0].children[0].value).toBe('Hi')
  })

  it('a locked section exposes no feedback control', () => {
    render(<DocumentTree doc={doc} onSave={vi.fn()} notes={{}} setNote={vi.fn()} />)
    // Feedback buttons carry an accessible name starting with "Feedback on".
    expect(screen.queryByRole('button', { name: /Feedback on Skills/i })).toBeNull()
    expect(screen.getByRole('button', { name: /Feedback on Summary/i })).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd react-dashboard && npx vitest run src/components/widgets/document/DocumentTree.test.jsx`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `DocumentTree.jsx`**

Create `react-dashboard/src/components/widgets/document/DocumentTree.jsx`:

```javascript
import { useState } from 'react'
import { FieldWidget } from '../profile-tree/fieldWidgets'
import { setFieldValue, anchorLabel, sectionLocked } from './docTreeOps'

// Render a field leaf: label + value editor (reusing the profile-tree widgets) +,
// when the field's section is unlocked, a feedback toggle.
function FieldRow({ root, field, onSave, notes, setNote }) {
  const [open, setOpen] = useState(false)
  const locked = sectionLocked(root, field.id)
  const note = notes[field.id]?.note || ''
  return (
    <div className="mb-3">
      <div className="flex items-center justify-between gap-2">
        <label className="text-xs text-space-dim">{field.name}</label>
        {!locked && (
          <button
            type="button" aria-label={`Feedback on ${anchorLabel(root, field.id)}`}
            className="text-space-dim hover:text-purple-300 text-xs"
            onClick={() => setOpen((v) => !v)}
          >💬</button>
        )}
      </div>
      <FieldWidget field={field} onChange={(v) => onSave(setFieldValue(root, field.id, v))} />
      {open && !locked && (
        <textarea
          className="mt-1 w-full bg-white/5 border border-space-border rounded px-2 py-1 text-xs text-space-text"
          placeholder="What should change here?" value={note}
          onChange={(e) => setNote(field.id, {
            section: (function () { const s = sectionLocked; return null })() || undefined,
            label: anchorLabel(root, field.id),
            note: e.target.value,
          })}
        />
      )}
    </div>
  )
}

function fieldsOf(node) {
  // Yield the field leaves under a section child (field | group | list of groups).
  if (node.type === 'field') return [node]
  if (node.type === 'group') return node.children || []
  if (node.type === 'list') return (node.children || []).flatMap((g) => g.children || [])
  return []
}

function SectionBlock({ root, section, onSave, notes, setNote, sectionNote, setSectionNote }) {
  const locked = !!section.locked
  const [open, setOpen] = useState(false)
  return (
    <section className="mb-6">
      <div className="flex items-center justify-between gap-2 border-b border-space-border mb-2">
        <h3 className="text-sm font-semibold text-space-text">{section.name}</h3>
        {!locked && (
          <button
            type="button" aria-label={`Feedback on ${section.name}`}
            className="text-space-dim hover:text-purple-300 text-xs"
            onClick={() => setOpen((v) => !v)}
          >💬</button>
        )}
      </div>
      {open && !locked && (
        <textarea
          className="mb-2 w-full bg-white/5 border border-space-border rounded px-2 py-1 text-xs text-space-text"
          placeholder="What should change in this section?"
          value={sectionNote?.note || ''}
          onChange={(e) => setSectionNote(section.id, {
            section: section.name, label: section.name, note: e.target.value,
          })}
        />
      )}
      {(section.children || []).flatMap(fieldsOf).map((f) => (
        <FieldRow key={f.id} root={root} field={f} onSave={onSave} notes={notes} setNote={setNote} />
      ))}
    </section>
  )
}

export default function DocumentTree({ doc, onSave, notes, setNote }) {
  return (
    <div>
      {(doc.children || []).map((section) => (
        <SectionBlock
          key={section.id} root={doc} section={section}
          onSave={onSave} notes={notes}
          setNote={(fieldId, n) => setNote(fieldId, { ...n, section: section.name })}
          sectionNote={notes[section.id]}
          setSectionNote={setNote}
        />
      ))}
    </div>
  )
}
```

> Note for the implementer: in `FieldRow` the field-note's `section` is supplied by the parent `SectionBlock` wrapper (`setNote` is rewrapped to inject `section: section.name`), so do not try to compute it inside `FieldRow`. Replace the placeholder self-invoking expression with `undefined` — the wrapper overwrites it. Keep `label` as the field anchor.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd react-dashboard && npx vitest run src/components/widgets/document/DocumentTree.test.jsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/widgets/document/DocumentTree.jsx react-dashboard/src/components/widgets/document/DocumentTree.test.jsx
git commit -m "[feat] Generic tree-v1 document renderer/editor (DocumentTree)"
```

---

### Task 5: Rewire `DocumentModal` to the tree; retire legacy résumé components

**Files:**
- Modify: `react-dashboard/src/components/widgets/DocumentModal.jsx`
- Delete: `react-dashboard/src/components/widgets/document/InteractiveResume.jsx`, `ResumeSection.jsx`, `items.jsx`, `ItemPopover.jsx`, `ItemEditor.jsx` (legacy résumé surface, replaced by `DocumentTree`). Keep `CoverView.jsx` and `highlight.css` (cover still uses them).
- Test: `react-dashboard/src/components/widgets/DocumentModal.test.jsx` (create if absent)

> Deletion authorization: the approved 4D spec explicitly replaces these legacy résumé components. Before deleting, grep the repo to confirm no remaining importers other than the old `DocumentModal` (which this task rewires). If any other importer exists, stop and report.

**Interfaces:**
- Consumes: `DocumentTree` (`./document/DocumentTree`), `CoverView` (`./document/CoverView`), `getDocument`/`putDocument`/`submitFeedback` (`../../api`).
- Produces: a modal that branches on `doc.schema`: tree-v1 résumé → `DocumentTree`; cover → `CoverView`; legacy résumé (no `schema`) → guard panel. Node-anchored notes collected for feedback.

- [ ] **Step 1: Write the failing tests**

Create `react-dashboard/src/components/widgets/DocumentModal.test.jsx` (mock the api module):

```javascript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import DocumentModal from './DocumentModal'

vi.mock('../../api', () => ({
  getDocument: vi.fn(),
  putDocument: vi.fn(() => Promise.resolve({})),
  submitFeedback: vi.fn(() => Promise.resolve({})),
}))
import { getDocument } from '../../api'

const job = { job_key: 'jk', title: 'Dev' }

describe('DocumentModal schema branch', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders DocumentTree for a tree-v1 résumé', async () => {
    getDocument.mockResolvedValue({
      schema: 'tree-v1', type: 'root', id: 'r', children: [
        { type: 'section', id: 's1', name: 'Summary', locked: false, children: [
          { type: 'field', id: 'f1', name: 'Summary', kind: 'text', value: 'Hi' }] }],
    })
    render(<DocumentModal job={job} docType="resume" processing={false} onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('Summary')).toBeTruthy())
    expect(screen.getByDisplayValue('Hi')).toBeTruthy()
  })

  it('shows a guard for a legacy résumé row (no schema)', async () => {
    getDocument.mockResolvedValue({ profile_summary: 'old', experience: [], projects: [], skills: [] })
    render(<DocumentModal job={job} docType="resume" processing={false} onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/regenerate/i)).toBeTruthy())
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd react-dashboard && npx vitest run src/components/widgets/DocumentModal.test.jsx`
Expected: FAIL (still imports/renders `InteractiveResume`; no guard).

- [ ] **Step 3: Rewire `DocumentModal.jsx`**

Replace the legacy résumé import and the `SECTION_FIELD`/`handleSave` machinery. Specifically:

- Remove `import InteractiveResume from './document/InteractiveResume'` and the `SECTION_FIELD` const.
- Add `import DocumentTree from './document/DocumentTree'`.
- Replace `handleSave` with a tree saver:

```javascript
  const isTreeV1 = doc && doc.schema === 'tree-v1'
  const isLegacyResume = doc && docType === 'resume' && !isTreeV1

  const handleTreeSave = async (nextRoot) => {
    setDoc(nextRoot)                 // optimistic; keep edits visible
    try {
      await putDocument(job.job_key, 'resume', nextRoot)
      setLoadError(null)
    } catch (e) {
      setLoadError(e?.message || 'Failed to save changes')
    }
  }
```

- Replace the résumé render block:

```jsx
          {doc && docType === 'resume' && isTreeV1 && (
            <DocumentTree doc={doc} onSave={handleTreeSave} notes={notes} setNote={setNote} />
          )}
          {doc && isLegacyResume && (
            <p className="text-sm text-space-dim">
              This résumé was generated before the new editor. Regenerate it to edit inline.
            </p>
          )}
```

- The cover block (`docType === 'cover'` → `CoverView`) and the footer's `submitNotes`/`collected` logic are unchanged: `collected` already maps `notes` values to `{section,label,note}`; node-anchored notes now also carry those keys (plus a harmless `node_id` is not added — the modal keys notes by node id but the payload stays `{section,label,note}`). Disable the feedback footer when `isLegacyResume` (nothing to regenerate):

```jsx
            disabled={submitting || processing || !collected.length || isLegacyResume}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd react-dashboard && npx vitest run src/components/widgets/DocumentModal.test.jsx`
Expected: PASS.

- [ ] **Step 5: Confirm no other importers, then delete legacy components**

Run: `cd react-dashboard && grep -rl "InteractiveResume\|ResumeSection\|ItemPopover\|ItemEditor\|document/items" src | grep -v "node_modules"`
Expected: no matches outside the now-rewired `DocumentModal.jsx` history. If clean, delete the five legacy files:

```bash
git rm react-dashboard/src/components/widgets/document/InteractiveResume.jsx \
       react-dashboard/src/components/widgets/document/ResumeSection.jsx \
       react-dashboard/src/components/widgets/document/items.jsx \
       react-dashboard/src/components/widgets/document/ItemPopover.jsx \
       react-dashboard/src/components/widgets/document/ItemEditor.jsx
```

If any other importer exists, STOP and report instead of deleting.

- [ ] **Step 6: Run the full frontend suite + build**

Run: `cd react-dashboard && npx vitest run && npm run build`
Expected: all tests PASS; build succeeds (no dangling imports of the deleted files).

- [ ] **Step 7: Commit**

```bash
git add -A react-dashboard/src/components/widgets
git commit -m "[feat] Rewire DocumentModal to tree-v1 DocumentTree; retire legacy résumé editor"
```

---

## Self-Review

- **Spec coverage:** PUT tree-v1 branch (Task 1); `build_feedback_issues` section key + tree-v1 selective-regen feedback with empty-regenerable fallback to eval/ATS (Task 2); pure value/anchor helpers (Task 3); generic renderer reusing `FieldWidget`, values-only, locked-section feedback gating (Task 4); modal schema-branch + legacy guard + legacy component retirement (Task 5). Cover + legacy résumé refine paths untouched (Tasks 2 & 5). All spec sections covered.
- **Placeholder scan:** none — every code step shows full code. The one self-invoking expression in Task 4's draft is explicitly called out and resolved in the implementer note (set to `undefined`; the wrapper injects `section`).
- **Type consistency:** `setFieldValue`/`owningSection`/`anchorLabel`/`sectionLocked` signatures match between Tasks 3, 4. `FieldWidget({field,onChange})` matches `fieldWidgets.jsx`. `generate_resume_by_section(only_sections, critiques)` and `critiques[name]=[{description}]` match `core/section_generator.py`. `build_feedback_issues` output shape matches the spec. `_run_resume_feedback_refine` reuses real helper signatures verified in `web/intake_pipeline.py`/`core/job.py`.
- **Deletion guardrail:** Task 5 deletes legacy files only after a grep confirms no other importers and is authorized by the approved spec; the step says STOP-and-report otherwise.
