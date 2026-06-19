# Profile Tree-Edit Foundation (2A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the profile tree writable as a tree (GET/PUT endpoints) and make every save path preserve node IDs and tree-only data (the I1 fix), without any dashboard change.

**Architecture:** Add `apply_flat_to_tree` (overlay flat edits onto an existing tree in place, preserving IDs and untouched/custom nodes) and `merge_flat_into_stored` (pick the base tree, overlay, return the dict to store) to `core/profile_tree.py`, replacing the destructive `with_rebuilt_tree`. Rewire `User._to_dict`/`load_from_json` and the flat profile endpoints onto the overlay. Add `GET`/`PUT /api/config/profiles/{id}/tree` plus `validate_tree_limits` for the new tree write path.

**Tech Stack:** Python 3, Pydantic v2, SQLAlchemy, FastAPI, pytest.

## Global Constraints

- Python: type hints, `black` formatting, Google-style docstrings.
- Commit format `[type] Imperative subject`; types `feat|fix|refactor|docs|test|chore`. No Claude/Anthropic attribution, no `Co-Authored-By`.
- Tests under `tests/` (core: `tests/core/`, web: `tests/web/`), `test_*.py`; run with `pytest`.
- The tree is the source of truth; flat doc-section fields are derived via `tree_to_legacy`. Job-search metadata (`target_roles`, `target_salary_min/max`, `resume_path`, `md_path`, `website`) and LLM-config/uploaded-file keys stay as flat `data` keys and must survive round-trips.
- After ANY flat-field write, node IDs and tree-only data (custom `role is None` sections, `regen_lock`, `llm_output`/`llm_input`/`llm_instructions`, `visible`, `bullet_style`) must be preserved.
- Field `value` types by `kind`: `text`/`markdown` → `str`; `bullets`/`taglist` → `list[str]`. Assigning `FieldNode.value` directly does NOT run the model's `before` validator (Pydantic v2 doesn't re-validate on attribute assignment), so values must be coerced to the right Python type before assignment.
- Node IDs are stable hex UUIDs created by `_new_id()` (module-level in `core/profile_tree.py`). New nodes get fresh IDs; existing nodes keep theirs.
- Tree size caps for the PUT endpoint: ≤ 500 nodes, ≤ 6 levels deep. Cap/validation violations → HTTP 422.

## Existing code this plan builds on (in `core/profile_tree.py`)

- Node models `FieldNode` (`id,name,key,order,visible,kind,value,llm_output,llm_instructions,llm_input,regen_lock,min,max`), `GroupNode` (`id,name,order,visible,regen_lock,children`), `ListNode` (`id,name,order,visible,bullet_style,item_template,children`), `SectionNode` (`id,name,role,order,visible,children`), `RootNode` (`id,children`).
- `_new_id() -> str`; `validate_tree(root) -> None` raises `TreeValidationError`; `legacy_to_tree(data) -> RootNode`; `tree_to_legacy(root) -> dict`; `_section_by_role(root, role) -> SectionNode|None`; `_gpa_to_str(v) -> str`; `_gpa_to_float(v) -> float`; `with_rebuilt_tree(data) -> dict` (TO BE REMOVED).
- `tree_to_legacy` role→flat mapping: header group fields keyed `first_name,last_name,email,phone,location,github,linkedin,website`; summary field key `hero`; skills field key `skills` (taglist); experience item fields `company,title,start,end,summary`; education `institution,degree,field,graduated,gpa`; projects `name,description,url,technologies`.

## File Structure

- **Modify** `core/profile_tree.py` — add `_coerce_field_value`, `apply_flat_to_tree`, `merge_flat_into_stored`, `validate_tree_limits`; remove `with_rebuilt_tree`.
- **Modify** `core/user.py` — `_to_dict` overlays onto `self.profile_tree`; `load_from_json` uses `merge_flat_into_stored`; fix imports.
- **Modify** `web/routers/config.py` — `update_profile` + parse-merge use `merge_flat_into_stored`; add `GET`/`PUT /api/config/profiles/{id}/tree`.
- **Test** `tests/core/test_profile_tree.py`, `tests/core/test_user.py`, **Create** `tests/web/test_profile_tree_endpoints.py`.

