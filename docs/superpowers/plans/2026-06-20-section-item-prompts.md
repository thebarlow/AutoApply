# Section/Item Prompts + Profile Editor Modal — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Model 2 authorable per-section and per-item prompts with chip-based context injection, and rework the profile editor into a roomy modal with pop-out prompt editing.

**Architecture:** Backend adds `locked` + `prompt` fields to `SectionNode` and list-entry `GroupNode`, a `{profile.*}` token resolver, and section-generation that composes section/item prompts under a nested lock gate. Frontend extracts the existing chip-drag prompt editor from `PromptModal` into reusable pieces (`ChipTray` folder tree, `PromptField`, `PopOutEditor`), wires section/item lock toggles + prompt editors into the tree, and hosts the whole editor in a modal opened from the user's name.

**Tech Stack:** Python 3 / Pydantic v2 / FastAPI / pytest (backend); React 18 / Vite / Vitest / RTL / @dnd-kit / Tailwind (frontend).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-06-20-section-item-prompts-design.md`.
- Writability rule (verbatim): a field is LLM-written **iff** `section.locked == False` **and** its list-entry `GroupNode.locked == False` **and** `field.llm_output == True`. Locked nodes are never sent to the LLM; they fall back to stored values (verbatim) automatically because they are absent from the authored map.
- Defaults: sections/items default `locked == False`; fields keep `llm_output == False` default. Empty `prompt` (`""`) is valid.
- Item-lock and item-prompt apply only to **list entries** (groups inside a `ListNode`). A non-list section's structural singleton group gets no lock/prompt UI and is always treated as unlocked.
- Legacy `regen_lock` truthy on a **group** migrates to `locked == True`. `FieldNode.regen_lock` is unchanged and stays.
- Profile-tree token format: `{profile.<section_key>}` (whole section) and `{profile.<section_key>.<field_key>}` (one field). `<section_key>` = section `role` if set else slug(`name`); `<field_key>` = field `key`. Unknown tokens are left as-is (matches `_apply_template`). First match wins on duplicate slugs.
- Dev-only: Model 2 stays behind the admin compare harness; no production wiring; **no remote push / no merge to shared main** (initiative release constraint).
- Commit format `[type] Imperative subject`. No Claude/Anthropic attribution, no `Co-Authored-By`.
- Python: type hints, black, Google-style docstrings. Comments explain *why*.

---

### Task 1: Backend — `locked` + `prompt` on SectionNode & GroupNode, with regen_lock migration

**Files:**
- Modify: `core/profile_tree.py` (`GroupNode` ~56-65, `SectionNode` ~84-93)
- Test: `tests/core/test_profile_tree.py`

**Interfaces:**
- Produces: `SectionNode.locked: bool`, `SectionNode.prompt: str`, `GroupNode.locked: bool`, `GroupNode.prompt: str`. `GroupNode` no longer declares `regen_lock`, but a `model_validator(mode="before")` folds a legacy truthy `regen_lock` into `locked`.

- [ ] **Step 1: Write the failing test**

Add to `tests/core/test_profile_tree.py`:

```python
from core.profile_tree import GroupNode, SectionNode, RootNode, validate_tree


def test_section_and_group_have_lock_and_prompt_defaults():
    s = SectionNode(name="X")
    assert s.locked is False and s.prompt == ""
    g = GroupNode(name="G")
    assert g.locked is False and g.prompt == ""


def test_group_legacy_regen_lock_migrates_to_locked():
    g = GroupNode.model_validate({"type": "group", "name": "G", "regen_lock": True})
    assert g.locked is True


def test_group_explicit_locked_wins_over_legacy_regen_lock():
    g = GroupNode.model_validate(
        {"type": "group", "name": "G", "regen_lock": True, "locked": False}
    )
    assert g.locked is False


def test_tree_with_locks_and_prompts_validates():
    root = RootNode(children=[
        SectionNode(name="S", order=0, locked=True, prompt="Tailor S",
                    children=[GroupNode(name="G", locked=True, prompt="Tailor G")]),
    ])
    validate_tree(root)  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_profile_tree.py -k "lock or prompt" -v`
Expected: FAIL (AttributeError / ValidationError — `locked`/`prompt` unknown).

- [ ] **Step 3: Write minimal implementation**

In `core/profile_tree.py`, update imports to include the validator:

```python
from pydantic import BaseModel, Field, field_validator, model_validator
```

Replace `GroupNode` (lines ~56-65) with:

```python
class GroupNode(BaseModel):
    """A bundle of fields; also serves as a list's item instance/template."""

    type: Literal["group"] = "group"
    id: str = Field(default_factory=_new_id)
    name: str = ""
    order: int = 0
    visible: bool = True
    locked: bool = False
    prompt: str = ""
    children: list[FieldNode] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _migrate_regen_lock(cls, data):
        # Legacy trees stored a group's pin as ``regen_lock``; fold it into the
        # new ``locked`` gate unless ``locked`` is already given explicitly.
        if isinstance(data, dict) and "locked" not in data and data.get("regen_lock"):
            data = {**data, "locked": True}
        return data
```

Replace `SectionNode` (lines ~84-93) with:

```python
class SectionNode(BaseModel):
    """A top-level block. ``role`` ties presets to the legacy adapter."""

    type: Literal["section"] = "section"
    id: str = Field(default_factory=_new_id)
    name: str = ""
    role: Optional[str] = None
    order: int = 0
    visible: bool = True
    locked: bool = False
    prompt: str = ""
    children: list[SectionChild] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/core/test_profile_tree.py -v`
Expected: PASS (new tests + existing tree tests still green).

- [ ] **Step 5: Commit**

```bash
git add core/profile_tree.py tests/core/test_profile_tree.py
git commit -m "[feat] Add locked+prompt to SectionNode/GroupNode with regen_lock migration"
```

---

### Task 2: Backend — `{profile.*}` token resolver

**Files:**
- Modify: `core/profile_tree.py` (append a new function near `tree_to_legacy`)
- Test: `tests/core/test_profile_tree.py`

**Interfaces:**
- Produces: `resolve_profile_tokens(root: RootNode, text: str) -> str`. Substitutes `{profile.<section_key>}` and `{profile.<section_key>.<field_key>}`; leaves unknown tokens untouched.

- [ ] **Step 1: Write the failing test**

Add to `tests/core/test_profile_tree.py`:

```python
from core.profile_tree import (
    FieldNode, GroupNode, ListNode, RootNode, SectionNode, resolve_profile_tokens,
)


def _sample_root():
    return RootNode(children=[
        SectionNode(name="Skills", role="skills", order=0, children=[
            FieldNode(name="Technical", key="skills", kind="taglist",
                      value=["Python", "Go"])]),
        SectionNode(name="My Awards", role=None, order=1, children=[
            GroupNode(name="Awards", children=[
                FieldNode(name="Award", key="award", kind="text", value="Winner")])]),
    ])


def test_resolve_field_token():
    out = resolve_profile_tokens(_sample_root(), "Have: {profile.skills.skills}")
    assert out == "Have: Python, Go"


