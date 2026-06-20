# Per-Section Résumé Generation (Phase 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Model 2 (per-section, schema-driven résumé generation) plus a dev-only side-by-side comparison harness against Model 1 (the current single-call path), and a minimal per-field role control in the tree editor.

**Architecture:** Frontend: surface the already-persisted field attrs (`llm_input`/`llm_output`/`llm_instructions`/`regen_lock`) as per-field role controls in the existing tree editor (pure-frontend; the whole-tree `PUT` already stores them). Backend: a new `core/section_generator.py` walks the tree and makes one focused LLM call per section that has unlocked outputable fields; a throwaway `core/tree_render.py` renders the result (incl. custom sections) to Markdown; a dev-only admin-gated endpoint runs both models dry and returns both Markdowns + eval scores; a dev page shows them side by side.

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy / Pydantic v2 / pytest (backend); React 18 / Vite / Vitest / RTL / react-markdown / react-router (frontend).

## Roadmap Context (read first — this plan starts a fresh session)

This is **sub-project #3** of the "user-defined resume sections" initiative (replace the hardcoded 5-section résumé model with a user-definable schema tree). Full roadmap + cold-start facts live in the auto-memory `project-profile-schema-engine` (load it first) and `core/CONTEXT.md` → "Profile Schema Engine". The recursive tree (`root → section → list/group → field`) in `core/profile_tree.py` is the profile source of truth. Sub-projects #1, #2A/2B/2C are DONE and merged to local `main`.

**Spec:** `docs/superpowers/specs/2026-06-20-section-generation-design.md` (read it).