---

### Task 1: `apply_flat_to_tree` — in-place overlay

**Files:**
- Modify: `core/profile_tree.py`
- Test: `tests/core/test_profile_tree.py`

**Interfaces:**
- Consumes: existing models, `_section_by_role`, `_gpa_to_str`.
- Produces:
  - `_coerce_field_value(kind: str, raw: object) -> str | list[str]` — coerce a raw value to the type required by `kind`.
  - `apply_flat_to_tree(tree: RootNode, flat: dict) -> RootNode` — overlay the flat doc-section fields onto `tree` IN PLACE and return the same `tree`. Scalars (header contact, `hero`, `skills`) matched by `(role, key)`; list sections (`experience`→`work_history`, `education`→`education`, `projects`→`projects`) matched by index (update in place / append cloned-from-`item_template` with fresh IDs / truncate tail). Only keys present in a flat row are written, so tree-only fields and custom sections are left untouched. Education `gpa` is converted via `_gpa_to_str` before assignment.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/core/test_profile_tree.py
def _tree_with_custom_and_lock():
    """A migrated tree plus a custom section and a regen-locked experience item."""
    from core.profile_tree import FieldNode, GroupNode, ListNode, SectionNode, legacy_to_tree

    tree = legacy_to_tree(LEGACY)  # header/summary/experience/education/projects/skills
    # lock the first experience item
    exp = next(s for s in tree.children if s.role == "experience")
    exp.children[0].children[0].regen_lock = True
    # add a custom (role=None) section with a single text field
    tree.children.append(
        SectionNode(
            name="Awards", role=None, order=99,
            children=[GroupNode(name="Awards", children=[
                FieldNode(name="Award", key="award", kind="text", value="Hackathon Winner"),
            ])],
        )
    )
    return tree


def test_apply_flat_overlay_updates_scalar_preserving_id():
    from core.profile_tree import apply_flat_to_tree, _section_by_role, legacy_to_tree

    tree = legacy_to_tree(LEGACY)
    email_field = _section_by_role(tree, "header").children[0].children
    target = next(f for f in email_field if f.key == "email")
    original_id = target.id
    apply_flat_to_tree(tree, {"email": "new@x.com"})
    target = next(f for f in _section_by_role(tree, "header").children[0].children if f.key == "email")
    assert target.value == "new@x.com"
    assert target.id == original_id  # id preserved


def test_apply_flat_overlay_list_update_append_truncate():
    from core.profile_tree import apply_flat_to_tree, _section_by_role, legacy_to_tree

    tree = legacy_to_tree(LEGACY)  # 1 work_history entry
    exp_list = _section_by_role(tree, "experience").children[0]
    first_item_id = exp_list.children[0].id

    # 2 rows: update existing + append one
    apply_flat_to_tree(tree, {"work_history": [
        {"company": "Acme2", "title": "SWE", "start": "2022", "end": "Now", "summary": "Updated."},
        {"company": "NewCo", "title": "Lead", "start": "2024", "end": "Now", "summary": "Led."},
    ]})
    assert len(exp_list.children) == 2
    assert exp_list.children[0].id == first_item_id  # preserved
    vals0 = {f.key: f.value for f in exp_list.children[0].children}
    assert vals0["company"] == "Acme2"

    # back to 0 rows: truncate
    apply_flat_to_tree(tree, {"work_history": []})
    assert len(exp_list.children) == 0