def test_resolve_section_token_joins_fields():
    out = resolve_profile_tokens(_sample_root(), "{profile.my_awards}")
    assert "Award: Winner" in out


def test_resolve_unknown_token_left_as_is():
    out = resolve_profile_tokens(_sample_root(), "{profile.nope.x} {job.title}")
    assert out == "{profile.nope.x} {job.title}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_profile_tree.py -k resolve -v`
Expected: FAIL (ImportError — `resolve_profile_tokens` undefined).

- [ ] **Step 3: Write minimal implementation**

Append to `core/profile_tree.py`:

```python
def _section_key(section: SectionNode) -> str:
    """Stable injection key for a section: its role, else a slug of its name."""
    if section.role:
        return section.role
    return re.sub(r"[^a-z0-9]+", "_", section.name.lower()).strip("_")


def _field_value_str(field: FieldNode) -> str:
    """Render a field value for prompt injection."""
    if isinstance(field.value, list):
        return ", ".join(str(v) for v in field.value)
    return "" if field.value is None else str(field.value)


def _section_fields(section: SectionNode) -> list[FieldNode]:
    """All FieldNodes anywhere under a section (groups, list entries, bare)."""
    fields: list[FieldNode] = []

    def walk(node: object) -> None:
        if isinstance(node, FieldNode):
            fields.append(node)
            return
        for c in getattr(node, "children", None) or []:
            walk(c)

    for child in section.children:
        walk(child)
    return fields


def resolve_profile_tokens(root: "RootNode", text: str) -> str:
    """Substitute ``{profile.<section>}`` / ``{profile.<section>.<field>}`` tokens.

    ``<section>`` is a section's role or slugified name; ``<field>`` is a field
    key. A section token expands to ``"<name>: <value>"`` lines for that
    section's fields. Unknown sections/fields are left untouched. First section
    matching a key wins.

    Args:
        root: The profile tree.
        text: A prompt string possibly containing profile tokens.

    Returns:
        ``text`` with recognized profile tokens substituted.
    """
    import re

    by_key: dict[str, SectionNode] = {}
    for s in root.children:
        by_key.setdefault(_section_key(s), s)

    def _replace(m: "re.Match[str]") -> str:
        sec_key, field_key = m.group(1), m.group(2)
        sec = by_key.get(sec_key)
        if sec is None:
            return m.group(0)
        if field_key is None:
            lines = [f"{f.name}: {_field_value_str(f)}" for f in _section_fields(sec)]
            return "\n".join(lines)
        for f in _section_fields(sec):
            if f.key == field_key:
                return _field_value_str(f)
        return m.group(0)

    return re.sub(r"\{profile\.(\w+)(?:\.(\w+))?\}", _replace, text)
```

Add `import re` at module top if not already present (it is imported locally in `_apply_template`; add a top-level `import re` after `import uuid` to avoid repeated local imports). Confirm `re` is available to `resolve_profile_tokens`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/core/test_profile_tree.py -k resolve -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/profile_tree.py tests/core/test_profile_tree.py
git commit -m "[feat] Add {profile.*} token resolver to profile tree"
```

---

### Task 3: Backend — section_generator consumes locks + section/item prompts + token resolution

**Files:**
- Modify: `core/section_generator.py`
- Test: `tests/core/test_section_generator.py`

**Interfaces:**
- Consumes: `SectionNode.locked/.prompt`, `GroupNode.locked/.prompt` (Task 1); a `resolve` callable (Task 4 supplies it; defaults to identity here).
- Produces: `generate_resume_by_section(root, job_ctx, client, model, resolve=None)` — new optional `resolve: Callable[[str], str] | None` parameter. A locked section is skipped (no call); a locked list entry is treated as anchors-only (never authored). Section/item prompts are injected into the built prompt, each passed through `resolve`.

- [ ] **Step 1: Write the failing test**

Add to `tests/core/test_section_generator.py` (create if absent; follow the existing stub pattern — patch `core.job._llm_json_with_retry` or the module's local import). Use this self-contained approach that stubs the retry helper:

```python
import json
import core.section_generator as sg
from core.profile_tree import FieldNode, GroupNode, ListNode, RootNode, SectionNode
from core.section_generator import SectionOutput, generate_resume_by_section


def _capture_stub(captured):
    def _stub(prompt, client, model, schema, **kw):
        captured.append(prompt)
        # Echo every requested field key as "TAILORED".
        return SectionOutput(fields={}, entries={})
    return _stub


def test_locked_section_is_skipped(monkeypatch):
    captured = []
    monkeypatch.setattr(sg, "_llm_json_with_retry", _capture_stub(captured), raising=False)
    # Patch the local import target too:
    import core.job
    monkeypatch.setattr(core.job, "_llm_json_with_retry", _capture_stub(captured))
    root = RootNode(children=[
        SectionNode(name="Sum", order=0, locked=True, children=[
            FieldNode(name="Hero", key="hero", kind="markdown", value="x", llm_output=True)]),
    ])
    out = generate_resume_by_section(root, "JOB", object(), "m")
    assert out == {}
    assert captured == []  # no call for a locked section


def test_section_and_item_prompts_appear_in_prompt(monkeypatch):
    captured = []
    import core.job
    monkeypatch.setattr(core.job, "_llm_json_with_retry", _capture_stub(captured))
    root = RootNode(children=[
        SectionNode(name="Exp", order=0, prompt="SECTION_GUIDE", children=[
            ListNode(name="Exp", item_template=GroupNode(children=[
                FieldNode(name="Bul", key="bul", kind="markdown", value="", llm_output=True)]),
                children=[GroupNode(name="E", prompt="ITEM_GUIDE", children=[
                    FieldNode(name="Bul", key="bul", kind="markdown", value="", llm_output=True)])])]),
    ])
    generate_resume_by_section(root, "JOB", object(), "m", resolve=lambda s: s.replace("GUIDE", "G!"))
    assert len(captured) == 1
    assert "SECTION_G!" in captured[0]
    assert "ITEM_G!" in captured[0]


