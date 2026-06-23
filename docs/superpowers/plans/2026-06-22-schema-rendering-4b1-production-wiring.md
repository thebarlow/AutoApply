# 4B-1 Tree-v1 Production Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make production résumé generation, storage, render, PDF, and refinement use the 4A document-tree path (stored under `schema:"tree-v1"`), so user-defined sections appear on generated résumés, while existing legacy `documents` rows keep rendering unchanged.

**Architecture:** A new `documents.structured_json` discriminator (`schema:"tree-v1"`) selects the document-tree path vs. the legacy `ResumeDocument` path at every load site. Generation runs `core.section_generator` → `core.document_tree.build_resume_document_tree` → serialized tree; rendering runs `core.tree_assembler.assemble_resume_tree_markdown` with **no YAML frontmatter** (contact/education are ordinary body sections). PDF rendering is already `meta`-driven, so a tree-v1 `_render_meta` returning `{}` disables the legacy education-injection automatically; presentation is finished with CSS. Interim refinement re-runs the per-section generator for all `llm_output` sections (per-section scoring is 4B-2).

**Tech Stack:** Python 3, Pydantic v2 (`RootNode` already serializes), pytest, pandoc + Jinja2 + Chromium (Playwright) for PDF.

## Global Constraints

- **Local `main` only** — do NOT push `main`; this is part of the unfinished #4–#6/#5 swap.
- **Legacy rows render identically** — any `documents` row with no `schema` key (or an unknown value) MUST render through the existing `ResumeDocument` path (`assemble_resume_markdown` + frontmatter) byte-for-byte as before.
- **Cover letters untouched** — `CoverDocument` paths are not modified; covers never gain a `schema` key.
- **Tree order is authoritative** — never canonically reorder sections.
- **No deletions** — `ResumeGeneration`, `core.document_builder.build_resume_document`/`apply_resume_patch`, and `core/tree_render.py` stay (legacy refine + tracked carry-forward). Removing `tree_render.py` is a separate approval.
- **Discriminator value** — the exact string is `"tree-v1"`; the top-level JSON key is `"schema"`.
- **Snapshot safety** — a stored tree-v1 document renders without reading the live profile (the tree IS the snapshot), mirroring today's `_render_meta` guarantee.

---

### Task 1: Schema discriminator + document-tree (de)serialization

**Files:**
- Create: `core/resume_document_io.py`
- Test: `tests/core/test_resume_document_io.py`

**Interfaces:**
- Consumes: `core.profile_tree.RootNode` (Pydantic model: `.model_dump_json()`, `RootNode.model_validate(dict)`).
- Produces:
  - `SCHEMA_TREE_V1: str = "tree-v1"`
  - `serialize_document_tree(root: RootNode) -> str` — JSON string of the tree with a top-level `"schema": "tree-v1"` key added.
  - `resolve_schema(raw: str) -> str | None` — returns the `"schema"` value, or `None` if absent/unparseable.
  - `is_tree_v1(raw: str) -> bool` — `resolve_schema(raw) == SCHEMA_TREE_V1`.
  - `deserialize_document_tree(raw: str) -> RootNode` — parse a tree-v1 JSON string back to a `RootNode` (ignores the `"schema"` key).

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_resume_document_io.py
import json

from core.profile_tree import FieldNode, GroupNode, RootNode, SectionNode
from core.resume_document_io import (
    SCHEMA_TREE_V1,
    deserialize_document_tree,
    is_tree_v1,
    resolve_schema,
    serialize_document_tree,
)


def _tree() -> RootNode:
    return RootNode(children=[
        SectionNode(name="Header", role="header", order=0, children=[
            GroupNode(name="Contact", children=[
                FieldNode(name="Email", key="email", kind="text", value="a@b.co"),
            ]),
        ]),
    ])


def test_serialize_injects_schema_key():
    raw = serialize_document_tree(_tree())
    assert json.loads(raw)["schema"] == SCHEMA_TREE_V1


def test_resolve_schema_reads_value():
    assert resolve_schema(serialize_document_tree(_tree())) == "tree-v1"


def test_resolve_schema_absent_is_none():
    assert resolve_schema('{"type": "root", "children": []}') is None


def test_resolve_schema_unparseable_is_none():
    assert resolve_schema("not json") is None


def test_is_tree_v1():
    assert is_tree_v1(serialize_document_tree(_tree())) is True
    assert is_tree_v1('{"type":"root","children":[]}') is False


def test_roundtrip_preserves_tree():
    root = _tree()
    back = deserialize_document_tree(serialize_document_tree(root))
    assert back.model_dump() == root.model_dump()


def test_roundtrip_preserves_locked_and_custom_section():
    root = RootNode(children=[
        SectionNode(name="Patents", order=0, locked=True, children=[
            GroupNode(name="g", children=[
                FieldNode(name="Title", key="title", kind="text", value="X"),
            ]),
        ]),
    ])
    back = deserialize_document_tree(serialize_document_tree(root))
    assert back.model_dump() == root.model_dump()
    assert back.children[0].locked is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_resume_document_io.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.resume_document_io'`

- [ ] **Step 3: Write minimal implementation**

