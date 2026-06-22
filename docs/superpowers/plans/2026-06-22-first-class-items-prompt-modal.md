# First-Class List Items, Prompt Modal & Header Editing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make list entries first-class (eye/lock/message icons, rename, body-click expand), move all prompt editing into a single modal with per-entry chip sub-folders and a folded preview, allow add/remove fields on every preset section, honor visibility in the production document, and polish pill insertion/styling.

**Architecture:** Backend gains a pure `build_section_prompt` helper (the canonical folded `[Section: … [Item: …]]` format) reused by `section_generator`, plus visibility filtering in `tree_to_legacy`. Frontend retires inline prompt fields in favor of a `PromptEditorModal` (sole prompt surface, hosting the chip tray + folded preview), upgrades list entries to the section control idiom, and fixes drop-point pill insertion + green styling.

**Tech Stack:** Python 3 / Pydantic v2 / pytest (backend); React 18 / Vite / Vitest / RTL / @dnd-kit / Tailwind (frontend).

## Global Constraints

- Python: type hints, black formatting, Google-style docstrings.
- No Claude/Anthropic attribution in commits; commit format `[type] Imperative subject`.
- No remote push / no merge to shared `main` (initiative release constraint).
- The profile tree stored as JSON in `user_profile.data` is the source of truth; node ids are stable and rename-safe.
- Profile tokens are node-id based: `{profile:<nodeId>}`; job tokens `{job.<field>}`.
- Frontend tests: `cd react-dashboard && npm run test`. Backend tests: `python -m pytest` from repo root.
- The canonical folded-prompt format string MUST be identical between Python (`build_section_prompt`) and JS (`buildFoldedPreview`): `[<SectionName>: <section.prompt> [<ItemName>: <item.prompt>] …]`.

---

### Task 1: `build_section_prompt` folded assembly (backend)

**Files:**
- Modify: `core/profile_tree.py` (add helper near `_field_value_str`, ~line 569)
- Test: `tests/core/test_profile_tree.py`

**Interfaces:**
- Consumes: `SectionNode`, `ListNode`, `GroupNode` from `core.profile_tree`.
- Produces: `build_section_prompt(section: SectionNode) -> str`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/core/test_profile_tree.py` (ensure `build_section_prompt`, `SectionNode`, `ListNode`, `GroupNode`, `FieldNode` are imported):

```python
def test_build_section_prompt_section_only():
    sec = SectionNode(name="Summary", prompt="Be punchy", order=0,
                      children=[FieldNode(name="Hero", key="hero", kind="markdown")])
    assert build_section_prompt(sec) == "[Summary: Be punchy]"


def test_build_section_prompt_folds_unlocked_items():
    lst = ListNode(name="Experience", children=[
        GroupNode(name="Research Assistant", prompt="stress ML pubs"),
        GroupNode(name="Barista", prompt="keep it brief"),
    ])
    sec = SectionNode(name="Experience", prompt="Lead with impact", order=0, children=[lst])
    out = build_section_prompt(sec)
    assert out == ("[Experience: Lead with impact "
                   "[Research Assistant: stress ML pubs] [Barista: keep it brief]]")


def test_build_section_prompt_skips_locked_and_empty_items():
    lst = ListNode(name="Experience", children=[
        GroupNode(name="Locked Job", prompt="ignored", locked=True),
        GroupNode(name="Empty Job", prompt=""),
        GroupNode(name="Real Job", prompt="emphasize leadership"),
    ])
    sec = SectionNode(name="Experience", prompt="", order=0, children=[lst])
    assert build_section_prompt(sec) == "[Experience: [Real Job: emphasize leadership]]"


def test_build_section_prompt_locked_section_empty():
    sec = SectionNode(name="Skills", prompt="anything", locked=True, order=0)
    assert build_section_prompt(sec) == ""


def test_build_section_prompt_all_empty_returns_empty():
    sec = SectionNode(name="Skills", prompt="", order=0,
                      children=[FieldNode(name="S", key="skills", kind="taglist")])
    assert build_section_prompt(sec) == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/core/test_profile_tree.py -k build_section_prompt -v`
Expected: FAIL with `ImportError`/`NameError: build_section_prompt`.

- [ ] **Step 3: Implement the helper**

Add to `core/profile_tree.py` (after `_field_value_str`):

```python
def _entry_label(group: GroupNode) -> str:
    """An entry's display name, falling back to its first non-empty field value."""
    if group.name.strip():
        return group.name.strip()
    for f in group.children:
        s = _field_value_str(f).strip()
        if s:
            return s
    return "Entry"


def build_section_prompt(section: SectionNode) -> str:
    """Assemble a section's authoring prompt, nesting unlocked list-entry prompts.

    Produces ``[<SectionName>: <section.prompt> [<ItemName>: <item.prompt>] …]``.
    Empty section/item prompts are omitted; a locked section returns ``""`` (it is
    never authored); locked entries are skipped. Returns ``""`` when neither the
    section prompt nor any item prompt is present.

    Args:
        section: The section to assemble a prompt for.

    Returns:
        The folded prompt string, or ``""`` when nothing is authored.
    """
    if section.locked:
        return ""
    parts: list[str] = []
    if section.prompt.strip():
        parts.append(section.prompt.strip())
    child = section.children[0] if section.children else None
    if isinstance(child, ListNode):
        for entry in child.children:
            if entry.locked or not entry.prompt.strip():
                continue
            parts.append(f"[{_entry_label(entry)}: {entry.prompt.strip()}]")
    if not parts:
        return ""
    return f"[{section.name}: {' '.join(parts)}]"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/core/test_profile_tree.py -k build_section_prompt -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add core/profile_tree.py tests/core/test_profile_tree.py