def test_apply_flat_overlay_preserves_custom_section_and_lock():
    from core.profile_tree import apply_flat_to_tree, _section_by_role

    tree = _tree_with_custom_and_lock()
    apply_flat_to_tree(tree, {"skills": ["Rust"], "work_history": [
        {"company": "Acme", "title": "SWE", "start": "2022", "end": "Now", "summary": "x"},
    ]})
    # custom section survived
    awards = next((s for s in tree.children if s.role is None and s.name == "Awards"), None)
    assert awards is not None
    assert awards.children[0].children[0].value == "Hackathon Winner"
    # regen lock survived
    exp = _section_by_role(tree, "experience")
    assert exp.children[0].children[0].regen_lock is True


def test_apply_flat_overlay_education_gpa_coerced_to_str():
    from core.profile_tree import apply_flat_to_tree, _section_by_role, legacy_to_tree

    tree = legacy_to_tree(LEGACY)
    apply_flat_to_tree(tree, {"education": [
        {"institution": "MIT", "degree": "B.S.", "field": "CS", "graduated": "2020", "gpa": 4.0},
    ]})
    item = _section_by_role(tree, "education").children[0].children[0]
    gpa = next(f.value for f in item.children if f.key == "gpa")
    assert gpa == "4.0" and isinstance(gpa, str)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_profile_tree.py -k apply_flat -v`
Expected: FAIL with `ImportError: cannot import name 'apply_flat_to_tree'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to core/profile_tree.py (after _gpa_to_float / before or after tree_to_legacy)

# Role → flat list key for the repeating sections.
_LIST_ROLE_FLATKEY = {
    "experience": "work_history",
    "education": "education",
    "projects": "projects",
}


def _coerce_field_value(kind: str, raw: object) -> "str | list[str]":
    """Coerce a raw value to the Python type a FieldNode of ``kind`` stores.

    Mirrors FieldNode's value normalizer, for use on direct attribute
    assignment (Pydantic v2 does not re-validate on assignment).
    """
    if kind in ("text", "markdown"):
        if isinstance(raw, list):
            return " ".join(str(x) for x in raw)
        return "" if raw is None else str(raw)
    if isinstance(raw, str):
        return [raw] if raw else []
    if raw is None:
        return []
    return [str(x) for x in raw]


def _row_for_role(role: str, row: dict) -> dict:
    """Apply per-role flat-row value conversions (education gpa → str)."""
    if role == "education":
        return {**row, "gpa": _gpa_to_str(row.get("gpa"))}
    return row


def _overlay_group(group: GroupNode, row: dict) -> None:
    """Update a group's field values from ``row``, by key, preserving IDs.

    Only keys present in ``row`` are written; other fields (incl. tree-only
    custom fields) are left untouched.
    """
    for f in group.children:
        if f.key in row:
            f.value = _coerce_field_value(f.kind, row[f.key])


def _new_item_from_template(template: GroupNode, row: dict) -> GroupNode:
    """Clone a list's item_template into a fresh item populated from ``row``."""
    item = template.model_copy(deep=True)
    item.id = _new_id()
    for f in item.children:
        f.id = _new_id()
        if f.key in row:
            f.value = _coerce_field_value(f.kind, row[f.key])
    return item