```python
# core/resume_document_io.py
"""Serialize/deserialize a résumé *document tree* with a schema discriminator.

The ``documents.structured_json`` column stores either a legacy ``ResumeDocument``
(no ``schema`` key) or a tree-v1 document tree (a ``RootNode`` JSON with a
top-level ``"schema": "tree-v1"`` key). Every read path uses ``resolve_schema`` /
``is_tree_v1`` to branch. Pure module — no DB, no LLM, no filesystem.
"""
from __future__ import annotations

import json

from core.profile_tree import RootNode

SCHEMA_TREE_V1 = "tree-v1"


def serialize_document_tree(root: RootNode) -> str:
    """JSON for a document tree, with the ``schema`` discriminator added."""
    data = json.loads(root.model_dump_json())
    data["schema"] = SCHEMA_TREE_V1
    return json.dumps(data)


def resolve_schema(raw: str) -> str | None:
    """The stored ``schema`` value, or ``None`` if absent/unparseable."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    value = data.get("schema")
    return value if isinstance(value, str) else None


def is_tree_v1(raw: str) -> bool:
    """True iff ``raw`` is a tree-v1 document tree."""
    return resolve_schema(raw) == SCHEMA_TREE_V1


def deserialize_document_tree(raw: str) -> RootNode:
    """Parse a tree-v1 JSON string back into a ``RootNode`` (ignores ``schema``)."""
    data = json.loads(raw)
    data.pop("schema", None)
    return RootNode.model_validate(data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_resume_document_io.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add core/resume_document_io.py tests/core/test_resume_document_io.py
git commit -m "[feat] Add tree-v1 schema discriminator + document-tree (de)serialization"
```

---

### Task 2: Contact-section presentation renderer (name as H1, ordered contact line)

The 4A `_header_section_md` renders the contact section as `## Header` + `**First Name:** …`
lines — fine for a generic section, wrong for a résumé header. Rewrite it so the default
tree-v1 résumé shows the name as a top-level H1 and the remaining contact fields as one
ATS-ordered text line (email, phone, location, then links). Icon-grid styling is deferred to
sub-project #6; the plain text line is more ATS-robust.

**Files:**
- Modify: `core/tree_assembler.py:86-99` (`_header_section_md`)
- Test: `tests/core/test_tree_assembler_presets.py` (update the existing header golden)

**Interfaces:**
- Consumes: `SectionNode` whose single child is a `GroupNode` of contact `FieldNode`s keyed
  `first_name,last_name,email,phone,location,github,linkedin,website` (see
  `core/section_presets.py:11-34`).
- Produces: `_header_section_md(section) -> str` emitting `# <First Last>` then a blank line
  then a ` · `-joined contact line of the non-empty non-name fields in tree order; links
  (`github`/`linkedin`/`website`) render as `[display](value)` with `display` = value minus
  scheme/`www.`. Returns `""` if the group is empty.

- [ ] **Step 1: Write the failing test**

First inspect the current header golden in `tests/core/test_tree_assembler_presets.py` and
replace the header-section expectation with the block below (keep the other preset tests).

```python
# in tests/core/test_tree_assembler_presets.py
from core.profile_tree import FieldNode, GroupNode, RootNode, SectionNode
from core.tree_assembler import assemble_resume_tree_markdown, _header_section_md


def _header(**vals) -> SectionNode:
    keys = [
        ("first_name", "First Name"), ("last_name", "Last Name"),
        ("email", "Email"), ("phone", "Phone"), ("location", "Location"),
        ("github", "GitHub"), ("linkedin", "LinkedIn"), ("website", "Website"),
    ]
    fields = [
        FieldNode(name=label, key=key, kind="text", order=i, value=vals.get(key, ""))
        for i, (key, label) in enumerate(keys)
    ]
    return SectionNode(name="Header", role="header", order=0,
                       children=[GroupNode(name="Contact", children=fields)])


def test_header_name_is_h1_and_contacts_one_line():
    section = _header(
        first_name="Jane", last_name="Doe", email="jane@x.co",
        phone="555-1212", location="Brooklyn, NY",
        github="https://github.com/jane",
    )
    md = _header_section_md(section)
    assert md == (
        "# Jane Doe\n\n"
        "jane@x.co · 555-1212 · Brooklyn, NY · [github.com/jane](https://github.com/jane)"
    )


def test_header_empty_group_returns_blank():
    assert _header_section_md(_header()) == "# "  # name-only H1 collapses; see impl


def test_header_skips_blank_fields_preserves_order():
    section = _header(first_name="A", last_name="B", email="a@b.co",
                      website="https://www.site.com/")
    md = _header_section_md(section)
    assert md == "# A B\n\na@b.co · [site.com](https://www.site.com/)"
```

Note: `test_header_empty_group_returns_blank` is a placeholder asserting the empty behavior;
finalize it in Step 3 to match the implementation (an all-empty header returns `""`). Write
the impl so an all-empty group returns `""`, then set this test to
`assert _header_section_md(_header()) == ""`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_tree_assembler_presets.py -v`
Expected: FAIL (header golden mismatch — old output was `## Header` + bold lines)

- [ ] **Step 3: Write minimal implementation**

Replace `_header_section_md` in `core/tree_assembler.py`:

```python
def _strip_url(url: str) -> str:
    """Display form of a URL: scheme and leading www. removed, trailing / dropped."""
    return (
        url.replace("https://www.", "").replace("http://www.", "")
        .replace("https://", "").replace("http://", "").rstrip("/")
    )


_HEADER_LINK_KEYS = {"github", "linkedin", "website"}


def _header_section_md(section: SectionNode) -> str:
    """Résumé header: name as H1, remaining contact fields as one ordered line.

    Name comes from ``first_name``/``last_name`` (joined). Remaining non-empty
    fields render in tree order as a ` · `-joined line; link-kind fields render as
    Markdown links with a scheme-stripped display. ATS-load-bearing order
    (email, phone, location, …) follows the tree's field order.
    """
    child = section.children[0] if section.children else None
    if not isinstance(child, GroupNode):
        return ""

    by_key = {f.key: f for f in child.children}

    def _val(f: FieldNode) -> str:
        v = f.value if isinstance(f.value, str) else ", ".join(str(x) for x in f.value)
        return v.strip()

    first = _val(by_key["first_name"]) if "first_name" in by_key else ""
    last = _val(by_key["last_name"]) if "last_name" in by_key else ""
    name = f"{first} {last}".strip()

    parts: list[str] = []
    for f in child.children:
        if f.key in ("first_name", "last_name"):
            continue
        val = _val(f)
        if not val:
            continue
        if f.key in _HEADER_LINK_KEYS:
            parts.append(f"[{_strip_url(val)}]({val})")
        else:
            parts.append(val)

    if not name and not parts:
        return ""
    lines = []
    if name:
        lines.append(f"# {name}")
    if parts:
        lines.append(" · ".join(parts))
    return "\n\n".join(lines)
```

Then set `test_header_empty_group_returns_blank` to `assert _header_section_md(_header()) == ""`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_tree_assembler_presets.py tests/core/test_tree_render_e2e.py -v`
Expected: PASS (update the e2e golden in `test_tree_render_e2e.py` if it pinned the old
header output; re-run until green).

- [ ] **Step 5: Commit**

```bash
git add core/tree_assembler.py tests/core/test_tree_assembler_presets.py tests/core/test_tree_render_e2e.py
git commit -m "[feat] Render tree-v1 résumé header as H1 name + ordered contact line"
```

---

### Task 3: `write_resume_markdown` + `_render_meta` branch on document type

`write_resume_markdown(doc)` currently always prepends frontmatter and uses
`assemble_resume_markdown`. Make it dispatch: a `RootNode` (tree-v1) writes **no frontmatter**
via `assemble_resume_tree_markdown`; a `ResumeDocument` keeps today's behavior. `_render_meta`
returns `{}` for a tree-v1 stored row (contact/education live in the body), so `render_pdf`'s
education-injection becomes a no-op.

**Files:**
- Modify: `core/job.py:922-932` (`write_resume_markdown`), `core/job.py:1191-1204` (`_render_meta`)
- Test: `tests/core/test_job_tree_render.py` (create)

**Interfaces:**
- Consumes: `core.resume_document_io.is_tree_v1`/`deserialize_document_tree`,
  `core.tree_assembler.assemble_resume_tree_markdown`, `core.profile_tree.RootNode`.
- Produces: `write_resume_markdown(self, doc: "ResumeDocument | RootNode") -> None` — writes
  `{job_key}_resume.md`; tree input → no frontmatter. `_render_meta("resume", db)` returns
  `{}` when the stored row is tree-v1.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_job_tree_render.py
from pathlib import Path

from core.job import Job, _OUTPUTS_DIR
from core.profile_tree import FieldNode, GroupNode, RootNode, SectionNode


def _tree() -> RootNode:
    return RootNode(children=[
        SectionNode(name="Header", role="header", order=0, children=[
            GroupNode(name="Contact", children=[
                FieldNode(name="First Name", key="first_name", kind="text", value="Jane"),
                FieldNode(name="Last Name", key="last_name", kind="text", value="Doe"),
                FieldNode(name="Email", key="email", kind="text", value="j@x.co"),
            ]),
        ]),
        SectionNode(name="Patents", order=1, children=[
            GroupNode(name="g", children=[
                FieldNode(name="Detail", key="detail", kind="markdown", value="A patent."),
            ]),
        ]),
    ])


def test_write_resume_markdown_tree_has_no_frontmatter(tmp_path, monkeypatch):
    job = Job(job_key="jk1", title="t", company="c")
    job.write_resume_markdown(_tree())
    md = (_OUTPUTS_DIR / "jk1_resume.md").read_text(encoding="utf-8")
    assert not md.startswith("---")        # no YAML frontmatter
    assert "# Jane Doe" in md
    assert "## Patents" in md              # custom section reaches the .md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_job_tree_render.py -v`
Expected: FAIL (current `write_resume_markdown` calls `assemble_resume_markdown(doc)` which
rejects a `RootNode`, and prepends frontmatter)

- [ ] **Step 3: Write minimal implementation**

In `core/job.py`, add imports near the other core imports (top of file):

```python
from core.tree_assembler import assemble_resume_tree_markdown
from core.resume_document_io import is_tree_v1, deserialize_document_tree
from core.profile_tree import RootNode
```

Replace `write_resume_markdown`:

```python
    def write_resume_markdown(self, doc: "ResumeDocument | RootNode") -> None:
        """Write the derived résumé .md.

        A document tree (tree-v1) is rendered by the generic tree assembler with
        NO front matter — contact and education are ordinary body sections. A
        legacy ``ResumeDocument`` keeps the front matter + fixed assembler path.
        """
        _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        md_path = _OUTPUTS_DIR / f"{self.job_key}_resume.md"
        if isinstance(doc, RootNode):
            md_path.write_text(assemble_resume_tree_markdown(doc), encoding="utf-8")
            return
        frontmatter = self._build_frontmatter_from_header(doc.header, doc.education)
        body = assemble_resume_markdown(doc)
        md_path.write_text(frontmatter + body, encoding="utf-8")
```

Replace `_render_meta` so a tree-v1 row yields empty meta:

```python
    def _render_meta(self, doc_type: str, db: Session) -> dict:
        """Render meta from the stored document snapshot, falling back to profile.

        For a tree-v1 résumé row there is no front-matter channel — contact and
        education render from the body — so meta is empty.
        """
        from core.user import User
        row = Document.fetch(db, self.job_key, doc_type, profile_id=self.profile_id)
        if row is not None:
            if doc_type == "resume" and is_tree_v1(row.structured_json):
                return {}
            model = ResumeDocument if doc_type == "resume" else CoverDocument
            stored = model.model_validate_json(row.structured_json)
            education = getattr(stored, "education", [])
            return self._meta_from_header(stored.header, education)
        return self._frontmatter_data(User.load(db), db)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_job_tree_render.py tests/core/test_job.py -v`
Expected: PASS (the existing `test_job.py` legacy résumé tests still pass)

- [ ] **Step 5: Commit**

```bash
git add core/job.py tests/core/test_job_tree_render.py
git commit -m "[feat] Branch write_resume_markdown/_render_meta on tree-v1 documents"
```

---

### Task 4: `generate_resume_md` produces and stores a tree-v1 document

Switch production résumé generation to the document-tree path: per-section generation →
`build_resume_document_tree` → store under `schema:"tree-v1"` → write the tree markdown.

**Files:**
- Modify: `core/job.py:858-889` (`generate_resume_md`)
- Test: `tests/core/test_job_generate_tree.py` (create)

**Interfaces:**
- Consumes: `user.profile_tree_root() -> RootNode`, `job.build_resume_prompt(user, template, db)`,
  `core.section_generator.generate_resume_by_section`, `core.profile_tree.resolve_profile_tokens`,
  `core.job._apply_template`, `core.document_tree.build_resume_document_tree`,
  `core.resume_document_io.serialize_document_tree`, `Document.upsert`.
- Produces: `generate_resume_md(self, user, prompt_content, client, model, db) -> None` —
  unchanged signature; writes a `documents` row whose `structured_json` is tree-v1 and a
  `{job_key}_resume.md` with no frontmatter.

The existing `_model2_markdown` in `web/routers/dev.py:41-56` is the reference for the
generation sequence (root, prompt, `resolve` closure, `generate_resume_by_section`,
`build_resume_document_tree`).

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_job_generate_tree.py
import json

from core.job import Job, _OUTPUTS_DIR
from core.resume_document_io import is_tree_v1
from db.database import Document


def test_generate_resume_md_writes_tree_v1(db_session, seeded_user, monkeypatch):
    """generate_resume_md stores a tree-v1 row and a frontmatter-free .md."""
    import core.section_generator as sg

    # Stub per-section generation: author the summary field deterministically.
    def fake_generate(root, job_ctx, client, model, resolve=None):
        out = {}
        for s in root.children:
            child = s.children[0] if s.children else None
            # bake the summary markdown field
            from core.profile_tree import FieldNode, GroupNode
            if isinstance(child, GroupNode):
                for f in child.children:
                    if f.llm_output:
                        out[f.id] = "Generated."
            elif isinstance(child, FieldNode) and child.llm_output:
                out[child.id] = "Generated."
        return out

    monkeypatch.setattr(sg, "generate_resume_by_section", fake_generate)
    monkeypatch.setattr("core.job.generate_resume_by_section", fake_generate, raising=False)

    job = Job(job_key="genjk", title="t", company="c", profile_id=seeded_user.profile_id)
    job.extracted_description = "Build things."
    db_session.add(job); db_session.commit()

    job.generate_resume_md(seeded_user, "{job.extracted_description}", client=object(),
                           model="m", db=db_session)

    row = Document.fetch(db_session, "genjk", "resume", profile_id=seeded_user.profile_id)
    assert row is not None
    assert is_tree_v1(row.structured_json)
    md = (_OUTPUTS_DIR / "genjk_resume.md").read_text(encoding="utf-8")
    assert not md.startswith("---")
```

If the repo lacks `db_session`/`seeded_user` fixtures with these exact names, adapt to the
fixtures used by `tests/core/test_job.py` / `tests/db/test_documents.py` (inspect their
`conftest.py`), keeping the assertions identical.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_job_generate_tree.py -v`
Expected: FAIL (current `generate_resume_md` stores a legacy `ResumeDocument`, so
`is_tree_v1` is False)

- [ ] **Step 3: Write minimal implementation**