git commit -m "[feat] Add build_section_prompt folded-prompt assembly"
```

---

### Task 2: Honor visibility in `tree_to_legacy` (backend)

**Files:**
- Modify: `core/profile_tree.py:486-566` (`tree_to_legacy` + `_rows`)
- Test: `tests/core/test_profile_tree.py`

**Interfaces:**
- Consumes: `RootNode`, existing `tree_to_legacy`.
- Produces: `tree_to_legacy` that omits invisible sections, list entries, and header/summary/skills fields. Signature unchanged.

- [ ] **Step 1: Write the failing tests**

Add to `tests/core/test_profile_tree.py`. These build a tree via `legacy_to_tree`, hide nodes, and assert the projection drops them. (Inspect the round-trip in existing tests for the exact legacy dict shape; this uses `legacy_to_tree`/`tree_to_legacy` already imported there.)

```python
def test_tree_to_legacy_omits_invisible_experience_entry():
    legacy = {
        "first_name": "A", "last_name": "B",
        "work_history": [
            {"company": "Acme", "title": "Eng", "start": "2020", "end": "2022", "summary": "x"},
            {"company": "Globex", "title": "Eng", "start": "2018", "end": "2020", "summary": "y"},
        ],
    }
    root = legacy_to_tree(legacy)
    exp = next(s for s in root.children if s.role == "experience")
    exp.children[0].children[1].visible = False  # hide the Globex entry
    out = tree_to_legacy(root)
    companies = [r["company"] for r in out["work_history"]]
    assert companies == ["Acme"]


def test_tree_to_legacy_omits_invisible_section():
    root = legacy_to_tree({"first_name": "A", "skills": ["Python", "Go"]})
    skills = next(s for s in root.children if s.role == "skills")
    skills.visible = False
    assert tree_to_legacy(root)["skills"] == []


def test_tree_to_legacy_omits_invisible_header_field():
    root = legacy_to_tree({"first_name": "A", "email": "a@b.c"})
    header = next(s for s in root.children if s.role == "header")
    for f in header.children[0].children:
        if f.key == "email":
            f.visible = False
    assert tree_to_legacy(root)["email"] == ""