def apply_flat_to_tree(tree: "RootNode", flat: dict) -> "RootNode":
    """Overlay flat doc-section fields onto an existing tree, in place.

    Scalars (header contact, summary ``hero``, ``skills``) are matched by
    ``(role, key)``; list sections (experience/education/projects) are matched
    by index — existing items updated in place (IDs preserved), extra flat rows
    appended (cloned from item_template with fresh IDs), trailing items removed.
    Only flat keys that are present are written, so custom (``role is None``)
    sections and tree-only fields/attributes survive untouched.

    Args:
        tree: The existing tree to mutate.
        flat: A flat profile dict (subset is fine; absent keys are skipped).

    Returns:
        The same ``tree`` instance, mutated.
    """
    header = _section_by_role(tree, "header")
    if header and header.children and isinstance(header.children[0], GroupNode):
        for f in header.children[0].children:
            if f.key in flat:
                f.value = _coerce_field_value(f.kind, flat[f.key])

    summary = _section_by_role(tree, "summary")
    if summary and summary.children and isinstance(summary.children[0], FieldNode):
        if "hero" in flat:
            summary.children[0].value = _coerce_field_value(summary.children[0].kind, flat["hero"])

    skills = _section_by_role(tree, "skills")
    if skills and skills.children and isinstance(skills.children[0], FieldNode):
        if "skills" in flat:
            skills.children[0].value = _coerce_field_value(skills.children[0].kind, flat["skills"])

    for role, fkey in _LIST_ROLE_FLATKEY.items():
        if fkey not in flat:
            continue
        sect = _section_by_role(tree, role)
        if not sect or not sect.children or not isinstance(sect.children[0], ListNode):
            continue
        lst = sect.children[0]
        rows = [_row_for_role(role, r) for r in (flat.get(fkey) or [])]
        for i, row in enumerate(rows):
            if i < len(lst.children):
                _overlay_group(lst.children[i], row)
            else:
                lst.children.append(_new_item_from_template(lst.item_template, row))
        if len(rows) < len(lst.children):
            del lst.children[len(rows):]

    return tree
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_profile_tree.py -k apply_flat -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add core/profile_tree.py tests/core/test_profile_tree.py
git commit -m "[feat] Add apply_flat_to_tree in-place overlay"
```

---

### Task 2: Consolidate write paths onto the overlay (I1 fix)

**Files:**
- Modify: `core/profile_tree.py` (add `merge_flat_into_stored`; remove `with_rebuilt_tree`)
- Modify: `core/user.py:172` (`_to_dict`), `core/user.py:226` (`load_from_json`), imports at `core/user.py:13-19`
- Modify: `web/routers/config.py` (`update_profile` ~line 696; parse-merge ~line 851; import)
- Test: `tests/core/test_user.py`

**Interfaces:**
- Consumes: `apply_flat_to_tree`, `legacy_to_tree`, `validate_tree`, `RootNode` (Task 1 + existing).
- Produces: `merge_flat_into_stored(existing_data: dict, new_flat: dict) -> dict` — returns the dict to persist: picks the base tree (validate the existing `profile_tree` if present, else `legacy_to_tree` of the merged flat), overlays `new_flat` (minus any client-supplied `profile_tree`), validates, and returns `new_flat` plus a fresh `profile_tree`. Replaces `with_rebuilt_tree` everywhere.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/core/test_user.py
def test_custom_section_and_lock_survive_flat_save(db_session):
    import json as _json
    from core.user import User

    db_session.add(User(name="Matt", data=_json.dumps(SAMPLE_DATA)))
    db_session.commit()
    User.load(db_session)  # migrate + persist a tree

    # Inject a custom section + regen lock directly into the stored tree, as a
    # future builder (2C) would, then mutate a flat field and save().
    row = db_session.query(User).first()
    stored = _json.loads(row.data)
    tree = stored["profile_tree"]
    tree["children"].append({
        "type": "section", "id": "custom1", "name": "Awards", "role": None,
        "order": 99, "visible": True,
        "children": [{
            "type": "group", "id": "g1", "name": "Awards", "order": 0,
            "visible": True, "regen_lock": False,
            "children": [{
                "type": "field", "id": "f1", "name": "Award", "key": "award",
                "order": 0, "visible": True, "kind": "text", "value": "Winner",
                "llm_output": False, "llm_instructions": "", "llm_input": False,
                "regen_lock": False, "min": None, "max": None,
            }],
        }],
    })
    # lock the first experience item's first field
    exp = next(s for s in tree["children"] if s.get("role") == "experience")
    exp["children"][0]["children"][0]["children"][0]["regen_lock"] = True
    row.data = _json.dumps(stored)
    db_session.commit()

    u = User.load(db_session)
    u.skills = ["Rust", "Go"]          # flat mutation
    u.save(db_session)                 # must NOT destroy custom section / lock / ids

    reloaded = db_session.query(User).first()
    out = _json.loads(reloaded.data)
    roles = [s.get("role") for s in out["profile_tree"]["children"]]
    assert None in roles  # custom section survived
    awards = next(s for s in out["profile_tree"]["children"] if s.get("role") is None)
    assert awards["children"][0]["children"][0]["value"] == "Winner"
    assert awards["id"] == "custom1"  # id preserved
    exp2 = next(s for s in out["profile_tree"]["children"] if s.get("role") == "experience")
    assert exp2["children"][0]["children"][0]["children"][0]["regen_lock"] is True
    # flat edit applied
    assert _json.loads(reloaded.data)["skills"] == ["Rust", "Go"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_user.py::test_custom_section_and_lock_survive_flat_save -v`
