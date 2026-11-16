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

`build_render_html` (steps 1–3) is split out of `render_pdf` as a test seam; it returns the exact HTML handed to Chromium.

### Render security (audit H1/M1)

Invariant: **user content is never rendered as raw HTML; Chromium renders offline with JS disabled.** Profile fields, document fields, and LLM output (which can carry job-description prompt injection) all reach this path, and `POST /api/profile/export-master` returns the PDF directly — so a live `<iframe>`/`<img>` would be SSRF into Railway's private network with the response printed into the PDF.

- **pandoc**: `-f markdown-raw_html-raw_attribute-native_divs-native_spans` (`_PANDOC_FROM`). `-raw_html` alone is not enough: `raw_attribute` (`` `<script>`{=html} `` / ```` ```{=html} ```` fences) is a second passthrough. Literal tags come out as escaped text. Output on all existing generated `.md` files was byte-identical before/after.
- **Jinja**: `Environment(autoescape=True)`. Only `css`, `content_html`, `content_pre`, `content_post` are wrapped in `Markup` (in `build_render_html`); every meta field (name, email, links, education, company…) is escaped. Template `| safe` is only used on those values and on the hardcoded SVG icon literals. Don't add new `| safe` on user data.
- **Chromium**: `browser.new_context(java_script_enabled=False)` + `context.route("**/*", _route_handler)`, which allows only `about:blank` and `data:` and aborts everything else (http/https/file). The templates need nothing external: CSS is inlined into `<style>`, icons are inline SVG, and no web fonts are loaded (font stacks fall back to locally installed fonts). If a template ever needs a font, inline it as a `data:` URI — don't widen the allowlist.
- **Sandbox**: Playwright's default `chromium_sandbox=False` launches Chromium with `--no-sandbox`. Left as-is: the Docker image runs as root (no `USER`), where Chromium refuses to start sandboxed. Enabling it needs a non-root user in the Dockerfile and verification that Railway permits the unprivileged user namespaces Chromium's sandbox uses (open item). **Mitigations while unsandboxed (2026-11-16):** (1) `_sanitize_fragment` strips every `<img>` (keeping alt text) from the pandoc fragment — `data:` URIs are not network requests, so the route interceptor never sees them, and image decoders are the main JS-free renderer exploit path (cf. libwebp CVE-2023-4863); (2) pandoc's attribute syntaxes (`bracketed_spans`, `link_attributes`, `fenced_divs`, `header_attributes`, code attributes) are disabled and any `style="…"` attribute is stripped, so user markdown can't inject CSS; (3) `p.chromium.launch(env=_chromium_env())` passes only an allowlist of non-secret env vars (PATH/HOME/TMP/locale/fontconfig + Windows system dirs), so a compromised renderer can't read Stripe/session/LLM/`KEY_ENCRYPTION_KEY`/`DATABASE_URL` from its own environment. Residual: as root it could still read the parent's `/proc/<pid>/environ` — the real fix is non-root + sandbox, or moving rendering to a secret-less service.
- **Concurrency**: `_RENDER_SEMAPHORE` (`threading.BoundedSemaphore`, size `PDF_RENDER_CONCURRENCY`, default 2, min 1) wraps each Chromium launch; extra renders block in the threadpool rather than exhaust memory.
- **Link schemes**: `_sanitize_fragment` keeps only `http(s):`/`mailto:`/`tel:`/`#` hrefs; any other scheme (`javascript:`, `data:`, `file:`…) loses its `href`, and a scheme-less `example.com` (common in profile link fields) becomes `https://example.com` instead of a dead relative link.

The CSS file is resolved by stripping `_template` from the template stem (e.g. `resume_template.html` → `resume.css`).

Both résumé and cover-letter rendering pass `max_pages=1` (`generate_resume_pdf` and `generate_cover_pdf` in `core/job.py`). If content overflows one page, `render_pdf` auto-shrinks the Playwright print scale in steps (down to a `_PDF_SCALE_FLOOR` of 0.8) until it fits, raising `RuntimeError` only if it still overflows at the floor. Note: Chromium ignores CSS `zoom` and visual `transform` in its print path — only `page.pdf(scale=)` actually reduces the page count. The CSS should still keep typical content near one page so the shrink factor stays mild (readable text). For covers, `cover.css` reserves `1.05in` of `.cover-body` bottom padding as clearance so the sign-off never spills into/behind the fixed `.bottom-bar`, and the `cover.md` prompt caps body length (~225–275 words, max 300) to keep content on one page.

### Education position: PDF vs. canonical Markdown

`render_pdf` (in `core/utils.py`) is **unchanged** in Phase 3a. It strips any Education section from the Markdown body and re-injects it from `meta['education']` (now sourced from the `Document` snapshot via `_render_meta`) positioned immediately after Profile — matching the existing template layout.

The assembled `.md` file follows canonical order (Profile → Experience → Education → Projects → Skills), so Education appears third in the file. The PDF overrides this and places Education second (after Profile). This divergence is intentional for Phase 3a; render internals are out of scope until Phase 3b.

### tree-v1 rendering

Tree-v1 résumés render contact info and education from the body markdown with empty `meta` (no YAML frontmatter, no education injection). The name arrives as a body `<h1>` and the contact line as the `<p>` immediately after it; CSS in `resume.css` (`.resume > h1` rules) styles them. The icon-grid contact block and meta-driven education injection are legacy-only; rich/icon contact formatting is a future #6 (user-formatted templates) feature.