def test_tree_to_legacy_all_visible_unchanged():
    legacy = {"first_name": "A", "last_name": "B", "email": "a@b.c",
              "skills": ["Python"],
              "work_history": [{"company": "Acme", "title": "Eng", "start": "2020",
                                "end": "2022", "summary": "x"}]}
    root = legacy_to_tree(legacy)
    out = tree_to_legacy(root)
    assert out["first_name"] == "A"
    assert out["skills"] == ["Python"]
    assert [r["company"] for r in out["work_history"]] == ["Acme"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/core/test_profile_tree.py -k tree_to_legacy -v`
Expected: the three "omits" tests FAIL (invisible nodes still emitted); `all_visible_unchanged` may already pass.

- [ ] **Step 3: Add the visibility guards**

In `core/profile_tree.py`, edit `tree_to_legacy`:

Header projection — guard the field loop:
```python
    header = _section_by_role(root, "header")
    if header and header.visible and header.children and isinstance(header.children[0], GroupNode):
        for f in header.children[0].children:
            if f.visible and f.key in out:
                out[f.key] = f.value
```

Summary:
```python
    summary = _section_by_role(root, "summary")
    if (summary and summary.visible and summary.children
            and isinstance(summary.children[0], FieldNode)
            and summary.children[0].visible):
        out["hero"] = summary.children[0].value
```

Skills:
```python
    skills = _section_by_role(root, "skills")
    if (skills and skills.visible and skills.children
            and isinstance(skills.children[0], FieldNode)
            and skills.children[0].visible):
        out["skills"] = list(skills.children[0].value)
```

`_rows` — skip invisible sections and entries:
```python
    def _rows(role: str) -> list[dict]:
        sect = _section_by_role(root, role)
        if (not sect or not sect.visible or not sect.children
                or not isinstance(sect.children[0], ListNode)):
            return []
        return [
            {f.key: f.value for f in item.children}
            for item in sect.children[0].children
            if item.visible
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/core/test_profile_tree.py -k tree_to_legacy -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the full profile_tree suite (regression)**

Run: `python -m pytest tests/core/test_profile_tree.py -v`
Expected: PASS (no regressions).

- [ ] **Step 6: Commit**

```bash
git add core/profile_tree.py tests/core/test_profile_tree.py
git commit -m "[feat] Honor node visibility in tree_to_legacy projection"
```

---

### Task 3: `section_generator` consumes the folded prompt (backend)

**Files:**
- Modify: `core/section_generator.py:58-94` (`_build_scalar_prompt`, `_build_list_prompt`)
- Test: `tests/core/test_section_generator.py`

**Interfaces:**
- Consumes: `build_section_prompt` from `core.profile_tree`.
- Produces: prompts that begin with the folded `[Section: …]` block instead of the old `guide`/`item_guide` text. `generate_resume_by_section` signature unchanged.

- [ ] **Step 1: Write the failing test**

Add to `tests/core/test_section_generator.py`. Stub `_llm_json_with_retry` to capture the prompt (it is imported locally in `generate_resume_by_section` via `from core.job import _llm_json_with_retry`, so patch it on `core.job`):

```python
import core.job
from core.profile_tree import (
    FieldNode, GroupNode, ListNode, RootNode, SectionNode,
)
from core.section_generator import generate_resume_by_section, SectionOutput


def test_list_prompt_contains_folded_format(monkeypatch):
    captured = {}

    def fake(prompt, client, model, schema, **kw):
        captured["prompt"] = prompt
        return SectionOutput(entries={})

    monkeypatch.setattr(core.job, "_llm_json_with_retry", fake)

    entry = GroupNode(name="Research Assistant", prompt="stress ML pubs", children=[
        FieldNode(name="Summary", key="summary", kind="markdown",
                  value="old", llm_output=True),
    ])
    lst = ListNode(name="Experience", item_template=GroupNode(), children=[entry])
    sec = SectionNode(name="Experience", role="experience", prompt="Lead with impact",
                      order=0, children=[lst])
    root = RootNode(children=[sec])

    generate_resume_by_section(root, "JOBCTX", client=object(), model="m")
    assert "[Experience: Lead with impact [Research Assistant: stress ML pubs]]" in captured["prompt"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_section_generator.py -k folded -v`
Expected: FAIL (prompt has old `guide` text, not the bracketed folded format).

- [ ] **Step 3: Swap the guide text for `build_section_prompt`**

In `core/section_generator.py`:

Add to the import line:
```python
from core.profile_tree import (
    FieldNode, GroupNode, ListNode, RootNode, SectionNode, build_section_prompt,
)
```

In `_build_scalar_prompt`, replace the `guide` line:
```python
def _build_scalar_prompt(section: SectionNode, group: GroupNode, job_ctx: str) -> str:
    """Prompt for a section whose child is a single group (or bare field wrapped)."""
    ctx = "\n".join(_group_context(group)) or "(none)"
    specs = "\n".join(_outputable_specs(group))
    folded = build_section_prompt(section)
    guide = f"{folded}\n\n" if folded else ""
    return (
        f"{guide}You are tailoring the résumé section '{section.name}' to a job.\n\n"
        f"JOB:\n{job_ctx}\n\n"
        f"EXISTING SECTION DATA (anchors — do not change these):\n{ctx}\n\n"
        f"Write tailored content for these fields:\n{specs}\n\n"
        'Return JSON: {"fields": {"<field_key>": "<value>"}} containing exactly '
        "the field keys above."
    )
```

In `_build_list_prompt`, drop the per-entry `item_guide` (now folded into the header) and replace the section `guide`:
```python
def _build_list_prompt(section: SectionNode, lst: ListNode, job_ctx: str) -> str:
    """Prompt for a repeating-list section (one call authors every unlocked entry)."""
    blocks = []
    for entry in lst.children:
        ctx = "\n".join(_group_context(entry)) or "(none)"
        if entry.locked:
            blocks.append(f'ENTRY id="{entry.id}" (FIXED — do not rewrite):\n{ctx}')
            continue
        specs = "\n".join(_outputable_specs(entry))
        blocks.append(
            f'ENTRY id="{entry.id}":\nanchors:\n{ctx}\nwrite:\n{specs}'
        )
    body = "\n\n".join(blocks)
    folded = build_section_prompt(section)
    guide = f"{folded}\n\n" if folded else ""
    return (
        f"{guide}You are tailoring the résumé section '{section.name}' to a job. Each "
        f"entry is a separate item; write its fields using its own anchors.\n\n"
        f"JOB:\n{job_ctx}\n\n{body}\n\n"
        'Return JSON: {"entries": {"<entry_id>": {"<field_key>": "<value>"}}} '
        "with an object for every entry id above that is not FIXED."
    )
```

- [ ] **Step 4: Run the test + full section_generator suite**

Run: `python -m pytest tests/core/test_section_generator.py -v`
Expected: PASS (new test + existing, possibly with prior assertions on `guidance:` updated — if an existing test asserted the old `item_guide`/`guide` wording, update it to assert the folded format).

- [ ] **Step 5: Commit**

```bash
git add core/section_generator.py tests/core/test_section_generator.py
git commit -m "[refactor] Feed folded section/item prompt to section_generator"
```

---

### Task 4: Chip-tray per-entry sub-folders + folded preview (frontend pure helpers)

**Files:**
- Modify: `react-dashboard/src/components/widgets/profile-tree/PromptField.jsx` (`buildChipGroups`, `buildLabelMap`; add `buildFoldedPreview`, `entryLabel`)
- Test: `react-dashboard/src/components/widgets/profile-tree/PromptField.test.jsx` (create if absent; else add cases)

**Interfaces:**
- Consumes: tree plain-object nodes.
- Produces:
  - `buildChipGroups(tree)` → groups where a **list** section yields nested `subfolders: [{ label, chips }]` (one per entry: a whole-entry pill `{profile:<entryId>}` + per-field pills `{profile:<fieldId>}`); non-list sections unchanged (flat `chips`).
  - `entryLabel(entry)` → `entry.name` || first non-empty field value || `'Entry'`.
  - `buildFoldedPreview(section)` → the JS mirror of Python `build_section_prompt`.
  - `buildLabelMap(tree)` updated so entry/field tokens map to human labels.

- [ ] **Step 1: Write the failing tests**

Add to `PromptField.test.jsx`:

```js
import { describe, it, expect } from 'vitest'
import { buildChipGroups, buildFoldedPreview, entryLabel } from './PromptField'

const listSection = {
  type: 'section', id: 'sec1', name: 'Experience', role: 'experience',
  prompt: 'Lead with impact',
  children: [{
    type: 'list', id: 'lst1', name: 'Experience',
    children: [
      { type: 'group', id: 'e1', name: 'Research Assistant', prompt: 'stress ML pubs',
        children: [{ type: 'field', id: 'f1', name: 'Title', key: 'title', value: 'RA' }] },
      { type: 'group', id: 'e2', name: '', prompt: '',
        children: [{ type: 'field', id: 'f2', name: 'Title', key: 'title', value: 'Barista' }] },
    ],
  }],
}
const tree = { type: 'root', id: 'r', children: [listSection] }

it('builds one sub-folder per entry with whole-entry + field pills', () => {
  const groups = buildChipGroups(tree)
  const exp = groups.find((g) => g.label === 'Experience')
  expect(exp.subfolders).toHaveLength(2)
  const first = exp.subfolders[0]
  expect(first.label).toBe('Research Assistant')
  expect(first.chips.map((c) => c.token)).toEqual(['{profile:e1}', '{profile:f1}'])
})

it('labels an unnamed entry from its first field value', () => {
  expect(entryLabel({ name: '', children: [{ value: 'Barista' }] })).toBe('Barista')
})

it('buildFoldedPreview mirrors the Python format', () => {
  expect(buildFoldedPreview(listSection)).toBe(
    '[Experience: Lead with impact [Research Assistant: stress ML pubs]]',
  )
})

it('buildFoldedPreview returns empty when nothing authored', () => {
  expect(buildFoldedPreview({ name: 'Skills', prompt: '', children: [] })).toBe('')
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd react-dashboard && npm run test -- PromptField`
Expected: FAIL (`buildFoldedPreview`/`entryLabel` not exported; `subfolders` undefined).

- [ ] **Step 3: Implement the helpers**

In `PromptField.jsx`:

```js
export function entryLabel(entry) {
  if (entry?.name && entry.name.trim()) return entry.name.trim()
  for (const f of entry?.children || []) {
    if (typeof f.value === 'string' && f.value.trim()) return f.value.trim()
    if (Array.isArray(f.value) && f.value.length) return f.value.join(', ')
  }
  return 'Entry'
}

export function buildFoldedPreview(section) {
  if (!section || section.locked) return ''
  const parts = []
  if (section.prompt && section.prompt.trim()) parts.push(section.prompt.trim())
  const child = (section.children || [])[0]
  if (child && child.type === 'list') {
    for (const entry of child.children || []) {
      if (entry.locked || !(entry.prompt && entry.prompt.trim())) continue
      parts.push(`[${entryLabel(entry)}: ${entry.prompt.trim()}]`)
    }
  }
  if (!parts.length) return ''
  return `[${section.name}: ${parts.join(' ')}]`
}
```

Rewrite `buildChipGroups` so a list section nests sub-folders (non-list unchanged):

```js
export function buildChipGroups(tree) {
  const groups = [{
    label: 'Job',
    chips: JOB_CHIPS.map((c) => ({ token: c.token, label: c.label, display: `Job: ${c.label}` })),
  }]
  for (const section of tree?.children || []) {
    const name = section.name || 'Section'
    const child = (section.children || [])[0]
    if (child && child.type === 'list') {
      const subfolders = (child.children || []).map((entry) => {
        const elabel = entryLabel(entry)
        const chips = [{ token: `{profile:${entry.id}}`, label: '(whole entry)', display: `${name} › ${elabel}` }]
        for (const f of entry.children || []) {
          const fname = f.name || f.key
          chips.push({ token: `{profile:${f.id}}`, label: fname, display: `${name} › ${elabel} › ${fname}` })
        }
        return { label: elabel, chips }
      })
      groups.push({ label: name, subfolders })
    } else {
      const chips = [{ token: `{profile:${section.id}}`, label: '(whole section)', display: name }]
      for (const f of sectionFields(section)) {
        const fname = f.name || f.key
        chips.push({ token: `{profile:${f.id}}`, label: fname, display: `${name} › ${fname}` })
      }
      groups.push({ label: name, chips })
    }
  }
  return groups
}
```

Update `buildLabelMap` to walk both flat `chips` and nested `subfolders`:

```js
export function buildLabelMap(tree) {
  const map = {}
  const add = (chips) => { for (const c of chips || []) map[c.token] = c.display }
  for (const g of buildChipGroups(tree)) {
    add(g.chips)
    for (const sf of g.subfolders || []) add(sf.chips)
  }
  return map
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd react-dashboard && npm run test -- PromptField`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/widgets/profile-tree/PromptField.jsx react-dashboard/src/components/widgets/profile-tree/PromptField.test.jsx
git commit -m "[feat] Per-entry chip sub-folders and folded-prompt preview helper"
```

---

### Task 5: Render nested chip sub-folders + green pills + drop-point insert

**Files:**
- Modify: `react-dashboard/src/components/widgets/profile-tree/PromptField.jsx` (`ChipFolder`/`ChipTray`, `Editor` `onDrop`, `pillHtml`)
- Modify: `react-dashboard/src/index.css` (add `.prompt-chip` green style)
- Test: `react-dashboard/src/components/widgets/profile-tree/PromptField.test.jsx`

**Interfaces:**
- Consumes: `buildChipGroups` groups that may carry `subfolders`.
- Produces: `ChipFolder` recursively renders sub-folders; pills styled green; drop inserts at release coordinates.

- [ ] **Step 1: Write the failing test**

Add to `PromptField.test.jsx`:

```js
import { render, screen, fireEvent } from '@testing-library/react'
import { ChipTray } from './PromptField'

it('expands an entry sub-folder to reveal its chips', () => {
  const groups = [{
    label: 'Experience',
    subfolders: [{ label: 'Research Assistant', chips: [
      { token: '{profile:e1}', label: '(whole entry)', display: 'Experience › RA' },
    ] }],
  }]
  render(<ChipTray groups={groups} onInsert={() => {}} />)
  fireEvent.click(screen.getByText('Experience'))
  fireEvent.click(screen.getByText('Research Assistant'))
  expect(screen.getByText('(whole entry)')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd react-dashboard && npm run test -- PromptField`
Expected: FAIL (sub-folder not rendered).

- [ ] **Step 3: Make `ChipFolder` recursive and add the CSS**

Replace `ChipFolder` in `PromptField.jsx`:

```jsx
function ChipFolder({ group, onInsert }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="flex flex-col">
      <button
        type="button"
        className="text-left text-xs font-semibold text-space-dim hover:text-space-text"
        onClick={() => setOpen((o) => !o)}
      ><span aria-hidden="true">{open ? '▾' : '▸'} </span>{group.label}</button>
      {open && group.chips && (
        <div className="flex flex-wrap gap-1.5 pl-3 py-1">
          {group.chips.map((c) => (
            <button
              key={c.token}
              type="button"
              draggable
              onDragStart={(e) => {
                e.dataTransfer.setData('text/plain', c.token)
                e.dataTransfer.setData('application/x-chip-label', c.display)
              }}
              onClick={() => onInsert(c.token, c.display)}
              className="px-2 py-0.5 rounded-full border border-emerald-500/40 bg-emerald-500/10 text-xs text-emerald-300 cursor-grab active:cursor-grabbing select-none"
            >{c.label}</button>
          ))}
        </div>
      )}
      {open && group.subfolders && (
        <div className="flex flex-col pl-3">
          {group.subfolders.map((sf) => (
            <ChipFolder key={sf.label} group={sf} onInsert={onInsert} />
          ))}
        </div>
      )}
    </div>
  )
}
```

Update `pillHtml` to carry the green class inline (so it survives the innerHTML round-trip without Tailwind purge concerns):

```js
function pillHtml(token, label) {
  return `<span class="prompt-chip" contenteditable="false" data-token="${escapeHtml(token)}">${escapeHtml(label || token)}</span>`
}
```

Add to `react-dashboard/src/index.css`:

```css
.prompt-chip {
  display: inline-block;
  padding: 0 0.35rem;
  margin: 0 0.1rem;
  border-radius: 0.375rem;
  background: rgba(16, 185, 129, 0.18);
  color: #6ee7b7;
  border: 1px solid rgba(16, 185, 129, 0.45);
  white-space: nowrap;
}
```

Also set the same inline style on the runtime-created pill in `insertPillAtCaret` so freshly dropped pills match before re-render (add `span.className = 'prompt-chip'` — already present, the CSS rule now styles it).

- [ ] **Step 4: Drop at release point**

Replace `Editor`'s `onDrop` with a coordinate-based caret lookup, falling back to the existing caret/append path:

```jsx
  const onDrop = (e) => {
    e.preventDefault()
    const token = e.dataTransfer.getData('text/plain')
    const label = e.dataTransfer.getData('application/x-chip-label')
    if (!token) return
    const root = ref.current
    let range = null
    if (document.caretRangeFromPoint) {
      range = document.caretRangeFromPoint(e.clientX, e.clientY)
    } else if (document.caretPositionFromPoint) {
      const pos = document.caretPositionFromPoint(e.clientX, e.clientY)
      if (pos) { range = document.createRange(); range.setStart(pos.offsetNode, pos.offset); range.collapse(true) }
    }
    if (range && root && root.contains(range.startContainer)) {
      const sel = window.getSelection()
      sel.removeAllRanges()
      sel.addRange(range)
    }
    insertPillAtCaret(root, token, label || labels[token] || token)
    emit()
  }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd react-dashboard && npm run test -- PromptField`
Expected: PASS (sub-folder test + existing pill tests; drop-point path is feature-detected so jsdom falls through to the prior behavior).

- [ ] **Step 6: Commit**

```bash
git add react-dashboard/src/components/widgets/profile-tree/PromptField.jsx react-dashboard/src/index.css react-dashboard/src/components/widgets/profile-tree/PromptField.test.jsx
git commit -m "[feat] Nested chip sub-folders, green pills, drop-point insertion"
```

---

### Task 6: `PromptEditorModal` + retire inline prompt fields

**Files:**
- Create: `react-dashboard/src/components/widgets/profile-tree/PromptEditorModal.jsx`
- Modify: `react-dashboard/src/components/widgets/profile-tree/TreeNode.jsx` (remove inline `PromptField` from `SectionView` and `SortableEntry`)
- Test: `react-dashboard/src/components/widgets/profile-tree/PromptEditorModal.test.jsx`

**Interfaces:**
- Consumes: `PromptField` internals (`ChipTray`, `Editor`) via the existing `PromptField` export — the modal renders a `PromptField` plus, for sections, a `buildFoldedPreview` block.
- Produces: `PromptEditorModal({ node, isSection, tree, onChange, onClose })` — overlay with editor + (section-only) read-only folded preview + locked-node note.

- [ ] **Step 1: Write the failing tests**

Create `PromptEditorModal.test.jsx`:

```js
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { PromptEditorModal } from './PromptEditorModal'

const tree = { type: 'root', id: 'r', children: [] }

it('shows the folded preview for a section node', () => {
  const node = {
    type: 'section', id: 's1', name: 'Experience', prompt: 'Lead with impact',
    children: [{ type: 'list', id: 'l1', children: [
      { type: 'group', id: 'e1', name: 'RA', prompt: 'stress pubs', children: [] },
    ] }],
  }
  render(<PromptEditorModal node={node} isSection tree={tree} onChange={() => {}} onClose={() => {}} />)
  expect(screen.getByText(/\[Experience: Lead with impact \[RA: stress pubs\]\]/)).toBeInTheDocument()
})

it('shows an inert note when the node is locked', () => {
  const node = { type: 'section', id: 's1', name: 'X', prompt: '', locked: true, children: [] }
  render(<PromptEditorModal node={node} isSection tree={tree} onChange={() => {}} onClose={() => {}} />)
  expect(screen.getByText(/inert while .* locked/i)).toBeInTheDocument()
})

it('closes on the close button', () => {
  const onClose = vi.fn()
  const node = { type: 'group', id: 'e1', name: 'RA', prompt: '', children: [] }
  render(<PromptEditorModal node={node} isSection={false} tree={tree} onChange={() => {}} onClose={onClose} />)
  fireEvent.click(screen.getByLabelText('Close prompt editor'))
  expect(onClose).toHaveBeenCalled()
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd react-dashboard && npm run test -- PromptEditorModal`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement the modal**

Create `PromptEditorModal.jsx`:

```jsx
import { useEffect } from 'react'
import { PromptField, buildFoldedPreview } from './PromptField'

// The sole surface for editing a section/item authoring prompt. Opened by the ✉
// control on a section or list entry. Hosts the pill editor + chip tray, and for
// sections a read-only folded preview mirroring the backend build_section_prompt.
export function PromptEditorModal({ node, isSection, tree, onChange, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const locked = !!node.locked
  const title = `${isSection ? 'Section' : 'Item'} prompt — ${node.name || 'Untitled'}`
  const preview = isSection ? buildFoldedPreview(node) : ''

  return (
    <div
      className="fixed inset-0 z-[170] flex items-center justify-center bg-black/60"
      onClick={onClose}
    >
      <div
        className="bg-[#0f0f1a] border border-space-border rounded-2xl p-5 w-[48rem] max-w-[92vw] flex flex-col gap-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-space-text">{title}</h2>
          <button
            type="button" aria-label="Close prompt editor" onClick={onClose}
            className="text-space-dim hover:text-space-text text-xl leading-none"
          >×</button>
        </div>
        {locked && (
          <p className="text-xs text-amber-400">
            This prompt is saved but inert while the {isSection ? 'section' : 'item'} is
            locked — the LLM skips locked nodes.
          </p>
        )}
        <PromptField
          value={node.prompt || ''} tree={tree}
          ariaLabel={title} placeholder="How should the LLM tailor this?"
          onChange={onChange}
        />
        {isSection && (
          <div className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-space-dim">Folded prompt sent to the LLM</span>
            <pre className="text-xs text-space-text bg-white/5 border border-space-border rounded p-2 whitespace-pre-wrap">{preview || '(empty)'}</pre>
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Remove the inline `PromptField` blocks from `TreeNode.jsx`**

In `SectionView`, delete the `{!collapsed && !locked && (<PromptField … ariaLabel="Section prompt" … />)}` block. In `SortableEntry`, delete the `{!collapsed && !sectionLocked && !locked && (<PromptField … ariaLabel="Item prompt" … />)}` block. Remove the now-unused `import { PromptField } from './PromptField'` if nothing else uses it in this file (the modal is wired in Task 7). Leave `tree` props threaded — Task 7 needs them.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd react-dashboard && npm run test -- PromptEditorModal`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add react-dashboard/src/components/widgets/profile-tree/PromptEditorModal.jsx react-dashboard/src/components/widgets/profile-tree/PromptEditorModal.test.jsx react-dashboard/src/components/widgets/profile-tree/TreeNode.jsx
git commit -m "[feat] Add PromptEditorModal; retire inline prompt fields"
```

---

### Task 7: First-class list items + controls cleanup (wire ✉, eye, rename, body-expand; drop ↑/↓ and ▸/▾)

**Files:**
- Modify: `react-dashboard/src/components/widgets/profile-tree/TreeNode.jsx` (`SortableEntry`, `SectionView`, `SectionChild`, `ListView`)
- Test: `react-dashboard/src/components/widgets/profile-tree/TreeNode.test.jsx` (add cases; create if absent)

**Interfaces:**
- Consumes: `PromptEditorModal`; `ops.toggleVisible`, `ops.rename`, `ops.setPrompt`, `ops.toggleLocked` (all already on the ops bundle).
- Produces: section & entry rows with 🔒/👁/✉ controls, drag-handle-only reorder, body-click expand, double-click entry rename.

- [ ] **Step 1: Write the failing tests**

Add to `TreeNode.test.jsx` (use a minimal tree + a no-op `ops` with `vi.fn()` members). Note these reference behaviors not present yet:

```js
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SectionView } from './TreeNode'

function makeOps() {
  return {
    setValue: vi.fn(), rename: vi.fn(), toggleVisible: vi.fn(), remove: vi.fn(),
    move: vi.fn(), addItem: vi.fn(), addField: vi.fn(), reorder: vi.fn(),
    setInstructions: vi.fn(), toggleWritten: vi.fn(), toggleLocked: vi.fn(),
    setPrompt: vi.fn(),
  }
}

const expSection = {
  type: 'section', id: 's1', name: 'Experience', role: 'experience', visible: true,
  prompt: '', children: [{
    type: 'list', id: 'l1', name: 'Experience', children: [
      { type: 'group', id: 'e1', name: 'RA', visible: true, prompt: '', children: [
        { type: 'field', id: 'f1', name: 'Title', key: 'title', kind: 'text', value: 'RA', visible: true },
      ] },
    ],
  }],
}
const tree = { type: 'root', id: 'r', children: [expSection] }

it('section bar has no up/down or expand-arrow buttons', () => {
  const ops = makeOps()
  render(<SectionView section={expSection} isFirst isLast ops={ops} tree={tree} initialCollapsed={false} />)
  expect(screen.queryByLabelText('Move up')).toBeNull()
  expect(screen.queryByLabelText('Expand section')).toBeNull()
  expect(screen.queryByLabelText('Collapse section')).toBeNull()
})

it('opens the prompt modal from the section message icon', () => {
  const ops = makeOps()
  render(<SectionView section={expSection} isFirst isLast ops={ops} tree={tree} initialCollapsed={false} />)
  fireEvent.click(screen.getByLabelText('Edit section prompt'))
  expect(screen.getByText(/Section prompt — Experience/)).toBeInTheDocument()
})

it('list entry exposes eye and message controls', () => {
  const ops = makeOps()
  render(<SectionView section={expSection} isFirst isLast ops={ops} tree={tree} initialCollapsed={false} />)
  expect(screen.getByLabelText('Edit item prompt')).toBeInTheDocument()
  expect(screen.getByLabelText(/item.*output|Hide item|Show item/i)).toBeInTheDocument()
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd react-dashboard && npm run test -- TreeNode`
Expected: FAIL (Move up still present, no "Edit section prompt" control).

- [ ] **Step 3: Rework `SectionView`**

In `TreeNode.jsx`, import the modal and `useState` is already imported. At top:
```jsx
import { PromptEditorModal } from './PromptEditorModal'
```

Replace `SectionView`'s control cluster: remove `<MoveButtons … />` and the ▸/▾ expand `<button>`; add a ✉ message button; keep lock, eye, remove. Add modal state. The header bar still toggles collapse on body click.

```jsx
export function SectionView({ section, isFirst, isLast, ops, dragHandle, tree, initialCollapsed = true }) {
  const preset = isPresetSection(section)
  const child = section.children[0]
  const [collapsed, setCollapsed] = useState(initialCollapsed)
  const [promptOpen, setPromptOpen] = useState(false)
  const toggle = () => setCollapsed((c) => !c)
  const locked = !!section.locked
  return (
    <div className={`border border-space-border rounded-xl p-4 flex flex-col gap-3 ${section.visible ? '' : 'opacity-60'}`}>
      <div className={`${headerRow} cursor-pointer`} onClick={toggle}>
        <span className="inline-flex items-center gap-2">
          {dragHandle}
          <RenameLabel name={section.name} editable onRename={(n) => ops.rename(section.id, n)} />
        </span>
        <span className="inline-flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
          <button
            type="button"
            aria-label={locked ? 'Unlock section for LLM' : 'Lock section from LLM'}
            title={locked ? 'Locked — LLM leaves this section as typed' : 'LLM may tailor this section'}
            className="px-1.5 py-0.5 text-space-dim hover:text-space-text transition-colors"
            onClick={() => ops.toggleLocked(section.id)}
          >{locked ? '🔒' : '🔓'}</button>
          <VisibleToggle visible={section.visible} onToggle={() => ops.toggleVisible(section.id)} label="section" />
          <button
            type="button" aria-label="Edit section prompt" title="Section prompt"
            className="px-1.5 py-0.5 text-space-dim hover:text-space-text transition-colors"
            onClick={() => setPromptOpen(true)}
          >✉</button>
          {!preset && <RemoveButton onRemove={() => ops.remove(section.id)} label="Remove section" />}
        </span>
      </div>
      {!collapsed && child && (
        <SectionChild child={child} preset={preset} ops={ops} tree={tree} sectionLocked={locked} />
      )}
      {promptOpen && (
        <PromptEditorModal
          node={section} isSection tree={tree}
          onChange={(t) => ops.setPrompt(section.id, t)}
          onClose={() => setPromptOpen(false)}
        />
      )}
    </div>
  )
}
```

- [ ] **Step 4: Rework `SortableEntry`**

Remove `MoveButtons` and the ▸/▾ button; make the header bar body-click toggle collapse; add eye + ✉ controls; add modal state. Replace the `Entry {index + 1}` static label with a `RenameLabel` on `item.name` (double-click rename), falling back to summary when collapsed/empty.

```jsx
function SortableEntry({ item, index, count, ops, tree, sectionLocked }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: item.id })
  const [collapsed, setCollapsed] = useState(true)
  const [promptOpen, setPromptOpen] = useState(false)
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }
  const summary = entrySummary(item)
  const locked = !!item.locked
  const toggle = () => setCollapsed((c) => !c)
  return (
    <div
      ref={setNodeRef} style={style}
      className="border border-space-border/50 rounded-lg p-3 flex flex-col gap-2"
    >
      <div className={`${headerRow} cursor-pointer`} onClick={toggle}>
        <span className="inline-flex items-center gap-2 min-w-0" onClick={(e) => e.stopPropagation()}>
          <button
            type="button" aria-label="Drag to reorder item"
            className="cursor-grab active:cursor-grabbing px-1 text-space-dim hover:text-space-text"
            {...attributes} {...listeners}
          >⋮⋮</button>
          <RenameLabel name={item.name || `Entry ${index + 1}`} editable onRename={(n) => ops.rename(item.id, n)} />
          {collapsed && !item.name && summary && (
            <span className="text-xs text-space-text truncate">— {summary}</span>
          )}
        </span>
        <span className="inline-flex items-center" onClick={(e) => e.stopPropagation()}>
          {!sectionLocked && (
            <button
              type="button"
              aria-label={locked ? 'Unlock item for LLM' : 'Lock item from LLM'}
              title={locked ? 'Locked — LLM leaves this entry as typed' : 'LLM may tailor this entry'}
              className="px-1.5 py-0.5 text-space-dim hover:text-space-text transition-colors"
              onClick={() => ops.toggleLocked(item.id)}
            >{locked ? '🔒' : '🔓'}</button>
          )}
          <VisibleToggle visible={item.visible} onToggle={() => ops.toggleVisible(item.id)} label="item in output" />
          {!sectionLocked && (
            <button
              type="button" aria-label="Edit item prompt" title="Item prompt"
              className="px-1.5 py-0.5 text-space-dim hover:text-space-text transition-colors"
              onClick={() => setPromptOpen(true)}
            >✉</button>
          )}
          <RemoveButton onRemove={() => ops.remove(item.id)} label="Remove item" />
        </span>
      </div>
      {!collapsed && <GroupView group={item} fieldsEditable={false} ops={ops} />}
      {promptOpen && (
        <PromptEditorModal
          node={item} isSection={false} tree={tree}
          onChange={(t) => ops.setPrompt(item.id, t)}
          onClose={() => setPromptOpen(false)}
        />
      )}
    </div>
  )
}
```

Note: `VisibleToggle` with `label="item in output"` produces aria-labels `Hide item in output` / `Show item in output` — the test's case-insensitive regex matches.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd react-dashboard && npm run test -- TreeNode`
Expected: PASS.

- [ ] **Step 6: Run the full frontend suite (regression)**

Run: `cd react-dashboard && npm run test`
Expected: PASS. If any prior test asserted `Move up`/`Expand section`/`Entry 1` labels or the inline `Section prompt`/`Item prompt` textareas, update those assertions to the new modal-based behavior.

- [ ] **Step 7: Commit**

```bash
git add react-dashboard/src/components/widgets/profile-tree/TreeNode.jsx react-dashboard/src/components/widgets/profile-tree/TreeNode.test.jsx
git commit -m "[feat] First-class list items; drag-only reorder; prompt-modal controls"
```

---

### Task 8: Add/remove fields on all preset sections

**Files:**
- Modify: `react-dashboard/src/components/widgets/profile-tree/TreeNode.jsx` (`SectionChild` → `GroupView fieldsEditable`)
- Test: `react-dashboard/src/components/widgets/profile-tree/TreeNode.test.jsx`

**Interfaces:**
- Consumes: existing `GroupView` `fieldsEditable` prop + `AddFieldForm`.
- Produces: preset sections with a `group` child render the add-field form and per-field remove buttons.

- [ ] **Step 1: Write the failing test**

Add to `TreeNode.test.jsx`:

```js
it('preset header section allows adding a field', () => {
  const ops = makeOps()
  const header = {
    type: 'section', id: 'h1', name: 'Header', role: 'header', visible: true, prompt: '',
    children: [{ type: 'group', id: 'g1', name: 'Header', visible: true, children: [
      { type: 'field', id: 'hf1', name: 'Email', key: 'email', kind: 'text', value: '', visible: true },
    ] }],
  }
  const t = { type: 'root', id: 'r', children: [header] }
  render(<SectionView section={header} isFirst isLast ops={ops} tree={t} initialCollapsed={false} />)
  expect(screen.getByText('+ Add field')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd react-dashboard && npm run test -- TreeNode`
Expected: FAIL (preset group passes `fieldsEditable={!preset}` → false → no add-field form).

- [ ] **Step 3: Make preset group children editable**

In `TreeNode.jsx`, change `SectionChild`'s group branch:

```jsx
function SectionChild({ child, preset, ops, tree, sectionLocked }) {
  if (child.type === 'list') return <ListView list={child} ops={ops} tree={tree} sectionLocked={sectionLocked} />
  if (child.type === 'group') return <GroupView group={child} fieldsEditable ops={ops} />
  // bare field child (e.g. summary hero, skills taglist)
  return <FieldView field={child} fieldsEditable={false} ops={ops} />
}
```

(`preset` is now unused by `SectionChild`; leave the prop for call-site stability or drop it — if dropped, also remove it from the `<SectionChild … preset={preset} … />` call in `SectionView`. Keep `isPresetSection` import; it still gates the section Remove button.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd react-dashboard && npm run test -- TreeNode`
Expected: PASS.

- [ ] **Step 5: Run the full frontend suite**

Run: `cd react-dashboard && npm run test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add react-dashboard/src/components/widgets/profile-tree/TreeNode.jsx react-dashboard/src/components/widgets/profile-tree/TreeNode.test.jsx
git commit -m "[feat] Allow add/remove fields on preset sections"
```

---

### Task 9: Docs + full-suite verification

**Files:**
- Modify: `react-dashboard/CONTEXT.md`, `core/CONTEXT.md`
- Modify: `TODO.md` (if it tracks this sub-project's UI gaps)

**Interfaces:** none (documentation).

- [ ] **Step 1: Update `core/CONTEXT.md`**

Document `build_section_prompt` (folded `[Section: … [Item: …]]` format, canonical, mirrored in JS), and that `tree_to_legacy` now omits invisible sections/entries/fields.

- [ ] **Step 2: Update `react-dashboard/CONTEXT.md`**

Document: prompts edited only via `PromptEditorModal` (✉ control); list entries are first-class (eye/lock/message/rename/body-expand, drag-only reorder); chip tray uses per-entry sub-folders; pills are green and drop at the release point; preset sections allow add/remove fields. Note `MoveButtons` is retained in `structuralControls.jsx` but no longer rendered in the tree.

- [ ] **Step 3: Run the entire backend + frontend suites**

Run: `python -m pytest -q`
Expected: PASS.
Run: `cd react-dashboard && npm run test`
Expected: PASS.
Run: `cd react-dashboard && npm run build`
Expected: build succeeds (catches any unused-import/syntax breakage).

- [ ] **Step 4: Commit**

```bash
git add react-dashboard/CONTEXT.md core/CONTEXT.md TODO.md
git commit -m "[docs] Document prompt modal, first-class items, visibility filtering"
```

---

## Manual Verification (deferred to user, after merge-readiness)

Run `start.bat dev` on the branch:
1. Drag a chip and release mid-text → pill lands at the drop point (not the end).
2. Pills render **green**.
3. Open ✉ on Experience → modal shows the editable box + folded preview updating live as you type a section prompt and as you set item prompts.
4. List entry: double-click its name to rename; body-click expands; eye toggles visibility.
5. Hide a job (eye off) → regenerate/inspect a generated résumé → that job is absent.
6. Add a field to the Header section → saves and round-trips (rendering on PDF pending #4).
7. Full save → reload → all prompts/locks/names/visibility intact.

---

## Self-Review Notes

- **Spec coverage:** header add/remove → T8; remove ↑/↓ + ▸/▾ → T7; message-icon prompt modal → T6+T7; entry body-expand → T7; entry first-class (lock/prompt/eye/rename) → T7; entry pills in folder → T4/T5; pills only in modal → T6 (inline removed); item-prompt folding (backend + preview) → T1/T3 + T6; drop-point insert → T5; green pills → T5; visibility round-trip → T2. All covered.
- **Type consistency:** `build_section_prompt` (Py) ↔ `buildFoldedPreview` (JS) share the exact format string. `ops.toggleVisible/rename/setPrompt/toggleLocked` already exist on the bundle (`ProfileTreeEditor.jsx:43-54`); no new ops needed. `entryLabel` (JS) ↔ `_entry_label` (Py) are independent but both name-or-first-value.