Expected: FAIL — with the current `with_rebuilt_tree`, the custom section and lock are destroyed and `custom1`/IDs are regenerated.

- [ ] **Step 3: Write minimal implementation**

In `core/profile_tree.py`, replace `with_rebuilt_tree` (lines 282-300) with:

```python
def merge_flat_into_stored(existing_data: dict, new_flat: dict) -> dict:
    """Return the dict to persist: ``new_flat`` plus a tree with flat overlaid.

    Picks the base tree from ``existing_data['profile_tree']`` when present
    (preserving its IDs and tree-only data); otherwise builds one from the
    merged flat via ``legacy_to_tree``. Any ``profile_tree`` inside ``new_flat``
    is ignored (the stored tree is authoritative). The flat doc-section fields
    are overlaid onto the base tree in place.

    Args:
        existing_data: The currently stored profile dict (may have profile_tree).
        new_flat: The new flat profile dict to persist.

    Returns:
        ``new_flat`` (minus any stale profile_tree) plus a fresh ``profile_tree``.
    """
    base = existing_data.get("profile_tree")
    if base:
        tree = RootNode.model_validate(base)
    else:
        tree = legacy_to_tree({**existing_data, **new_flat})
    out = dict(new_flat)
    out.pop("profile_tree", None)
    apply_flat_to_tree(tree, out)
    validate_tree(tree)
    out["profile_tree"] = tree.model_dump(mode="json")
    return out
```

In `core/user.py`, update the import block (lines 13-19) — drop `with_rebuilt_tree`, add `apply_flat_to_tree` and `merge_flat_into_stored`:

```python
from core.profile_tree import (
    RootNode,
    apply_flat_to_tree,
    legacy_to_tree,
    merge_flat_into_stored,
    tree_to_legacy,
    validate_tree,
)
```

Replace `_to_dict` line 172 (`d = with_rebuilt_tree(d)`) with an in-place overlay onto the live tree:

```python
        apply_flat_to_tree(self.profile_tree, d)
        d["profile_tree"] = self.profile_tree.model_dump(mode="json")
```

Replace `load_from_json` line 226 (`data = with_rebuilt_tree(data)`) with:

```python
        data = merge_flat_into_stored({}, data)
```

In `web/routers/config.py`, update the import (the line `from core.profile_tree import with_rebuilt_tree`) to:

```python
from core.profile_tree import merge_flat_into_stored
```

In `update_profile`, replace `row.data = json.dumps(with_rebuilt_tree(data))` with:

```python
    existing = json.loads(row.data) if row.data else {}
    row.data = json.dumps(merge_flat_into_stored(existing, data))
```

In the parse-merge endpoint, replace `row.data = json.dumps(with_rebuilt_tree(merged))` with:

```python
    existing = json.loads(row.data) if row.data else {}
    row.data = json.dumps(merge_flat_into_stored(existing, merged))
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/core/test_user.py::test_custom_section_and_lock_survive_flat_save -v`
Expected: PASS

