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
| `resume_template.html` | Jinja2 template; receives rendered HTML fragment and inlines CSS |
| `resume.css` | All layout, typography, and spacing for resumes |
| `cover_template.html` | Jinja2 template for cover letters |
| `cover.css` | All layout, typography, and spacing for cover letters |

## Pipeline

`Job.generate_resume_pdf()` calls `core.utils.render_pdf`, which:

1. Runs **pandoc** to convert the Markdown document (resume or cover letter) to an HTML fragment.
2. Jinja2 wraps the fragment using the appropriate `*_template.html`, inlining the paired `.css` file into the `<head>`.
3. **Playwright** (headless Chromium) renders the full HTML page to PDF.

Resume rendering passes `max_pages=1` and raises `RuntimeError` if the output exceeds one page. There is no auto-shrink — the template and CSS must keep content within one page.
