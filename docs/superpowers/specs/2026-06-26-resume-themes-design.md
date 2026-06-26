# #6B-2 — Profile-level Résumé Themes — Design

**Status:** Approved design (2026-06-26). Sub-project #6B-2 of the Profile Schema Engine swap.

**Release constraint:** Merge to LOCAL `main` only. Do NOT push `main` until the entire schema-engine swap (#1–#6) is complete.

## Goal

Let a user choose one of a small, curated set of pre-built, ATS-safe CSS
themes for their résumé PDFs. The theme is a profile-level setting, picked in
the profile editor, applied to that profile's résumé renders, and re-applied
to an already-generated résumé the next time it is opened (served) if the
theme changed since it was last rendered. Cover letters are out of scope.

## Why curated themes (not user CSS / knobs / WYSIWYG)

ATS-safety is enforced by construction: users never author or edit CSS. They
pick from themes we write and maintain, each of which preserves the
properties an ATS parser needs — selectable text, single-column flow,
standard fonts, no text rendered over background images. This is the meaning
of "ATS-safety enforced by templates" for this sub-project. Structured
per-knob controls, free-form CSS, direct-edit-on-PDF (WYSIWYG), and
per-document overrides are explicitly out of scope.

## Decisions (locked during brainstorming)

| Dimension | Decision |
|---|---|
| Control surface | Curated theme picker (fixed set; we own the CSS) |
| Binding scope | **Profile-level only** — one theme per profile, all that profile's résumés |
| Document types | **Résumé only** — `resume.css`; cover keeps fixed styling |
| Picker location | **Profile editor / settings** (`<select>`, alongside name/Prompts/Export/Reset) |
| Apply timing | **Re-render on open** — `serve_resume` re-renders if the profile theme changed since last render |

## Themes (initial set: 3)

| id | label | look |
|---|---|---|
| `classic` | Classic | The **existing** `generator/resume.css`, unchanged — serif section headers, ALL-CAPS h2. The default. |
| `modern` | Modern | Sans-serif body and headings, lighter section rules, a subtle heading accent. |
| `compact` | Compact | Tighter margins, spacing, and base font size for dense one-page résumés. |

`classic` is the default and maps to the current `resume.css` with **zero
visual change** for existing users. The three-theme set is a starting point;
adding a theme later is "author one more CSS file + one registry entry."

## Architecture

### Theme registry — `generator/themes.py` (new)

Mirrors the `core/output_formats.py` pattern from #6B-1.

```python
@dataclass(frozen=True)
class Theme:
    id: str
    label: str
    css_filename: str   # filename within generator/ (resolved relative to the generator dir)

CLASSIC = Theme(id="classic", label="Classic", css_filename="resume.css")
MODERN  = Theme(id="modern",  label="Modern",  css_filename="themes/resume_modern.css")
COMPACT = Theme(id="compact", label="Compact", css_filename="themes/resume_compact.css")

THEMES: list[Theme] = [CLASSIC, MODERN, COMPACT]
DEFAULT_THEME_ID = "classic"

def get_theme(theme_id: str) -> Theme | None: ...        # None when unknown
def all_themes() -> list[Theme]: ...                      # ordered, for the API
def resolve_theme(theme_id: str | None) -> Theme: ...     # falls back to CLASSIC on None/"" /unknown
```

- `classic`'s `css_filename` points at the existing `generator/resume.css` —
  no duplication.
- `modern` / `compact` CSS files live in `generator/themes/`.
- Pure module, no DB, no I/O beyond the dataclass.

### Theme CSS files — `generator/themes/resume_modern.css`, `generator/themes/resume_compact.css` (new)

Each is a **standalone, self-contained** résumé stylesheet (the same role
`resume.css` plays today — `render_pdf` inlines exactly one CSS file). They
are authored, not derived from `resume.css` by overlay, so each can be read
and reasoned about on its own.

**Hard requirement — both render paths must work under every theme.** A
résumé renders either as tree-v1 (contact as a body `<h1>` + the `<p>` after
it; styled by `.resume > h1` rules) or as legacy (`.resume-header` icon-grid).
Every theme MUST carry working rules for **both** selector families, and must
keep the ATS-safe invariants listed above. A theme that styles only one path
is a defect.

### Render mechanism — `core/utils.py` `render_pdf`

`render_pdf` currently derives its CSS from the template stem
(`resume_template.html` → `resume.css`, line 106). Add an optional explicit
CSS-path override:

```python
def render_pdf(md_path, pdf_path, template_path, max_pages=None, meta=None,
               css_path: Path | None = None) -> None:
```

- `css_path=None` → unchanged behavior (derive from template stem). This
  keeps cover rendering and every existing caller byte-identical.
- `css_path` given → inline that file instead.

### Profile setting — `core/user.py`

Add `resume_theme` exactly as `resume_max_pages` is handled:

- `_load_from_data`: `self.resume_theme = raw.get("resume_theme") or DEFAULT_THEME_ID`
- `_to_dict`: `d["resume_theme"] = self.resume_theme`

Empty / missing / unknown → resolves to `classic` (via `resolve_theme` at
render time, so a stale/garbage stored value can never break a render).

### Render resolution — `core/job.py`

Mirror `_resolve_resume_max_pages`:

```python
def _resolve_resume_theme(self, db) -> Theme:
    user = User.load(db, profile_id=self.profile_id)
    return resolve_theme(user.resume_theme)
```

`generate_resume_pdf` resolves the theme, passes its CSS path to
`render_pdf(..., css_path=<generator_dir>/<theme.css_filename>)`, and records
the theme used on the Job (below). The default (`classic` → `resume.css`)
produces a byte-identical render to today.

### Staleness / re-render on open

Add a nullable column `resume_rendered_theme = Column(String)` to the `jobs`
table (`core/job.py` Job model). Migration: idempotent `ALTER TABLE` in
`db/init_db.py` (SQLite, dev) **and** an Alembic migration (Postgres, hosted)
— follow the existing pattern for adding a jobs column.

- `generate_resume_pdf` sets `self.resume_rendered_theme = theme.id` alongside
  `resume_path` / `resume_generated_at`.
- `serve_resume` (`web/routers/jobs.py`): before serving, load the profile's
  current theme; if `resolve_theme(user.resume_theme).id !=
  (job.resume_rendered_theme or "classic")` **and** the résumé markdown
  exists, re-render via `generate_resume_pdf` (which updates the stamp), then
  serve. If the markdown is missing, serve the existing file unchanged (no
  crash on legacy rows that predate this column — a NULL stamp is treated as
  `classic`).

This makes a theme change visible on next open without a manual save, and
costs a Chromium render only when the theme actually differs.

### API — `web/routers/themes.py` (new), registered in `web/main.py`

`GET /api/themes` → `[{"id": ..., "label": ...}]` from `all_themes()`. Mirrors
`GET /api/output-formats`. No auth specifics beyond the existing router
conventions.

### Frontend — profile editor

- `react-dashboard/src/api.js`: `getThemes()` → `GET /api/themes`.
- Profile editor: a `<select>` listing themes (label shown, id stored),
  bound to the profile's `resume_theme`, written through the **existing
  profile update endpoint** (the same flat `update_profile` PUT that already
  persists `resume_max_pages` et al.). No new write endpoint.
- Default selection reflects the stored value (or `classic`).

## Data flow

```
Profile editor <select> ──PUT (existing update_profile)──► user_profile.data["resume_theme"]
                                                                     │
GET /{job}/resume ─► serve_resume ─► load profile theme ─┐           │
                                                          ▼           ▼
                          theme changed since last render? ── yes ─► generate_resume_pdf
                                                          │                 │ _resolve_resume_theme
                                                          │                 │ render_pdf(css_path=theme css)
                                                          │                 │ job.resume_rendered_theme = theme.id
                                                          ▼                 ▼
                                                       serve cached / freshly-rendered PDF
```

## Back-compat invariants

1. `classic` is the default; an existing profile with no `resume_theme`
   renders byte-identically to today.
2. `render_pdf` with no `css_path` is unchanged — covers and all non-résumé
   callers are untouched.
3. A NULL `resume_rendered_theme` (every pre-migration jobs row) is treated as
   `classic`; such a row re-renders only if the profile now selects a
   non-classic theme.
4. Both tree-v1 and legacy résumé render paths work under all three themes.

## Out of scope

- Cover-letter themes.
- Structured per-knob controls (font/size/color/density).
- Free-form / user-authored CSS.
- Direct-edit-on-PDF (WYSIWYG).
- Per-document theme override (binding is profile-level only).
- Eager batch re-render of all a profile's résumés on theme change.

## Testing

- **Registry** (`tests/.../test_themes.py`): ids/labels; `get_theme` unknown →
  None; `resolve_theme` None/""/unknown → CLASSIC; `classic.css_filename ==
  "resume.css"`.
- **render_pdf override**: `css_path` given inlines that file; `css_path=None`
  inlines the stem-derived file (existing behavior unchanged).
- **`_resolve_resume_theme`**: default profile → CLASSIC; explicit `modern` →
  MODERN; garbage stored value → CLASSIC.
- **User setting**: `resume_theme` round-trips through `_to_dict` /
  `_load_from_data`; missing key → `classic`.
- **`serve_resume` staleness**: profile theme differs from
  `resume_rendered_theme` → re-render invoked + stamp updated; same theme → no
  re-render; NULL stamp + classic profile → no re-render; missing markdown →
  serve existing file, no crash.
- **Endpoint**: `GET /api/themes` returns the three themes with id+label.
- **Frontend**: picker renders options from `getThemes`, shows stored value,
  writes through the profile update path.
- **Theme CSS smoke**: a tree-v1 résumé and a legacy résumé each render to a
  non-empty PDF under `modern` and `compact` (the both-paths invariant).