Add imports near the other core imports in `core/job.py`:

```python
from core.section_generator import generate_resume_by_section
from core.document_tree import build_resume_document_tree
from core.resume_document_io import serialize_document_tree
from core.profile_tree import resolve_profile_tokens
```

Replace `generate_resume_md`:

```python
    def generate_resume_md(
        self,
        user: Any,
        prompt_content: str,
        client: Any,
        model: str,
        db: Session,
    ) -> None:
        """Generate the résumé as a tree-v1 document and write its Markdown.

        Runs per-section generation against the profile tree, materializes a
        self-contained document tree (pruned, value-baked, locked nodes verbatim),
        stores it under ``schema:"tree-v1"`` (source of truth), and writes the
        derived ``.md`` (no front matter).
        """
        root = user.profile_tree_root()
        prompt = self.build_resume_prompt(user, prompt_content, db)

        def resolve(text: str) -> str:
            text = resolve_profile_tokens(root, text)
            return _apply_template(text, {"job": self, "user": user})

        authored = generate_resume_by_section(root, prompt, client, model, resolve=resolve)
        doc_tree = build_resume_document_tree(root, authored)
        Document.upsert(
            db, self.job_key, "resume",
            serialize_document_tree(doc_tree), profile_id=self.profile_id,
        )
        self.write_resume_markdown(doc_tree)
```

Note: `build_resume_prompt`'s second arg is the prompt template; production callers pass the
resolved resume prompt content. The `resolve` closure substitutes `{job.*}`/`{profile.*}`
tokens that the user injected into per-section prompts (same as the dev harness).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_job_generate_tree.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/job.py tests/core/test_job_generate_tree.py
git commit -m "[feat] generate_resume_md produces and stores a tree-v1 document"
```

---

### Task 5: Interim tree-v1 refinement in `_refine_doc_md`

`_refine_doc_md` for résumés patches a `ResumeDocument` via `apply_resume_patch`. Branch it:
a tree-v1 row re-runs per-section generation for all `llm_output` sections (interim — 4B-2
adds per-section scoring), rebuilds the document tree, re-persists tree-v1, re-renders.
Legacy rows keep the prose-patch path unchanged.

**Files:**
- Modify: `core/job.py:578-643` (`_refine_doc_md`)
- Test: `tests/core/test_job_refine_tree.py` (create)

**Interfaces:**
- Consumes: `core.resume_document_io.is_tree_v1`, `generate_resume_by_section`,
  `build_resume_document_tree`, `serialize_document_tree`, `user.profile_tree_root`.
- Produces: `_refine_doc_md` unchanged signature; for a tree-v1 résumé row it re-persists a
  tree-v1 row and re-writes the `.md`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_job_refine_tree.py
from core.job import Job
from core.resume_document_io import is_tree_v1, serialize_document_tree
from core.document_tree import build_resume_document_tree
from db.database import Document


def test_refine_tree_v1_repersists_tree(db_session, seeded_user, monkeypatch):
    root = seeded_user.profile_tree_root()
    tree = build_resume_document_tree(root, {})
    job = Job(job_key="rfjk", title="t", company="c", profile_id=seeded_user.profile_id)
    db_session.add(job); db_session.commit()
    Document.upsert(db_session, "rfjk", "resume", serialize_document_tree(tree),
                    profile_id=seeded_user.profile_id)

    captured = {"called": False}
    def fake_generate(root, job_ctx, client, model, resolve=None):
        captured["called"] = True
        return {}
    monkeypatch.setattr("core.job.generate_resume_by_section", fake_generate)

    job._refine_doc_md("resume", seeded_user, "{critique}", client=object(),
                       model="m", issues=[{"issue": "x"}], db=db_session)

    assert captured["called"] is True
    row = Document.fetch(db_session, "rfjk", "resume", profile_id=seeded_user.profile_id)
    assert is_tree_v1(row.structured_json)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_job_refine_tree.py -v`
Expected: FAIL (current code calls `ResumeDocument.model_validate_json` on the tree JSON →
ValidationError)

- [ ] **Step 3: Write minimal implementation**

In `_refine_doc_md`, inside the `if doc_type == "resume":` branch, before
`doc = ResumeDocument.model_validate_json(row.structured_json)`, add the tree-v1 branch:

```python
        if doc_type == "resume" and is_tree_v1(row.structured_json):
            # Interim tree-v1 refine: re-author all llm_output sections with the
            # critique in context, rebuild the document tree, re-persist + re-render.
            # (Per-section scoring / selective regen is 4B-2.)
            root = user.profile_tree_root()
            critique = json.dumps(issues)
            base_prompt = _apply_template(
                refine_prompt.replace("{critique}", critique),
                {"job": self, "user": user},
            )

            def resolve(text: str) -> str:
                text = resolve_profile_tokens(root, text)
                return _apply_template(text, {"job": self, "user": user})

            job_ctx = f"{base_prompt}\n\n{self.extracted_description or ''}"
            authored = generate_resume_by_section(root, job_ctx, client, model, resolve=resolve)
            doc_tree = build_resume_document_tree(root, authored)
            Document.upsert(db, self.job_key, "resume",
                            serialize_document_tree(doc_tree), profile_id=self.profile_id)
            self.write_resume_markdown(doc_tree)
            return
```