**This plan delivers:** a dev-only comparison harness — Model 2 (per-section) vs Model 1 (single-call) — NOT a production switch. After it lands, the user eyeballs outputs and picks a winner; productionizing folds into a later sub-project. Custom sections still do NOT render on real generated documents (that is #4); `tree_render.py` here is a throwaway for the harness only.

**Before starting:** create a feature branch off `main` (`git checkout -b feat/section-generation`). On completion, use `superpowers:finishing-a-development-branch` → merge to local `main` (NO push).

**After this lands (before context-clearing for #4):** update the `project-profile-schema-engine` auto-memory: mark #3 DONE (with commit range), set CURRENT STATE to "#3 done, comparison harness live; NEXT: user picks Model1/Model2 winner, then brainstorm→spec→plan→impl #4 (schema-driven rendering)".

### Cold-start facts (a fresh session needs these; verify before relying on them)

- **Where you are in git:** sub-projects #1, #2A/2B/2C are merged to **local `main`** (latest 2C work + follow-ups: entry-collapse, drag activation distance, dev-OAuth proxy fix). `main` is **ahead of `origin/main` and intentionally NOT pushed** — do not push. Start this work on a new branch `feat/section-generation` off `main`.
- **Read first:** root `CLAUDE.md` (routing table + SaaS/multi-tenancy context), `core/CONTEXT.md` (→ "Profile Schema Engine" and "Structured Résumé / Cover Generation"), `web/CONTEXT.md` (route surface + Auth), and `react-dashboard/CONTEXT.md` (per-file routing, profile-tree rows). Read a target dir's `CONTEXT.md` before editing it.
- **The tree is already hydrated on `User`:** `User.load(db, profile_id)` sets `self.profile_tree` as a validated `RootNode` (legacy profiles migrated on load). So `User.profile_tree_root()` in Task 3 just returns `self.profile_tree`; the section generator walks that, NOT the legacy-flattened attrs.
- **Field attrs already persist with no backend change:** `FieldNode` carries `llm_input`/`llm_output`/`llm_instructions`/`regen_lock` (`core/profile_tree.py`); the whole-tree `PUT /api/config/profiles/{id}/tree` validates and stores them, and the frontend `makeField` already seeds their defaults. Tasks 1–2 only surface controls that mutate them.
- **LLM stubbing in tests:** `core.job` exposes module-level `call_llm`; `_llm_json_with_retry` calls it. Tests `monkeypatch.setattr(jobmod, "call_llm", stub)` (see `tests/core/test_llm_json_retry.py`). The section generator reuses `core.job._llm_json_with_retry`, so its tests monkeypatch `core.job.call_llm` — that is why the Task 3 tests patch `jobmod`.
- **Prompt keys:** résumé prompt = `user.resolve_prompt("resume")`, eval prompt = `user.resolve_prompt("resume_eval")`. Client/model = `get_client_for_profile(user, user.prompt_resume_model)`.
- **Admin gate:** `require_admin` lives in `web/routers/credits.py` (raises 403 if the active account isn't admin). The dev endpoint depends on it. The Admin React page (`AdminPage.jsx`) gates on `me.is_admin` and uses a `FUNCTIONS` switcher — add the compare view as a new function entry, not a new route.
- **Docs are git-ignored but tracked by force:** `docs/superpowers/*` is in `.gitignore`; specs/plans are committed with `git add -f` (this plan and the 2C spec/plan were added that way). The plan/spec files for #3 are already committed (`0b9c72a` spec, `102d328` plan).
- **Frontend deps already present:** `react-markdown` and `react-router-dom` are in `react-dashboard/package.json` — no install needed for the compare page.

### Manual verification after merge (jsdom/pytest can't cover this)

The automated tests stub the LLM, so Model 2 is never exercised end-to-end against a real model. After merge, to actually compare outputs: (1) on a test profile, open the tree editor and set some fields to **LLM-written** (and optionally add a custom section from the 2C gallery with an outputable field); save. (2) As an **admin** account, open Admin → **Résumé Compare**, enter a real `job_key` that has an extracted description, and Compare. (3) Eyeball the two columns + eval scores. This is the whole point of the sub-project — the user decides Model 1 vs Model 2 from real output. Note it costs real LLM tokens (unmetered) and needs an admin account + a job with a description.

## Global Constraints

- **RELEASE CONSTRAINT:** do NOT push `main` until the ENTIRE initiative (through #5) is complete. Each sub-project merges to LOCAL `main` only.
- The profile **tree** is the source of truth. The editor persists only via `PUT /api/config/profiles/{id}/tree`. No backend/API changes to the tree endpoints in this plan; the field attrs already round-trip and persist.
- **Field-role taxonomy** (drives Model 2): **LLM-outputable** = `llm_output=True` (regenerated from `llm_instructions` + section context; rendered; `regen_lock=True` keeps current value this run). **Immutable** = `llm_output=False, llm_input=False` (rendered verbatim; fed to the LLM as section context). **Context-only** = `llm_input=True, llm_output=False` (fed to the LLM; NOT rendered).
- Field `value` types by `kind`: `text`/`markdown` → string; `bullets`/`taglist` → list of strings.
- Model 2 makes **no** LLM call for a section with zero unlocked outputable fields.
- The harness must NOT persist: Model 1 runs dry (no `Document.upsert`, no `.md` write). The harness is NOT metered and does NOT run the ATS gate.
- Scope: résumé only. Out of scope: metering, ATS, PDF, the real phase-4 renderer, cover letters, productionizing Model 2.
- Python: type hints, `black`, Google-style docstrings. JS: existing dashboard conventions (ES modules, function components, hooks, Tailwind, the shared look). Commit format `[type] Imperative subject`; types `feat|fix|refactor|docs|test|chore`. No Claude/Anthropic attribution, no `Co-Authored-By`.
- Python tests: `pytest` from repo root. Frontend tests: `npm run test` from `react-dashboard/`. Each task: failing test → run (fail) → implement → run (green) → commit.

## File Structure

- **Create** `react-dashboard/src/components/widgets/profile-tree/` role helpers in existing `treeOps.js` (+ `treeOps.test.js`) — `fieldRole`, `setFieldRole`, `setLlmInstructions`, `toggleRegenLock`.
- **Modify** `.../profile-tree/TreeNode.jsx` (+ `TreeNode.test.jsx`) — `FieldView` role control.
- **Modify** `.../profile-tree/ProfileTreeEditor.jsx` — add `setRole`/`setInstructions`/`toggleLock` to the `ops` bundle.
- **Create** `core/section_generator.py` (+ `tests/core/test_section_generator.py`) — Model 2 engine + `SectionOutput` contract.
- **Create** `core/tree_render.py` (+ `tests/core/test_tree_render.py`) — throwaway tree→Markdown renderer.
- **Modify** `core/user.py` — `User.profile_tree_root()` accessor (folded into Task 3).
- **Modify** `core/job.py` (+ `tests/core/test_job_eval_body.py`) — extract `_evaluate_body`; add `evaluate_resume_body`.
- **Create** `web/routers/dev.py` (+ `tests/web/test_resume_compare.py`) — `POST /api/dev/resume-compare/{job_key}`; register in `web/main.py`.
- **Create** `react-dashboard/src/components/admin/ResumeCompare.jsx` (+ `.test.jsx`); **Modify** `react-dashboard/src/components/AdminPage.jsx`, `react-dashboard/src/api.js`.
- **Modify** `core/CONTEXT.md`, `react-dashboard/CONTEXT.md`, `web/CONTEXT.md` — document phase 3.

---

### Task 1: Field-role tree helpers (pure, frontend)

**Files:**
- Modify: `react-dashboard/src/components/widgets/profile-tree/treeOps.js`
- Modify: `react-dashboard/src/components/widgets/profile-tree/treeOps.test.js`

**Interfaces:**
- Consumes: existing `updateNode`.
- Produces:
  - `fieldRole(field) -> 'output' | 'context' | 'immutable'` — derive the role from a field's flags.
  - `setFieldRole(tree, fieldId, role) -> tree` — set `llm_input`/`llm_output` per the taxonomy (`output`→`{llm_output:true, llm_input:false}`; `context`→`{llm_output:false, llm_input:true}`; `immutable`→`{llm_output:false, llm_input:false}`).
  - `setLlmInstructions(tree, fieldId, text) -> tree` — set `llm_instructions`.
  - `toggleRegenLock(tree, fieldId) -> tree` — flip `regen_lock`.

- [ ] **Step 1: Write the failing tests**

Update the import line at the top of `treeOps.test.js` to include the new names:

```js
import {
  PRESET_ROLES, isPresetSection, renumber, updateNode, removeNode,
  moveNode, makeField, addField, addListItem, addCustomSection,
  cloneWithFreshIds, addSection, reorderSiblings,
  fieldRole, setFieldRole, setLlmInstructions, toggleRegenLock,
} from './treeOps'
```

Append these describes at the end of `treeOps.test.js`:

```js
describe('field role helpers', () => {
  function tree() {
    return { type: 'root', id: 'r', children: [
      { type: 'section', id: 's', name: 'S', role: null, order: 0, visible: true, children: [
        { type: 'group', id: 'g', name: 'G', order: 0, visible: true, regen_lock: false, children: [
          { type: 'field', id: 'f', name: 'F', key: 'f', order: 0, visible: true,
            kind: 'markdown', value: '', llm_output: false, llm_instructions: '',
            llm_input: false, regen_lock: false, min: null, max: null },
        ] },
      ] },
    ] }
  }

  it('derives role from flags', () => {
    expect(fieldRole({ llm_output: true, llm_input: false })).toBe('output')
    expect(fieldRole({ llm_output: false, llm_input: true })).toBe('context')
    expect(fieldRole({ llm_output: false, llm_input: false })).toBe('immutable')
  })

  it('setFieldRole sets the flag pair and is immutable', () => {
    const t = tree()
    const out = setFieldRole(t, 'f', 'output')
    expect(out).not.toBe(t)
    const f = out.children[0].children[0].children[0]
    expect(f.llm_output).toBe(true)
    expect(f.llm_input).toBe(false)
    const ctx = setFieldRole(t, 'f', 'context').children[0].children[0].children[0]
    expect(ctx.llm_output).toBe(false)
    expect(ctx.llm_input).toBe(true)
    const imm = setFieldRole(t, 'f', 'immutable').children[0].children[0].children[0]
    expect(imm.llm_output).toBe(false)
    expect(imm.llm_input).toBe(false)
  })

  it('setLlmInstructions writes the text', () => {
    const f = setLlmInstructions(tree(), 'f', 'Rewrite punchier')
      .children[0].children[0].children[0]
    expect(f.llm_instructions).toBe('Rewrite punchier')
  })

  it('toggleRegenLock flips the lock', () => {
    const f = toggleRegenLock(tree(), 'f').children[0].children[0].children[0]
    expect(f.regen_lock).toBe(true)
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd react-dashboard && npm run test -- treeOps`
Expected: FAIL — `fieldRole`/`setFieldRole`/`setLlmInstructions`/`toggleRegenLock` not exported.

- [ ] **Step 3: Write the implementation**

Append to `react-dashboard/src/components/widgets/profile-tree/treeOps.js`:

```js
// Derive a field's role from its LLM flags. See the field-role taxonomy.
export const fieldRole = (field) =>
  field.llm_output ? 'output' : field.llm_input ? 'context' : 'immutable'

// Set llm_input/llm_output for `fieldId` per the role taxonomy.
export function setFieldRole(tree, fieldId, role) {
  const flags = {
    output: { llm_output: true, llm_input: false },
    context: { llm_output: false, llm_input: true },
    immutable: { llm_output: false, llm_input: false },
  }[role]
  return updateNode(tree, fieldId, (f) => ({ ...f, ...flags }))
}

// Set the per-field regeneration prompt.
export function setLlmInstructions(tree, fieldId, text) {
  return updateNode(tree, fieldId, (f) => ({ ...f, llm_instructions: text }))
}

// Flip the "pin current value" lock.
export function toggleRegenLock(tree, fieldId) {
  return updateNode(tree, fieldId, (f) => ({ ...f, regen_lock: !f.regen_lock }))
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd react-dashboard && npm run test -- treeOps`
Expected: PASS (all existing + new describes).

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/widgets/profile-tree/treeOps.js react-dashboard/src/components/widgets/profile-tree/treeOps.test.js
git commit -m "[feat] Add field-role tree helpers (role/instructions/regen-lock)"
```

---

### Task 2: Field-role control in the editor

**Files:**
- Modify: `react-dashboard/src/components/widgets/profile-tree/ProfileTreeEditor.jsx`
- Modify: `react-dashboard/src/components/widgets/profile-tree/TreeNode.jsx`
- Modify: `react-dashboard/src/components/widgets/profile-tree/TreeNode.test.jsx`

**Interfaces:**
- Consumes: `setFieldRole`, `setLlmInstructions`, `toggleRegenLock`, `fieldRole` (Task 1).
- Produces: `FieldView` renders a role `<select>` (writing `ops.setRole`), a regen-lock checkbox (`ops.toggleLock`), and an `llm_instructions` `<textarea>` (shown only when role is `output`, writing `ops.setInstructions`). New `ops` entries: `setRole(id, role)`, `setInstructions(id, text)`, `toggleLock(id)`.

- [ ] **Step 1: Write the failing test**

In `react-dashboard/src/components/widgets/profile-tree/TreeNode.test.jsx`, add this test to the `describe('SectionView custom', …)` block (the `customSection` fixture there has one field `fa`):

```jsx
  it('shows a field role selector and reveals instructions for outputable', () => {
    const ops = noopOps({ setRole: vi.fn(), setInstructions: vi.fn(), toggleLock: vi.fn() })
    render(<SectionView section={customSection} isFirst isLast={false} ops={ops} />)
    fireEvent.click(screen.getByLabelText('Expand section'))
    // immutable by default → no instructions box
    expect(screen.queryByLabelText('LLM instructions')).toBeNull()
    const select = screen.getByLabelText('Field role')
    fireEvent.change(select, { target: { value: 'output' } })
    expect(ops.setRole).toHaveBeenCalledWith('fa', 'output')
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd react-dashboard && npm run test -- TreeNode`
Expected: FAIL — no `Field role` control rendered.

- [ ] **Step 3: Add the ops to `ProfileTreeEditor.jsx`**

In `react-dashboard/src/components/widgets/profile-tree/ProfileTreeEditor.jsx`:

(a) Add `setFieldRole, setLlmInstructions, toggleRegenLock` to the existing `treeOps` import.

(b) Add three entries to the `ops` bundle (next to the existing `setValue`/`rename` callbacks), matching the existing `useCallback` pattern:

```jsx
    setRole: useCallback((id, role) => setTree((t) => setFieldRole(t, id, role)), []),
    setInstructions: useCallback((id, text) => setTree((t) => setLlmInstructions(t, id, text)), []),
    toggleLock: useCallback((id) => setTree((t) => toggleRegenLock(t, id)), []),
```

- [ ] **Step 4: Render the control in `FieldView` (`TreeNode.jsx`)**

In `react-dashboard/src/components/widgets/profile-tree/TreeNode.jsx`, add `fieldRole` to the existing `treeOps` import:

```jsx
import { isPresetSection, fieldRole } from './treeOps'
```

Replace the existing `FieldView` function with this version (adds the role row beneath the widget):

```jsx
// A single field: label (renamable only on custom groups) + visible + widget,
// then a role row (context/immutable/LLM-outputable + regen-lock + instructions).
function FieldView({ field, fieldsEditable, ops }) {
  const role = fieldRole(field)
  return (
    <div className={rowWrap}>
      <div className={headerRow}>
        <RenameLabel
          name={field.name} editable={fieldsEditable}
          onRename={(n) => ops.rename(field.id, n)}
        />
        <VisibleToggle visible={field.visible} onToggle={() => ops.toggleVisible(field.id)} />
      </div>
      <div className={field.visible ? '' : 'opacity-50'}>
        <FieldWidget field={field} onChange={(v) => ops.setValue(field.id, v)} />
      </div>
      <div className="flex items-center gap-3 flex-wrap text-xs text-space-dim">
        <label className="inline-flex items-center gap-1">
          <span>Role</span>
          <select
            aria-label="Field role" value={role}
            className="bg-white text-black border border-space-border rounded px-1 py-0.5"
            onChange={(e) => ops.setRole(field.id, e.target.value)}
          >
            <option className="bg-white text-black" value="immutable">Verbatim</option>
            <option className="bg-white text-black" value="context">Context only</option>
            <option className="bg-white text-black" value="output">LLM-written</option>
          </select>
        </label>
        <label className="inline-flex items-center gap-1">
          <input
            type="checkbox" checked={!!field.regen_lock}
            onChange={() => ops.toggleLock(field.id)}
          />
          <span>Lock</span>
        </label>
      </div>
      {role === 'output' && (
        <textarea
          aria-label="LLM instructions" rows={2}
          placeholder="How should the LLM write this field?"
          value={field.llm_instructions || ''}
          className="bg-white/5 border border-space-border rounded px-2 py-1 text-sm text-space-text"
          onChange={(e) => ops.setInstructions(field.id, e.target.value)}
        />
      )}
    </div>
  )
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd react-dashboard && npm run test -- TreeNode ProfileTreeEditor`
Expected: PASS — new role test passes; existing TreeNode/ProfileTreeEditor tests still pass.

- [ ] **Step 6: Commit**

```bash
git add react-dashboard/src/components/widgets/profile-tree/ProfileTreeEditor.jsx react-dashboard/src/components/widgets/profile-tree/TreeNode.jsx react-dashboard/src/components/widgets/profile-tree/TreeNode.test.jsx
git commit -m "[feat] Add per-field role control (verbatim/context/LLM-written) to tree editor"
```

---

### Task 3: Model 2 engine — `core/section_generator.py`

**Files:**
- Create: `core/section_generator.py`
- Modify: `core/user.py`
- Create: `tests/core/test_section_generator.py`

**Interfaces:**
- Consumes: `RootNode`/`SectionNode`/`ListNode`/`GroupNode`/`FieldNode` from `core.profile_tree`; `_llm_json_with_retry` and module-level `call_llm` from `core.job`.
- Produces:
  - `User.profile_tree_root() -> RootNode` (in `core/user.py`) — returns the already-hydrated `self.profile_tree`.
  - `SectionOutput(BaseModel)` — `fields: dict[str, str | list[str]] = {}`, `entries: dict[str, dict[str, str | list[str]]] = {}`.
  - `generate_resume_by_section(root, job_ctx, client, model) -> dict[str, str | list[str]]` — map of `field_node_id -> authored value` for every unlocked outputable field across visible sections.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_section_generator.py`:

```python
from __future__ import annotations

import core.job as jobmod
from core.profile_tree import (
    FieldNode, GroupNode, ListNode, RootNode, SectionNode,
)
from core.section_generator import generate_resume_by_section


def _field(key, *, output=False, ctx=False, lock=False, value="", kind="markdown"):
    return FieldNode(
        name=key.title(), key=key, kind=kind, value=value,
        llm_output=output, llm_input=ctx, regen_lock=lock,
        llm_instructions=("write " + key) if output else "",
    )


def _scalar_section():
    # Custom section with a group: one outputable field + one immutable anchor.
    return SectionNode(name="Leadership", role=None, children=[
        GroupNode(name="Leadership", children=[
            _field("org", value="Acme"),                         # immutable
            _field("blurb", output=True, value="old blurb"),     # outputable
        ])
    ])


def _list_section():
    tmpl = GroupNode(name="E", children=[_field("company"), _field("summary", output=True)])
    return SectionNode(name="Experience", role="experience", children=[
        ListNode(name="Experience", item_template=tmpl, children=[
            GroupNode(name="E", id="e0", children=[
                _field("company", value="Acme"), _field("summary", output=True, value="old0")]),
            GroupNode(name="E", id="e1", children=[
                _field("company", value="Beta"), _field("summary", output=True, value="old1")]),
        ])
    ])


def _stub(map_by_call):
    """call_llm stub: returns successive JSON strings, recording prompts."""
    state = {"i": 0, "prompts": []}

    def stub(prompt, client, model, max_tokens=8192):
        state["prompts"].append(prompt)
        r = map_by_call[min(state["i"], len(map_by_call) - 1)]
        state["i"] += 1
        return r

    return stub, state


def test_scalar_section_authors_outputable_only(monkeypatch):
    root = RootNode(children=[_scalar_section()])
    blurb_id = root.children[0].children[0].children[1].id
    stub, state = _stub(['{"fields": {"blurb": "new blurb"}}'])
    monkeypatch.setattr(jobmod, "call_llm", stub)
    out = generate_resume_by_section(root, "JOB", client=None, model="m")
    assert out == {blurb_id: "new blurb"}
    # immutable anchor value was provided as context to the LLM
    assert "Acme" in state["prompts"][0]


def test_list_section_keys_by_entry(monkeypatch):
    root = RootNode(children=[_list_section()])
    s0 = root.children[0].children[0].children[0].children[1].id  # e0.summary
    s1 = root.children[0].children[0].children[1].children[1].id  # e1.summary
    stub, _ = _stub(['{"entries": {"e0": {"summary": "n0"}, "e1": {"summary": "n1"}}}'])
    monkeypatch.setattr(jobmod, "call_llm", stub)
    out = generate_resume_by_section(root, "JOB", client=None, model="m")
    assert out == {s0: "n0", s1: "n1"}


def test_regen_lock_excludes_field_and_skips_call_when_all_locked(monkeypatch):
    sec = SectionNode(name="X", role=None, children=[
        GroupNode(name="X", children=[_field("b", output=True, lock=True, value="keep")])])
    root = RootNode(children=[sec])
    stub, state = _stub(['{"fields": {}}'])
    monkeypatch.setattr(jobmod, "call_llm", stub)
    out = generate_resume_by_section(root, "JOB", client=None, model="m")
    assert out == {}
    assert state["i"] == 0  # no outputable-unlocked fields → no LLM call


def test_section_failure_falls_back_and_continues(monkeypatch):
    root = RootNode(children=[_scalar_section(), _list_section()])
    s0 = root.children[1].children[0].children[0].children[1].id
    s1 = root.children[1].children[0].children[1].children[1].id
    # First section returns garbage (unparseable both times), second succeeds.
    stub, _ = _stub(['not json', 'still not json',
                     '{"entries": {"e0": {"summary": "n0"}, "e1": {"summary": "n1"}}}'])
    monkeypatch.setattr(jobmod, "call_llm", stub)
    out = generate_resume_by_section(root, "JOB", client=None, model="m")
    # Failed scalar section contributes nothing; list section still authored.
    assert out == {s0: "n0", s1: "n1"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_section_generator.py -q`
Expected: FAIL — `core.section_generator` does not exist.

- [ ] **Step 3: Add `User.profile_tree_root`**

In `core/user.py`, add this method to the `User` class (near `render_for_prompt`):

```python
    def profile_tree_root(self) -> "RootNode":
        """Return the hydrated profile tree (source of truth for schema-driven generation)."""
        return self.profile_tree
```

(`RootNode` is already imported at the top of `core/user.py`.)

- [ ] **Step 4: Write `core/section_generator.py`**

Create `core/section_generator.py`:

```python
"""Model 2: per-section, schema-driven résumé generation.

Walks the profile tree and makes one focused LLM call per section that has
unlocked LLM-outputable fields, returning authored values keyed by field node
id. Pure of DB; reuses core.job's hardened JSON call. See
docs/superpowers/specs/2026-06-20-section-generation-design.md.
"""

from __future__ import annotations

from typing import Any, Union

from pydantic import BaseModel, Field

from core.profile_tree import FieldNode, GroupNode, ListNode, RootNode, SectionNode

Value = Union[str, list[str]]


class SectionOutput(BaseModel):
    """One section's LLM output. Scalar sections fill ``fields``; list sections
    fill ``entries`` (keyed by entry node id, then field key)."""

    fields: dict[str, Value] = Field(default_factory=dict)
    entries: dict[str, dict[str, Value]] = Field(default_factory=dict)


def _outputable(field: FieldNode) -> bool:
    """A field the LLM should (re)write this run: outputable and not pinned."""
    return field.llm_output and not field.regen_lock


def _render_field_context(field: FieldNode) -> str:
    """One context line for an immutable/context-only field."""
    val = field.value if isinstance(field.value, str) else ", ".join(field.value)
    return f"- {field.name} ({field.key}): {val}"


def _group_context(group: GroupNode) -> list[str]:
    """Context lines for a group's non-outputable, visible fields."""
    return [
        _render_field_context(f)
        for f in group.children
        if f.visible and not f.llm_output
    ]


def _outputable_specs(group: GroupNode) -> list[str]:
    """Instruction lines for a group's unlocked outputable fields."""
    return [
        f'- "{f.key}": {f.llm_instructions or ("Write the " + f.name)}'
        for f in group.children
        if _outputable(f)
    ]


def _build_scalar_prompt(section: SectionNode, group: GroupNode, job_ctx: str) -> str:
    """Prompt for a section whose child is a single group (or bare field wrapped)."""
    ctx = "\n".join(_group_context(group)) or "(none)"
    specs = "\n".join(_outputable_specs(group))
    return (
        f"You are tailoring the résumé section '{section.name}' to a job.\n\n"
        f"JOB:\n{job_ctx}\n\n"
        f"EXISTING SECTION DATA (anchors — do not change these):\n{ctx}\n\n"
        f"Write tailored content for these fields:\n{specs}\n\n"
        'Return JSON: {"fields": {"<field_key>": "<value>"}} containing exactly '
        "the field keys above."
    )


def _build_list_prompt(section: SectionNode, lst: ListNode, job_ctx: str) -> str:
    """Prompt for a repeating-list section (one call authors every entry)."""
    blocks = []
    for entry in lst.children:
        ctx = "\n".join(_group_context(entry)) or "(none)"
        specs = "\n".join(_outputable_specs(entry))
        blocks.append(f'ENTRY id="{entry.id}":\nanchors:\n{ctx}\nwrite:\n{specs}')
    body = "\n\n".join(blocks)
    return (
        f"You are tailoring the résumé section '{section.name}' to a job. Each "
        f"entry is a separate item; write its fields using its own anchors.\n\n"
        f"JOB:\n{job_ctx}\n\n{body}\n\n"
        'Return JSON: {"entries": {"<entry_id>": {"<field_key>": "<value>"}}} '
        "with an object for every entry id above."
    )


def _section_child(section: SectionNode):
    """A section has exactly one child (validated)."""
    return section.children[0] if section.children else None


def generate_resume_by_section(
    root: RootNode, job_ctx: str, client: Any, model: str
) -> dict[str, Value]:
    """Author every unlocked outputable field across visible sections.

    Makes one LLM call per section that has unlocked outputable fields. A section
    whose call fails to parse contributes nothing (its fields fall back to stored
    values downstream) and generation continues with the next section.

    Args:
        root: The profile tree.
        job_ctx: Job context markdown (extracted description).
        client: OpenAI-compatible client.
        model: Model identifier.

    Returns:
        ``field_node_id -> authored value`` for every authored field.
    """
    from core.job import _llm_json_with_retry  # local import avoids a cycle

    out: dict[str, Value] = {}
    for section in root.children:
        if not section.visible:
            continue
        child = _section_child(section)
        if isinstance(child, ListNode):
            entries_with_work = [e for e in child.children if any(_outputable(f) for f in e.children)]
            if not entries_with_work:
                continue
            prompt = _build_list_prompt(section, child, job_ctx)
        elif isinstance(child, GroupNode):
            if not any(_outputable(f) for f in child.children):
                continue
            prompt = _build_scalar_prompt(section, child, job_ctx)
        elif isinstance(child, FieldNode):
            if not _outputable(child):
                continue
            # Wrap the bare field as a one-field group for uniform handling.
            prompt = _build_scalar_prompt(section, GroupNode(name=section.name, children=[child]), job_ctx)
        else:
            continue

        try:
            result = _llm_json_with_retry(
                prompt, client, model, SectionOutput, max_tokens=8192,
                empty_msg=f"Section '{section.name}' generation returned empty content.",
            )
        except Exception:
            continue  # failed section falls back to stored values

        if isinstance(child, ListNode):
            by_id = {e.id: e for e in child.children}
            for entry_id, kv in result.entries.items():
                entry = by_id.get(entry_id)
                if entry is None:
                    continue
                for f in entry.children:
                    if _outputable(f) and f.key in kv:
                        out[f.id] = kv[f.key]
        else:
            group = child if isinstance(child, GroupNode) else None
            fields = group.children if group else [child]
            for f in fields:
                if _outputable(f) and f.key in result.fields:
                    out[f.id] = result.fields[f.key]
    return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/core/test_section_generator.py -q`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add core/section_generator.py core/user.py tests/core/test_section_generator.py
git commit -m "[feat] Add per-section résumé generator (Model 2 engine)"
```

---

### Task 4: Throwaway tree→Markdown renderer — `core/tree_render.py`

**Files:**
- Create: `core/tree_render.py`
- Create: `tests/core/test_tree_render.py`

**Interfaces:**
- Consumes: `RootNode`/`SectionNode`/`ListNode`/`GroupNode`/`FieldNode`.
- Produces: `render_tree_markdown(root, authored) -> str` — overlay `authored` (`field_id -> value`) onto outputable fields (stored value when absent), render visible sections incl. custom; omit context-only fields; skip hidden nodes.

- [ ] **Step 1: Write the failing test**

Create `tests/core/test_tree_render.py`:

```python
from __future__ import annotations

from core.profile_tree import (
    FieldNode, GroupNode, ListNode, RootNode, SectionNode,
)
from core.tree_render import render_tree_markdown


def _f(key, value, *, output=False, ctx=False, kind="markdown", visible=True):
    return FieldNode(name=key.title(), key=key, kind=kind, value=value, visible=visible,
                     llm_output=output, llm_input=ctx)


def test_renders_sections_overlays_authored_and_omits_context_only():
    blurb = _f("blurb", "stored", output=True)
    root = RootNode(children=[
        SectionNode(name="Leadership", role=None, children=[
            GroupNode(name="Leadership", children=[
                _f("org", "Acme"),                       # immutable → rendered
                blurb,                                    # outputable → overlaid
                _f("note", "secret", ctx=True),           # context-only → omitted
            ])
        ]),
        SectionNode(name="Skills", role="skills", children=[
            _f("skills", ["Python", "SQL"], kind="taglist")
        ]),
    ])
    md = render_tree_markdown(root, {blurb.id: "authored blurb"})
    assert "## Leadership" in md
    assert "authored blurb" in md       # overlay applied
    assert "stored" not in md           # stored outputable value replaced
    assert "Acme" in md                 # immutable rendered
    assert "secret" not in md           # context-only omitted
    assert "## Skills" in md
    assert "Python" in md and "SQL" in md


def test_locked_outputable_uses_stored_value_when_absent_from_authored():
    f = _f("b", "kept", output=True)
    root = RootNode(children=[SectionNode(name="X", role=None, children=[
        GroupNode(name="X", children=[f])])])
    md = render_tree_markdown(root, {})  # nothing authored
    assert "kept" in md


def test_hidden_section_skipped():
    root = RootNode(children=[SectionNode(name="Hidden", role=None, visible=False, children=[
        GroupNode(name="Hidden", children=[_f("a", "x")])])])
    assert "Hidden" not in render_tree_markdown(root, {})


def test_list_entries_render():
    root = RootNode(children=[SectionNode(name="Experience", role="experience", children=[
        ListNode(name="Experience", item_template=GroupNode(name="E", children=[_f("company", "")]),
                 children=[
                     GroupNode(name="E", children=[_f("company", "Acme"), _f("summary", "did things")]),
                     GroupNode(name="E", children=[_f("company", "Beta"), _f("summary", "more things")]),
                 ])])])
    md = render_tree_markdown(root, {})
    assert "Acme" in md and "Beta" in md and "did things" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_tree_render.py -q`
Expected: FAIL — `core.tree_render` does not exist.

- [ ] **Step 3: Write the implementation**

Create `core/tree_render.py`:

```python
"""THROWAWAY renderer: profile tree -> readable Markdown for the Model 1 vs
Model 2 comparison harness only.

This is NOT the production schema-driven renderer (that is sub-project #4). It
exists only to make Model 2 output legible for side-by-side comparison; its
format is intentionally simple and may differ from the canonical assembler.
"""

from __future__ import annotations

from core.profile_tree import (
    FieldNode, GroupNode, ListNode, RootNode, SectionNode,
)

Authored = dict[str, "str | list[str]"]


def _is_context_only(f: FieldNode) -> bool:
    return f.llm_input and not f.llm_output


def _value(f: FieldNode, authored: Authored):
    """Authored value if present (outputable), else the stored value."""
    return authored.get(f.id, f.value)


def _render_field(f: FieldNode, authored: Authored) -> list[str]:
    if not f.visible or _is_context_only(f):
        return []
    val = _value(f, authored)
    if isinstance(val, list):
        if not val:
            return []
        return [f"- {item}" for item in val]
    if not str(val).strip():
        return []
    if f.kind == "markdown":
        return [str(val)]
    return [f"**{f.name}:** {val}"]


def _render_group(g: GroupNode, authored: Authored) -> list[str]:
    lines: list[str] = []
    for f in g.children:
        lines += _render_field(f, authored)
    return lines


def render_tree_markdown(root: RootNode, authored: Authored) -> str:
    """Render the tree to Markdown, overlaying ``authored`` onto outputable fields.

    Args:
        root: The profile tree.
        authored: ``field_node_id -> value`` from the section generator.

    Returns:
        Markdown string (no YAML front matter).
    """
    out: list[str] = []
    for section in root.children:
        if not section.visible:
            continue
        child = section.children[0] if section.children else None
        body: list[str] = []
        if isinstance(child, ListNode):
            for entry in child.children:
                if not entry.visible:
                    continue
                body += _render_group(entry, authored)
                body.append("")
        elif isinstance(child, GroupNode):
            body += _render_group(child, authored)
        elif isinstance(child, FieldNode):
            body += _render_field(child, authored)
        if not [ln for ln in body if ln.strip()]:
            continue
        out.append(f"## {section.name}")
        out.append("")
        out += body
        out.append("")
    return "\n".join(out).strip() + "\n"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_tree_render.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add core/tree_render.py tests/core/test_tree_render.py
git commit -m "[feat] Add throwaway tree->markdown renderer for comparison harness"
```

---

### Task 5: Eval-on-body refactor + dev comparison endpoint

**Files:**
- Modify: `core/job.py`
- Create: `tests/core/test_job_eval_body.py`
- Create: `web/routers/dev.py`
- Modify: `web/main.py`
- Create: `tests/web/test_resume_compare.py`

**Interfaces:**
- Consumes: `generate_resume_by_section` (Task 3), `render_tree_markdown` (Task 4), existing `build_resume_prompt`/`_llm_json_with_retry`/`build_resume_document`/`assemble_resume_markdown`, `User.load`/`resolve_prompt`, `get_client_for_profile`, `require_admin`, `current_profile_id`.
- Produces:
  - `Job._evaluate_body(doc_type, body, eval_prompt, user, client, model) -> dict` — eval a Markdown body string (the existing `_evaluate_doc_md` now reads the file then delegates here).
  - `Job.evaluate_resume_body(body, eval_prompt, user, client, model) -> dict` — public wrapper.
  - `POST /api/dev/resume-compare/{job_key}` → `{"model1": {...}, "model2": {...}}`, each `{"markdown": str, "score": float, "issues": list}` or `{"error": str}`.

- [ ] **Step 1: Write the failing eval-body test**

Create `tests/core/test_job_eval_body.py`:

```python
from __future__ import annotations

import core.job as jobmod
from core.job import Job


def test_evaluate_body_scores_a_markdown_string(monkeypatch):
    monkeypatch.setattr(jobmod, "call_llm",
                        lambda *a, **k: '{"score": 0.82, "issues": []}')
    job = Job(job_key="k", profile_id=1)
    out = job.evaluate_resume_body("## Experience\n\n- did things",
                                   "EVAL {current_document}", user=None, client=None, model="m")
    assert out["score"] == 0.82
    assert out["issues"] == []


def test_evaluate_body_empty_is_hard_fail(monkeypatch):
    monkeypatch.setattr(jobmod, "call_llm", lambda *a, **k: '{"score": 1.0, "issues": []}')
    job = Job(job_key="k", profile_id=1)
    out = job.evaluate_resume_body("   ", "EVAL {current_document}",
                                   user=None, client=None, model="m")
    assert out["score"] == 0.0  # empty body short-circuits, never scored by LLM
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_job_eval_body.py -q`
Expected: FAIL — `Job.evaluate_resume_body` does not exist.

- [ ] **Step 3: Refactor `_evaluate_doc_md` to delegate, add the body methods**

In `core/job.py`, replace the body of `_evaluate_doc_md` from the line `_, body = _strip_yaml_frontmatter(...)` onward so the file read delegates to a new `_evaluate_body`. The method becomes:

```python
        md_path = _OUTPUTS_DIR / f"{self.job_key}_{doc_type}.md"
        if not md_path.exists():
            raise FileNotFoundError(
                f"{doc_type.capitalize()} markdown not found: {md_path}"
            )
        _, body = _strip_yaml_frontmatter(md_path.read_text(encoding="utf-8"))
        return self._evaluate_body(doc_type, body, eval_prompt, user, client, model)

    def _evaluate_body(
        self, doc_type: str, body: str, eval_prompt: str, user: Any, client: Any, model: str
    ) -> dict:
        """Evaluate a Markdown body string. Empty body → hard fail (never scored)."""
        from core.llm import call_llm

        if not body.strip():
            return {
                "score": 0.0,
                "issues": [{
                    "category": "personalization",
                    "description": "Document body is empty — nothing to evaluate.",
                }],
            }
        prompt = eval_prompt.replace("{current_document}", body)
        prompt = _apply_template(prompt, {"job": self, "user": user})
        raw = call_llm(prompt, client, model, max_tokens=8192)
        parsed = parse_llm_json(raw, EvalResponse)
        return {
            "score": parsed.score,
            "issues": [i.model_dump() for i in parsed.issues],
        }

    def evaluate_resume_body(
        self, body: str, eval_prompt: str, user: Any, client: Any, model: str
    ) -> dict:
        """Public: evaluate an arbitrary résumé Markdown body (comparison harness)."""
        return self._evaluate_body("resume", body, eval_prompt, user, client, model)
```

(Delete the now-moved empty-body/`prompt`/`call_llm`/`parse` lines that previously lived inline in `_evaluate_doc_md`.)

- [ ] **Step 4: Run the eval-body test (green) + existing job tests**

Run: `pytest tests/core/test_job_eval_body.py tests/core/test_job.py -q`
Expected: PASS (new body tests + existing job tests unaffected).

- [ ] **Step 5: Write the failing endpoint test**

Create `tests/web/test_resume_compare.py`:

```python
from __future__ import annotations

import web.routers.dev as devmod


class _Job:
    job_key = "k"
    def build_resume_prompt(self, user, prompt, db):
        return "RESUME_PROMPT"
    def evaluate_resume_body(self, body, eval_prompt, user, client, model):
        return {"score": 0.7 if "ONE" in body else 0.9, "issues": []}


def test_run_comparison_returns_both_models(monkeypatch):
    # Model 1 path: stub the building blocks devmod uses.
    monkeypatch.setattr(devmod, "_model1_markdown", lambda job, user, client, model, db: "## M ONE")
    monkeypatch.setattr(devmod, "_model2_markdown", lambda job, user, client, model, db: "## M TWO")
    out = devmod.run_comparison(
        _Job(), user=object(), client=object(), model="m",
        eval_prompt="EVAL {current_document}", db=None,
    )
    assert out["model1"]["markdown"] == "## M ONE"
    assert out["model2"]["markdown"] == "## M TWO"
    assert out["model1"]["score"] == 0.7
    assert out["model2"]["score"] == 0.9


def test_one_model_failure_still_returns_other(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("model1 broke")
    monkeypatch.setattr(devmod, "_model1_markdown", boom)
    monkeypatch.setattr(devmod, "_model2_markdown", lambda *a, **k: "## OK TWO")
    out = devmod.run_comparison(
        _Job(), user=object(), client=object(), model="m",
        eval_prompt="EVAL {current_document}", db=None,
    )
    assert "error" in out["model1"]
    assert out["model2"]["markdown"] == "## OK TWO"
```

- [ ] **Step 6: Run endpoint test to verify it fails**

Run: `pytest tests/web/test_resume_compare.py -q`
Expected: FAIL — `web.routers.dev` does not exist.

- [ ] **Step 7: Write `web/routers/dev.py`**

Create `web/routers/dev.py`:

```python
"""Dev-only, admin-gated comparison harness: Model 1 (single-call) vs Model 2
(per-section) résumé generation. Runs both dry (no persistence, no metering, no
ATS) and returns both Markdowns + eval scores for side-by-side review.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.document_assembler import assemble_resume_markdown
from core.document_builder import build_resume_document
from core.job import Job, _llm_json_with_retry
from core.llm import get_client_for_profile
from core.schemas import ResumeGeneration
from core.section_generator import generate_resume_by_section
from core.tree_render import render_tree_markdown
from core.user import User
from db.database import get_db
from web.routers.credits import require_admin
from web.tenancy import current_profile_id

router = APIRouter()


def _model1_markdown(job: Job, user: Any, client: Any, model: str, db: Session) -> str:
    """Model 1 (single-call) résumé Markdown, dry — no Document.upsert, no file write."""
    prompt = job.build_resume_prompt(user, user.resolve_prompt("resume"), db)
    generation = _llm_json_with_retry(
        prompt, client, model, ResumeGeneration, max_tokens=16384,
        empty_msg="Model 1 returned empty content.",
    )
    doc = build_resume_document(user, generation, db)
    return assemble_resume_markdown(doc)


def _model2_markdown(job: Job, user: Any, client: Any, model: str, db: Session) -> str:
    """Model 2 (per-section) résumé Markdown via the schema-driven generator."""
    root = user.profile_tree_root()
    prompt = job.build_resume_prompt(user, "{job.extracted_description}", db)
    authored = generate_resume_by_section(root, prompt, client, model)
    return render_tree_markdown(root, authored)


def _one_model(fn, job, user, client, model, eval_prompt, db) -> dict:
    """Run one model's markdown fn + eval; capture failures per-model."""
    try:
        md = fn(job, user, client, model, db)
    except Exception as exc:  # noqa: BLE001 — surface to the page, never 500 the pair
        return {"error": str(exc)}
    result = {"markdown": md}
    result.update(job.evaluate_resume_body(md, eval_prompt, user, client, model))
    return result


def run_comparison(job, user, client, model, eval_prompt, db) -> dict:
    """Run both models independently and return both results."""
    return {
        "model1": _one_model(_model1_markdown, job, user, client, model, eval_prompt, db),
        "model2": _one_model(_model2_markdown, job, user, client, model, eval_prompt, db),
    }


@router.post("/api/dev/resume-compare/{job_key}")
def resume_compare(
    job_key: str,
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
    _admin=Depends(require_admin),
):
    """Generate the résumé both ways for ``job_key`` and return both + eval scores."""
    job = Job.get(job_key, db, profile_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    user = User.load(db, profile_id=profile_id)
    client, model = get_client_for_profile(user, user.prompt_resume_model)
    eval_prompt = user.resolve_prompt("resume_eval")
    return run_comparison(job, user, client, model, eval_prompt, db)
```

- [ ] **Step 8: Register the router in `web/main.py`**

In `web/main.py`, add the import alongside the other router imports and include it next to the others (e.g. after `app.include_router(prompts.router)`):

```python
from web.routers import dev
...
app.include_router(dev.router)
```

- [ ] **Step 9: Run endpoint + eval tests to verify they pass**

Run: `pytest tests/web/test_resume_compare.py tests/core/test_job_eval_body.py -q`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add core/job.py tests/core/test_job_eval_body.py web/routers/dev.py web/main.py tests/web/test_resume_compare.py
git commit -m "[feat] Add eval-on-body + dev resume-compare endpoint (Model 1 vs Model 2)"
```

---

### Task 6: Dev side-by-side page + docs

**Files:**
- Modify: `react-dashboard/src/api.js`
- Create: `react-dashboard/src/components/admin/ResumeCompare.jsx`
- Create: `react-dashboard/src/components/admin/ResumeCompare.test.jsx`
- Modify: `react-dashboard/src/components/AdminPage.jsx`
- Modify: `core/CONTEXT.md`, `react-dashboard/CONTEXT.md`, `web/CONTEXT.md`

**Interfaces:**
- Consumes: `POST /api/dev/resume-compare/{job_key}` (Task 5); `react-markdown` (already a dependency); the AdminPage function-switcher.
- Produces: `resumeCompare(jobKey)` in `api.js`; a `ResumeCompare` component; an admin function entry.

- [ ] **Step 1: Write the failing component test**

Create `react-dashboard/src/components/admin/ResumeCompare.test.jsx`:

```jsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import ResumeCompare from './ResumeCompare'
import * as api from '../../api'

describe('ResumeCompare', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('runs the comparison and shows both columns with scores', async () => {
    vi.spyOn(api, 'resumeCompare').mockResolvedValue({
      model1: { markdown: '## One body', score: 0.7, issues: [] },
      model2: { markdown: '## Two body', score: 0.9, issues: [] },
    })
    render(<ResumeCompare />)
    fireEvent.change(screen.getByLabelText('Job key'), { target: { value: 'job-1' } })
    fireEvent.click(screen.getByText('Compare'))
    await waitFor(() => expect(api.resumeCompare).toHaveBeenCalledWith('job-1'))
    expect(await screen.findByText('One body')).toBeInTheDocument()
    expect(screen.getByText('Two body')).toBeInTheDocument()
    expect(screen.getByText(/0\.7/)).toBeInTheDocument()
    expect(screen.getByText(/0\.9/)).toBeInTheDocument()
  })

  it('shows a model error without crashing the other column', async () => {
    vi.spyOn(api, 'resumeCompare').mockResolvedValue({
      model1: { error: 'boom' },
      model2: { markdown: '## Two body', score: 0.9, issues: [] },
    })
    render(<ResumeCompare />)
    fireEvent.change(screen.getByLabelText('Job key'), { target: { value: 'j' } })
    fireEvent.click(screen.getByText('Compare'))
    expect(await screen.findByText(/boom/)).toBeInTheDocument()
    expect(screen.getByText('Two body')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd react-dashboard && npm run test -- ResumeCompare`
Expected: FAIL — `./ResumeCompare` not found.

- [ ] **Step 3: Add the API call**

In `react-dashboard/src/api.js`, add (next to the other exports):

```js
export const resumeCompare = (jobKey) =>
  _fetch(`/api/dev/resume-compare/${jobKey}`, { method: 'POST' })
```

- [ ] **Step 4: Write the component**

Create `react-dashboard/src/components/admin/ResumeCompare.jsx`:

```jsx
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { resumeCompare } from '../../api'

function Column({ title, data }) {
  if (!data) return null
  return (
    <div className="flex-1 min-w-0 border border-space-border rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-semibold">{title}</h3>
        {data.error == null && (
          <span className="text-xs text-space-dim">score {Number(data.score).toFixed(2)}</span>
        )}
      </div>
      {data.error != null ? (
        <p className="text-red-400 text-sm">Error: {data.error}</p>
      ) : (
        <div className="prose prose-invert prose-sm max-w-none">
          <ReactMarkdown>{data.markdown}</ReactMarkdown>
        </div>
      )}
    </div>
  )
}

export default function ResumeCompare() {
  const [jobKey, setJobKey] = useState('')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const run = async () => {
    setBusy(true); setErr(''); setResult(null)
    try {
      setResult(await resumeCompare(jobKey.trim()))
    } catch (e) {
      setErr(String(e.message || e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-end gap-2">
        <label className="flex flex-col text-sm gap-1">
          <span className="text-space-dim">Job key</span>
          <input
            aria-label="Job key" value={jobKey}
            className="bg-white/5 border border-space-border rounded px-2 py-1 text-sm"
            onChange={(e) => setJobKey(e.target.value)}
          />
        </label>
        <button
          type="button" disabled={busy || !jobKey.trim()}
          className="px-3 py-1.5 rounded-lg border border-space-border bg-[#1a1a2e] hover:bg-[#23233a] disabled:opacity-50"
          onClick={run}
        >{busy ? 'Comparing…' : 'Compare'}</button>
      </div>
      {err && <p className="text-red-400 text-sm">{err}</p>}
      {result && (
        <div className="flex gap-4 items-start">
          <Column title="Model 1 (single-call)" data={result.model1} />
          <Column title="Model 2 (per-section)" data={result.model2} />
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Wire it into `AdminPage.jsx`**

In `react-dashboard/src/components/AdminPage.jsx`:

(a) Import the component:

```jsx
import ResumeCompare from './admin/ResumeCompare'
```

(b) Add a function entry:

```jsx
const FUNCTIONS = [
  { key: 'users', label: 'Manage Users' },
  { key: 'resume-compare', label: 'Résumé Compare' },
]
```

(c) Render it when active (next to the existing `ManageUsers` line):

```jsx
            {active === 'users' && <ManageUsers />}
            {active === 'resume-compare' && <ResumeCompare />}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd react-dashboard && npm run test -- ResumeCompare`
Expected: PASS (2 tests).

- [ ] **Step 7: Run the full frontend suite + build**

Run (from `react-dashboard/`): `npm run test`
Expected: PASS (all suites).

Run: `npm run build`
Expected: build succeeds.

- [ ] **Step 8: Run the full backend suite for touched modules**

Run: `pytest tests/core/test_section_generator.py tests/core/test_tree_render.py tests/core/test_job_eval_body.py tests/core/test_job.py tests/web/test_resume_compare.py -q`
Expected: PASS.

- [ ] **Step 9: Update docs**

In `core/CONTEXT.md` → "Profile Schema Engine": add that sub-project **#3** ships Model 2 (`core/section_generator.py` — per-section, schema-driven generation keyed by field roles `llm_output`/`llm_input`/`regen_lock`) plus a **throwaway** `core/tree_render.py` used only by the dev comparison harness; real schema-driven rendering of custom sections on documents is still #4.

In `react-dashboard/CONTEXT.md` (profile-tree rows): note that fields now carry a role control (Verbatim / Context only / LLM-written) + regen-lock + an `llm_instructions` box (shown for LLM-written), persisted via the existing tree `PUT`; and that the Admin page has a dev-only "Résumé Compare" view (`admin/ResumeCompare.jsx`) calling `POST /api/dev/resume-compare/{job_key}`.

In `web/CONTEXT.md`: document the dev-only, admin-gated `POST /api/dev/resume-compare/{job_key}` (`web/routers/dev.py`) — runs Model 1 (dry, single-call) and Model 2 (per-section) and returns both Markdowns + eval scores; not metered, no ATS, no persistence.

- [ ] **Step 10: Commit**

```bash
git add react-dashboard/src/api.js react-dashboard/src/components/admin/ResumeCompare.jsx react-dashboard/src/components/admin/ResumeCompare.test.jsx react-dashboard/src/components/AdminPage.jsx core/CONTEXT.md react-dashboard/CONTEXT.md web/CONTEXT.md
git commit -m "[feat] Add dev résumé-compare page; document phase 3"
```

---

## Self-Review

**Spec coverage:**
- Field-role taxonomy (context/immutable/outputable) + regen-lock + instructions → Tasks 1 (helpers) & 2 (editor UI). ✓
- `User.profile_tree_root()` → Task 3 Step 3. ✓
- `core/section_generator.py` per-section engine (one call/section, regen_lock respected, list keying, no-call when no outputable, per-section failure fallback) → Task 3. ✓
- `core/tree_render.py` throwaway renderer (overlay authored, omit context-only, skip hidden, custom sections) → Task 4. ✓
- Dev endpoint runs Model 1 dry + Model 2, eval each, returns both, per-model failure isolation → Task 5. ✓
- Eval on an arbitrary body (not just the on-disk file) → Task 5 (`_evaluate_body`/`evaluate_resume_body`). ✓
- Dev side-by-side page with scores → Task 6. ✓
- No metering/ATS/persistence; résumé only → endpoint never calls `meter_action`/ATS/`Document.upsert`; Model 1 path is dry. ✓
- Docs updated → Task 6 Step 9. ✓
- Out of scope (cover letters, PDF, real renderer, productionizing) → not implemented. ✓

**Placeholder scan:** none — every code step contains complete code; every run step has an exact command + expected result.

**Type/identifier consistency:** `generate_resume_by_section(root, job_ctx, client, model)` and `SectionOutput{fields, entries}` defined in Task 3, consumed in Task 5 (`_model2_markdown`). `render_tree_markdown(root, authored)` defined in Task 4, consumed in Task 5. `Job.evaluate_resume_body(body, eval_prompt, user, client, model)` defined in Task 5 Step 3, consumed by `_one_model` in the same task and stubbed in its test. `User.profile_tree_root()` defined in Task 3, consumed in Task 5 `_model2_markdown`. Frontend `setFieldRole`/`setLlmInstructions`/`toggleRegenLock`/`fieldRole` defined in Task 1, consumed by the `ops` bundle (Task 2) and `FieldView` (Task 2). `resumeCompare(jobKey)` defined in Task 6 Step 3, consumed by `ResumeCompare` and its test. The endpoint shape `{model1,model2}` with `{markdown,score,issues}|{error}` is consistent between Task 5 (`run_comparison`/`_one_model`) and Task 6 (`Column`).