def test_locked_item_not_authored(monkeypatch):
    def _stub(prompt, client, model, schema, **kw):
        # Author both entries if asked; gating must prevent the locked one.
        return SectionOutput(entries={"keep": {"bul": "NEW"}, "lock": {"bul": "NEW"}})
    import core.job
    monkeypatch.setattr(core.job, "_llm_json_with_retry", _stub)
    tmpl = GroupNode(children=[FieldNode(name="Bul", key="bul", kind="markdown", llm_output=True)])
    keep = GroupNode(id="keep", name="E", children=[
        FieldNode(id="kf", name="Bul", key="bul", kind="markdown", value="", llm_output=True)])
    lock = GroupNode(id="lock", name="E", locked=True, children=[
        FieldNode(id="lf", name="Bul", key="bul", kind="markdown", value="", llm_output=True)])
    root = RootNode(children=[SectionNode(name="Exp", order=0, children=[
        ListNode(name="Exp", item_template=tmpl, children=[keep, lock])])])
    out = generate_resume_by_section(root, "JOB", object(), "m")
    assert out == {"kf": "NEW"}  # locked entry's field never authored
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_section_generator.py -v`
Expected: FAIL (`resolve` kwarg unknown / section prompt not in prompt / locked gating absent).

- [ ] **Step 3: Write minimal implementation**

In `core/section_generator.py`:

Add to imports:

```python
from collections.abc import Callable
```

Change the list-entry filter and the scalar prompt builders to honor `locked`. Replace `_build_scalar_prompt` and `_build_list_prompt` and add prompt-prefix handling:

```python
def _build_scalar_prompt(section: SectionNode, group: GroupNode, job_ctx: str) -> str:
    """Prompt for a section whose child is a single group (or bare field wrapped)."""
    ctx = "\n".join(_group_context(group)) or "(none)"
    specs = "\n".join(_outputable_specs(group))
    guide = f"{section.prompt}\n\n" if section.prompt else ""
    return (
        f"{guide}You are tailoring the résumé section '{section.name}' to a job.\n\n"
        f"JOB:\n{job_ctx}\n\n"
        f"EXISTING SECTION DATA (anchors — do not change these):\n{ctx}\n\n"
        f"Write tailored content for these fields:\n{specs}\n\n"
        'Return JSON: {"fields": {"<field_key>": "<value>"}} containing exactly '
        "the field keys above."
    )


def _build_list_prompt(section: SectionNode, lst: ListNode, job_ctx: str) -> str:
    """Prompt for a repeating-list section (one call authors every unlocked entry)."""
    blocks = []
    for entry in lst.children:
        ctx = "\n".join(_group_context(entry)) or "(none)"
        if entry.locked:
            blocks.append(f'ENTRY id="{entry.id}" (FIXED — do not rewrite):\n{ctx}')
            continue
        specs = "\n".join(_outputable_specs(entry))
        item_guide = f"guidance: {entry.prompt}\n" if entry.prompt else ""
        blocks.append(
            f'ENTRY id="{entry.id}":\n{item_guide}anchors:\n{ctx}\nwrite:\n{specs}'
        )
    body = "\n\n".join(blocks)
    guide = f"{section.prompt}\n\n" if section.prompt else ""
    return (
        f"{guide}You are tailoring the résumé section '{section.name}' to a job. Each "
        f"entry is a separate item; write its fields using its own anchors.\n\n"
        f"JOB:\n{job_ctx}\n\n{body}\n\n"
        'Return JSON: {"entries": {"<entry_id>": {"<field_key>": "<value>"}}} '
        "with an object for every entry id above that is not FIXED."
    )
```

Rewrite `generate_resume_by_section`:

```python
def generate_resume_by_section(
    root: RootNode,
    job_ctx: str,
    client: Any,
    model: str,
    resolve: "Callable[[str], str] | None" = None,
) -> dict[str, Value]:
    """Author every writable field across visible, unlocked sections.

    Makes one LLM call per unlocked section that has writable fields. ``resolve``,
    when given, is applied to each built prompt to substitute ``{job.*}`` /
    ``{profile.*}`` tokens that the user injected into section/item prompts. A
    locked section is skipped entirely; a locked list entry is passed as fixed
    context and never authored. Failed sections contribute nothing.

    Args:
        root: The profile tree.
        job_ctx: Job context markdown (extracted description).
        client: OpenAI-compatible client.
        model: Model identifier.
        resolve: Optional token-substitution callable applied to each prompt.

    Returns:
        ``field_node_id -> authored value`` for every authored field.
    """
    from core.job import _llm_json_with_retry  # local import avoids a cycle

    apply = resolve or (lambda s: s)
    out: dict[str, Value] = {}
    for section in root.children:
        if not section.visible or section.locked:
            continue
        child = _section_child(section)
        if isinstance(child, ListNode):
            entries_with_work = [
                e for e in child.children
                if not e.locked and any(_outputable(f) for f in e.children)
            ]
            if not entries_with_work:
                continue
            prompt = _build_list_prompt(section, child, job_ctx)
        elif isinstance(child, GroupNode):
            if child.locked or not any(_outputable(f) for f in child.children):
                continue
            prompt = _build_scalar_prompt(section, child, job_ctx)
        elif isinstance(child, FieldNode):
            if not _outputable(child):
                continue
            prompt = _build_scalar_prompt(
                section, GroupNode(name=section.name, children=[child]), job_ctx
            )
        else:
            continue

        try:
            result = _llm_json_with_retry(
                apply(prompt), client, model, SectionOutput, max_tokens=8192,
                empty_msg=f"Section '{section.name}' generation returned empty content.",
            )
        except Exception:
            continue

        if isinstance(child, ListNode):
            by_id = {e.id: e for e in child.children if not e.locked}
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/core/test_section_generator.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/section_generator.py tests/core/test_section_generator.py
git commit -m "[feat] section_generator: lock gating + section/item prompts + token resolve"
```

---

### Task 4: Backend — wire resolver into the Model 2 compare path

**Files:**
- Modify: `web/routers/dev.py` (`_model2_markdown` ~39-44)
- Test: `tests/web/test_resume_compare.py`

**Interfaces:**
- Consumes: `resolve_profile_tokens` (Task 2), `generate_resume_by_section(..., resolve=)` (Task 3), `_apply_template` from `core.job`.
- Produces: Model 2 now resolves `{job.*}` and `{profile.*}` tokens inside section/item prompts before generation.

- [ ] **Step 1: Write the failing test**

Add to `tests/web/test_resume_compare.py` a unit test of the resolver wiring (follow existing fixtures there for `job`/`user`; if the suite already stubs generation, assert the composed resolver substitutes both namespaces). Minimal standalone resolver test:

```python
from core.job import _apply_template
from core.profile_tree import RootNode, SectionNode, FieldNode, resolve_profile_tokens


def test_combined_resolver_substitutes_job_and_profile():
    root = RootNode(children=[SectionNode(name="Skills", role="skills", order=0,
        children=[FieldNode(name="T", key="skills", kind="taglist", value=["Python"])])])

    class _Job:
        title = "Engineer"

    def resolve(text):
        text = resolve_profile_tokens(root, text)
        return _apply_template(text, {"job": _Job()})

    assert resolve("{job.title} knows {profile.skills.skills}") == "Engineer knows Python"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/web/test_resume_compare.py -k combined_resolver -v`
Expected: FAIL (test new) — then PASS once imports resolve; the real change is in `dev.py` below. (This test guards the resolver contract `dev.py` relies on.)

- [ ] **Step 3: Write minimal implementation**

In `web/routers/dev.py`, update imports:

```python
from core.job import Job, _apply_template, _llm_json_with_retry
from core.profile_tree import resolve_profile_tokens
```

Replace `_model2_markdown` (lines ~39-44):

```python
def _model2_markdown(job: Job, user: Any, client: Any, model: str, db: Session) -> str:
    """Model 2 (per-section) résumé Markdown via the schema-driven generator.

    Section/item prompts may inject ``{job.*}`` and ``{profile.*}`` tokens; both
    are resolved against this job and the live profile tree before each call.
    """
    root = user.profile_tree_root()
    prompt = job.build_resume_prompt(user, "{job.extracted_description}", db)

    def resolve(text: str) -> str:
        text = resolve_profile_tokens(root, text)
        return _apply_template(text, {"job": job})

    authored = generate_resume_by_section(root, prompt, client, model, resolve=resolve)
    return render_tree_markdown(root, authored)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/web/test_resume_compare.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/routers/dev.py tests/web/test_resume_compare.py