(Place this immediately after the `row is None` guard / `critique`/`prompt` setup but before
the legacy `if doc_type == "resume":` body; keep the legacy body for non-tree rows.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_job_refine_tree.py tests/core/test_job_refine_structured.py -v`
Expected: PASS (legacy structured-refine tests unaffected)

- [ ] **Step 5: Commit**

```bash
git add core/job.py tests/core/test_job_refine_tree.py
git commit -m "[feat] Interim tree-v1 refinement: re-author sections, re-persist tree"
```

---

### Task 6: `_restore_best` re-renders tree-v1 turn snapshots

The auto-refine loop snapshots each turn's `structured_json` and `_restore_best` re-persists
the best turn, re-rendering via `ResumeDocument`. Branch the re-render on the discriminator.

**Files:**
- Modify: `web/intake_pipeline.py:157-191` (`_restore_best`)
- Test: `tests/web/test_intake_pipeline.py` (add a case)

**Interfaces:**
- Consumes: `core.resume_document_io.is_tree_v1`, `deserialize_document_tree`.
- Produces: `_restore_best` re-renders a tree-v1 best turn via `write_resume_markdown(tree)`
  + `generate_resume_pdf`, without constructing a `ResumeDocument`.

- [ ] **Step 1: Write the failing test**

Add to `tests/web/test_intake_pipeline.py` a test that drives `_run_doc_refinement`'s
`_restore_best` indirectly, or unit-test the branch by extracting it. Minimal targeted test:
store a tree-v1 turn snapshot file + row, call the restore path, assert no exception and the
`.md` is frontmatter-free. If `_restore_best` is a closure, test via the public
`_run_doc_refinement` with a stubbed eval/refine producing two turns; assert the restored
`{job_key}_resume.md` has no `---` prefix.

```python
def test_restore_best_tree_v1(tmp_path, monkeypatch, db_session, seeded_user):
    # Arrange a tree-v1 row + a turn_0 snapshot identical to it, then force the
    # loop to restore. Assert the rendered .md has no frontmatter.
    # (See existing intake_pipeline tests for the loop-stubbing pattern.)
    ...
```

Implementer: model this on the existing refinement tests in the file; the binding assertion
is `not md.startswith("---")` after restore of a tree-v1 snapshot.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/web/test_intake_pipeline.py -v`
Expected: FAIL (restore path calls `ResumeDocument.model_validate_json` on tree JSON)

- [ ] **Step 3: Write minimal implementation**

In `_restore_best`, replace the résumé render branch:

```python
                from core.schemas import ResumeDocument, CoverDocument
                from core.resume_document_io import is_tree_v1, deserialize_document_tree
                if doc_type == "resume":
                    if is_tree_v1(structured_json):
                        job2.write_resume_markdown(deserialize_document_tree(structured_json))
                    else:
                        job2.write_resume_markdown(ResumeDocument.model_validate_json(structured_json))
                    job2.generate_resume_pdf(template_path, db2, max_pages=1)
                else:
                    job2.write_cover_markdown(CoverDocument.model_validate_json(structured_json))
                    job2.generate_cover_pdf(template_path, db2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/web/test_intake_pipeline.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/intake_pipeline.py tests/web/test_intake_pipeline.py
git commit -m "[feat] _restore_best re-renders tree-v1 turn snapshots"
```

---

### Task 7: Turn-snapshot render endpoint branches on tree-v1

`GET …/{doc_type}/turn/{n}` renders a stored turn snapshot via `assemble_resume_markdown`.
Branch it so a tree-v1 snapshot renders via `assemble_resume_tree_markdown`. The
`get_document` GET already returns raw `structured_json` (a tree-v1 doc returns its tree JSON
as-is — the legacy DocumentModal can't read it yet; that's the accepted 4D gap), so it needs
no change.

**Files:**
- Modify: `web/routers/jobs.py:470-475` (turn-snapshot render)
- Test: `tests/web/test_document_api.py` (add a case)

**Interfaces:**
- Consumes: `core.resume_document_io.is_tree_v1`, `deserialize_document_tree`,
  `core.tree_assembler.assemble_resume_tree_markdown`.
- Produces: the turn endpoint returns tree-assembled Markdown for tree-v1 snapshots.

- [ ] **Step 1: Write the failing test**

```python
# in tests/web/test_document_api.py
def test_turn_snapshot_renders_tree_v1(client, tmp_path, seeded_job, monkeypatch):
    # Write a tree-v1 turn snapshot file at generator/outputs/{job}_resume_turn_0.json
    # then GET the turn endpoint; assert the body contains "# " (H1 name) and no "---".
    ...
```

Model on the existing turn-snapshot test in this file; binding assertions: response is 200,
contains the tree's H1 (`"# "`), and does not start with `---`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/web/test_document_api.py -v`
Expected: FAIL (`ResumeDocument.model_validate_json` raises `ValidationError` → 422)

- [ ] **Step 3: Write minimal implementation**

Replace the résumé branch in the turn endpoint:

```python
    try:
        if doc_type == "resume":
            from core.resume_document_io import is_tree_v1, deserialize_document_tree
            from core.tree_assembler import assemble_resume_tree_markdown
            if is_tree_v1(raw):
                return assemble_resume_tree_markdown(deserialize_document_tree(raw))
            return assemble_resume_markdown(ResumeDocument.model_validate_json(raw))
        return assemble_cover_markdown(CoverDocument.model_validate_json(raw))
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Snapshot schema mismatch: {exc}") from exc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/web/test_document_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/routers/jobs.py tests/web/test_document_api.py
git commit -m "[feat] Turn-snapshot endpoint renders tree-v1 snapshots"
```

---

### Task 8: ATS gate adapter for tree-v1 documents

`run_ats_check` loads a `ResumeDocument` and passes it to `ats_gate.run_gate`, which reads
only `doc.header.{name,email,phone,location}` and `doc.section_order`. For a tree-v1 row,
project the document tree into a minimal `ResumeDocument` (header + section_order) so the
existing gate runs unchanged. (Full ATS rework — dropping fixed-heading checks — is 4C.)

**Files:**
- Modify: `core/job.py:999-1002` (the `ResumeDocument.model_validate_json` load in `run_ats_check`)
- Create: `core/ats_tree_adapter.py`
- Test: `tests/core/test_ats_tree_adapter.py` (create)

**Interfaces:**
- Consumes: the document tree (`RootNode`), `core.schemas.ResumeDocument`/`ResumeHeader`.
- Produces: `resume_document_for_ats(root: RootNode) -> ResumeDocument` — a `ResumeDocument`
  with `header` populated from the tree's `role="header"` section (name = first+last; email,
  phone, location, github, linkedin, website by field key) and `section_order` = the visible
  section names, lowercased. Other `ResumeDocument` lists are left empty (the gate ignores
  them).

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_ats_tree_adapter.py
from core.ats_tree_adapter import resume_document_for_ats
from core.profile_tree import FieldNode, GroupNode, RootNode, SectionNode