Run: `pytest tests/core -q`
Expected: PASS (no regressions — existing migration/idempotency/round-trip tests still green)

- [ ] **Step 5: Commit**

```bash
git add core/profile_tree.py core/user.py web/routers/config.py tests/core/test_user.py
git commit -m "[fix] Consolidate write paths onto in-place tree overlay; remove with_rebuilt_tree"
```

---

### Task 3: Tree GET/PUT endpoints + size limits

**Files:**
- Modify: `core/profile_tree.py` (add `validate_tree_limits`)
- Modify: `web/routers/config.py` (add two endpoints + a request body model)
- Create: `tests/web/test_profile_tree_endpoints.py`

**Interfaces:**
- Consumes: `RootNode`, `validate_tree`, `tree_to_legacy`, `merge_flat_into_stored`, `TreeValidationError`, `User`.
- Produces:
  - `validate_tree_limits(root: RootNode, *, max_nodes: int = 500, max_depth: int = 6) -> None` — raises `TreeValidationError` if the tree exceeds the node count or depth caps (root=depth 0; a list's `item_template` counts as a node one level below the list).
  - `GET /api/config/profiles/{id}/tree` → `{"tree": <profile_tree JSON>}` (tenant-guarded; loads/migrates via `User.load`).
  - `PUT /api/config/profiles/{id}/tree` body `{"tree": {...}}` → validates (`model_validate` → `validate_tree_limits` → `validate_tree`), stores tree + derived flat (preserving non-section metadata), returns `{"tree": ...}`. Validation failures → HTTP 422.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_profile_tree_endpoints.py
# Mirrors the fixture pattern in tests/web/test_profile_api.py: a shared
# in-memory db_session, get_db overridden with a lambda, and the dev tenancy
# seam resolving the caller to profile id=1 without any auth setup.
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, get_db
from core.user import User
from web.main import app

SAMPLE = {
    "first_name": "Matt", "last_name": "Barlow", "email": "m@x.com",
    "phone": "555", "location": "Remote", "github": "gh", "linkedin": "li",
    "website": "w", "hero": "Engineer", "skills": ["Python", "SQL"],
    "work_history": [{"company": "Acme", "title": "SWE", "start": "2022",
                      "end": "Now", "summary": "Built."}],
    "education": [{"institution": "Columbia", "degree": "B.S.", "field": "EE",
                   "graduated": "2018", "gpa": 3.5}],
    "projects": [], "target_roles": ["Backend"],
}


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(User(id=1, name="Matt", data=json.dumps(SAMPLE)))
    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_get_tree_returns_sections(client):
    r = client.get("/api/config/profiles/1/tree")
    assert r.status_code == 200
    tree = r.json()["tree"]
    roles = [s["role"] for s in tree["children"]]
    assert roles == ["header", "summary", "experience", "education", "projects", "skills"]


def test_put_tree_preserves_ids_and_custom_section(client):
    tree = client.get("/api/config/profiles/1/tree").json()["tree"]
    header_email = next(f for f in tree["children"][0]["children"][0]["children"]
                        if f["key"] == "email")
    header_email["value"] = "edited@x.com"
    email_id = header_email["id"]
    tree["children"].append({
        "type": "section", "id": "cust-uuid", "name": "Awards", "role": None,
        "order": 50, "visible": True,
        "children": [{"type": "group", "id": "g", "name": "Awards", "order": 0,
                      "visible": True, "regen_lock": False, "children": [
                          {"type": "field", "id": "fa", "name": "Award",
                           "key": "award", "order": 0, "visible": True,
                           "kind": "text", "value": "Winner", "llm_output": False,
                           "llm_instructions": "", "llm_input": False,
                           "regen_lock": False, "min": None, "max": None}]}],
    })
    r = client.put("/api/config/profiles/1/tree", json={"tree": tree})
    assert r.status_code == 200

    got = client.get("/api/config/profiles/1/tree").json()["tree"]
    got_email = next(f for f in got["children"][0]["children"][0]["children"]
                     if f["key"] == "email")
    assert got_email["value"] == "edited@x.com"
    assert got_email["id"] == email_id  # preserved
    assert any(s["id"] == "cust-uuid" for s in got["children"])  # custom section persisted
    # flat profile reflects the role-mapped edit
    flat = client.get("/api/config/profiles/1").json()["data"]
    assert flat["email"] == "edited@x.com"


def test_put_tree_rejects_malformed(client):
    # duplicate ids -> validate_tree failure -> 422
    bad = {"type": "root", "id": "r", "children": [
        {"type": "section", "id": "dup", "name": "A", "role": None, "order": 0,
         "visible": True, "children": [
             {"type": "field", "id": "dup", "name": "x", "key": "x", "order": 0,
              "visible": True, "kind": "text", "value": "", "llm_output": False,
              "llm_instructions": "", "llm_input": False, "regen_lock": False,
              "min": None, "max": None}]}]}
    r = client.put("/api/config/profiles/1/tree", json={"tree": bad})
    assert r.status_code == 422


def test_put_tree_rejects_oversized(client):
    tree = client.get("/api/config/profiles/1/tree").json()["tree"]
    # append > 500 trivial custom sections
    for i in range(600):
        tree["children"].append({
            "type": "section", "id": f"s{i}", "name": f"S{i}", "role": None,
            "order": 1000 + i, "visible": True,
            "children": [{"type": "field", "id": f"f{i}", "name": "x", "key": "x",
                          "order": 0, "visible": True, "kind": "text", "value": "",
                          "llm_output": False, "llm_instructions": "",
                          "llm_input": False, "regen_lock": False,
                          "min": None, "max": None}]})
    r = client.put("/api/config/profiles/1/tree", json={"tree": tree})
    assert r.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/web/test_profile_tree_endpoints.py -v`
Expected: FAIL (404 on the new routes / `validate_tree_limits` ImportError)

- [ ] **Step 3: Write minimal implementation**

Add to `core/profile_tree.py`:

```python
def validate_tree_limits(
    root: "RootNode", *, max_nodes: int = 500, max_depth: int = 6
) -> None:
    """Raise TreeValidationError if the tree is too large or too deep.

    Root is depth 0; a ListNode's item_template counts as a node one level
    below the list. Guards the PUT endpoint against abusive/runaway trees.
    """
    count = 0

    def walk(node: object, depth: int) -> None:
        nonlocal count
        count += 1
        if depth > max_depth:
            raise TreeValidationError(f"Tree exceeds max depth {max_depth}")
        for c in (getattr(node, "children", None) or []):
            walk(c, depth + 1)
        if isinstance(node, ListNode):
            walk(node.item_template, depth + 1)

    walk(root, 0)
    if count > max_nodes:
        raise TreeValidationError(f"Tree exceeds max nodes {max_nodes}")
```

Add to `web/routers/config.py` — import the names and the validation error, define a body model, and add the two endpoints. Place near the other profile endpoints:

```python
from pydantic import BaseModel  # already imported; reuse
from core.profile_tree import (
    RootNode,
    TreeValidationError,
    tree_to_legacy,
    validate_tree,
    validate_tree_limits,
)


class TreeBody(BaseModel):
    tree: dict


@router.get("/api/config/profiles/{profile_id}/tree")
def get_profile_tree(
    profile_id: int,
    db: Session = Depends(get_db),
    caller_id: int = Depends(current_profile_id),
) -> dict[str, Any]:
    if profile_id != caller_id:
        raise HTTPException(status_code=404, detail="Profile not found")
    try:
        user = User.load(db, profile_id=profile_id)
    except RuntimeError:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"tree": user.profile_tree.model_dump(mode="json")}