git commit -m "[feat] Resolve {job.*}/{profile.*} in Model 2 section prompts"
```

---

### Task 5: Frontend — treeOps for section/item lock + prompt

**Files:**
- Modify: `react-dashboard/src/components/widgets/profile-tree/treeOps.js`
- Test: `react-dashboard/src/components/widgets/profile-tree/treeOps.test.js`

**Interfaces:**
- Produces: `toggleLocked(tree, id)` (flips `locked` on a section or group), `setNodePrompt(tree, id, text)` (sets `prompt` on a section or group), `isLocked(node)`.

- [ ] **Step 1: Write the failing test**

Add to `treeOps.test.js`:

```js
import { toggleLocked, setNodePrompt, isLocked } from './treeOps'

const tree = () => ({
  type: 'root', id: 'r', children: [{
    type: 'section', id: 's', name: 'S', role: null, order: 0, visible: true,
    locked: false, prompt: '', children: [{
      type: 'group', id: 'g', name: 'G', order: 0, visible: true,
      locked: false, prompt: '', children: [] }],
  }],
})

describe('toggleLocked / setNodePrompt', () => {
  it('toggles locked on a section', () => {
    const t = toggleLocked(tree(), 's')
    expect(t.children[0].locked).toBe(true)
  })
  it('toggles locked on a group', () => {
    const t = toggleLocked(tree(), 'g')
    expect(t.children[0].children[0].locked).toBe(true)
  })
  it('sets a section prompt without mutating input', () => {
    const orig = tree()
    const t = setNodePrompt(orig, 's', 'Tailor it')
    expect(t.children[0].prompt).toBe('Tailor it')
    expect(orig.children[0].prompt).toBe('')
  })
  it('isLocked reads the flag', () => {
    expect(isLocked({ locked: true })).toBe(true)
    expect(isLocked({})).toBe(false)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd react-dashboard && npx vitest run src/components/widgets/profile-tree/treeOps.test.js`
Expected: FAIL (functions undefined).

- [ ] **Step 3: Write minimal implementation**

Append to `treeOps.js`:

```js
// Whether a node (section or group) forbids LLM writes to its subtree.
export const isLocked = (node) => !!node.locked

// Flip the `locked` gate on a section or list-entry group by id.
export function toggleLocked(tree, id) {
  return updateNode(tree, id, (n) => ({ ...n, locked: !n.locked }))
}

// Set the authoring prompt on a section or list-entry group by id.
export function setNodePrompt(tree, id, text) {
  return updateNode(tree, id, (n) => ({ ...n, prompt: text }))
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd react-dashboard && npx vitest run src/components/widgets/profile-tree/treeOps.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/widgets/profile-tree/treeOps.js react-dashboard/src/components/widgets/profile-tree/treeOps.test.js
git commit -m "[feat] treeOps: toggleLocked + setNodePrompt for sections/items"
```

---

### Task 6: Frontend — shared PromptField (ChipTray folder tree + caret-insert + PopOutEditor)

**Files:**
- Create: `react-dashboard/src/components/widgets/profile-tree/PromptField.jsx`
- Create: `react-dashboard/src/components/widgets/profile-tree/PromptField.test.jsx`

**Interfaces:**
- Consumes: `_section_key` semantics (mirror the backend: token = `{profile.<role|slug(name)>.<field.key>}` and section token `{profile.<key>}`).
- Produces:
  - `buildChipGroups(tree) -> Array<{label, chips: Array<{label, token}>}>` — a `Job` group plus one group per section (a section-level chip + one chip per field).
  - `ChipTray({ groups, onInsert })` — collapsible folders; each chip draggable (`dataTransfer text/plain = token`) and clickable (`onInsert(token)`).
  - `PromptField({ value, onChange, tree, ariaLabel, placeholder, rows })` — textarea with drop-to-insert-at-caret, a chip tray, and a pop-out button.
  - `PopOutEditor({ value, onChange, tree, title, onClose })` — centered modal: big textarea + chip tray.

- [ ] **Step 1: Write the failing test**

Create `PromptField.test.jsx`:

```jsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { buildChipGroups, ChipTray, PromptField } from './PromptField'

const tree = {
  type: 'root', id: 'r', children: [{
    type: 'section', id: 's', name: 'My Skills', role: null, order: 0, visible: true,
    children: [{ type: 'group', id: 'g', name: 'G', order: 0, visible: true, children: [
      { type: 'field', id: 'f', name: 'Tech', key: 'tech', order: 0, visible: true,
        kind: 'taglist', value: ['Python'] }] }],
  }],
}

describe('buildChipGroups', () => {
  it('has a Job group and a per-section group with field tokens', () => {
    const groups = buildChipGroups(tree)
    const job = groups.find((g) => g.label === 'Job')
    expect(job.chips.some((c) => c.token === '{job.description}')).toBe(true)
    const sec = groups.find((g) => g.label === 'My Skills')
    expect(sec.chips.some((c) => c.token === '{profile.my_skills}')).toBe(true)
    expect(sec.chips.some((c) => c.token === '{profile.my_skills.tech}')).toBe(true)
  })
})

describe('ChipTray', () => {
  it('inserts a chip token on click after expanding its folder', () => {
    const onInsert = vi.fn()
    render(<ChipTray groups={buildChipGroups(tree)} onInsert={onInsert} />)
    fireEvent.click(screen.getByText('Job')) // expand folder
    fireEvent.click(screen.getByText('description'))
    expect(onInsert).toHaveBeenCalledWith('{job.description}')
  })
})

describe('PromptField', () => {
  it('appends an inserted token to the value', () => {
    const onChange = vi.fn()
    render(<PromptField value="hi " onChange={onChange} tree={tree} ariaLabel="Section prompt" />)
    fireEvent.click(screen.getByText('Job'))
    fireEvent.click(screen.getByText('title'))
    expect(onChange).toHaveBeenCalledWith('hi {job.title}')
  })

  it('opens and closes the pop-out editor', () => {
    render(<PromptField value="x" onChange={vi.fn()} tree={tree} ariaLabel="Section prompt" />)
    fireEvent.click(screen.getByLabelText('Expand editor'))
    expect(screen.getByLabelText('Section prompt (expanded)')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Close editor'))
    expect(screen.queryByLabelText('Section prompt (expanded)')).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd react-dashboard && npx vitest run src/components/widgets/profile-tree/PromptField.test.jsx`
Expected: FAIL (module missing).

- [ ] **Step 3: Write minimal implementation**

Create `PromptField.jsx`:

```jsx
import { useState, useRef, useCallback } from 'react'

const JOB_CHIPS = [
  { label: 'title', token: '{job.title}' },
  { label: 'company', token: '{job.company}' },
  { label: 'location', token: '{job.location}' },
  { label: 'salary', token: '{job.salary}' },
  { label: 'description', token: '{job.description}' },
  { label: 'processed description', token: '{job.extracted_description}' },
]

const slug = (s) => String(s || '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
const sectionKey = (section) => section.role || slug(section.name)

function sectionFields(section) {
  const out = []
  const walk = (n) => {
    if (n.type === 'field') { out.push(n); return }
    for (const c of n.children || []) walk(c)
  }
  for (const c of section.children || []) walk(c)
  return out
}

// A Job group plus one folder per profile section (section-level chip + a chip
// per field). Mirrors the backend token scheme in resolve_profile_tokens.
export function buildChipGroups(tree) {
  const groups = [{ label: 'Job', chips: JOB_CHIPS }]
  for (const section of tree?.children || []) {
    const key = sectionKey(section)
    const chips = [{ label: `(whole section)`, token: `{profile.${key}}` }]
    for (const f of sectionFields(section)) {
      chips.push({ label: f.name || f.key, token: `{profile.${key}.${f.key}}` })
    }
    groups.push({ label: section.name || key, chips })
  }
  return groups
}

function ChipFolder({ group, onInsert }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="flex flex-col">
      <button
        type="button"
        className="text-left text-xs font-semibold text-space-dim hover:text-space-text"
        onClick={() => setOpen((o) => !o)}
      >{open ? '▾' : '▸'} {group.label}</button>
      {open && (
        <div className="flex flex-wrap gap-1.5 pl-3 py-1">
          {group.chips.map((c) => (
            <button
              key={c.token}
              type="button"
              draggable
              onDragStart={(e) => e.dataTransfer.setData('text/plain', c.token)}
              onClick={() => onInsert(c.token)}
              className="px-2 py-0.5 rounded-full border border-purple-500/40 bg-purple-500/10 text-xs text-purple-300 cursor-grab active:cursor-grabbing select-none"
            >{c.label}</button>
          ))}
        </div>
      )}
    </div>
  )
}

export function ChipTray({ groups, onInsert }) {
  return (
    <div className="flex flex-col gap-1 border border-space-border rounded-lg p-2">
      {groups.map((g) => (
        <ChipFolder key={g.label} group={g} onInsert={onInsert} />
      ))}
    </div>
  )
}

// Insert `token` at the textarea's caret (or end), returning the new string.
function insertAtCaret(ref, value, token) {
  const ta = ref.current
  const offset = ta && ta.selectionStart != null ? ta.selectionStart : value.length
  const next = value.slice(0, offset) + token + value.slice(offset)
  if (ta) {
    requestAnimationFrame(() => {
      ta.focus()
      ta.setSelectionRange(offset + token.length, offset + token.length)
    })
  }
  return next
}

export function PromptField({ value, onChange, tree, ariaLabel, placeholder, rows = 3 }) {
  const ref = useRef(null)
  const [popOut, setPopOut] = useState(false)
  const groups = buildChipGroups(tree)

  const insert = useCallback((token) => {
    onChange(insertAtCaret(ref, value ?? '', token))
  }, [value, onChange])

  const onDrop = (e) => {
    e.preventDefault()
    const token = e.dataTransfer.getData('text/plain')
    if (token) insert(token)
  }

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-start gap-1.5">
        <textarea
          ref={ref} aria-label={ariaLabel} rows={rows} placeholder={placeholder}
          value={value ?? ''}
          className="flex-1 bg-white/5 border border-space-border rounded px-2 py-1 text-sm text-space-text resize-y"
          onChange={(e) => onChange(e.target.value)}
          onDrop={onDrop} onDragOver={(e) => e.preventDefault()}
        />
        <button
          type="button" aria-label="Expand editor" title="Pop out"
          className="px-1.5 py-0.5 text-space-dim hover:text-space-text"
          onClick={() => setPopOut(true)}
        >⤢</button>
      </div>
      <ChipTray groups={groups} onInsert={insert} />
      {popOut && (
        <PopOutEditor
          value={value} onChange={onChange} tree={tree}
          title={ariaLabel} onClose={() => setPopOut(false)}
        />
      )}
    </div>
  )
}

export function PopOutEditor({ value, onChange, tree, title, onClose }) {
  const ref = useRef(null)
  const groups = buildChipGroups(tree)
  const insert = (token) => onChange(insertAtCaret(ref, value ?? '', token))
  const onDrop = (e) => {
    e.preventDefault()
    const token = e.dataTransfer.getData('text/plain')
    if (token) insert(token)
  }
  return (
    <div className="fixed inset-0 z-[160] flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="bg-[#0f0f1a] border border-space-border rounded-2xl p-5 w-[48rem] max-w-[92vw] flex flex-col gap-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-space-text">{title}</h2>
          <button
            type="button" aria-label="Close editor" onClick={onClose}
            className="text-space-dim hover:text-space-text text-xl leading-none"
          >×</button>
        </div>
        <textarea
          ref={ref} aria-label={`${title} (expanded)`} rows={16} value={value ?? ''}
          className="bg-white/5 border border-space-border rounded px-3 py-2 text-sm text-space-text resize-y"
          onChange={(e) => onChange(e.target.value)}
          onDrop={onDrop} onDragOver={(e) => e.preventDefault()}
        />
        <ChipTray groups={groups} onInsert={insert} />
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd react-dashboard && npx vitest run src/components/widgets/profile-tree/PromptField.test.jsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/widgets/profile-tree/PromptField.jsx react-dashboard/src/components/widgets/profile-tree/PromptField.test.jsx
git commit -m "[feat] Shared PromptField: folder ChipTray + caret-insert + pop-out"
```

---

### Task 7: Frontend — wire section/item lock toggles + prompt editors into TreeNode

**Files:**
- Modify: `react-dashboard/src/components/widgets/profile-tree/TreeNode.jsx`
- Modify: `react-dashboard/src/components/widgets/profile-tree/ProfileTreeEditor.jsx` (ops + pass `tree` down)
- Test: `react-dashboard/src/components/widgets/profile-tree/TreeNode.test.jsx`

**Interfaces:**
- Consumes: `PromptField` (Task 6); `toggleLocked`/`setNodePrompt` (Task 5); `LlmWriteToggle` (existing).
- Produces: `SectionView` and `SortableEntry` accept `tree` (chip source) and use `ops.toggleLocked(id)` / `ops.setPrompt(id, text)`. A section shows a lock toggle and, when unlocked, a section `PromptField`. A list entry shows a lock toggle and, when the section and entry are unlocked, an item `PromptField`.

- [ ] **Step 1: Write the failing test**

Add to `TreeNode.test.jsx` (extend `noopOps` with `toggleLocked`, `setPrompt`; pass `tree` prop = a root wrapping the section):

```jsx
import { buildChipGroups } from './PromptField' // ensures module wired

function rootOf(section) {
  return { type: 'root', id: 'r', children: [section] }
}

it('shows a section lock toggle and a prompt editor when unlocked', () => {
  const ops = noopOps()
  render(<SectionView section={customSection} isFirst isLast={false} ops={ops} tree={rootOf(customSection)} />)
  // section unlocked by default → lock offers to lock, prompt editor present
  expect(screen.getByLabelText('Lock section from LLM')).toBeInTheDocument()
  expect(screen.getByLabelText('Section prompt')).toBeInTheDocument()
})

it('hides the section prompt editor when the section is locked', () => {
  const locked = { ...customSection, locked: true }
  render(<SectionView section={locked} isFirst isLast={false} ops={noopOps()} tree={rootOf(locked)} />)
  expect(screen.queryByLabelText('Section prompt')).toBeNull()
  expect(screen.getByLabelText('Unlock section for LLM')).toBeInTheDocument()
})

it('toggles section lock by id', () => {
  const ops = noopOps()
  render(<SectionView section={customSection} isFirst isLast={false} ops={ops} tree={rootOf(customSection)} />)
  fireEvent.click(screen.getByLabelText('Lock section from LLM'))
  expect(ops.toggleLocked).toHaveBeenCalledWith('sec-c')
})

it('shows an item lock + item prompt on a list entry when unlocked', () => {
  const ops = noopOps()
  render(<SectionView section={presetListSection} isFirst={false} isLast ops={ops} tree={rootOf(presetListSection)} />)
  fireEvent.click(screen.getByLabelText('Expand section'))
  expect(screen.getByLabelText('Lock item from LLM')).toBeInTheDocument()
  expect(screen.getByLabelText('Item prompt')).toBeInTheDocument()
})
```

Update `noopOps` to include: `toggleLocked: vi.fn(), setPrompt: vi.fn(),`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd react-dashboard && npx vitest run src/components/widgets/profile-tree/TreeNode.test.jsx`
Expected: FAIL (controls absent, `tree` unused).

- [ ] **Step 3: Write minimal implementation**

In `TreeNode.jsx`:

Add import:

```jsx
import { PromptField } from './PromptField'
```

Add a section lock control next to the visibility toggle. In `SectionView`, change the signature to accept `tree`, and add the lock + prompt UI. Replace the right-side action span and the body in `SectionView`:

```jsx
export function SectionView({ section, isFirst, isLast, ops, dragHandle, tree, initialCollapsed = true }) {
  const preset = isPresetSection(section)
  const child = section.children[0]
  const [collapsed, setCollapsed] = useState(initialCollapsed)
  const toggle = () => setCollapsed((c) => !c)
  const locked = !!section.locked
  return (
    <div className={`border border-space-border rounded-xl p-4 flex flex-col gap-3 ${section.visible ? '' : 'opacity-60'}`}>
      <div className={`${headerRow} cursor-pointer`} onClick={toggle}>
        <span className="inline-flex items-center gap-2">
          {dragHandle}
          <button
            type="button"
            aria-label={collapsed ? 'Expand section' : 'Collapse section'}
            className="px-1 text-space-dim hover:text-space-text transition-colors"
            onClick={(e) => { e.stopPropagation(); toggle() }}
          >{collapsed ? '▸' : '▾'}</button>
          <RenameLabel name={section.name} editable onRename={(n) => ops.rename(section.id, n)} />
        </span>
        <span className="inline-flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
          <MoveButtons
            canUp={!isFirst} canDown={!isLast}
            onUp={() => ops.move(section.id, -1)} onDown={() => ops.move(section.id, 1)}
          />
          <button
            type="button"
            aria-label={locked ? 'Unlock section for LLM' : 'Lock section from LLM'}
            title={locked ? 'Locked — LLM leaves this section as typed' : 'LLM may tailor this section'}
            className="px-1.5 py-0.5 text-space-dim hover:text-space-text transition-colors"
            onClick={() => ops.toggleLocked(section.id)}
          >{locked ? '🔒' : '🔓'}</button>
          <VisibleToggle visible={section.visible} onToggle={() => ops.toggleVisible(section.id)} label="section" />
          {!preset && <RemoveButton onRemove={() => ops.remove(section.id)} label="Remove section" />}
        </span>
      </div>
      {!collapsed && !locked && (
        <PromptField
          ariaLabel="Section prompt" placeholder="How should the LLM tailor this whole section?"
          value={section.prompt || ''} tree={tree}
          onChange={(t) => ops.setPrompt(section.id, t)}
        />
      )}
      {!collapsed && child && (
        <SectionChild child={child} preset={preset} ops={ops} tree={tree} sectionLocked={locked} />
      )}
    </div>
  )
}
```

Thread `tree` and `sectionLocked` through `SectionChild` and `ListView` to `SortableEntry`:

```jsx
function SectionChild({ child, preset, ops, tree, sectionLocked }) {
  if (child.type === 'list') return <ListView list={child} ops={ops} tree={tree} sectionLocked={sectionLocked} />
  if (child.type === 'group') return <GroupView group={child} fieldsEditable={!preset} ops={ops} />
  return <FieldView field={child} fieldsEditable={false} ops={ops} />
}
```

```jsx
function ListView({ list, ops, tree, sectionLocked }) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )
  const handleDragEnd = ({ active, over }) => {
    if (over && active.id !== over.id) ops.reorder(active.id, over.id)
  }
  return (
    <div className="flex flex-col gap-4">
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={list.children.map((i) => i.id)} strategy={verticalListSortingStrategy}>
          {list.children.map((item, i) => (
            <SortableEntry
              key={item.id} item={item} index={i} count={list.children.length} ops={ops}
              tree={tree} sectionLocked={sectionLocked}
            />
          ))}
        </SortableContext>
      </DndContext>
      <AddButton label="+ Add entry" onClick={() => ops.addItem(list.id)} />
    </div>
  )
}
```

In `SortableEntry`, add the item lock toggle and item prompt. Add `tree, sectionLocked` to its props, compute `locked`, and add controls into the action span and below the header:

```jsx
function SortableEntry({ item, index, count, ops, tree, sectionLocked }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: item.id })
  const [collapsed, setCollapsed] = useState(true)
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }
  const summary = entrySummary(item)
  const locked = !!item.locked
  return (
    <div
      ref={setNodeRef} style={style}
      className="border border-space-border/50 rounded-lg p-3 flex flex-col gap-2"
    >
      <div className={headerRow}>
        <span className="inline-flex items-center gap-2 min-w-0">
          <button
            type="button" aria-label="Drag to reorder item"
            className="cursor-grab active:cursor-grabbing px-1 text-space-dim hover:text-space-text"
            {...attributes} {...listeners}
          >⋮⋮</button>
          <button
            type="button"
            aria-label={collapsed ? 'Expand item' : 'Collapse item'}
            className="px-1 text-space-dim hover:text-space-text transition-colors"
            onClick={() => setCollapsed((c) => !c)}
          >{collapsed ? '▸' : '▾'}</button>
          <span className="text-xs text-space-dim shrink-0">Entry {index + 1}</span>
          {collapsed && summary && (
            <span className="text-xs text-space-text truncate">— {summary}</span>
          )}
        </span>
        <span className="inline-flex items-center">
          <MoveButtons
            canUp={index > 0} canDown={index < count - 1}
            onUp={() => ops.move(item.id, -1)} onDown={() => ops.move(item.id, 1)}
          />
          {!sectionLocked && (
            <button
              type="button"
              aria-label={locked ? 'Unlock item for LLM' : 'Lock item from LLM'}
              title={locked ? 'Locked — LLM leaves this entry as typed' : 'LLM may tailor this entry'}
              className="px-1.5 py-0.5 text-space-dim hover:text-space-text transition-colors"
              onClick={() => ops.toggleLocked(item.id)}
            >{locked ? '🔒' : '🔓'}</button>
          )}
          <RemoveButton onRemove={() => ops.remove(item.id)} label="Remove item" />
        </span>
      </div>
      {!collapsed && !sectionLocked && !locked && (
        <PromptField
          ariaLabel="Item prompt" placeholder="How should the LLM tailor this entry?"
          value={item.prompt || ''} tree={tree}
          onChange={(t) => ops.setPrompt(item.id, t)}
        />
      )}
      {!collapsed && <GroupView group={item} fieldsEditable={false} ops={ops} />}
    </div>
  )
}
```

In `ProfileTreeEditor.jsx`: import the new ops and pass `tree` to sections. Update the import block:

```jsx
import {
  updateNode, removeNode, moveNode, addField, addListItem, addSection, reorderSiblings,
  setLlmInstructions, toggleLlmWritten, deepEqual, toggleLocked, setNodePrompt,
} from './treeOps'
```

Add to the `ops` object:

```jsx
    toggleLocked: useCallback((id) => setTree((t) => toggleLocked(t, id)), []),
    setPrompt: useCallback((id, text) => setTree((t) => setNodePrompt(t, id, text)), []),
```

Pass `tree` into `SortableSection` and on to `SectionView`. Update the map call:

```jsx
            <SortableSection
              key={section.id} section={section} tree={tree}
              isFirst={i === 0} isLast={i === sections.length - 1} ops={ops}
              initialCollapsed={section.id !== expandSectionId}
            />
```

And `SortableSection`:

```jsx
function SortableSection({ section, isFirst, isLast, ops, initialCollapsed, tree }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: section.id })
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }
  const handle = (
    <button
      type="button" aria-label="Drag to reorder section"
      className="cursor-grab active:cursor-grabbing px-1 text-space-dim hover:text-space-text"
      onClick={(e) => e.stopPropagation()}
      {...attributes} {...listeners}
    >⋮⋮</button>
  )
  return (
    <div ref={setNodeRef} style={style}>
      <SectionView
        section={section} isFirst={isFirst} isLast={isLast} ops={ops}
        dragHandle={handle} initialCollapsed={initialCollapsed} tree={tree}
      />
    </div>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd react-dashboard && npx vitest run src/components/widgets/profile-tree/TreeNode.test.jsx src/components/widgets/profile-tree/ProfileTreeEditor.test.jsx`
Expected: PASS (existing ProfileTreeEditor tests still green — the new `tree` prop is additive).

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/widgets/profile-tree/TreeNode.jsx react-dashboard/src/components/widgets/profile-tree/ProfileTreeEditor.jsx react-dashboard/src/components/widgets/profile-tree/TreeNode.test.jsx
git commit -m "[feat] Section/item lock toggles + prompt editors in the tree"
```

---

### Task 8: Frontend — pop-out for long-text field values

**Files:**
- Modify: `react-dashboard/src/components/widgets/profile-tree/fieldWidgets.jsx` (`MarkdownField`)
- Test: `react-dashboard/src/components/widgets/profile-tree/fieldWidgets.test.jsx`

**Interfaces:**
- Consumes: `PopOutEditor` (Task 6) — used without a chip tray for plain values by passing `tree={null}` (chip groups still render only the Job group; acceptable) OR a no-chip variant. To keep values chip-free, render `PopOutEditor` with `tree={{ children: [] }}` so only the Job folder shows; that's still useful context for a value? No — values are not prompts. Use a minimal inline expand modal instead (below) to avoid chips on values.

- [ ] **Step 1: Write the failing test**

Add to `fieldWidgets.test.jsx`:

```jsx
import { MarkdownField } from './fieldWidgets'

describe('MarkdownField pop-out', () => {
  it('expands to a large editor and edits there', () => {
    const onChange = vi.fn()
    render(<MarkdownField value="hello" onChange={onChange} />)
    fireEvent.click(screen.getByLabelText('Expand field editor'))
    const big = screen.getByLabelText('Expanded field editor')
    fireEvent.change(big, { target: { value: 'hello world' } })
    expect(onChange).toHaveBeenLastCalledWith('hello world')
    fireEvent.click(screen.getByLabelText('Close field editor'))
    expect(screen.queryByLabelText('Expanded field editor')).toBeNull()
  })
})
```

Ensure the test file imports `fireEvent`/`screen`/`render`/`describe`/`it`/`expect`/`vi` as the rest of the file does.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd react-dashboard && npx vitest run src/components/widgets/profile-tree/fieldWidgets.test.jsx`
Expected: FAIL (no expand button).

- [ ] **Step 3: Write minimal implementation**

In `fieldWidgets.jsx`, add `useState` is already imported. Replace `MarkdownField`:

```jsx
export function MarkdownField({ value, onChange }) {
  const [popOut, setPopOut] = useState(false)
  return (
    <div className="flex items-start gap-1.5">
      <textarea
        className={`${inputClass} min-h-[80px] resize-y`} value={value ?? ''}
        onChange={(e) => onChange(e.target.value)}
      />
      <button
        type="button" aria-label="Expand field editor" title="Pop out"
        className="px-1.5 py-0.5 text-space-dim hover:text-space-text"
        onClick={() => setPopOut(true)}
      >⤢</button>
      {popOut && (
        <div className="fixed inset-0 z-[160] flex items-center justify-center bg-black/60" onClick={() => setPopOut(false)}>
          <div
            className="bg-[#0f0f1a] border border-space-border rounded-2xl p-5 w-[48rem] max-w-[92vw] flex flex-col gap-3"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-end">
              <button
                type="button" aria-label="Close field editor" onClick={() => setPopOut(false)}
                className="text-space-dim hover:text-space-text text-xl leading-none"
              >×</button>
            </div>
            <textarea
              aria-label="Expanded field editor" rows={16} value={value ?? ''}
              className="bg-white/5 border border-space-border rounded px-3 py-2 text-sm text-space-text resize-y"
              onChange={(e) => onChange(e.target.value)}
            />
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd react-dashboard && npx vitest run src/components/widgets/profile-tree/fieldWidgets.test.jsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/widgets/profile-tree/fieldWidgets.jsx react-dashboard/src/components/widgets/profile-tree/fieldWidgets.test.jsx
git commit -m "[feat] Pop-out editor for markdown field values"
```

---

### Task 9: Frontend — host the profile editor in a modal opened from the user's name

**Files:**
- Modify: `react-dashboard/src/components/widgets/Settings.jsx` (UserHome wiring ~1357-1377)
- Create: `react-dashboard/src/components/widgets/ProfileEditorModal.jsx`
- Test: `react-dashboard/src/components/widgets/ProfileEditorModal.test.jsx`

**Interfaces:**
- Consumes: `ProfileDetailView` (existing default export of `ProfileDetail.jsx`).
- Produces: `ProfileEditorModal({ children, onClose })` — a large centered overlay. Settings renders it when a profile is selected from the user name, instead of swapping to the cramped `profileDetail` view.

- [ ] **Step 1: Write the failing test**

Create `ProfileEditorModal.test.jsx`:

```jsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ProfileEditorModal from './ProfileEditorModal'

describe('ProfileEditorModal', () => {
  it('renders children and closes on the close button and backdrop', () => {
    const onClose = vi.fn()
    render(<ProfileEditorModal onClose={onClose}><p>inside</p></ProfileEditorModal>)
    expect(screen.getByText('inside')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Close profile editor'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd react-dashboard && npx vitest run src/components/widgets/ProfileEditorModal.test.jsx`
Expected: FAIL (module missing).

- [ ] **Step 3: Write minimal implementation**

Create `ProfileEditorModal.jsx`:

```jsx
import { useEffect } from 'react'

// Large centered overlay that hosts the full profile editor. Replaces the
// narrow pushed "profileDetail" view so the section tree has room to breathe.
export default function ProfileEditorModal({ children, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-[120] flex items-start justify-center bg-black/60 p-6 overflow-y-auto" onClick={onClose}>
      <div
        className="bg-[#0f0f1a] border border-space-border rounded-2xl w-[60rem] max-w-[95vw] my-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-space-border">
          <span className="text-xs font-semibold uppercase tracking-widest text-space-dim">Edit Profile</span>
          <button
            type="button" aria-label="Close profile editor" onClick={onClose}
            className="text-space-dim hover:text-space-text text-xl leading-none"
          >×</button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  )
}
```

In `Settings.jsx`: import the modal at top with the other widget imports:

```jsx
import ProfileEditorModal from './ProfileEditorModal'
```

Change the `UserHome` `onSelect` to open the modal rather than swap views, and replace the `profileDetail` view block with a modal render. Update the `onSelect` handler (line ~1359):

```jsx
                onSelect={(id) => { setDetailProfileId(id); setView('main') }}
```

Remove the `{view === 'profileDetail' && ...}` block (lines ~1375-1377) and instead render the modal after the `<AnimatePresence>` content `</div>` (still inside the panel root, sibling to the content div ~line 1380):

```jsx
      {detailProfileId != null && (
        <ProfileEditorModal onClose={() => setDetailProfileId(null)}>
          <ProfileDetailView
            profileId={detailProfileId}
            onDelete={() => setDetailProfileId(null)}
          />
        </ProfileEditorModal>
      )}
```

Note: `ProfileDetailView` is imported in `Settings.jsx` as `ProfileDetailView` (line 7). Confirm `detailProfileId` state already exists in `Settings.jsx`; if `view`/`setView` no longer references `'profileDetail'` anywhere else, leave the other view states untouched.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd react-dashboard && npx vitest run src/components/widgets/ProfileEditorModal.test.jsx`
Then the full frontend suite: `cd react-dashboard && npx vitest run`
Expected: PASS (all suites green).

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/widgets/ProfileEditorModal.jsx react-dashboard/src/components/widgets/ProfileEditorModal.test.jsx react-dashboard/src/components/widgets/Settings.jsx
git commit -m "[feat] Host profile editor in a modal opened from the user name"
```

---

### Task 10: Docs — update CONTEXT.md notes

**Files:**
- Modify: `react-dashboard/CONTEXT.md` (profile-tree section)
- Modify: `core/CONTEXT.md` (section_generator + profile_tree notes)

**Interfaces:** none (documentation only).

- [ ] **Step 1: Update `react-dashboard/CONTEXT.md`**

In the profile-tree area, add bullets:
- `PromptField.jsx` — shared prompt editor: folder `ChipTray` (Job + per-section/field tokens), drag/click-to-insert at caret, `PopOutEditor` modal. Used by section + item prompt editors.
- Section/item lock icons (🔒/🔓) gate LLM authoring (`locked`); section/item prompt editors appear when unlocked. Field lock/eye unchanged.
- Profile editor now opens in `ProfileEditorModal` from the user's name (was the narrow pushed view).

- [ ] **Step 2: Update `core/CONTEXT.md`**

Add:
- `profile_tree.resolve_profile_tokens(root, text)` resolves `{profile.<section>.<field>}` / `{profile.<section>}`; section key = role or slug(name).
- `section_generator.generate_resume_by_section(..., resolve=)` skips locked sections/items, injects section/item `prompt`, and applies `resolve` to each prompt. `dev.py` composes `resolve_profile_tokens` + `_apply_template({job})`.
- `SectionNode`/`GroupNode` gained `locked` + `prompt`; group `regen_lock` migrates to `locked`.

- [ ] **Step 3: Commit**

```bash
git add react-dashboard/CONTEXT.md core/CONTEXT.md
git commit -m "[docs] Note section/item prompts, locks, and editor modal"
```

---

## Self-Review

**Spec coverage:**
- Data model (section/item `locked`+`prompt`, migration, writability) → Task 1, gating in Task 3. ✅
- `{profile.*}` resolver → Task 2; wired Task 4. ✅
- section_generator composing section+item prompts under locks → Task 3. ✅
- Chip folder tray + caret insert + pop-out → Task 6. ✅
- Section/item lock toggles + prompt editors → Task 7. ✅
- Pop-out on long-text values → Task 8. ✅
- Editor modal from user name → Task 9. ✅
- Defaults / verbatim-via-absence / dev-only / no-push → Global Constraints + Tasks 1,3. ✅

**Placeholder scan:** none — every code step contains full code.

**Type/name consistency:** `toggleLocked`/`setNodePrompt` (Task 5) used by `ops.toggleLocked`/`ops.setPrompt` (Task 7). `buildChipGroups`/`ChipTray`/`PromptField`/`PopOutEditor` (Task 6) consumed in Tasks 7. `generate_resume_by_section(..., resolve=)` (Task 3) called in Task 4. `resolve_profile_tokens` (Task 2) used in Task 4. `ProfileDetailView` default export consumed in Task 9. Consistent.

**Open risk carried from spec:** section slug keys can orphan tokens on rename (documented; switch to node-id keys only if it bites). First-match-wins on duplicate slugs.
