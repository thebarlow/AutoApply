# TODO

Backlog for multi-session work. Update this file whenever scope changes or an item is completed:
mark items `[x]`, move them to **Done**, or revise scope notes inline.

## Bugs

_(none)_

## Features

- [ ] **Job analysis: skill frequency** — Identify how common certain skills are across job
  requirements/preferences. Starting point for a broader analytics feature. Source data: scraped
  jobs in the SQLite DB.

- [ ] **Document user feedback** — Let the user give feedback on a generated document (resume/cover
  letter) that feeds back into regeneration.

- [ ] **Persistent user memory** — Store durable user directives, e.g. "Never say this",
  "This project is my best portfolio piece". Referenced by the LLM during generation.

- [ ] **User skill interview** — Combines job analysis + persistent memory. Interview the user on
  comfort level with specific techs; confidence tier governs how the LLM references them
  (omit low-confidence, slight upsell on mid-confidence, full claim on high-confidence).

- [ ] **Nicer process/skill formatting** — Format process descriptions with more tables, fewer
  bullet points, less prose. Condense phrasing:
  "Strong proficiency in Python" → "Python",
  "Hands-on experience with LLMs and generative AI" → "LLMs, generative AI".

## Done

- [x] **One-page resume overflow** — Pearson resume ran ~0.5in past one page; refine/edit paths
  silently emitted 2-page PDFs (page check disabled). Added auto-shrink in `render_pdf` (steps the
  Playwright `page.pdf(scale=)` down to a 0.8 floor until it fits), tightened `resume.css` spacing,
  and re-enabled `max_pages=1` on the edit/refine paths.