def _root():
    return RootNode(children=[
        SectionNode(name="Header", role="header", order=0, children=[
            GroupNode(name="Contact", children=[
                FieldNode(name="First Name", key="first_name", kind="text", value="Jane"),
                FieldNode(name="Last Name", key="last_name", kind="text", value="Doe"),
                FieldNode(name="Email", key="email", kind="text", value="j@x.co"),
                FieldNode(name="Phone", key="phone", kind="text", value="555"),
                FieldNode(name="Location", key="location", kind="text", value="NY"),
            ]),
        ]),
        SectionNode(name="Patents", order=1, children=[
            GroupNode(name="g", children=[
                FieldNode(name="d", key="d", kind="text", value="x"),
            ]),
        ]),
    ])


def test_header_projection():
    doc = resume_document_for_ats(_root())
    assert doc.header.name == "Jane Doe"
    assert doc.header.email == "j@x.co"
    assert doc.header.phone == "555"
    assert doc.header.location == "NY"


def test_section_order_lowercased():
    doc = resume_document_for_ats(_root())
    assert doc.section_order == ["header", "patents"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_ats_tree_adapter.py -v`
Expected: FAIL (`ModuleNotFoundError: core.ats_tree_adapter`)

- [ ] **Step 3: Write minimal implementation**

```python
# core/ats_tree_adapter.py
"""Project a tree-v1 résumé document into the minimal ``ResumeDocument`` the ATS
gate reads (header + section_order). Interim for 4B-1; the ATS gate is reworked to
consume the tree directly in 4C.
"""
from __future__ import annotations

from core.profile_tree import FieldNode, GroupNode, RootNode, SectionNode
from core.schemas import ResumeDocument, ResumeHeader


def _header_fields(root: RootNode) -> dict[str, str]:
    for s in root.children:
        if s.role == "header" and s.children and isinstance(s.children[0], GroupNode):
            out: dict[str, str] = {}
            for f in s.children[0].children:
                if isinstance(f, FieldNode) and isinstance(f.value, str):
                    out[f.key] = f.value.strip()
            return out
    return {}


def resume_document_for_ats(root: RootNode) -> ResumeDocument:
    """Minimal ``ResumeDocument`` for the ATS gate: header + section_order only."""
    hf = _header_fields(root)
    name = f"{hf.get('first_name', '')} {hf.get('last_name', '')}".strip()
    header = ResumeHeader(
        name=name,
        email=hf.get("email", ""),
        phone=hf.get("phone", ""),
        location=hf.get("location", ""),
        github=hf.get("github", ""),
        linkedin=hf.get("linkedin", ""),
        website=hf.get("website", ""),
    )
    section_order = [s.name.lower() for s in root.children if s.visible]
    return ResumeDocument(header=header, section_order=section_order)
```

Verify `ResumeHeader`'s field names against `core/schemas.py:128` and adjust kwargs to match
(use only fields that exist; omit any the model doesn't define).

In `core/job.py` `run_ats_check`, replace the load:

```python
        from core.resume_document_io import is_tree_v1, deserialize_document_tree
        from core.ats_tree_adapter import resume_document_for_ats
        if is_tree_v1(row.structured_json):
            doc = resume_document_for_ats(deserialize_document_tree(row.structured_json))
        else:
            doc = ResumeDocument.model_validate_json(row.structured_json)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_ats_tree_adapter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/ats_tree_adapter.py core/job.py tests/core/test_ats_tree_adapter.py
git commit -m "[feat] ATS gate adapter projects tree-v1 docs to minimal ResumeDocument"
```

---

### Task 9: Résumé CSS for tree-v1 body header + education; render smoke test

With tree-v1, the contact block (body `<h1>` + contact line) and education rows arrive as
body HTML from pandoc, not from the template's `meta` header. Add CSS so they look
presentable, and add a render smoke test (gated behind pandoc/Chromium availability) that a
tree-v1 résumé renders to a non-empty PDF with the name in the extracted text.

**Files:**
- Modify: `generator/resume.css` (add body-header + body-education rules)
- Test: `tests/generator/test_tree_pdf_render.py` (create; gate on pandoc + Chromium)
- Update: `generator/CONTEXT.md` (note tree-v1 renders contact/education from body, no
  frontmatter; icon-grid contact is a #6 feature)

**Interfaces:**
- Consumes: `core.utils.render_pdf` (already meta-driven; empty meta = no education injection),
  the tree markdown from Task 2/3.
- Produces: CSS only + a smoke test; no Python API changes.

- [ ] **Step 1: Write the failing test**

```python
# tests/generator/test_tree_pdf_render.py
import shutil
import subprocess
from pathlib import Path

import pytest

from core.utils import render_pdf

pytestmark = pytest.mark.skipif(
    shutil.which("pandoc") is None, reason="pandoc not available"
)


def _chromium_ok() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch().close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _chromium_ok(), reason="Chromium not available")
def test_tree_v1_resume_renders_pdf(tmp_path):
    md = "# Jane Doe\n\nj@x.co · 555\n\n## Patents\n\nA patent.\n"
    md_path = tmp_path / "x_resume.md"
    md_path.write_text(md, encoding="utf-8")
    pdf_path = tmp_path / "x_resume.pdf"
    template = Path("generator/resume_template.html")
    render_pdf(md_path, pdf_path, template, max_pages=1, meta={})
    assert pdf_path.exists() and pdf_path.stat().st_size > 0
    from pypdf import PdfReader
    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(pdf_path)).pages)
    assert "Jane Doe" in text
    assert "Patents" in text
