# generator/

Handles resume and cover letter generation: converts job data + user profile into tailored PDFs.

## File tree

```
generator/
├── resume_template.html   # Jinja2 shell — wraps MD-rendered HTML fragment with <head> + inlined CSS
├── resume.css             # Layout and typography for resume PDFs
├── cover_template.html    # Jinja2 shell — same role for cover letters
├── cover.css              # Layout and typography for cover letter PDFs
└── outputs/               # Generated PDFs and intermediate files (gitignored)
```

## Responsibilities

| File | Role |
|---|---|
| `resume_template.html` | Jinja2 template; renders name/contact header (2×3 grid with SVG icons), injects Education from frontmatter, then LLM body |
| `resume.css` | Layout and typography for resumes; serif section headers, ALL CAPS h2 |
| `cover_template.html` | Jinja2 template; black bars top/bottom, 2-col gray header, date injection, auto sign-off |
| `cover.css` | Layout and typography for cover letters |

## Pipeline

`Job.generate_resume_pdf()` calls `core.utils.render_pdf`, which:

1. Runs **pandoc** to convert the Markdown document body to an HTML fragment (YAML frontmatter is stripped by pandoc).
2. `_parse_frontmatter` extracts contact fields and structured education entries from the YAML block.
3. Jinja2 (`Environment` with `strip_url` filter) renders the template with the fragment, frontmatter vars, and today's date.
4. **Playwright** (headless Chromium) renders the full HTML page to PDF.

The CSS file is resolved by stripping `_template` from the template stem (e.g. `resume_template.html` → `resume.css`).

Resume rendering passes `max_pages=1` and raises `RuntimeError` if the output exceeds one page. There is no auto-shrink — the template and CSS must keep content within one page.
