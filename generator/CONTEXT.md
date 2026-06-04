# generator/

Handles resume and cover letter generation: converts job data + user profile into tailored PDFs.

## File tree

```
generator/
├── resume_template.html   # Jinja2 shell — wraps MD-rendered HTML fragment with <head> + inlined CSS
├── resume.css             # Layout and typography for resume PDFs
├── cover_template.html    # Jinja2 shell — same role for cover letters
├── cover.css              # Layout and typography for cover letter PDFs
├── master_template.html   # Jinja2template for the user's master resume (multi-page, no LLM body injection)
├── master.css             # Layout and typography for the master resume PDF
└── outputs/               # Generated PDFs and intermediate files (gitignored)
```

## Responsibilities

| File | Role |
|---|---|
| `resume_template.html` | Jinja2 template; renders name/contact header (2×3 grid with SVG icons), injects Education from frontmatter, then LLM body |
| `resume.css` | Layout and typography for resumes; serif section headers, ALL CAPS h2 |
| `cover_template.html` | Jinja2 template; black bars top/bottom, 2-col gray header, date injection, auto sign-off |
| `cover.css` | Layout and typography for cover letters |
| `master_template.html` | Jinja2 template for master resume; same header structure, no page limit; used by `web/routers/config.py` |
| `master.css` | Layout and typography for the master resume; letter size with tighter margins |

## Generated Document Storage (`documents` table)

Since Phase 3a, every résumé and cover letter generated via `Job.generate_resume_md` / `generate_cover_md` has a corresponding row in the `documents` table (`db/database.py` → `Document` model). The row holds the full typed artifact as `structured_json` (a serialized `ResumeDocument` or `CoverDocument`). This is the **source of truth** for the generated content; the `.md` files in `outputs/` are derived from it.

The `Document` snapshot also carries the contact/education data captured at generation time. `Job._render_meta` reads from this snapshot when rendering an existing job's PDF, so the header and education block reflect the profile as it was when the document was generated — not the current live profile.

## Pipeline

`Job.generate_resume_pdf()` calls `core.utils.render_pdf`, which:

1. Runs **pandoc** to convert the Markdown document body to an HTML fragment (YAML frontmatter is stripped by pandoc).
2. `_parse_frontmatter` extracts contact fields and structured education entries from the YAML block.
3. Jinja2 (`Environment` with `strip_url` filter) renders the template with the fragment, frontmatter vars, and today's date.
4. **Playwright** (headless Chromium) renders the full HTML page to PDF.

The CSS file is resolved by stripping `_template` from the template stem (e.g. `resume_template.html` → `resume.css`).

Resume rendering passes `max_pages=1`. If content overflows one page, `render_pdf` auto-shrinks the Playwright print scale in steps (down to a `_PDF_SCALE_FLOOR` of 0.8) until it fits, raising `RuntimeError` only if it still overflows at the floor. Note: Chromium ignores CSS `zoom` and visual `transform` in its print path — only `page.pdf(scale=)` actually reduces the page count. The CSS should still keep typical content near one page so the shrink factor stays mild (readable text).

### Education position: PDF vs. canonical Markdown

`render_pdf` (in `core/utils.py`) is **unchanged** in Phase 3a. It strips any Education section from the Markdown body and re-injects it from `meta['education']` (now sourced from the `Document` snapshot via `_render_meta`) positioned immediately after Profile — matching the existing template layout.

The assembled `.md` file follows canonical order (Profile → Experience → Education → Projects → Skills), so Education appears third in the file. The PDF overrides this and places Education second (after Profile). This divergence is intentional for Phase 3a; render internals are out of scope until Phase 3b.