@router.put("/api/config/profiles/{profile_id}/tree")
def put_profile_tree(
    profile_id: int,
    body: TreeBody,
    db: Session = Depends(get_db),
    caller_id: int = Depends(current_profile_id),
) -> dict[str, Any]:
    if profile_id != caller_id:
        raise HTTPException(status_code=404, detail="Profile not found")
    row = db.query(User).filter_by(id=profile_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    try:
        root = RootNode.model_validate(body.tree)
        validate_tree_limits(root)
        validate_tree(root)
    except (ValueError, TreeValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    existing = json.loads(row.data) if row.data else {}
    derived = tree_to_legacy(root)
    merged = {**existing, **derived, "profile_tree": root.model_dump(mode="json")}
    row.data = json.dumps(merged)
    db.commit()
    return {"tree": root.model_dump(mode="json")}
```

Note: `RootNode.model_validate` raises `pydantic.ValidationError` (a subclass of `ValueError`) on type errors, so the `except (ValueError, TreeValidationError)` catches both malformed JSON shapes and invariant failures.

- [ ] **Step 4: Run tests**

Run: `pytest tests/web/test_profile_tree_endpoints.py -v`
Expected: PASS (4 tests)

Run: `pytest tests/core -q && pytest tests/web -q`
Expected: PASS (no regressions)

- [ ] **Step 5: Update docs + commit**

In `core/CONTEXT.md` → "Profile Schema Engine", update the I1 prerequisite note to reflect that 2A resolved the write-path issue: flat writes now overlay onto the existing tree in place (`apply_flat_to_tree`) preserving IDs and tree-only data, and a tree-aware `GET`/`PUT /api/config/profiles/{id}/tree` exists (consumed by the 2B editor). Note custom sections are still not rendered on documents until #4.

```bash
git add core/profile_tree.py web/routers/config.py tests/web/test_profile_tree_endpoints.py core/CONTEXT.md
git commit -m "[feat] Add profile tree GET/PUT endpoints with size limits"
```

---

## Self-Review

**Spec coverage:**
- Tree API GET/PUT (whole-tree, ID-preserving, validate, derive flat, store both) → Task 3. ✓
- I1 in-place overlay replacing `with_rebuilt_tree` → Tasks 1 & 2. ✓
- Custom sections / tree-only data preserved on flat save → Task 2 test; on tree PUT → Task 3 test. ✓
- Validation + node/depth caps → 422 → Task 3. ✓
- Coexistence: legacy flat `update_profile` retained, now ID-preserving; `_hydrate` unchanged → Task 2. ✓
- Metadata survival (`target_roles`, salary, paths, LLM/upload keys) → `merge_flat_into_stored` keeps `{**existing/new_flat}` and PUT keeps `{**existing, **derived}`; covered by Task 3's flat-reflection assertion and existing core round-trip tests. ✓
- Testing items (I1 regression, overlay value/shape, PUT round-trip, PUT validation, generation consistency) → mapped across Tasks 1-3. ✓

**Intentional deviation from spec wording:** the spec said "remove `with_rebuilt_tree`; `load_from_json` migrates-then-overlays." The plan removes `with_rebuilt_tree` and routes `load_from_json` through `merge_flat_into_stored({}, data)`, which for an empty base builds the tree via `legacy_to_tree` (the correct build-from-scratch semantics for a fresh JSON import) — same net behavior, one helper. Noted in Global Constraints/Task 2.

**Placeholder scan:** none — every step has complete code and exact commands.

**Type consistency:** `apply_flat_to_tree(tree, flat) -> RootNode`, `merge_flat_into_stored(existing, new) -> dict`, `validate_tree_limits(root, *, max_nodes, max_depth)`, `_coerce_field_value(kind, raw)` are referenced consistently. Endpoint paths `/api/config/profiles/{id}/tree` consistent. `TreeBody.tree: dict` matches the `{"tree": ...}` request/response shape used in tests.
