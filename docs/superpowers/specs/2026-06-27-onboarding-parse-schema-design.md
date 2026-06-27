# #5 — Onboarding Parse → Schema Sections — Design

**Status:** Approved design (2026-06-27). Final sub-project (#5) of the Profile Schema Engine swap.

**Release constraint:** Merge to LOCAL `main` only. This is the LAST sub-project — once #5 merges, the whole swap (#1–#6) is complete and `main` may be pushed (with explicit user approval).

## Goal

Make résumé parsing schema-aware: extract the built-in sections as today, **and** detect résumé sections that don't map to a built-in type (Certifications, Publications, Awards, Languages, Volunteer, …), infer a structure for each, and let the user review every section — per-section — before anything is written to the profile. Works for both first-run onboarding and re-parsing an existing profile.

## Problem

`User.from_pdf` / `from_markdown` parse into a fixed `ParseResponse` (contact, hero, skills, work_history, education, projects). Anything else in the résumé has no slot and is silently dropped. The parse also **auto-applies** — it persists immediately, with no review.

## Decisions (locked during brainstorming)

| Dimension | Decision |
|---|---|
| Novel sections | **Create real schema sections** (first-class, editable, renderable) — not a catch-all dump |
| Review | **Preview + confirm** before commit (not auto-apply) |
| Entry points | **Both** onboarding (`StepResume`) and existing-profile re-parse |
| Re-parse on matched sections | **Per-section choice** (add / replace / merge / skip), default never clobbers existing data |

## Structure vocabulary (5 kinds)

The tree's node types (`FieldNode` kinds `text`/`markdown`/`bullets`/`taglist`; `GroupNode` = one record; `ListNode` = repeating records) compose into exactly the section shapes a parsed section can take. The parse emits one `kind` per novel section, named to match the existing leaf kinds — **no new node type is introduced** (`markdown` already IS the prose leaf, as used by Summary):

| `kind` | Tree shape built | Example sections |
|---|---|---|
| `markdown` | section → one `markdown` FieldNode | About, Objective, References-on-request |
| `bullets` | section → one `bullets` FieldNode | Achievements, Highlights |
| `taglist` | section → one `taglist` FieldNode | Interests, Coursework, Languages (names) |
| `fields` | section → one `GroupNode` (one record of label/value fields) | a one-off labeled block |
| `list` | section → one `ListNode` (repeating records) | Certifications, Publications, Awards, Volunteer, Languages w/ proficiency, grouped skills |

Out of scope (deliberate, not structural gaps): numbered-list / citation *rendering* (a `bullet_style` concern), and nested sub-sections (the closed vocabulary is section→list→group→field by design).

## Architecture

### 1. Parse schema — open sections (`core/schemas.py`)

Keep the existing fixed fields untouched (they feed rendering/generation and must keep their preset keys). **Add** an `extra_sections` list to `ParseResponse` — empty = today's behavior, fully back-compat:

```python
class ParsedField(BaseModel):
    label: str = ""
    value: str = ""

class ParsedEntry(BaseModel):
    fields: list[ParsedField] = Field(default_factory=list)

class ExtraSection(BaseModel):
    name: str = ""
    kind: Literal["markdown", "bullets", "taglist", "fields", "list"]
    markdown: str = ""                                   # kind == "markdown"
    items: list[str] = Field(default_factory=list)       # kind in {"bullets","taglist"}
    fields: list[ParsedField] = Field(default_factory=list)   # kind == "fields"
    entries: list[ParsedEntry] = Field(default_factory=list)  # kind == "list"

# ParseResponse gains:
    extra_sections: list[ExtraSection] = Field(default_factory=list)
```

The `prompts/defaults/resume_parse.md` prompt is extended: extract the known sections into the fixed fields as before; emit everything else as `extra_sections`, choosing the closest `kind`; never invent facts; preserve wording. The `resume_parse` prompt is DB-backed and seeded — bump the seed and document that existing profiles keep their customized prompt (so the new capability activates after a prompt reset, or we re-seed; the plan decides the migration nuance).

### 2. Tree builder (`core/profile_tree.py` or a new `core/parsed_sections.py`)

`build_section_from_parsed(extra: ExtraSection) -> SectionNode`:

- `markdown` → `SectionNode(name, role="", children=[FieldNode(name, kind="markdown", value=markdown)])`
- `bullets` → one `FieldNode(kind="bullets", value=items)`
- `taglist` → one `FieldNode(kind="taglist", value=items)`
- `fields` → one `GroupNode` of `text` FieldNodes (one per `label/value`)
- `list` → one `ListNode` whose `item_template` is a `GroupNode` built from the **union** of entry field labels; one child `GroupNode` per entry

Novel-section fields default `llm_output=False` (verbatim factual content — the per-section generator must not rewrite certifications etc.). `role=""` → they render through the existing 4A generic-section renderer and validate under the ≤500-node / ≤6-deep tree caps.

### 3. Two-phase API (`web/routers/config.py`)

Split the single auto-applying parse into propose → apply. Keep the legacy `POST …/parse` working unchanged (auto-applies built-in fields only; ignores `extra_sections`) so existing tests/callers are unaffected; the new UI uses the two new endpoints.

**Propose** — `POST /api/config/profiles/{id}/parse/propose` (stateless, no persist):
runs the LLM parse, then returns a `ParseProposal`:

```python
ProposedAction = Literal["add", "replace", "merge", "skip"]

class ProposedSection(BaseModel):
    name: str                       # display name; editable in preview (novel only)
    kind: Literal["markdown","bullets","taglist","fields","list"]
    origin: Literal["builtin", "novel"]
    builtin_role: str = ""          # e.g. "experience"/"skills" when origin=="builtin"
    matches_existing: bool          # a same-name/role section already exists in the profile
    existing_has_data: bool         # …and it currently holds data
    default_action: ProposedAction
    allowed_actions: list[ProposedAction]
    preview: dict                   # display-only summary (entry/item counts, first values)

class ParseProposal(BaseModel):
    builtin: ParseResponse          # authoritative payload for applying built-in sections
    sections: list[ProposedSection] # uniform preview rows (built-in-derived + novel)
    is_onboarding: bool             # profile has no parsed data yet → defaults populate everything
```

- Built-in sections appear as `origin="builtin"` rows derived from `builtin`; their content is applied via the existing reliable flat path (`merge_flat_into_stored` / preset sections), **not** rebuilt by `build_section_from_parsed`.
- `allowed_actions` reflects merge-compatibility: `merge` offered only for `list`, `taglist`, `bullets`; `markdown`/`fields` get `replace`/`skip`/`add` only.
- **Defaults** (never clobber existing data): onboarding → built-in `replace` (populate empty presets), novel `add`. Re-parse → matched-with-data `skip`, matched-empty `replace`, novel `add`.

**Apply** — `POST /api/config/profiles/{id}/parse/apply`:
body = the (possibly user-edited) `ParseProposal` with each section's chosen `action`. Server re-validates and persists:

- `add` → built-in: build preset section from `builtin` payload by role; novel: `build_section_from_parsed`; append to root.
- `replace` → find matched existing `SectionNode` (case-fold name / role); replace its content in place (preserving node id where possible).
- `merge` → `list`: append parsed records to the existing `ListNode.children`; `taglist`/`bullets`: union/append items into the existing `FieldNode.value` (case-insensitive dedup for taglist).
- `skip` → no-op.

Reuses the §2.A in-place-preserving overlay where a built-in section is targeted, and the tree caps (`validate_tree_limits`) before commit (422 on violation). LLM-config and file-pointer fields are preserved exactly as the current `parse` endpoint does.

### 4. Preview/confirm UI (`react-dashboard`)

A shared `ParsePreview` component, used by both `StepResume` (onboarding) and the existing-profile re-parse trigger (`ProfileDetail`). Renders the `sections` list in two visual groups — **Standard sections** (`origin="builtin"`) and **Additional sections found** (`origin="novel"`, showing the inferred `kind` and a content preview). Per row: an action control limited to `allowed_actions`, and a rename field for novel sections. Confirm posts the edited proposal to `…/parse/apply`. Deeper restructuring (changing a section's kind/fields) is deferred to the existing tree editor (#2B/#2C) — the preview is review + accept/rename/drop/merge, not a full editor.

New API client helpers (`api.js`): `proposeParse(profileId)`, `applyParse(profileId, proposal)`.

## Data flow

```
upload ─► POST …/parse/propose ──► LLM parse (fixed fields + extra_sections)
                                     │
                                     ▼
                         ParseProposal { builtin, sections[], is_onboarding }
                                     │  (no persist)
                                     ▼
                ParsePreview: per-section action + rename  ──► POST …/parse/apply
                                                                  │ build/merge tree
                                                                  │ validate_tree_limits
                                                                  ▼
                                                            persist profile
```

## Back-compat invariants

1. Empty `extra_sections` → the built-in extraction and applied tree are identical to today.
2. Legacy `POST …/parse` endpoint unchanged (built-in only) — existing tests/callers unaffected.
3. Built-in sections always apply via the existing preset/flat path → rendering, generation, and the ATS gate are unaffected.
4. `add-only`-safe defaults: a re-parse never overwrites a section that already holds data unless the user explicitly chooses replace/merge.

## Out of scope

- Changing built-in extraction shape or keys.
- Editing a section's structure inside the preview (kind change, add/remove fields) — that's the tree editor's job.
- Numbered-list rendering, nested sub-sections, alias/skill-grouping during taglist merge (stays a skill-analytics concern).
- Background/async parse (parse stays synchronous, as today).

## Testing

- **Schema:** `ExtraSection` validates per kind; `ParseResponse.extra_sections` defaults empty; a fixture résumé with a Certifications + Languages block round-trips.
- **Builder:** `build_section_from_parsed` for each of the 5 kinds yields the right node shape; `list` builds a union item_template; novel fields are `llm_output=False`, `role=""`.
- **Apply semantics:** add / replace / merge / skip each do the right thing for built-in and novel; `merge` rejected/absent for `markdown`/`fields`; taglist merge dedups case-insensitively; tree caps enforced (422).
- **Propose endpoint:** returns built-in + novel rows; correct `matches_existing` / `existing_has_data` / defaults for onboarding vs re-parse; no persistence.
- **Apply endpoint:** persists per decisions; preserves LLM-config + file pointers; legacy `parse` endpoint still green.
- **Frontend:** `ParsePreview` renders both groups, gates actions to `allowed_actions`, posts the edited proposal; onboarding vs re-parse default actions.
