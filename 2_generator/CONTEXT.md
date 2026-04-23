# Generator Context

Reads pending job JSON files from `../jobs/pending/`, generates a tailored one-page resume and cover letter for each via Claude, renders the resume to PDF via Pandoc + XeLaTeX, then moves the job JSON to `../jobs/processed/`.

## Entry Point

```
python resume_agent.py
```

Run from any directory — paths are resolved relative to the script's location.

## Key Paths

| Variable | Resolved Path |
|---|---|
| `MASTER_RESUME` | `C:\Users\barlo\Personal\Resume\master_resume.md` |
| `PENDING_DIR` | `../jobs/pending/` |
| `PROCESSED_DIR` | `../jobs/processed/` |
| `OUTPUTS_DIR` | `../jobs/outputs/` |
| `TEMPLATE` | `resume_template.tex` (same directory as script) |

## Pipeline (per job)

1. Read job JSON from `pending/`
2. Build resume prompt (master resume + job posting + formatting rules) → call `claude -p`
3. Strip any name/contact header Claude may have included
4. Prepend YAML frontmatter (name, email, phone, location)
5. Write `{job_key}_resume.md` to `outputs/`
6. Render PDF: `pandoc {md} -o {pdf} --pdf-engine=xelatex --template=resume_template.tex`
7. Build cover letter prompt → call `claude -p`
8. Write `{job_key}_cover.md` to `outputs/`
9. Move JSON: `pending/{key}.json` → `processed/{key}.json`

## Output Files

```
../jobs/outputs/
├── {job_key}_resume.md
├── {job_key}_resume.pdf
└── {job_key}_cover.md
```

## Resume Prompt Rules (summary)

- Profile: max 500 characters
- Education: both degrees, no bullets
- Experience: all 3 entries, max 2 bullets each (120 chars), stress job-relevant skills
- Projects: 2–4, reordered by relevance, 1 bullet each
- Skills: Python/Git/Docker/SQL always included, max 6 categories, sorted by relevance

## Cover Letter Rules (summary)

- Exactly 3 paragraphs: fit + interest / specific value-add / close
- Addressed to hiring team at the company
- Signed as Matthew Barlow with contact info
- No mention of n8n or no-code tools

## Dependencies

- `claude` CLI available in PATH
- `pandoc` + `xelatex` installed