```

- [ ] **Step 2: Run test to verify it fails (or skips cleanly)**

Run: `python -m pytest tests/generator/test_tree_pdf_render.py -v`
Expected: PASS if pandoc+Chromium present (the existing template already renders body HTML
with empty meta) — if it FAILS on layout/styling, fix in Step 3; if pandoc/Chromium absent it
SKIPS. The CSS work in Step 3 is required regardless for acceptable presentation.

- [ ] **Step 3: Add the CSS**

Append to `generator/resume.css` (match existing selector/style conventions; adjust to the
file's actual `.resume` scoping):

```css
/* tree-v1: contact header rendered from body markdown (no meta header block).
   Name is a body <h1>; the contact line is the <p> immediately after it. */
.resume > main h1,
.resume h1 {
  text-align: center;
  margin: 0 0 0.15rem 0;
  font-size: 1.8rem;
}
.resume h1 + p {
  text-align: center;
  margin: 0 0 0.6rem 0;
  font-size: 0.92rem;
}
.resume h1 + p a { text-decoration: none; }

/* tree-v1 education rows render as body paragraphs under an <h2>Education</h2>. */
```

(If the existing `.resume-header h1` rule conflicts, scope the new rule to body content,
e.g. `.resume main > h1`, so the legacy meta header is unaffected.)

- [ ] **Step 4: Re-run the render test**

Run: `python -m pytest tests/generator/test_tree_pdf_render.py -v`
Expected: PASS (or SKIP without pandoc/Chromium)

- [ ] **Step 5: Commit**

```bash
git add generator/resume.css tests/generator/test_tree_pdf_render.py generator/CONTEXT.md
git commit -m "[feat] tree-v1 résumé CSS for body header/education + render smoke test"
```

---

## Self-Review Notes (carry into final whole-branch review)

- **Spec coverage:** Task 1 = discriminator + serialization; Task 4 = generation; Tasks 3/7 =
  render branches; Task 9 = PDF/frontmatter retire (CSS + empty-meta path); Tasks 5/6 =
  interim refine + restore; Task 8 = ATS loader adapt. `get_document` GET needs no change
  (returns raw JSON; 4D handles the modal). Legacy paths preserved at every site.
- **Minor finding to record:** dropping the icon-grid contact in the default tree-v1 template
  is a deliberate divergence from "looks like today's output" — icon-grid contact is restored
  as a #6 (user-formatted templates) feature; flag to the user during execution.
- **Carry-forwards (from 4A, still open):** remove orphaned `core/tree_render.py` (needs
  approval; nothing references it after 4B-1 — confirm with grep); add a direct `_list_rows`
  invisible-entry test.
- **Fixture names** (`db_session`, `seeded_user`, `seeded_job`, `client`) are placeholders —
  each implementer must confirm the real fixture names in the relevant `conftest.py` and adapt
  while keeping the assertions identical.
- **Out of scope (do not build):** per-section eval scoring/selective regen (4B-2), ATS
  fixed-heading removal (4C), DocumentModal rebuild + tree-v1 PUT (4D), deleting
  `ResumeGeneration`/`build_resume_document`.
